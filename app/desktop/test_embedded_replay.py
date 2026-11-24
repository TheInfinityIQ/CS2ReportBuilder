"""Renderer ownership and cancel races, using application-owned widgets."""
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

import embedded_replay as embedded


class EmbeddedLifecycleTests(unittest.TestCase):
    def test_attachment_never_queries_the_window_lock_from_the_ui_thread(self):
        child=embedded.ChildWindow.__new__(embedded.ChildWindow)
        child.attaching=True;child.api=Mock();child.handle=123
        self.assertFalse(child.valid())
        child.api.IsWindow.assert_not_called();child.api.GetParent.assert_not_called()

    def test_unacknowledged_native_resize_is_retried(self):
        child=embedded.ChildWindow.__new__(embedded.ChildWindow)
        child.handle=123;child.last_display=(763,526,True);child.api=Mock();child.valid=lambda:True
        def old_size(_,pointer):pointer._obj.right=903;pointer._obj.bottom=586;return True
        child.api.GetClientRect.side_effect=old_size
        child.display(763,526,True)
        child.api.SetWindowPos.assert_called_once()
        child.api.SetWindowPos.reset_mock()
        def acknowledged(_,pointer):pointer._obj.right=763;pointer._obj.bottom=526;return True
        child.api.GetClientRect.side_effect=acknowledged
        child.display(763,526,True)
        child.api.SetWindowPos.assert_not_called()

    def setUp(self):
        self.root=tk.Tk();self.root.withdraw()
        self.panel=embedded.EmbeddedReplay(self.root)
        fixtures=embedded.STATE/'standalone3d/test-fixtures';fixtures.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=fixtures)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.root.update_idletasks()
        self.panel.close()
        for timer in self.root.tk.call('after','info'):self.root.tk.call('after','cancel',timer)
        self.root.destroy();self.temp.cleanup()
        self.panel=None;self.root=None
        import gc
        gc.collect()

    def until(self,predicate):
        deadline=time.monotonic()+2
        while time.monotonic()<deadline and not predicate():
            self.root.update();time.sleep(.005)
        self.assertTrue(predicate())

    def test_cancel_closes_a_started_renderer_still_in_the_delivery_queue(self):
        process=Mock();group=Mock()
        self.panel.messages.put((self.panel.generation,'started',(process,group,'4.7.2')))
        self.panel.stop()
        group.terminate.assert_called_once();group.close.assert_called_once()
        self.assertIsNone(self.panel.process)

    def test_cancel_during_runtime_discovery_prevents_launch(self):
        entered=threading.Event();release=threading.Event();finished=threading.Event()
        def version(_):
            entered.set();release.wait(2);finished.set();return '4.7.2'
        with patch.object(embedded.launcher,'find_godot',return_value='godot.exe'), \
             patch.object(embedded.launcher,'runtime_version',side_effect=version), \
             patch.object(embedded.launcher,'launch') as launch:
            self.panel.start('downloaded.dem');self.assertTrue(entered.wait(1))
            self.panel.close();release.set();self.assertTrue(finished.wait(1))
            launch.assert_not_called()

    def test_ready_shutdown_requests_quit_and_keeps_parent_until_exit(self):
        process=Mock();process.poll.return_value=None
        entered=threading.Event();release=threading.Event()
        def wait(**kwargs):entered.set();release.wait(2);return 0
        process.wait.side_effect=wait;group=Mock()
        self.panel.session=embedded.Path(self.temp.name);self.panel.process=process;self.panel.group=group
        self.panel.ready=True;self.panel.command_sequence=9
        with patch.object(embedded,'save_json') as save:
            self.assertFalse(self.panel.close());self.assertTrue(entered.wait(1))
            self.assertEqual(save.call_args.args[1],{'id':10,'action':'quit'})
            group.terminate.assert_not_called();group.close.assert_not_called()
            release.set();self.assertTrue(self.panel.retiring[0].wait(1))
            self.assertTrue(self.panel.close());group.close.assert_called_once()

    def test_unresponsive_ready_renderer_has_bounded_shutdown(self):
        process=Mock();process.poll.return_value=None
        process.wait.side_effect=[embedded.subprocess.TimeoutExpired('renderer',4),0]
        group=Mock();self.panel.session=embedded.Path(self.temp.name)
        self.panel.process=process;self.panel.group=group;self.panel.ready=True
        with patch.object(embedded,'save_json'):
            self.panel.stop();self.assertTrue(self.panel.retiring[0].wait(1))
        group.terminate.assert_called_once();group.close.assert_called_once()

    def test_seek_is_queued_until_the_demo_is_ready(self):
        self.panel.session=embedded.Path(self.temp.name)
        with patch.object(embedded,'save_json') as save:
            self.panel.seek(456)
            self.assertEqual(self.panel.pending_tick,456);save.assert_not_called()
            self.panel.ready=True;self.panel.seek(456)
            self.assertEqual(save.call_args.args[1],{'id':1,'action':'seek','tick':456})

    def test_switching_recordings_reuses_the_owned_renderer(self):
        self.panel.session=embedded.Path(self.temp.name)
        process=Mock();process.poll.return_value=None
        self.panel.process=process;self.panel.ready=True;self.panel.demo='old.dem'
        with patch.object(embedded.launcher,'launch') as launch, patch.object(embedded,'save_json') as save:
            self.panel.start('new.dem')
            launch.assert_not_called();process.terminate.assert_not_called()
            self.assertFalse(self.panel.ready)
            self.assertEqual(save.call_args.args[1]['action'],'load')

    def test_replacement_at_same_path_reloads_instead_of_seeking_old_recording(self):
        self.panel.session=embedded.Path(self.temp.name)
        self.panel.process=Mock()
        self.panel.process.poll.return_value=None
        self.panel.ready=True
        self.panel.demo=str((self.panel.session/'same.dem').resolve())
        self.panel.demo_sha='a'*64
        with patch.object(embedded,'save_json') as save:
            self.panel.start(self.panel.demo,tick=456,demo_sha='b'*64)
        self.assertEqual(save.call_args.args[1]['action'],'load')
        self.assertEqual(self.panel.demo_sha,'b'*64)
        self.assertEqual(self.panel.pending_tick,456)

    def test_startup_failure_produces_a_retryable_message(self):
        with patch.object(embedded.launcher,'find_godot',side_effect=ValueError('Runtime missing')):
            self.panel.start('downloaded.dem')
            self.until(lambda:'Runtime missing' in self.panel.status.get())
        self.assertIsNone(self.panel.process)
        self.assertFalse(self.panel.ready)

    def test_loading_does_not_join_renderer_window_input_queue(self):
        self.panel.session=embedded.Path(self.temp.name)
        process=Mock();process.poll.return_value=None
        self.panel.process=process;self.panel.child=Mock();self.panel.child.valid.return_value=False
        with patch.object(embedded,'read_json',side_effect=lambda path,default:{} if path.name=='request.json' else {'sequence':1,'state':'loading','message':'Preparing shaders'}):
            self.panel.poll()
        self.panel.child.find.assert_not_called()
        self.assertFalse(self.panel.ready)

    def test_ready_waits_for_asynchronous_window_attachment(self):
        self.panel.session=embedded.Path(self.temp.name)
        process=Mock();process.poll.return_value=None
        self.panel.process=process;self.panel.child=Mock();self.panel.child.valid.return_value=False;self.panel.child.find.return_value=False
        with patch.object(embedded,'read_json',side_effect=lambda path,default:{} if path.name=='request.json' else {'sequence':1,'state':'ready'}):
            self.panel.poll()
        self.assertIs(self.panel.process,process)
        self.assertEqual(self.panel.last_sequence,-1)
        self.assertFalse(self.panel.ready)

    def test_map_warning_does_not_grant_or_start_preparation(self):
        with patch.object(embedded.map_setup,'approve') as approve:
            self.panel.show_map_setup({'map':'de_overpass','label':'Overpass','in_pool':False})
            self.root.update_idletasks()
            self.assertIn('outside your selected',self.panel.status.get())
            self.assertTrue(self.panel.map_warning.winfo_manager())
            approve.assert_not_called()
            self.assertIsNone(self.panel.process)
            self.panel.stop()
            self.assertIsNone(self.panel.map_setup_request)
            self.assertFalse(self.panel.map_warning.winfo_manager())

    def test_only_prepare_button_grants_the_displayed_map(self):
        self.panel.show_map_setup({'map':'de_overpass','label':'Overpass','in_pool':False,'fingerprint':'revision'})
        finished=threading.Event()
        with patch.object(embedded.map_setup,'approve',side_effect=lambda *args:finished.set()) as approve, \
             patch.object(embedded.map_setup,'configured_game',return_value='installed-game'):
            self.panel.map_prepare_button.invoke()
            self.assertTrue(finished.wait(1))
            self.assertEqual(approve.call_args.args,('installed-game',self.panel.map_setup_request))

    def test_hidden_playback_pauses_after_a_pending_seek_is_acknowledged(self):
        self.panel.session=embedded.Path(self.temp.name);self.panel.ready=True
        self.panel.command_sequence=5;self.panel.command_ack=4
        with patch.object(embedded,'save_json') as save:
            self.panel.pause_when_hidden();self.assertTrue(self.panel.pending_pause);save.assert_not_called()
            process=Mock();process.poll.return_value=None;self.panel.process=process;self.panel.child=Mock()
            with patch.object(embedded,'read_json',side_effect=lambda path,default:{} if path.name=='request.json' else {'sequence':1,'state':'ready','command_ack':5}):
                self.panel.poll()
            self.assertFalse(self.panel.pending_pause)
            self.assertEqual(save.call_args.args[1],{'id':6,'action':'pause'})


if __name__=='__main__':unittest.main()
