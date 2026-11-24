"""Application-owned CS2 playback process. All integration stays outside CS2."""
from __future__ import annotations
import ctypes as c
from ctypes import wintypes as w
from pathlib import Path
import subprocess
import time
import re

import cs2_jump
from jobs import STATE, WindowsProcessGroup, save_json
from extractor.job_lock import exclusive
import native_viewer as native
import replay_inventory as replays
from native_security import SettingsLease, active_cfg, private_profile


class ManagedSession:
    def __init__(self, game=None, *, allow_unverified=False, experimental_control_guard=None):
        self.game = Path(game or native.configured_game()).resolve()
        self.process = None; self.job = None; self.lease = None; self.output = None
        self.profile = None; self.window = None; self.before_runtime = None
        self.started = 0.; self.stopped = False
        self.allow_unverified = allow_unverified
        self.session_lock = None
        self._demo_active = False
        self.started_wall = 0.
        self.control_guard = experimental_control_guard
        self.control = None
        self.demo_sha = None
        self.demo_compat = None

    def start(self, demo, *, cancel=None):
        if self.process or self.stopped: raise ValueError('This playback session cannot be reused.')
        if cancel and cancel.is_set(): raise ValueError('Private playback startup was cancelled.')
        demo = Path(demo).resolve()
        if not demo.is_relative_to(replays.replay_root()):
            raise ValueError('Only downloaded demos in replays are available for watching.')
        if not demo.is_file() or demo.suffix.casefold() != '.dem': raise ValueError('Choose an existing .dem recording.')
        cs2_jump.console_path(demo)
        lock = exclusive(STATE/'native-engine-session.lock')
        lock.__enter__(); self.session_lock = lock
        try:
            if cs2_jump.is_running(): raise ValueError('CS2 is already running. Its session was left untouched.')
            self.before_runtime = native.runtime_profile(self.game)
            cfg = active_cfg(self.game)
            self.lease = SettingsLease(self.game)
            if not self.allow_unverified:
                from native_compatibility import require_verified
                require_verified(self.before_runtime, cfg/'cs2_video.txt')
            self.profile = private_profile(cfg)
            save_json(self.profile['session']/'baseline-settings.json', self.lease.before)
            self.output = (self.profile['session']/'logs/stdout.log').open('wb')
            self.demo_sha = native.checksum(demo)
            from native_demo_compat import prepare
            self.demo_compat=prepare(demo,self.demo_sha,self.before_runtime['fingerprint'],allow_unverified=self.allow_unverified)
            playback=self.demo_compat['path']
            cs2_jump.console_path(playback)
            info = subprocess.STARTUPINFO(); info.dwFlags = subprocess.STARTF_USESHOWWINDOW; info.wShowWindow = 4
            args = [str(self.game/'bin/win64/cs2.exe'), '-insecure', '-con_logfile',
                    str(self.profile['session']/'logs/engine.log'), '+playdemo', playback.as_posix()]
            if self.control_guard:
                if not self.control_guard.healthy():raise ValueError('A local control restriction is required before enabling VConsole.')
                if not self.allow_unverified:
                    from native_controls import require_verified as require_controls
                    require_controls(self.before_runtime)
                args[1:1]=['-vconsole','-vconport',str(self.control_guard.port)]
            if cancel and cancel.is_set(): raise ValueError('Private playback startup was cancelled.')
            self.started_wall = time.time()
            try:
                self.process = subprocess.Popen(args, cwd=self.profile['session'], env=self.profile['env'],
                    stdout=self.output, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                    startupinfo=info, creationflags=subprocess.CREATE_NO_WINDOW)
                if self.control_guard:self.control_guard.process=self.process
            except OSError as exc:
                if exc.winerror == 5:
                    raise ValueError('Windows denied private playback startup. If FACEIT anti-cheat is running, close it for offline demo playback and retry. No security settings were changed.') from exc
                raise
            self.job = WindowsProcessGroup(self.process)
            if not self.job.handle: raise ValueError('The private engine could not be assigned to its ownership group.')
            self.started = time.monotonic()
            save_json(self.profile['session']/'session.json', {'version': 1, 'pid': self.process.pid,
                'runtime_fingerprint': self.before_runtime['fingerprint'], 'demo_sha256': self.demo_sha,
                'playback_copy':{k:str(v) if isinstance(v,Path) else v for k,v in self.demo_compat.items()},
                'display': self.profile['display'], 'copied_bytes': self.profile['copied_bytes'],
                'original_settings_files': sum(v is not None for v in self.lease.before.values())})
        except Exception:
            self.stop(); raise
        return self

    def find_window(self):
        if not self.process or self.process.poll() is not None: return None
        candidates = [v for v in native.game_windows() if v['pid'] == self.process.pid
                      and Path(v['executable']).resolve() == self.game/'bin/win64/cs2.exe']
        if len(candidates) != 1: return None
        source = candidates[0]
        self._mask_owned(source['hwnd'])
        self.window = source
        return source

    def _mask_owned(self, hwnd):
        # Only our live process handle/PID may be altered. This does not apply
        # to the generic read-only attachment of the user's normal game.
        if self.process.poll() is not None: raise ValueError('The private engine exited.')
        api = c.WinDLL('user32', use_last_error=True)
        api.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
        pid = w.DWORD(); api.GetWindowThreadProcessId(hwnd, c.byref(pid))
        if pid.value != self.process.pid: raise ValueError('The game window is not owned by this session.')
        api.GetWindowLongPtrW.argtypes = [w.HWND, c.c_int]; api.GetWindowLongPtrW.restype = c.c_ssize_t
        api.SetWindowLongPtrW.argtypes = [w.HWND, c.c_int, c.c_ssize_t]; api.SetWindowLongPtrW.restype = c.c_ssize_t
        api.SetLayeredWindowAttributes.argtypes = [w.HWND, w.DWORD, w.BYTE, w.DWORD]
        api.EnableWindow.argtypes = [w.HWND, w.BOOL]
        api.IsWindowEnabled.argtypes = [w.HWND]; api.IsWindowEnabled.restype = w.BOOL
        style = api.GetWindowLongPtrW(hwnd, -20)
        c.set_last_error(0)
        result = api.SetWindowLongPtrW(hwnd, -20, style | 0x80000 | 0x20 | 0x08000000 | 0x80)
        if not result and c.get_last_error(): raise c.WinError(c.get_last_error())
        if not api.SetLayeredWindowAttributes(hwnd, 0, 1, 2): raise c.WinError(c.get_last_error())
        # A concealed playback window must never become a keyboard/mouse target.
        # This changes only our owned HWND's input eligibility, not game bindings.
        api.EnableWindow(hwnd, False)
        if api.IsWindowEnabled(hwnd): raise ValueError('The private window could not be made non-interactive.')

    def logs(self):
        if not self.profile: return ''
        result = []
        for name in ('stdout.log', 'engine.log'):
            path = self.profile['session']/'logs'/name
            if path.is_file():
                with path.open('rb') as stream: result.append(stream.read(2 * 1024 * 1024).decode('utf-8', errors='replace'))
        return '\n'.join(result)

    def redirected(self):
        return configuration_redirected(self.logs(), self.profile['usr_local'])

    def demo_active(self):
        if not self._demo_active: self._demo_active = 'Host activate: Playing Demo' in self.logs()
        return self._demo_active

    def input_disabled(self):
        if not self.window or not self.process or self.process.poll() is not None: return False
        api = c.WinDLL('user32', use_last_error=True)
        api.IsWindowEnabled.argtypes = [w.HWND]; api.IsWindowEnabled.restype = w.BOOL
        api.IsWindow.argtypes = [w.HWND]; api.IsWindow.restype = w.BOOL
        return bool(api.IsWindow(self.window['hwnd']) and not api.IsWindowEnabled(self.window['hwnd']))

    def changes(self):
        return self.lease.changes() if self.lease else []

    def failure_message(self, kind, stats=None):
        """Record failure evidence before stop() changes the process exit code."""
        code = self.process.poll() if self.process else None
        hexcode = f'0x{code & 0xffffffff:08X}' if code is not None else None
        if kind == 'engine_exit':
            if code and self.demo_compat and self.demo_compat.get('applied'):
                from native_demo_compat import record_crash
                record_crash(self.before_runtime['fingerprint'],self.demo_compat)
            if hexcode == '0xC0000005':
                message = 'CS2 crashed while playing this demo (access violation).'
            elif code == 0: message = 'The private CS2 process closed.'
            else: message = f'The private CS2 process exited unexpectedly ({hexcode or "unknown exit code"}).'
            versions = re.search(r'Demo is version (\d+), client is version (\d+)', self.logs())
            if versions and versions[1] != versions[2]:
                message += f' Demo version {versions[1]}; installed game version {versions[2]}. Compatibility may be the cause.'
        else:
            message = 'The private CS2 process was still running, but its picture could not be reconnected.'
            if stats and stats.error: message += f' Capture error 0x{stats.error & 0xffffffff:08X}.'
        message += ' No automatic restart was attempted.'
        if self.profile:
            folder = self.profile['session']
            evidence = {'kind':kind, 'exit_code':code, 'exit_hex':hexcode,
                        'pid':self.process.pid if self.process else None,
                        'runtime_fingerprint':(self.before_runtime or {}).get('fingerprint'),
                        'window':self.window, 'message':message, 'recorded_at':time.time()}
            if self.demo_compat:evidence['playback_copy']={k:str(v) if isinstance(v,Path) else v for k,v in self.demo_compat.items()}
            if stats:
                evidence['capture'] = {k:getattr(stats,k) for k in
                                      ('state','error','frames','width','height','seconds_since_frame')}
            try:
                evidence['crash_dump_candidates'] = [str(p) for p in (self.game/'bin/win64').glob('cs2_*.mdmp')
                    if self.started_wall and p.stat().st_mtime >= self.started_wall-2]
                save_json(folder/'playback-failure.json',evidence)
                message += f' Details: {folder / "playback-failure.json"}'
            except OSError: message += ' The session logs were retained.'
        return message

    def stop(self):
        if self.stopped: return
        self.stopped = True; changes = []
        try:
            if self.control:
                try:self.control.close()
                except OSError:pass
                self.control=None
            if self.process and self.process.poll() is None:
                if self.job and self.job.handle: self.job.terminate()
                else: self.process.terminate()
                self.process.wait(timeout=10)
        except Exception:
            # Retain the preference leases if the owned process could not stop.
            self.stopped = False
            raise
        try:
            if self.control_guard:self.control_guard.close()
            if self.lease: changes = self.lease.changes()
        finally:
            if self.output: self.output.close()
            if self.job: self.job.close()
            if self.lease: self.lease.close()
            if self.session_lock:
                self.session_lock.__exit__(None,None,None); self.session_lock = None
        if changes: raise ValueError('Original configuration paths changed; the session was stopped and no rollback was written.')


def configuration_redirected(logs, expected):
    paths = re.findall(r'\[Filesystem\]\s+USRLOCAL\s+"([^"\r\n]+)"', logs)
    normal = lambda value: str(value).replace('\\', '/').rstrip('/').casefold()
    return bool(paths) and all(normal(p) == normal(expected) for p in paths)
