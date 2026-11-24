from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

import native_security as security
import native_viewer as native


class SecurityTests(unittest.TestCase):
    def setUp(self):
        base = native.STATE/'native-security-tests'; base.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=base); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.cfg = self.root/'cfg'; self.cfg.mkdir()
        (self.cfg/'cs2_video.txt').write_text('"setting.defaultres" "1920" "setting.defaultresheight" "1080" '
            '"setting.fullscreen" "0" "setting.nowindowborder" "1"')
        (self.cfg/'cs2_user_keys.vcfg').write_text('original bindings')

    def test_read_lease_blocks_write_delete_and_replace_but_allows_reads(self):
        path = self.cfg/'cs2_user_keys.vcfg'
        with security.SettingsLease(roots=[self.cfg]) as lease:
            self.assertEqual(path.read_text(), 'original bindings')
            with self.assertRaises(OSError): path.write_text('changed')
            with self.assertRaises(OSError): path.unlink()
            replacement = self.root/'replacement.vcfg'; replacement.write_text('replacement')
            with self.assertRaises(OSError): replacement.replace(path)
            self.assertFalse(lease.changes())
        path.write_text('released'); self.assertEqual(path.read_text(), 'released')

    def test_private_copy_retains_exact_preferences_and_does_not_edit_parent_environment(self):
        before = dict(os.environ); hashes = native.settings_snapshot([self.cfg])
        profile = security.private_profile(self.cfg, base=self.root/'sessions')
        self.assertEqual(os.environ, before)
        self.assertEqual(native.settings_snapshot([self.cfg]), hashes)
        copied = profile['usr_local']/'cfg'
        for path in self.cfg.iterdir(): self.assertEqual((copied/path.name).read_bytes(), path.read_bytes())
        self.assertEqual(profile['display']['setting.defaultres'], 1920)
        self.assertEqual(profile['env']['USRLOCALCSGO'], str(profile['usr_local']))

    def test_exclusive_fullscreen_is_rejected_without_changing_it(self):
        video = self.cfg/'cs2_video.txt'; video.write_text(video.read_text().replace('"setting.fullscreen" "0"', '"setting.fullscreen" "1"'))
        before = video.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Exclusive fullscreen'):
            security.private_profile(self.cfg, base=self.root/'sessions')
        self.assertEqual(video.read_bytes(), before)


if __name__ == '__main__': unittest.main()
