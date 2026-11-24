"""Bounded capture smoke test using only windows owned by this test process.

This never finds, starts or interacts with CS2. --self-test exits after checks;
without it the two fixture windows stay open for visual inspection.
"""
import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import time
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_viewer import Capture


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--offscreen-source', action='store_true')
    parser.add_argument('--masked-source', action='store_true')
    args = parser.parse_args()
    root = tk.Tk(); root.title('Toolbox native viewport · Capture fixture'); root.geometry('900x650+0+0')
    root.configure(bg='#0c141d')
    text = tk.StringVar(value='Starting external GPU capture…')
    tk.Label(root, text='NATIVE VIEWPORT · TEST SOURCE', bg='#0c141d', fg='#75c7fb', font=('Segoe UI', 16)).pack(pady=12)
    tk.Label(root, text='The animated picture below is captured from a different window. Its resolution stays unchanged.',
             bg='#0c141d', fg='white', wraplength=820).pack()
    view = tk.Frame(root, bg='black'); view.pack(fill='both', expand=True, padx=20, pady=12)
    tk.Label(root, textvariable=text, bg='#0c141d', fg='white').pack(pady=10)
    source = tk.Toplevel(root); source.title('Toolbox capture source · Fixed 640×360'); source.geometry('640x360+30+40')
    if args.offscreen_source: source.geometry(f'640x360+{root.winfo_screenwidth()+80}+40')
    source.resizable(False, False)
    canvas = tk.Canvas(source, bg='#15293b', highlightthickness=0); canvas.pack(fill='both', expand=True)
    canvas.create_rectangle(20, 20, 620, 340, outline='#75c7fb', width=3)
    label = canvas.create_text(320, 100, text='CS2 TOOLBOX\nExternal GPU capture fixture', fill='white', font=('Segoe UI', 22), justify='center')
    ball = canvas.create_oval(30, 220, 65, 255, fill='#f59d32', outline='')
    state = {'capture': None, 'counter': 0, 'start': time.monotonic(), 'phase': 0, 'baseline': None, 'frames': []}

    def animate():
        state['counter'] += 1
        x = 40 + state['counter'] * 5 % 540
        canvas.coords(ball, x, 235, x + 35, 270)
        canvas.itemconfigure(label, text=f'CS2 TOOLBOX\nLive source frame {state["counter"]}')
        source.after(33, animate)

    def start():
        try:
            source.update_idletasks(); root.update_idletasks()
            state['baseline'] = (source.winfo_width(), source.winfo_height())
            state['capture'] = Capture(source.winfo_id(), view.winfo_id())
            if args.masked_source:
                # This test owns the source HWND. No external application is altered.
                api = ctypes.WinDLL('user32', use_last_error=True)
                api.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]; api.GetAncestor.restype = wintypes.HWND
                api.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]; api.GetWindowLongPtrW.restype = ctypes.c_ssize_t
                api.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]; api.SetWindowLongPtrW.restype = ctypes.c_ssize_t
                api.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.DWORD, wintypes.BYTE, wintypes.DWORD]
                hwnd = api.GetAncestor(source.winfo_id(), 2)
                style = api.GetWindowLongPtrW(hwnd, -20)
                api.SetWindowLongPtrW(hwnd, -20, style | 0x80000 | 0x20 | 0x08000000)
                if not api.SetLayeredWindowAttributes(hwnd, 0, 1, 2): raise ctypes.WinError(ctypes.get_last_error())
            # Cover part of the source with our own viewer; do not minimize it.
            root.lift(); poll()
        except Exception as exc: fail(str(exc))

    def fail(message):
        print(json.dumps({'ok': False, 'error': message}), flush=True)
        if state['capture']: state['capture'].close(); state['capture'] = None
        root.destroy(); raise SystemExit(1)

    def poll():
        try:
            c = state['capture']; stats = c.stats()
            if stats.state == 4: raise ValueError(f'Native failure: 0x{stats.error & 0xffffffff:08X}')
            text.set(f'{stats.frames} captured frames · Native source {stats.width} × {stats.height} · Viewer scales independently')
            elapsed = time.monotonic() - state['start']
            if state['phase'] == 0 and elapsed >= 2:
                if stats.frames < 5: raise ValueError('Fewer than five captured frames after two seconds.')
                state['frames'].append(stats.frames); state['phase'] = 1
                root.geometry('1100x720+0+0')
            elif state['phase'] == 1 and elapsed >= 4:
                if (source.winfo_width(), source.winfo_height()) != state['baseline']: raise ValueError('Viewer resize changed source dimensions.')
                if stats.frames <= state['frames'][0]: raise ValueError('Frames did not advance after resizing.')
                state['frames'].append(stats.frames); state['phase'] = 2
                c.close(); state['capture'] = Capture(source.winfo_id(), view.winfo_id())
            elif state['phase'] == 2 and elapsed >= 6:
                if stats.frames < 5: raise ValueError('Reconnect did not deliver frames.')
                if (source.winfo_width(), source.winfo_height()) != state['baseline']: raise ValueError('Reconnect changed source dimensions.')
                state['phase'] = 3
                red, green, blue, alpha = c.sample(100, 180)
                if not (blue > green > red >= 0 and blue > .02 and alpha > .9):
                    raise ValueError(f'Captured pixels do not match the fixture background: {(red, green, blue, alpha)}')
                mode = 'masked source' if args.masked_source else 'offscreen source' if args.offscreen_source else 'fully covered source'
                print(json.dumps({'ok': True, 'checks': ['frames', mode, 'app resize', 'source size unchanged', 'reconnect', 'actual pixel color'],
                                  'source_client': state['baseline'], 'captured_size': [stats.width, stats.height],
                                  'sample_rgba': [red, green, blue, alpha],
                                  'frame_counts': state['frames'] + [stats.frames]}), flush=True)
                if args.self_test:
                    c.close(); state['capture'] = None; root.destroy(); return
            root.after(100, poll)
        except Exception as exc: fail(str(exc))

    def resize(_):
        if state['capture']: state['capture'].resize()

    def close():
        if state['capture']: state['capture'].close(); state['capture'] = None
        root.destroy()

    view.bind('<Configure>', resize)
    root.protocol('WM_DELETE_WINDOW', close); source.protocol('WM_DELETE_WINDOW', close)
    animate(); root.after(200, start); root.mainloop()


if __name__ == '__main__': main()
