import json
from pathlib import Path
import tempfile
import unittest
from resume_analysis import can_resume_core


class ResumeGuardTests(unittest.TestCase):
    def test_only_verified_matching_interrupted_core_can_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary);(folder/'viewer_v8').mkdir()
            def put(name, value):
                (folder/name).write_text(json.dumps(value))
            put('match_summary.json', {'valid': True, 'viewer_entities_v8': {'demo_sha256': 'expected'}})
            put('integrity_checks.json', {'integrity_ok': True})
            put('viewer_v8/entity_meta.json', {'demo_sha256': 'expected', 'sampleHz': 16})
            self.assertTrue(can_resume_core(folder, 'expected', 16))
            self.assertFalse(can_resume_core(folder, 'other-demo', 16))
            self.assertFalse(can_resume_core(folder, 'expected', 32))
            put('analysis_run.json', {'success_count': 1})
            self.assertFalse(can_resume_core(folder, 'expected', 16))
            (folder/'analysis_run.json').unlink()
            put('integrity_checks.json', {'integrity_ok': False})
            self.assertFalse(can_resume_core(folder, 'expected', 16))

    def test_unknown_existing_folder_is_not_adopted(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertFalse(can_resume_core(Path(temporary), 'expected', 16))


if __name__ == '__main__':
    unittest.main()
