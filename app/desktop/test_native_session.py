from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import subprocess

import native_session as sessions
from native_session import configuration_redirected
import native_viewer as native


class SessionEvidenceTests(unittest.TestCase):
    def test_exact_filesystem_route_is_required_not_an_argument_or_prefix(self):
        path = r'C:\Toolbox\session\profile'
        self.assertTrue(configuration_redirected('[Filesystem] USRLOCAL "C:\\Toolbox\\session\\profile\\"', path))
        self.assertFalse(configuration_redirected('Command line: USRLOCAL=C:\\Toolbox\\session\\profile', path))
        self.assertFalse(configuration_redirected('[Filesystem] USRLOCAL "C:\\Toolbox\\session\\profile-other"', path))
        self.assertFalse(configuration_redirected('[Filesystem] USRLOCAL "C:\\Toolbox\\session\\profile"\n'
                                                 '[Filesystem] USRLOCAL "C:\\Steam\\normal"', path))


class SessionOwnershipTests(unittest.TestCase):
    def setUp(self):
        base = native.STATE/'native-session-tests'; base.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=base); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.demo = self.root/'recording.dem'; self.demo.write_bytes(b'fixture')
        p = patch.object(sessions, 'STATE', self.root); p.start(); self.addCleanup(p.stop)
        p = patch.object(sessions.replays, 'DEFAULT_REPLAYS', self.root); p.start(); self.addCleanup(p.stop)

    def test_existing_game_is_not_closed_or_restarted(self):
        session = sessions.ManagedSession()
        with patch.object(sessions.cs2_jump, 'is_running', return_value=True), patch.object(sessions.subprocess, 'Popen') as start:
            with self.assertRaisesRegex(ValueError, 'already running'): session.start(self.demo)
            start.assert_not_called()
        self.assertFalse((self.root/'native-engine-session.lock').exists())

    def test_demo_outside_replays_is_never_launched(self):
        with patch.object(sessions.replays,'DEFAULT_REPLAYS',self.root/'replays'), \
             patch.object(sessions.subprocess,'Popen') as start:
            with self.assertRaisesRegex(ValueError,'Only downloaded demos in replays'):
                sessions.ManagedSession().start(self.demo)
            start.assert_not_called()

    def test_cancelled_start_never_inspects_or_launches_game(self):
        cancel = Mock(); cancel.is_set.return_value = True
        with patch.object(sessions.cs2_jump,'is_running') as inspect, patch.object(sessions.subprocess,'Popen') as start:
            with self.assertRaisesRegex(ValueError,'cancelled'):
                sessions.ManagedSession().start(self.demo,cancel=cancel)
            inspect.assert_not_called(); start.assert_not_called()

    def test_failed_compatibility_gate_never_launches_and_releases_lease(self):
        lease = Mock(); lease.changes.return_value = []
        with patch.object(sessions.cs2_jump, 'is_running', return_value=False), \
             patch.object(native, 'runtime_profile', return_value={'fingerprint':'unknown'}), \
             patch.object(sessions, 'active_cfg', return_value=self.root), \
             patch.object(sessions, 'SettingsLease', return_value=lease), \
             patch('native_compatibility.require_verified', side_effect=ValueError('compatibility check')), \
             patch.object(sessions.subprocess, 'Popen') as start:
            with self.assertRaisesRegex(ValueError, 'compatibility check'):
                sessions.ManagedSession().start(self.demo)
            start.assert_not_called(); lease.close.assert_called_once_with()
        self.assertFalse((self.root/'native-engine-session.lock').exists())

    def test_stop_uses_only_the_owned_process_group_and_is_idempotent(self):
        session = sessions.ManagedSession(); session.process = Mock(); session.process.poll.return_value = None
        session.job = Mock(); session.job.handle = 1
        session.lease = Mock(); session.lease.changes.return_value = []
        session.stop(); session.stop()
        session.job.terminate.assert_called_once_with(); session.process.terminate.assert_not_called()
        session.lease.close.assert_called_once_with()

    def test_failed_stop_retains_read_only_leases(self):
        session = sessions.ManagedSession(); session.process = Mock(); session.process.poll.return_value = None
        session.process.wait.side_effect = subprocess.TimeoutExpired('owned engine',10)
        session.job = Mock(); session.job.handle = 1; session.lease = Mock()
        with self.assertRaises(subprocess.TimeoutExpired): session.stop()
        self.assertFalse(session.stopped); session.lease.close.assert_not_called(); session.job.close.assert_not_called()

    def test_failure_records_original_exit_and_versions_before_cleanup(self):
        import json
        session=sessions.ManagedSession(game=self.root)
        session.process=Mock();session.process.poll.return_value=-1073741819;session.process.pid=17
        session.profile={'session':self.root};session.before_runtime={'fingerprint':'build-fingerprint'}
        logs=self.root/'logs';logs.mkdir()
        (logs/'engine.log').write_text('Demo is version 14193, client is version 14196.')
        stats=Mock(state=3,error=0,frames=9,width=1920,height=1080,seconds_since_frame=1.)
        message=session.failure_message('engine_exit',stats)
        evidence=json.loads((self.root/'playback-failure.json').read_text())
        self.assertIn('CS2 crashed',message);self.assertIn('14193',message)
        self.assertEqual(evidence['exit_hex'],'0xC0000005')
        self.assertEqual(evidence['capture']['state'],3)
        self.assertEqual(evidence['runtime_fingerprint'],'build-fingerprint')
        session.process.terminate.assert_not_called()


if __name__ == '__main__': unittest.main()
