import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rebuild_all_v8 import plan,run,completed


class RebuildTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent,prefix='.v8-test-')
        self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.demos=self.root/'demos';self.demos.mkdir()
        (self.demos/'one').mkdir();(self.demos/'one/a.dem').write_bytes(b'demo')

    def test_collections_keep_same_named_demos_separate(self):
        (self.demos/'two').mkdir();(self.demos/'two/a.dem').write_bytes(b'other')
        items=plan(self.demos,self.root/'output')
        self.assertEqual(len(items),2)
        self.assertNotEqual(items[0]['output'],items[1]['output'])
        self.assertTrue(all(Path(i['output']).is_relative_to(self.root/'output') for i in items))

    def test_duplicate_stems_in_one_collection_rejected(self):
        (self.demos/'one/nested').mkdir();(self.demos/'one/nested/a.dem').touch()
        with self.assertRaisesRegex(ValueError,'Duplicate'):plan(self.demos,self.root/'output')

    def test_disk_reserve_stops_before_launch(self):
        with patch('rebuild_all_v8.shutil.disk_usage') as space,patch('rebuild_all_v8.subprocess.Popen') as process:
            space.return_value.free=1024**3
            status=run(plan(self.demos,self.root/'output'),self.root/'state')
            process.assert_not_called()
        self.assertEqual(status['status'],'low_disk')
        self.assertEqual(json.loads((self.root/'state/progress.json').read_text())['completed'],0)
        self.assertFalse(completed(self.root/'missing'))


if __name__=='__main__':unittest.main()
