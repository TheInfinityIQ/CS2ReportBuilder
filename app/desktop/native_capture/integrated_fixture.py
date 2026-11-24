"""Bounded test of the shipping panel with a managed real-engine demo.

Uses only the application's own widget methods and capture surfaces. No desktop
automation, synthetic input, Computer Use, or pre-existing CS2 session.
"""
import argparse
import json
from pathlib import Path
import sys
import time
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jobs import STATE, save_json
from native_view_panel import NativeViewPanel
from native_viewer import SettingsGuard, configured_game


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--demo', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=45)
    parser.add_argument('--require-verified', action='store_true')
    args = parser.parse_args()
    if not 15 <= args.seconds <= 90: parser.error('Use a bounded 15–90 second check.')
    root = tk.Tk(); root.title('Toolbox · Integrated private playback check'); root.geometry('1280x860+20+20')
    panel = NativeViewPanel(root, allow_unverified=not args.require_verified); panel.pack(fill='both', expand=True)
    before = SettingsGuard(configured_game()); started = time.monotonic()
    screen_before = [root.winfo_screenwidth(), root.winfo_screenheight()]
    state = {'finished': False, 'samples': [], 'session': None}

    def finish(ok, message):
        if state['finished']: return
        state['finished'] = True
        capture, session = panel.capture, panel.managed
        result = {'ok': ok, 'message': message, 'frames': capture.stats().frames if capture else 0,
                  'private_config_confirmed': session.redirected() if session else False,
                  'demo_active_confirmed': bool(session and 'Host activate: Playing Demo' in session.logs()),
                  'session': str(session.profile['session']) if session else state['session'],
                  'samples': state['samples'][-3:]}
        result['source_input_disabled'] = bool(session and session.input_disabled())
        if not result['source_input_disabled']: result['ok'] = False
        result['screen_before'] = screen_before
        result['screen_during'] = [root.winfo_screenwidth(), root.winfo_screenheight()]
        if capture: result['captured_size'] = [capture.stats().width, capture.stats().height]
        try: panel.close()
        except Exception as exc: result['ok'] = False; result['message'] += ' · ' + str(exc)
        result['original_settings_unchanged'] = not before.check()
        if not result['original_settings_unchanged']: result['ok'] = False
        result['owned_process_stopped'] = not session or session.process.poll() is not None
        result['original_settings_files'] = sum(v is not None for v in before.before.values())
        result['screen_after'] = [root.winfo_screenwidth(), root.winfo_screenheight()]
        result['screen_size_unchanged'] = result['screen_before'] == result['screen_during'] == result['screen_after']
        if not result['screen_size_unchanged']: result['ok'] = False
        if result['ok']:
            from native_compatibility import record_smoke
            try: result['validation_key'] = record_smoke(result)
            except Exception as exc: result['ok'] = False; result['message'] += ' · ' + str(exc)
        save_json(STATE/'native-last-integrated-smoke.json', result)
        print(json.dumps(result), flush=True)
        root.destroy()
        if not result['ok']: raise SystemExit(1)

    def poll():
        if state['finished']: return
        try:
            elapsed = time.monotonic() - started
            if panel.managed: state['session'] = str(panel.managed.profile['session'])
            if panel.capture and panel.managed:
                stats = panel.capture.stats()
                if stats.frames and int(elapsed) % 3 == 0 and len(state['samples']) < int(elapsed/3)+1:
                    state['samples'].append(list(panel.capture.sample(stats.width//2, stats.height//2)))
                active = 'Host activate: Playing Demo' in panel.managed.logs()
                visible_pixels = any(max(p[:3]) > .005 and p[3] > .9 for p in state['samples'])
                if elapsed >= 16 and stats.frames >= 60 and panel.managed.redirected() and active and visible_pixels:
                    finish(True, 'Shipping panel rendered the selected demo through its owned private engine.'); return
            if elapsed > 3 and not panel.pending_launch and not panel.managed and not panel.capture:
                finish(False, panel.status.get()); return
            if elapsed >= args.seconds: finish(False, 'The integrated acceptance check timed out.'); return
            root.after(200, poll)
        except Exception as exc: finish(False, str(exc))

    root.protocol('WM_DELETE_WINDOW', lambda: finish(False, 'The test window was closed.'))
    root.after(100, lambda: panel.start_private(args.demo)); root.after(300, poll); root.mainloop()


if __name__ == '__main__': main()
