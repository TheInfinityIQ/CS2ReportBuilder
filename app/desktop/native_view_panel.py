"""In-application GPU viewport with a read-only attachment boundary."""
from __future__ import annotations
import queue
from pathlib import Path
import threading
import time
import tkinter as tk

import native_viewer as native
from native_session import ManagedSession
import native_controls as controls
from playback_controls import PlaybackControls

BG = '#080d13'; FG = '#e0eaf2'; MUTED = '#8da2b6'


class NativeViewPanel(tk.Frame):
    def __init__(self, master, play_selected=None, *, allow_unverified=False, expand_view=None):
        super().__init__(master, bg=BG)
        self.capture = None; self.guard = None; self.closed = False
        self.checked = 0.; self.started = 0.; self.checking = False
        self.messages = queue.Queue(); self.profile = None; self.source = None
        self.managed = None; self.pending_launch = False; self.launch_generation = 0
        self.launch_lock = threading.Lock(); self.can_play = play_selected is not None
        self.allow_unverified = allow_unverified
        self.launch_cancel = None
        self.launch_stage=None
        self.expanded=False;self.pending_analysis_tick=None;self.controls_connecting=False
        self.control_record=None;self.control_default_set=False
        self.use_controls=tk.BooleanVar(value=False)
        self.recovering_since = None; self.capture_recoveries = 0
        self.next_version_check = time.monotonic() + 60
        self.status = tk.StringVar(value='Choose a match, then Play selected demo. Toolbox manages its private CS2 playback process.')
        self.compatibility = tk.StringVar(value='Game build not checked · Your normal preferences are protected during managed playback')
        row = tk.Frame(self, bg=BG); row.pack(fill='x', padx=10, pady=8)
        row.bind('<Configure>',self.flow_buttons)
        self.play_button = self.button(row, 'Play using CS2', play_selected or (lambda: None))
        if play_selected is None: self.play_button.configure(state='disabled')
        self.stop_button = self.button(row, 'Stop view', self.disconnect)
        self.show_button=tk.Menubutton(row,text='More',bg='#21394b',fg=FG,relief='flat',padx=12,pady=7)
        menu=tk.Menu(self.show_button,tearoff=False)
        menu.add_command(label='Attach to existing CS2',command=self.connect)
        menu.add_command(label='Check game version',command=self.check_version)
        menu.add_checkbutton(label='Enable demo controls (Windows approval)',variable=self.use_controls,state='disabled')
        self.control_menu=menu;self.control_menu_index=menu.index('end')
        self.show_button.configure(menu=menu);self.show_button.grid(row=0,column=2,padx=(0,8),pady=2)
        self.expand_button = self.button(row, 'Expand view (F11)', expand_view or (lambda: None))
        if expand_view is None: self.expand_button.configure(state='disabled')
        self.compatibility_label = tk.Label(self, textvariable=self.compatibility, bg=BG, fg=MUTED, anchor='w',
                 justify='left', wraplength=1050)
        self.compatibility_label.pack(fill='x', padx=10)
        self.playback=PlaybackControls(self)
        self.viewport = tk.Frame(self, bg='black', height=260)
        self.viewport.pack(fill='both', expand=True, padx=10, pady=8)
        self.placeholder = tk.Label(self.viewport, text='3D GAME VIEW\n\nCS2’s live picture will appear here.\nResolution and game preferences stay under your control.',
                                    bg='black', fg=MUTED, font=('Segoe UI', 12), justify='center')
        self.placeholder.place(relx=.5, rely=.5, anchor='center')
        self.viewport.bind('<Configure>', self.resize)
        tk.Label(self, textvariable=self.status, bg=BG, fg=FG, anchor='w', justify='left',
                 wraplength=1050).pack(fill='x', padx=10, pady=(0, 4))
        self.help_label = tk.Label(self, text='Your saved display settings stay unchanged. Demo controls require verification for this game build.', bg=BG, fg=MUTED, anchor='w',
                 justify='left', wraplength=1050)
        self.help_label.pack(fill='x', padx=10, pady=(0, 8))
        self.poll_timer = self.after(500, self.poll)
        self.bind('<Configure>', self.wrap_labels)
        self.viewport.bind('<Configure>', self.wrap_placeholder, add='+')
        self.check_version()

    def set_expanded(self, expanded):
        self.expanded=expanded
        self.expand_button.configure(text='Restore view (Esc)' if expanded else 'Expand view (F11)')
        self.update_playback_chrome()
        self.viewport.pack_configure(padx=0 if expanded else 10,pady=0 if expanded else 8)

    def update_playback_chrome(self):
        if self.expanded or (self.managed and self.managed.control_guard):
            self.compatibility_label.pack_forget();self.help_label.pack_forget()
        else:
            self.compatibility_label.pack(fill='x',padx=10,before=self.viewport)
            self.help_label.pack(fill='x',padx=10,pady=(0,8))

    def button(self, parent, text, action):
        b = tk.Button(parent, text=text, command=action, bg='#21394b', fg=FG, relief='flat', padx=12, pady=7)
        b.grid(row=0,column=len(parent.winfo_children())-1,padx=(0,8),pady=2,sticky='w'); return b

    def flow_buttons(self,event):
        row=column=used=0
        for button in event.widget.winfo_children():
            width=button.winfo_reqwidth()+8
            if used and used+width>event.width:row+=1;column=used=0
            button.grid_configure(row=row,column=column)
            column+=1;used+=width

    def wrap_labels(self, event):
        if event.widget is not self: return
        for child in self.winfo_children():
            if isinstance(child, tk.Label): child.configure(wraplength=max(100, event.width-20))

    def wrap_placeholder(self, event):
        self.placeholder.configure(wraplength=max(100, event.width-24))

    def check_version(self):
        if self.checking or self.closed: return
        self.checking = True
        game = Path(self.source['executable']).parents[2] if self.source else native.configured_game()
        self.next_version_check = time.monotonic() + 60
        def run():
            try: self.messages.put(('profile', native.observe_runtime(game)))
            except Exception as exc: self.messages.put(('profile_error', str(exc)))
        threading.Thread(target=run, daemon=True).start()

    def connect(self):
        self.disconnect()
        try:
            windows = native.game_windows()
            if not windows: raise ValueError('No visible CS2 window found. Open CS2 normally and leave it restored, then try again.')
            if len(windows) != 1: raise ValueError('More than one CS2 window is available. Leave only the intended game window visible before connecting.')
            source = windows[0]
            # Verify the executable's directory, never infer game state from the selected analysis.
            game = Path(source['executable']).parents[2]
            self.guard = native.SettingsGuard(game)
            self.viewport.update_idletasks()
            self.capture = native.Capture(source['hwnd'], self.viewport.winfo_id())
            self.source = source; self.started = time.monotonic(); self.checked = self.started
            self.placeholder.place_forget()
            self.status.set('Waiting for the first frame at CS2’s existing display settings…')
            self.check_version()
        except Exception as exc:
            self.disconnect(str(exc))

    def start_private(self, path, *, analysis_tick=None,tick_space='demo'):
        if analysis_tick is not None and not self.use_controls.get():
            self.status.set('Enable demo controls before watching a selected analysis moment.');return
        self.disconnect()
        self.pending_analysis_tick=(analysis_tick,tick_space) if analysis_tick is not None else None
        self.pending_launch = True
        self.launch_stage='queued'
        want_controls=self.use_controls.get()
        generation = self.launch_generation
        cancel = threading.Event(); self.launch_cancel = cancel
        self.status.set('Windows may ask for administrator approval for local playback controls…' if want_controls else
                        'Starting a private engine with copied preferences and read-only locks on your existing settings…')
        self.play_button.configure(state='disabled')
        def run():
            session = ManagedSession(allow_unverified=self.allow_unverified)
            try:
                if cancel.is_set(): return
                if want_controls:
                    controls.require_verified(native.runtime_profile(session.game))
                    import cs2_jump
                    if cs2_jump.is_running():raise ValueError('CS2 is already running. Its session was left untouched.')
                    session.control_guard=controls.LocalGuard(session.game)
                    self.launch_stage='approval'
                    # Shell elevation can activate COM extensions. This launch
                    # worker has no Tk/OLE apartment; initialize its own STA.
                    import ctypes
                    ole=ctypes.WinDLL('ole32')
                    ole.CoInitializeEx.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
                    ole.CoInitializeEx.restype=ctypes.c_long
                    hr=ole.CoInitializeEx(None,6)
                    if hr<0:raise ValueError(f'Could not initialize the local-control approval worker (0x{hr & 0xffffffff:08X}).')
                    try:session.control_guard.start()
                    finally:ole.CoUninitialize()
                self.launch_stage='engine'
                self.messages.put(('launch_progress',(generation,'Starting the private CS2 engine with your saved display settings…')))
                session.start(path, cancel=cancel)
                while time.monotonic() - session.started < 20:
                    if self.closed or generation != self.launch_generation:
                        session.stop(); return
                    if session.process.poll() is not None: raise ValueError(session.failure_message('engine_exit'))
                    if session.find_window(): break
                    time.sleep(.1)
                else: raise ValueError('The private engine did not provide a window within the startup limit.')
                with self.launch_lock:
                    cancelled = self.closed or generation != self.launch_generation
                    if not cancelled: self.messages.put(('managed', (generation, session)))
                if cancelled: session.stop()
            except Exception as exc:
                try: session.stop()
                except Exception as stop_error: exc = RuntimeError(str(exc) + ' · ' + str(stop_error))
                with self.launch_lock:
                    if not self.closed and generation == self.launch_generation:
                        self.messages.put(('managed_error', (generation, str(exc))))
        threading.Thread(target=run, daemon=True).start()

    def disconnect(self, message='View stopped. CS2 was left running at its existing settings.'):
        self.playback.disconnect();self.playback.pack_forget()
        stale_sessions = []; retained = []
        with self.launch_lock:
            if self.launch_cancel: self.launch_cancel.set()
            self.launch_generation += 1; self.pending_launch = False
            self.launch_stage=None
            try:
                while True:
                    item = self.messages.get_nowait()
                    if item[0] == 'managed': stale_sessions.append(item[1][1])
                    else: retained.append(item)
            except queue.Empty: pass
            for item in retained: self.messages.put(item)
        failure = None
        for session in stale_sessions:
            try: session.stop()
            except Exception as exc: failure = str(exc); self.managed = session
        if self.capture:
            try: self.capture.close()
            except Exception as exc: failure = str(exc)
            self.capture = None
        if self.managed:
            try:
                self.managed.stop()
                message = 'Private playback stopped. Your saved settings were preserved.' if message.startswith('View stopped.') else message
                self.managed = None
            except Exception as exc: failure = str(exc)
        if self.guard:
            try:
                if self.guard.check(): message = 'Saved-setting files changed during this view. Capture stopped; no settings were restored or overwritten.'
            except Exception as exc: failure = str(exc)
            self.guard = None
        self.source = None
        self.recovering_since = None; self.capture_recoveries = 0
        self.pending_analysis_tick=None
        self.controls_connecting=False
        if not self.closed:
            self.placeholder.place(relx=.5, rely=.5, anchor='center')
            self.status.set(failure or message)
            self.play_button.configure(state='normal' if self.can_play else 'disabled')
            self.update_playback_chrome()

    def resize(self, _=None):
        if self.capture:
            try: self.capture.resize()
            except Exception as exc: self.disconnect(str(exc))

    def poll(self):
        if self.closed: return
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind in ('profile','profile_error'): self.checking = False
                if kind == 'managed':
                    generation, session = value
                    if generation != self.launch_generation:
                        session.stop(); continue
                    self.managed = session; self.pending_launch = False
                    self.launch_stage=None
                    self.source = session.window; self.started = time.monotonic(); self.checked = self.started
                    try:
                        self.viewport.update_idletasks()
                        self.capture = native.Capture(self.source['hwnd'], self.viewport.winfo_id())
                        self.placeholder.place_forget()
                        self.check_version()
                    except Exception as exc: self.disconnect(str(exc))
                elif kind == 'managed_error':
                    generation, message = value
                    if generation == self.launch_generation:
                        self.pending_launch = False; self.status.set(message)
                        self.launch_stage=None
                        self.play_button.configure(state='normal' if self.can_play else 'disabled')
                elif kind=='launch_progress':
                    generation,message=value
                    if generation==self.launch_generation:self.status.set(message)
                elif kind == 'profile':
                    self.profile, changed = value
                    if changed and self.capture:
                        self.disconnect('The installed game changed. View stopped; check the game version before reconnecting.')
                    self.compatibility.set(f'CS2 {self.profile["version"].get("PatchVersion", "?")} · Build {self.profile["build"]} · '
                        + ('Game update detected; controls require new validation' if changed else 'Playback controls not yet validated'))
                    try:self.control_record=controls.require_verified(self.profile)
                    except (ValueError,OSError):self.control_record=None
                    self.control_menu.entryconfigure(self.control_menu_index,state='normal' if self.control_record else 'disabled')
                    if not self.control_record:self.use_controls.set(False)
                    elif not self.control_default_set:
                        self.use_controls.set(True);self.control_default_set=True
                    if self.control_record:self.compatibility.set(f'CS2 {self.profile["version"].get("PatchVersion", "?")} · Build {self.profile["build"]} · Core playback controls verified')
                    self.help_label.configure(text='Your saved resolution and display mode stay unchanged. '
                        + ('Demo controls are available in More (Windows approval). Free-camera mouse input is unavailable.' if self.control_record else
                           'Playback controls need verification for this game build. Watching does not require analysis.'))
                elif kind == 'profile_error': self.compatibility.set('Game version check unavailable: ' + value)
        except queue.Empty: pass
        if time.monotonic() >= self.next_version_check: self.check_version()
        if self.pending_analysis_tick is not None and self.playback.info:
            (tick,tick_space),self.pending_analysis_tick=self.pending_analysis_tick,None
            try:self.playback.seek_analysis_tick(tick,tick_space)
            except ValueError as exc:self.playback.note.set(str(exc))
        if self.capture:
            try:
                # An exited engine can invalidate its HWND and capture device at
                # the same time. Diagnose the process before the capture symptom.
                if self.managed and self.managed.process.poll() is not None:
                    try:final_stats = self.capture.stats()
                    except Exception:final_stats = None
                    raise ValueError(self.managed.failure_message('engine_exit', final_stats))
                if self.managed and self.managed.control_guard and not self.managed.control_guard.healthy():
                    raise ValueError('The local control restriction ended. Private playback stopped.')
                stats = self.capture.stats()
                if stats.state in (3, 4):
                    if self.managed:
                        if self.recover_capture(stats):
                            self.poll_timer = self.after(500, self.poll); return
                        raise ValueError(self.managed.failure_message('capture_stopped', stats))
                    raise ValueError('The attached CS2 window closed.' if stats.state == 3 else
                                     f'The capture device stopped (0x{stats.error & 0xffffffff:08X}). Attach again to retry.')
                self.recovering_since = None
                if time.monotonic() - self.checked >= 5:
                    self.checked = time.monotonic()
                    if (self.managed and self.managed.changes()) or (self.guard and self.guard.check()):
                        raise ValueError('Saved-setting files changed during this view. Capture stopped; no settings were restored or overwritten.')
                if self.managed:
                    if not self.managed.redirected():
                        self.status.set('Private engine rendering · Waiting to verify its separate configuration folder…')
                        if time.monotonic() - self.managed.started > 25:
                            raise ValueError('The private configuration folder was not confirmed. Playback stopped without changing your saved preferences.')
                        self.poll_timer = self.after(500, self.poll); return
                    if not self.managed.demo_active():
                        self.status.set('Loading the selected demo in the private engine… Your saved preferences remain protected.')
                        if time.monotonic() - self.managed.started > 90:
                            raise ValueError('This demo did not reach playback within the load limit. Its logs were retained; no automatic retry was started.')
                        self.poll_timer = self.after(500, self.poll); return
                    if self.managed.control_guard and not self.controls_connecting and stats.frames>=60:
                        record=controls.require_verified(self.managed.before_runtime)
                        self.controls_connecting=True
                        self.playback.pack(fill='x',padx=10,pady=4,before=self.viewport)
                        self.playback.connect(self.managed,record);self.update_playback_chrome()
                if stats.state == 2:
                    self.status.set('CS2 is minimized. Restore it manually to resume the picture; the viewer will not change its window.')
                elif stats.seconds_since_frame > 3 or (not stats.frames and time.monotonic() - self.started > 3):
                    self.status.set('No recent frames from CS2. Its display mode and settings have been left unchanged.')
                    if not stats.frames and time.monotonic() - self.started > 12:
                        raise ValueError('CS2 supplied no frames at its existing settings. This capture mode is unavailable; no display changes were made.')
                else:
                    detail = 'Private CS2 playback · Original settings locked read-only' if self.managed else 'Saved-setting monitor active (effective runtime settings are not certified)'
                    if self.managed and self.managed.demo_compat and self.managed.demo_compat.get('applied'):
                        detail='Compatibility playback copy · Original demo and saved settings unchanged'
                    self.status.set(f'Live frame feed · Captured window {stats.width} × {stats.height} · {stats.frames:,} frames received · ' + detail)
            except Exception as exc: self.disconnect(str(exc))
        self.poll_timer = self.after(500, self.poll)

    def recover_capture(self, stats):
        # Only reconnect the existing owned process. Never restart a crashed
        # demo or attach to another process discovered by title.
        now = time.monotonic()
        if self.recovering_since is None: self.recovering_since = now
        if now-self.recovering_since > 5 or self.capture_recoveries >= 2:return False
        source = self.managed.find_window()
        if source:
            self.capture.close();self.capture = None
            try:self.capture = native.Capture(source['hwnd'],self.viewport.winfo_id())
            except Exception:
                # Keep the failed source observable until the bounded retry ends.
                raise ValueError(self.managed.failure_message('capture_stopped',stats))
            self.capture_recoveries += 1;self.source = source;self.started = now
        self.status.set('Reconnecting the private playback picture… Your game settings are unchanged.')
        return True

    def close(self):
        if self.closed: return True
        self.disconnect()
        if self.managed: return False
        self.closed = True
        self.playback.close()
        self.after_cancel(self.poll_timer)
        return True
