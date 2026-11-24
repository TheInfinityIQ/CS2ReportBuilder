"""One bounded real-engine rendering check, driven by app code, never desktop input.

Requires an explicit demo path. It owns/stops only the CS2 process it launches,
keeps original preferences leased read-only, and uses a private config copy.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import time
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jobs import STATE, save_json
from native_session import ManagedSession
from native_viewer import Capture, SettingsGuard


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=45)
    args = parser.parse_args()
    if not 15 <= args.seconds <= 90: parser.error('Use a bounded 15–90 second check.')
    root = tk.Tk(); root.title('Toolbox · Private CS2 rendering check'); root.geometry('1280x860+20+20')
    root.configure(bg='#0c141d')
    label = tk.StringVar(value='Preparing a private playback process. Existing configuration files are protected against writes.')
    tk.Label(root, text='CS2 TOOLBOX · OWNED ENGINE', bg='#0c141d', fg='#75c7fb', font=('Segoe UI', 16)).pack(pady=10)
    tk.Label(root, textvariable=label, bg='#0c141d', fg='white', wraplength=1200).pack(padx=20)
    viewport = tk.Frame(root, bg='black'); viewport.pack(fill='both', expand=True, padx=16, pady=16)
    session = ManagedSession(allow_unverified=True); guard = SettingsGuard(session.game)
    state = {'capture': None, 'finished': False, 'samples': [], 'frames': 0, 'size': None, 'opened': False}
    begin = time.monotonic()

    def finish(ok, message):
        if state['finished']: return
        state['finished'] = True
        if state['capture']: state['capture'].close(); state['capture'] = None
        try: session.stop()
        except Exception as exc: ok = False; message += ' · ' + str(exc)
        changed = guard.check()
        if changed: ok = False; message += ' · Original settings changed.'
        logs = session.logs()
        result = {'ok': ok, 'message': message, 'frames': state['frames'], 'captured_size': state['size'],
                  'private_config_confirmed': bool(session.profile and session.redirected()),
                  'original_settings_unchanged': not changed, 'original_settings_files': sum(v is not None for v in guard.before.values()),
                  'demo_open_logged': state['opened'], 'samples': state['samples'][-3:],
                  'exit_code': session.process.poll() if session.process else None,
                  'session': str(session.profile['session']) if session.profile else None,
                  'log_bytes': len(logs)}
        save_json(STATE/'native-last-smoke.json', result)
        print(json.dumps(result), flush=True)
        root.destroy()
        if not ok: raise SystemExit(1)

    def start():
        try: session.start(args.demo); poll()
        except Exception as exc: finish(False, str(exc))

    def poll():
        if state['finished']: return
        try:
            if session.process.poll() is not None:
                raise ValueError('The owned engine exited before the rendering check completed.')
            if not state['capture']:
                window = session.find_window()
                if window:
                    viewport.update_idletasks()
                    state['capture'] = Capture(window['hwnd'], viewport.winfo_id())
                    root.lift()
            elapsed = time.monotonic() - begin
            if session.changes(): raise ValueError('A configuration path changed; stopping without writing a rollback.')
            logs = session.logs()
            state['opened'] = bool(re.search(r'(?i)(CDemoFile::|playing\s+(?:back\s+)?demo|demo\s+playback|demoplayer)', logs))
            if state['capture']:
                stats = state['capture'].stats(); state['frames'] = stats.frames
                state['size'] = [stats.width, stats.height]
                if stats.state == 4: raise ValueError(f'Capture error 0x{stats.error & 0xffffffff:08X}')
                if stats.frames and int(elapsed) % 3 == 0 and len(state['samples']) < int(elapsed/3)+1:
                    sample = state['capture'].sample(stats.width//2, stats.height//2)
                    state['samples'].append(list(sample))
                label.set(f'Owned engine · {stats.frames} frames · {stats.width} × {stats.height} · '
                          f'Private configuration: {session.redirected()} · Demo opened: {state["opened"]}')
                nonblack = any(max(p[:3]) > .005 and p[3] > .9 for p in state['samples'])
                if elapsed >= 15 and stats.frames >= 60 and session.redirected() and state['opened'] and nonblack:
                    finish(True, 'The private engine supplied non-black demo frames inside Toolbox.'); return
            if elapsed >= args.seconds:
                finish(False, 'The bounded rendering check did not satisfy every acceptance condition.'); return
            root.after(150, poll)
        except Exception as exc: finish(False, str(exc))

    def resize(_):
        if state['capture']: state['capture'].resize()

    viewport.bind('<Configure>', resize)
    root.protocol('WM_DELETE_WINDOW', lambda: finish(False, 'The rendering check was closed.'))
    root.after(200, start); root.mainloop()


if __name__ == '__main__': main()
