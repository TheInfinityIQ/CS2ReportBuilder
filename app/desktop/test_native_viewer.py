import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_viewer as native


class NativeViewerTests(unittest.TestCase):
    def setUp(self):
        base = native.STATE/'native-viewer-tests'; base.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=base); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.game = self.root/'Steam/steamapps/common/CS2/game'
        (self.game/'bin/win64').mkdir(parents=True); (self.game/'csgo/cfg').mkdir(parents=True)
        (self.game/'bin/win64/cs2.exe').write_bytes(b'game')
        (self.game/'bin/win64/engine2.dll').write_bytes(b'engine')
        (self.game/'csgo/steam.inf').write_text('PatchVersion=1.2.3\nClientVersion=123\n')
        self.manifest = self.game.parents[2]/'appmanifest_730.acf'
        self.write_manifest('100')

    def write_manifest(self, build, flags='4'):
        self.manifest.write_text('"AppState" { "appid" "730" "buildid" "'+build+'" "StateFlags" "'+flags+'" '
                                 '"InstalledDepots" { "2347770" { "manifest" "18446744073709551615" } } }')

    def test_inspection_is_read_only_and_identifiers_stay_strings(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        profile = native.runtime_profile(self.game)
        self.assertEqual(profile['build'], '100')
        self.assertEqual(profile['depots']['2347770'], '18446744073709551615')
        self.assertEqual(profile['automatic_launch'], 'unverified')
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_unchanged_installation_reuses_binary_hashes(self):
        profile = native.runtime_profile(self.game)
        with patch.object(native, 'checksum', side_effect=AssertionError('unnecessary binary read')):
            self.assertEqual(profile['fingerprint'], native.runtime_profile(self.game, previous=profile)['fingerprint'])

    def test_changed_build_keeps_previous_profile_and_invalidates_controls(self):
        store = self.root/'toolbox/profiles.json'
        old, changed = native.observe_runtime(self.game, store)
        self.assertFalse(changed)
        self.write_manifest('101')
        new, changed = native.observe_runtime(self.game, store)
        self.assertTrue(changed); self.assertNotEqual(old['fingerprint'], new['fingerprint'])
        self.assertEqual(new['controls'], 'unverified')
        self.assertEqual(len(json.loads(store.read_text())['profiles']), 2)

    def test_binary_change_changes_profile_even_without_build_id_change(self):
        old = native.runtime_profile(self.game)
        (self.game/'bin/win64/engine2.dll').write_bytes(b'new engine')
        self.assertNotEqual(old['fingerprint'], native.runtime_profile(self.game, previous=old)['fingerprint'])

    def test_corrupt_runtime_history_is_preserved(self):
        store = self.root/'profiles.json'; store.write_text('{ broken history')
        with self.assertRaisesRegex(ValueError, 'preserved'): native.observe_runtime(self.game, store)
        self.assertEqual(store.read_text(), '{ broken history')

    def test_incomplete_update_is_not_ready(self):
        self.write_manifest('100', '1026')
        with self.assertRaisesRegex(ValueError, 'not ready'): native.runtime_profile(self.game)

    def test_completed_download_counters_do_not_block_ready_installation(self):
        text = self.manifest.read_text().replace('"InstalledDepots"',
            '"BytesToDownload" "42" "BytesDownloaded" "42" "BytesToStage" "365" "BytesStaged" "365" "InstalledDepots"')
        self.manifest.write_text(text)
        self.assertEqual(native.runtime_profile(self.game)['build'], '100')
        self.manifest.write_text(text.replace('"BytesStaged" "365"', '"BytesStaged" "364"'))
        with self.assertRaisesRegex(ValueError, 'not ready'): native.runtime_profile(self.game)

    def test_manifest_change_during_inspection_is_rejected(self):
        original = native.checksum
        def moving(path):
            self.write_manifest('101')
            return original(path)
        with patch.object(native, 'checksum', side_effect=moving):
            with self.assertRaisesRegex(ValueError, 'changed the installation'): native.runtime_profile(self.game)

    def test_saved_settings_add_change_and_delete_detected_without_restoring(self):
        cfg = self.game/'csgo/cfg/user.vcfg'; cfg.write_text('sensitivity 1')
        guard = native.SettingsGuard(self.game, roots=[cfg.parent])
        self.assertFalse(guard.check())
        cfg.write_text('sensitivity 2')
        self.assertIn(str(cfg), guard.check()); self.assertEqual(cfg.read_text(), 'sensitivity 2')
        cfg.unlink(); self.assertIn(str(cfg), guard.check())
        new = cfg.with_name('video.txt'); new.write_text('resolution 1280 960')
        self.assertIn(str(new), guard.check()); self.assertTrue(new.is_file())

    def test_settings_hash_only_and_unrelated_logs_excluded(self):
        cfg = self.game/'csgo/cfg'; (cfg/'user.vcfg').write_text('private preference')
        guard = native.SettingsGuard(self.game, roots=[cfg])
        self.assertNotIn('private preference', json.dumps(guard.before))
        (cfg/'console.log').write_text('changed log'); self.assertFalse(guard.check())

    def test_new_user_config_is_detected(self):
        guard = native.SettingsGuard(self.game)
        cfg = self.root/'Steam/userdata/123/730/local/cfg'
        cfg.mkdir(parents=True); (cfg/'cs2_video.txt').write_text('new video')
        self.assertTrue(guard.check())

    def test_inaccessible_settings_fail_instead_of_claiming_clean(self):
        cfg = self.game/'csgo/cfg/user.vcfg'; cfg.write_text('x')
        with patch.object(native, 'checksum', side_effect=PermissionError('unreadable')):
            with self.assertRaises(PermissionError): native.SettingsGuard(self.game, roots=[cfg.parent])

    def test_unverified_launch_cannot_be_enabled_by_saved_profile(self):
        with self.assertRaisesRegex(ValueError, 'settings preservation'): native.require_verified_launch(self.game)

    def test_native_build_manifest_cannot_escape_build_directory_or_use_old_abi(self):
        build = self.root/'build'; build.mkdir()
        payload = build/'v_1/capture.dll'; payload.parent.mkdir(); payload.write_bytes(b'fixture')
        with patch.object(native, 'BUILD', build):
            (build/'current.json').write_text(json.dumps({'dll': 'v_1/capture.dll', 'abi': 2}))
            self.assertEqual(native.capture_library(), payload.resolve())
            (self.root/'outside.dll').write_bytes(b'outside')
            for path, abi in [('../outside.dll', 2), ('v_1/capture.dll', 1)]:
                (build/'current.json').write_text(json.dumps({'dll': path, 'abi': abi}))
                with self.assertRaisesRegex(ValueError, 'successful build'): native.capture_library()

    def test_manifest_parser_rejects_duplicate_keys_and_incomplete_input(self):
        for text in ['"AppState" { "a" "1" "a" "2" }', '"AppState" {', '}']:
            with self.assertRaises(ValueError): native.parse_vdf(text)


if __name__ == '__main__': unittest.main()
