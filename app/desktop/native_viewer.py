"""Read-only native game view. Never starts, resizes, configures or controls CS2."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import re
import struct

from jobs import STATE, read_json, save_json
from extractor.job_lock import exclusive

BUILD = Path(__file__).with_name('native_capture')/'build'
DEFAULT_GAME = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game')
PROFILES = STATE/'native-runtime-profiles.json'
MAX_SETTING_SIZE = 8 * 1024 * 1024


def checksum(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def parse_vdf(text):
    """Small strict parser for Steam's quoted text manifests (not arbitrary VDF)."""
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[{}]|[^\s{}"]+', re.sub(r'(?m)^\s*//[^\n]*', '', text))
    index = 0

    def value(token):
        if not token.startswith('"'): raise ValueError('Unsupported Steam manifest syntax.')
        return token[1:-1].replace('\\"', '"').replace('\\\\', '\\')

    def group(nested=False):
        nonlocal index
        result = {}
        while index < len(tokens):
            token = tokens[index]; index += 1
            if token == '}':
                if not nested: raise ValueError('Unexpected manifest closing brace.')
                return result
            key = value(token)
            if key in result or index >= len(tokens): raise ValueError('Invalid Steam manifest entry.')
            token = tokens[index]; index += 1
            result[key] = group(True) if token == '{' else value(token)
        if nested: raise ValueError('Incomplete Steam manifest.')
        return result

    return group()


def runtime_profile(game=DEFAULT_GAME, *, previous=None):
    """Inspect only. Fingerprint selected binaries; reuse hashes if file identity is stable."""
    game = Path(game).resolve()
    manifest = game.parents[2]/'appmanifest_730.acf'
    app = parse_vdf(manifest.read_text(encoding='utf-8-sig')).get('AppState', {})
    if app.get('appid') != '730': raise ValueError('This installation is not Steam application 730.')
    counters = [app.get(k, '0') for k in ('BytesToDownload', 'BytesDownloaded', 'BytesToStage', 'BytesStaged')]
    if not all(str(v).isdecimal() for v in counters): raise ValueError('Steam update counters are invalid.')
    to_download, downloaded, to_stage, staged = map(int, counters)
    # Steam retains completed download/staging counters after a successful update.
    if (app.get('StateFlags') != '4' or downloaded < to_download or staged < to_stage
            or app.get('TargetBuildID', '0') not in ('0', '', app.get('buildid'))):
        raise ValueError('Steam installation is not ready. Wait for the update to finish.')
    version = dict(line.split('=', 1) for line in (game/'csgo/steam.inf').read_text().splitlines() if '=' in line)
    binaries = {}
    for relative in ('bin/win64/cs2.exe', 'bin/win64/engine2.dll'):
        path = game/relative; before = path.stat()
        stamp = [str(path), before.st_size, before.st_mtime_ns, before.st_ctime_ns]
        old = (previous or {}).get('binaries', {}).get(relative, {})
        digest = old.get('sha256') if old.get('stamp') == stamp else None
        digest = digest or checksum(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('The game changed during inspection. Wait for Steam to finish.')
        binaries[relative] = {'stamp': stamp, 'sha256': digest}
    depots = {k: v['manifest'] for k, v in app.get('InstalledDepots', {}).items() if 'manifest' in v}
    identity = {'game': str(game), 'build': app.get('buildid'), 'version': version,
                'depots': depots, 'binaries': {k: v['sha256'] for k, v in binaries.items()}}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    # Catch manifest/version changes while binaries were being read.
    if parse_vdf(manifest.read_text(encoding='utf-8-sig')).get('AppState', {}) != app:
        raise ValueError('Steam changed the installation during inspection. Try again after the update.')
    if dict(line.split('=', 1) for line in (game/'csgo/steam.inf').read_text().splitlines() if '=' in line) != version:
        raise ValueError('Game version changed during inspection.')
    return {**identity, 'fingerprint': fingerprint, 'binaries': binaries,
            'automatic_launch': 'unverified', 'controls': 'unverified', 'game_capture': 'unverified'}


def observe_runtime(game=DEFAULT_GAME, store=PROFILES):
    store = Path(store)
    with exclusive(store.with_suffix('.lock')):
        try:
            data = json.loads(store.read_text(encoding='utf-8')) if store.exists() else {'version': 1, 'profiles': {}, 'installations': {}}
            if data.get('version') != 1 or not isinstance(data.get('profiles'), dict) or not isinstance(data.get('installations'), dict):
                raise ValueError('Unsupported runtime history format.')
        except (ValueError, AttributeError) as exc:
            raise ValueError('Saved runtime history could not be read; the existing file was preserved.') from exc
        key = str(Path(game).resolve())
        previous_id = data['installations'].get(key)
        previous = data['profiles'].get(previous_id)
        current = runtime_profile(game, previous=previous)
        changed = bool(previous_id and previous_id != current['fingerprint'])
        data['profiles'][current['fingerprint']] = current
        data['installations'][key] = current['fingerprint']
        save_json(store, data)
    return current, changed


def settings_roots(game=DEFAULT_GAME):
    """Known configuration locations only; no asset/demo scans or configuration writes."""
    game = Path(game).resolve()
    steam = game.parents[3]
    result = [game/'csgo/cfg']
    userdata = steam/'userdata'
    if userdata.is_dir():
        for account in sorted(userdata.iterdir()):
            if not account.name.isdecimal() or not account.is_dir(): continue
            result.extend([account/'730/local/cfg', account/'730/remote/cfg'])
            # Older builds also place preference files directly under remote.
            result.extend([account/'730/remote/cs2_user_convars.vcfg', account/'730/remote/cs2_user_keys.vcfg'])
    return result


def settings_snapshot(roots):
    """Hash only; never stores preference contents. Fail on inaccessible/unstable files."""
    result = {}; total = 0
    for root in map(Path, roots):
        if root.is_symlink() or root.is_junction(): raise ValueError('A configuration root is a link; its coverage needs review.')
        if not root.exists():
            result[str(root)] = None
            continue
        files = [root] if root.is_file() else sorted(root.rglob('*'))
        for path in files:
            if path.is_symlink() or path.is_junction(): raise ValueError('A configuration path is a link; its coverage needs review.')
            if not path.is_file(): continue
            if not (path.suffix.casefold() in {'.cfg', '.vcfg', '.txt'} or path.name.endswith('_lastclouded')): continue
            before = path.stat(); total += before.st_size
            if before.st_size > MAX_SETTING_SIZE or total > 64 * 1024 * 1024:
                raise ValueError('Configuration coverage exceeds the bounded settings check.')
            value = checksum(path); after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError('A settings file changed during inspection. Stop changing settings and retry.')
            result[str(path)] = value
    return result


def setting_changes(before, after):
    return sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))


class SettingsGuard:
    def __init__(self, game=DEFAULT_GAME, roots=None):
        self.game = game
        self.explicit_roots = list(roots) if roots is not None else None
        self.before = self.snapshot()

    def snapshot(self):
        return settings_snapshot(self.explicit_roots if self.explicit_roots is not None else settings_roots(self.game))

    def check(self):
        return setting_changes(self.before, self.snapshot())


class NativeStats(ctypes.Structure):
    _fields_ = [('frames', ctypes.c_uint64), ('width', ctypes.c_int32), ('height', ctypes.c_int32),
                ('state', ctypes.c_int32), ('error', ctypes.c_int32), ('seconds_since_frame', ctypes.c_double)]


def capture_library():
    try:
        manifest = json.loads((BUILD/'current.json').read_text(encoding='utf-8-sig'))
        path = (BUILD/manifest['dll']).resolve()
        if manifest.get('abi') != 2 or not path.is_relative_to(BUILD.resolve()) or not path.is_file():
            raise ValueError('Invalid native build manifest.')
        return path
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError('The native view needs a successful build. Run native_capture/build.cmd.') from exc


class Capture:
    def __init__(self, source, destination):
        if os.name != 'nt': raise ValueError('Native game capture requires Windows.')
        self.dll = ctypes.CDLL(str(capture_library())); self.handle = None
        self.dll.nv_create.argtypes = [w.HWND, w.HWND, w.LPWSTR, ctypes.c_int]
        self.dll.nv_create.restype = ctypes.c_void_p
        self.dll.nv_resize.argtypes = [ctypes.c_void_p]; self.dll.nv_resize.restype = ctypes.c_int
        self.dll.nv_stats.argtypes = [ctypes.c_void_p, ctypes.POINTER(NativeStats)]; self.dll.nv_stats.restype = ctypes.c_int
        self.dll.nv_stop.argtypes = [ctypes.c_void_p]; self.dll.nv_stop.restype = None
        self.dll.nv_sample.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_uint16)]
        self.dll.nv_sample.restype = ctypes.c_int
        error = ctypes.create_unicode_buffer(1024)
        self.handle = self.dll.nv_create(source, destination, error, len(error))
        if not self.handle: raise ValueError(error.value or 'Windows could not capture this window at its existing settings.')

    def resize(self):
        if self.handle and not self.dll.nv_resize(self.handle): raise ValueError('The view could not be resized.')

    def stats(self):
        value = NativeStats()
        if not self.handle or not self.dll.nv_stats(self.handle, ctypes.byref(value)): raise ValueError('The native view is closed.')
        return value

    def close(self):
        if self.handle:
            self.dll.nv_stop(self.handle); self.handle = None

    def sample(self, x, y):
        value = (ctypes.c_uint16 * 4)()
        if not self.handle or not self.dll.nv_sample(self.handle, x, y, value):
            raise ValueError('A diagnostic pixel could not be read.')
        return struct.unpack('<4e', bytes(value))

    def record_start(self, path):
        self.dll.nv_record_start.argtypes=[ctypes.c_void_p,w.LPCWSTR]
        self.dll.nv_record_start.restype=ctypes.c_int
        result=self.dll.nv_record_start(self.handle,str(Path(path).resolve()))
        if result!=1:raise ValueError(f'Windows video encoder could not start: {result:#x}')

    def record_frames(self):
        self.dll.nv_record_frames.argtypes=[ctypes.c_void_p]
        self.dll.nv_record_frames.restype=ctypes.c_int64
        result=self.dll.nv_record_frames(self.handle)
        if result<0:raise ValueError(f'Windows video encoder stopped: {result:#x}')
        return result

    def record_end(self):
        self.dll.nv_record_end.argtypes=[ctypes.c_void_p]
        self.dll.nv_record_end.restype=ctypes.c_int
        result=self.dll.nv_record_end(self.handle)
        if result!=1:raise ValueError(f'Windows video encoder could not finalize: {result:#x}')

    def record_snapshot(self,path):
        from PIL import Image
        stats=self.stats();pixels=(ctypes.c_uint8*(stats.width*stats.height*4))()
        self.dll.nv_record_pixels.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32]
        self.dll.nv_record_pixels.restype=ctypes.c_int
        if not self.dll.nv_record_pixels(self.handle,pixels,len(pixels)):
            raise ValueError('No recorded frame is available for reference verification.')
        Image.frombytes('RGB',(stats.width,stats.height),bytes(pixels),'raw','BGRX',0,-1).save(path)


def game_windows():
    """Read visible, non-minimized CS2 HWNDs and their executable identity."""
    if os.name != 'nt': return []
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user.IsWindowVisible.argtypes = [w.HWND]; user.IsWindowVisible.restype = w.BOOL
    user.IsIconic.argtypes = [w.HWND]; user.IsIconic.restype = w.BOOL
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.GetWindowTextLengthW.argtypes = [w.HWND]; user.GetWindowTextLengthW.restype = ctypes.c_int
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; kernel.OpenProcess.restype = w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    found = []

    def visit(hwnd, _):
        if not user.IsWindowVisible(hwnd) or user.IsIconic(hwnd) or not user.GetWindowTextLengthW(hwnd): return True
        pid = w.DWORD(); user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel.OpenProcess(0x1000, False, pid.value)
        if handle:
            try:
                path = ctypes.create_unicode_buffer(32768); length = w.DWORD(len(path))
                if kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(length)) and Path(path.value).name.casefold() == 'cs2.exe':
                    found.append({'hwnd': hwnd, 'pid': pid.value, 'executable': path.value})
            finally: kernel.CloseHandle(handle)
        return True

    user.EnumWindows.argtypes = [callback_type, w.LPARAM]
    user.EnumWindows(callback_type(visit), 0)
    return found


def configured_game():
    return Path(read_json(STATE/'settings.json', {}).get('cs2_game_directory') or DEFAULT_GAME)


def require_verified_launch(game=DEFAULT_GAME):
    # No production profile has passed isolated settings-preservation testing yet.
    # A cached profile or a successful capture must never accidentally enable launch.
    raise ValueError('Automatic CS2 launch is unavailable until settings preservation is verified. '
                     'Open CS2 normally, then use Show running CS2 in the 3D view. Your resolution and preferences will not be changed by the viewer.')
