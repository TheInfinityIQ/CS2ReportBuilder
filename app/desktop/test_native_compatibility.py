import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_compatibility as compatibility
import native_viewer as native


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        base = native.STATE/'native-compatibility-tests'; base.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=base); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.video = self.root/'video.txt'; self.video.write_text('original video')
        self.dll = self.root/'capture.dll'; self.dll.write_bytes(b'capture-v2')
        self.store = self.root/'compatibility.json'
        p = patch.object(native, 'capture_library', return_value=self.dll); p.start(); self.addCleanup(p.stop)
        self.runtime = {'fingerprint': 'known-engine'}

    def test_only_the_verified_engine_capture_and_video_combination_is_allowed(self):
        with self.assertRaisesRegex(ValueError, 'compatibility check'):
            compatibility.require_verified(self.runtime, self.video, store=self.store)
        key, _ = compatibility.signature(self.runtime, self.video)
        self.store.write_text(json.dumps({'version': 1, 'profiles': {key: {'verified': True}}}))
        compatibility.require_verified(self.runtime, self.video, store=self.store)
        with self.assertRaises(ValueError):
            compatibility.require_verified({'fingerprint': 'updated-engine'}, self.video, store=self.store)
        self.video.write_text('new video preferences')
        with self.assertRaises(ValueError): compatibility.require_verified(self.runtime, self.video, store=self.store)
        self.video.write_text('original video'); self.dll.write_bytes(b'rebuilt-capture')
        with self.assertRaises(ValueError): compatibility.require_verified(self.runtime, self.video, store=self.store)

    def test_incomplete_or_failed_smoke_test_cannot_enable_playback(self):
        with self.assertRaisesRegex(ValueError, 'every managed-rendering'):
            compatibility.record_smoke({'ok': True, 'frames': 1000}, store=self.store)
        self.assertFalse(self.store.exists())

    def test_malformed_compatibility_data_fails_closed(self):
        for value in [[], {'version':1,'profiles':[]}]:
            self.store.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'compatibility check'):
                compatibility.require_verified(self.runtime, self.video, store=self.store)


if __name__ == '__main__': unittest.main()
