"""Application-owned Tk tests: no desktop automation, CS2, mouse or keyboard input."""
import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import demo_review
import native_view_panel as view


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.geometry('1000x500+20+20')
        self.version = patch.object(view.NativeViewPanel, 'check_version').start()
        self.addCleanup(patch.stopall)
        self.panel = view.NativeViewPanel(self.root); self.panel.pack(fill='both', expand=True)
        self.root.update_idletasks()
        self.addCleanup(self.cleanup_ui)
        self.guard = Mock(); self.guard.check.return_value = []
        self.capture = Mock()
        self.capture.stats.return_value = SimpleNamespace(state=1, error=0, width=1280, height=960,
                                                         frames=30, seconds_since_frame=.01)

    def cleanup_ui(self):
        self.panel.close(); self.root.destroy()

    def poll_once(self):
        # Advance the app's own scheduler without creating a second polling loop.
        self.panel.after_cancel(self.panel.poll_timer)
        self.panel.poll()

    def connect_fixture(self):
        windows = [{'hwnd': 42, 'pid': 7, 'executable': str(view.native.DEFAULT_GAME/'bin/win64/cs2.exe')}]
        with patch.object(view.native, 'game_windows', return_value=windows), \
             patch.object(view.native, 'SettingsGuard', return_value=self.guard), \
             patch.object(view.native, 'Capture', return_value=self.capture):
            self.panel.connect()

    def test_missing_or_ambiguous_source_never_starts_capture(self):
        with patch.object(view.native, 'Capture') as start:
            for windows in [[], [{'hwnd': 1}, {'hwnd': 2}]]:
                with patch.object(view.native, 'game_windows', return_value=windows): self.panel.connect()
                self.assertIsNone(self.panel.capture)
            start.assert_not_called()

    def test_closing_before_queued_launch_is_shown_stops_its_owned_engine(self):
        session = Mock()
        self.panel.messages.put(('managed', (self.panel.launch_generation, session)))
        self.panel.close()
        session.stop.assert_called_once_with()
        self.assertTrue(self.panel.closed)

    def test_failed_engine_stop_prevents_closing_and_retains_ownership(self):
        session = Mock(); session.stop.side_effect = TimeoutError('owned engine still exiting')
        self.panel.managed = session
        try:
            self.assertFalse(self.panel.close())
            self.assertFalse(self.panel.closed); self.assertIs(self.panel.managed,session)
        finally: session.stop.side_effect = None

    def test_viewport_resize_calls_only_our_capture_surface(self):
        self.connect_fixture()
        self.panel.resize()
        self.capture.resize.assert_called_once_with()
        self.capture.stats.assert_not_called()
        self.poll_once()
        self.assertIn('1280 × 960', self.panel.status.get())
        self.assertIn('not certified', self.panel.status.get())

    def test_changed_saved_preferences_stop_capture_without_restoration(self):
        self.connect_fixture(); self.guard.check.return_value = ['video.txt']
        self.panel.checked = time.monotonic() - 6
        self.poll_once()
        self.capture.close.assert_called_once_with()
        self.assertIsNone(self.panel.capture)
        self.assertIn('no settings were restored', self.panel.status.get())

    def test_update_stops_view_and_leaves_controls_unverified(self):
        self.connect_fixture()
        self.panel.messages.put(('profile', ({'version': {'PatchVersion': 'new'}, 'build': '123','fingerprint':'unknown'}, True)))
        self.poll_once()
        self.capture.close.assert_called_once_with()
        self.assertIn('Game update detected', self.panel.compatibility.get())

    def test_minimized_source_is_reported_without_window_actions(self):
        self.connect_fixture(); self.capture.stats.return_value.state = 2
        self.poll_once()
        self.assertIn('Restore it manually', self.panel.status.get())
        self.capture.close.assert_not_called()

    def test_no_frame_timeout_stops_without_retries_or_display_changes(self):
        self.connect_fixture(); self.panel.started = time.monotonic() - 13
        self.capture.stats.return_value.frames = 0
        self.poll_once()
        self.capture.close.assert_called_once_with()
        self.assertIn('no display changes', self.panel.status.get())

    def managed_fixture(self):
        self.connect_fixture()
        session=Mock();session.process.poll.return_value=None
        session.demo_compat=None
        session.control_guard=None
        session.redirected.return_value=True;session.demo_active.return_value=True
        session.changes.return_value=[];session.started=time.monotonic()
        self.panel.managed=session
        return session

    def test_engine_crash_takes_priority_over_lost_window(self):
        session=self.managed_fixture();session.process.poll.return_value=0xC0000005
        session.failure_message.return_value='CS2 crashed while playing this demo (access violation).'
        self.capture.stats.return_value.state=3
        self.poll_once()
        self.assertIn('CS2 crashed',self.panel.status.get())
        session.failure_message.assert_called_once_with('engine_exit',self.capture.stats.return_value)
        session.find_window.assert_not_called();session.stop.assert_called_once_with()

    def test_lost_owned_window_reconnects_without_launching_another_engine(self):
        session=self.managed_fixture();self.capture.stats.return_value.state=3
        source={'hwnd':43,'pid':7,'executable':str(view.native.DEFAULT_GAME/'bin/win64/cs2.exe')}
        session.find_window.return_value=source
        replacement=Mock();replacement.stats.return_value=SimpleNamespace(state=1,error=0,width=1920,height=1080,
                                                                         frames=20,seconds_since_frame=.01)
        with patch.object(view.native,'Capture',return_value=replacement) as create, \
             patch.object(view,'ManagedSession') as launch:
            self.poll_once();self.poll_once()
            create.assert_called_once_with(43,self.panel.viewport.winfo_id());launch.assert_not_called()
        self.capture.close.assert_called_once_with();session.stop.assert_not_called()
        self.assertIn('1920 × 1080',self.panel.status.get())

    def test_engine_crash_is_reported_even_if_capture_stats_are_unavailable(self):
        session=self.managed_fixture();session.process.poll.return_value=0xC0000005
        session.failure_message.return_value='CS2 crashed while playing this demo.'
        self.capture.stats.side_effect=OSError('capture no longer available')
        self.poll_once()
        session.failure_message.assert_called_once_with('engine_exit',None)
        self.assertIn('CS2 crashed',self.panel.status.get())

    def test_missing_owned_window_has_bounded_recovery(self):
        session=self.managed_fixture();self.capture.stats.return_value.state=3
        session.find_window.return_value=None;session.failure_message.return_value='Picture could not be reconnected.'
        self.poll_once();self.assertIsNotNone(self.panel.capture)
        self.panel.recovering_since=time.monotonic()-6
        self.poll_once();session.stop.assert_called_once_with()
        self.assertIn('could not be reconnected',self.panel.status.get())

    def test_lost_local_control_restriction_stops_the_owned_engine(self):
        session=self.managed_fixture();session.control_guard=Mock();session.control_guard.healthy.return_value=False
        self.poll_once()
        session.stop.assert_called_once_with();self.capture.close.assert_called_once_with()
        self.assertIn('local control restriction ended',self.panel.status.get())


class ReviewLayoutTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.geometry('1320x860')
        ttk.Style(self.root).theme_use('clam')
        ttk.Style(self.root).configure('Treeview', rowheight=30)
        self.root.option_add('*Font', '{Segoe UI} 10')
        self.patches = [patch.object(view.NativeViewPanel, 'check_version'),
                        patch.object(demo_review.DemoReview, 'load_library'),
                        patch.object(demo_review.model.Moments, 'read', return_value=[])]
        for p in self.patches: p.start()
        self.window = demo_review.DemoReview(self.root, Mock())
        self.window.pack(fill='both',expand=True)
        # These are the opt-in legacy panel's layout checks. The normal
        # workflow starts in Demos and uses the standalone Watch tab.
        self.window.show_legacy()
        self.window.update()
        self.addCleanup(self.cleanup_ui)

    def cleanup_ui(self):
        self.window.close(); self.root.destroy()
        for p in reversed(self.patches): p.stop()

    def test_view_and_actions_fit_declared_minimum_and_default_sizes(self):
        self.window.tabs.select(self.window.embedded_view)
        for width, height in [(1000, 650), (1320, 860)]:
            with self.subTest(size=(width, height)):
                self.root.geometry(f'{width}x{height}')
                self.window.update(); self.window.update_idletasks()
                panel = self.window.embedded_view
                self.assertGreaterEqual(panel.viewport.winfo_height(), height-320, '3D viewport loses too much space to controls')
                self.assertFalse(self.window.analysis_footer.winfo_ismapped())
                for button in self.buttons(self.window):
                    if not button.winfo_ismapped(): continue
                    parent = button.master
                    self.assertLessEqual(button.winfo_x() + button.winfo_width(), parent.winfo_width(),
                                         f'Action clipped: {button.cget("text")}')

    def test_library_and_analysis_filters_remain_accessible(self):
        self.root.geometry('1000x650'); self.window.update()
        self.assertFalse(self.window.games.master.winfo_ismapped())
        self.window.toggle_library(); self.window.update()
        self.assertTrue(self.window.games.master.winfo_ismapped())
        self.window.toggle_library(); self.window.update()
        self.window.tabs.select(self.window.analysis_tab); self.window.update()
        self.window.moment_tabs.select(self.window.event_tab); self.window.update()
        self.assertTrue(self.window.review_nav.winfo_ismapped())
        self.assertTrue(self.window.analysis_footer.winfo_ismapped())
        self.window.tabs.select(self.window.native_view); self.window.update()
        self.assertFalse(self.window.review_nav.winfo_ismapped())
        self.assertGreaterEqual(self.window.native_view.viewport.winfo_height(), 100)

    def test_expand_view_uses_our_window_and_restores_analysis_and_library_access(self):
        self.root.geometry('1000x650');self.window.update()
        original=self.root.geometry()
        with patch.object(view.native,'Capture') as capture,patch.object(view.native,'game_windows') as source:
            self.window.native_view.expand_button.invoke();self.window.update()
            self.assertTrue(self.window.expanded)
            self.assertFalse(self.window.header.winfo_ismapped())
            self.assertGreaterEqual(self.window.native_view.viewport.winfo_height(),self.window.winfo_height()-120)
            self.window.toggle_expanded();self.window.update()
            self.assertFalse(self.window.expanded);self.assertEqual(self.root.geometry(),original)
            self.assertTrue(self.window.tabs.winfo_ismapped())
            self.window.show_downloaded();self.window.update()
            self.assertTrue(self.window.games.winfo_ismapped())
            self.window.tabs.select(self.window.analysis_tab);self.window.update()
            self.assertTrue(self.window.analysis_footer.winfo_ismapped())
            capture.assert_not_called();source.assert_not_called()

    def test_download_without_analysis_plays_without_requiring_a_round_or_file_picker(self):
        from pathlib import Path
        entry=dict(sha='a'*64,source='download:'+'a'*64,game='a'*64,map='de_mirage',
                   title='Downloaded demo',search='downloaded demo',folder=None,demo_path=Path('fixture.dem'))
        self.window.tabs.select(0);self.window.update()
        self.window.entries=[entry];self.window.filter_games();self.window.games.selection_set('0');self.window.choose_game()
        self.assertIsNone(self.window.match)
        self.assertEqual(self.window.tabs.select(),str(self.window.library_tab))
        self.window.show_legacy();self.window.update()
        def immediate(tag,fn,generation=None):self.window.events.put((tag,generation,fn()))
        with patch.object(self.window,'current',side_effect=AssertionError('analysis must not be required')), \
             patch.object(self.window,'work',side_effect=immediate), \
             patch.object(demo_review.replays,'resolve_entry',return_value=Path('fixture.dem')), \
             patch.object(self.window.native_view,'start_private') as start, \
             patch('tkinter.filedialog.askopenfilename') as picker:
            self.window.play_selected();self.window.after_cancel(self.window.poll_timer);self.window.poll()
            start.assert_called_once_with(Path('fixture.dem'));picker.assert_not_called()

    def test_saved_moments_for_missing_downloads_are_hidden_without_deleting_notes(self):
        note=dict(id='kept',sha='a'*64,map='de_mirage',round=1,note='Available')
        missing={**note,'id':'missing','sha':'b'*64,'note':'Unavailable'}
        self.window.entries=[{'sha':'a'*64}]
        with patch.object(self.window.moments,'read',return_value=[note,missing]), \
             patch.object(self.window.moments,'remove') as remove:
            self.window.refresh_saved()
            self.assertEqual(self.window.saved.get_children(),('kept',));remove.assert_not_called()

    def test_missing_download_refreshes_watch_list_without_opening_a_picker(self):
        self.window.events.put(('error',None,('play_demo','This demo is no longer available in replays.')))
        with patch.object(self.window,'load_library') as refresh, patch('tkinter.filedialog.askopenfilename') as picker:
            self.window.after_cancel(self.window.poll_timer);self.window.poll()
            refresh.assert_called_once_with();picker.assert_not_called()

    @staticmethod
    def buttons(widget):
        for child in widget.winfo_children():
            if isinstance(child, tk.Button): yield child
            yield from ReviewLayoutTests.buttons(child)


if __name__ == '__main__': unittest.main()
