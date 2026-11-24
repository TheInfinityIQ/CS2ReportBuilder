"""Read-only preference leases and private copies; no existing ACL/attribute edits.

Leases prevent modification/deletion of existing monitored files. Directory
additions and effective runtime settings require separate verification.
"""
from __future__ import annotations
import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
import re
import shutil
import uuid

import native_viewer as native


class SettingsLease:
    def __init__(self, game=native.DEFAULT_GAME, *, roots=None):
        self.game = Path(game)
        self.dynamic_roots = roots is None
        self.roots = list(roots) if roots is not None else native.settings_roots(game)
        self.handles = []; self.before = native.settings_snapshot(self.roots)
        self.api = c.WinDLL('kernel32', use_last_error=True)
        self.api.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
        self.api.CreateFileW.restype = w.HANDLE
        self.api.CloseHandle.argtypes = [w.HANDLE]
        try:
            for filename, digest in self.before.items():
                if digest is None: continue
                # Permit readers; deny writers, renames and deletion while held.
                handle = self.api.CreateFileW(filename, 0x80000000, 1, None, 3, 0x08000000, None)
                if handle == c.c_void_p(-1).value:
                    raise OSError('A configuration file is busy; private playback was not started.')
                self.handles.append(handle)
            if native.setting_changes(self.before, native.settings_snapshot(self.roots)):
                raise ValueError('Saved preferences changed while preparing their read-only leases.')
        except Exception:
            self.close(); raise

    def changes(self):
        roots = self.roots + native.settings_roots(self.game) if self.dynamic_roots else self.roots
        return native.setting_changes(self.before, native.settings_snapshot(roots))

    def close(self):
        for handle in self.handles: self.api.CloseHandle(handle)
        self.handles.clear()

    def __enter__(self): return self
    def __exit__(self, *_): self.close()


def video_preferences(cfg):
    path = Path(cfg)/'cs2_video.txt'
    data = dict(re.findall(r'"([^"\r\n]+)"\s*"([^"\r\n]*)"', path.read_text(encoding='utf-8-sig')))
    keys = ('setting.defaultres', 'setting.defaultresheight', 'setting.fullscreen', 'setting.nowindowborder')
    if any(k not in data or not data[k].isdecimal() for k in keys):
        raise ValueError('The current display preferences cannot be verified.')
    result = {k: int(data[k]) for k in keys}
    if result['setting.fullscreen'] != 0:
        raise ValueError('Exclusive fullscreen needs additional isolation testing. Your display mode was not changed.')
    if not (320 <= result[keys[0]] <= 16384 and 200 <= result[keys[1]] <= 16384):
        raise ValueError('The saved resolution is outside the supported range.')
    return result


def active_cfg(game=native.DEFAULT_GAME):
    import winreg
    roots = [p for p in native.settings_roots(game) if p.name == 'cfg' and p.parent.name == 'local'
             and (p/'cs2_video.txt').is_file()]
    active = None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam\ActiveProcess') as key:
            active = str(winreg.QueryValueEx(key, 'ActiveUser')[0])
    except OSError: pass
    match = next((p for p in roots if p.parents[2].name == active), None)
    if match: return match
    if len(roots) == 1: return roots[0]
    raise ValueError('The active Steam video profile could not be identified. No game was started.')


def private_profile(cfg, *, base=None):
    """Copy a bounded set of preferences outside Steam, without editing them."""
    cfg = Path(cfg).resolve(); display = video_preferences(cfg)
    base = Path(base or native.STATE/'native-sessions').resolve()
    session = base/uuid.uuid4().hex
    destination = session/'profile/cfg'; destination.mkdir(parents=True)
    total = 0
    for filename, digest in native.settings_snapshot([cfg]).items():
        if digest is None: continue
        path = Path(filename); total += path.stat().st_size
        if total > 8 * 1024 * 1024: raise ValueError('This profile exceeds the bounded copy limit.')
        target = destination/path.relative_to(cfg); target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        if native.checksum(target) != digest: raise ValueError('The private preference copy could not be verified.')
    (session/'temp').mkdir(); (session/'logs').mkdir()
    env = dict(os.environ)
    for key in ('USRLOCAL', 'USRLOCALCSGO', 'USRLOCALCS2', 'USRLOCAL_CSGO', 'USRLOCAL_CS2'):
        env[key] = str(session/'profile')
    env.update({'SteamAppId': '730', 'SteamGameId': '730', 'TEMP': str(session/'temp'), 'TMP': str(session/'temp')})
    return {'session': session, 'usr_local': session/'profile', 'env': env, 'display': display, 'copied_bytes': total}
