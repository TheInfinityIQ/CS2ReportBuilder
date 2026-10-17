import base64
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from viewer_entities_v8 import FILES, extract_entities, round_window, validate_sidecars


class EntityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.v8-test-', dir=Path(__file__).resolve().parent)
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.state = {'id': '32771', 'entityIndex': 3, 'serial': 2,
                      'x': 12.5, 'y': 2, 'z': 0}
        self.streams = {name: [] for name in FILES}

    def write(self):
        for name, rows in self.streams.items():
            with gzip.open(self.root / name, 'wt') as f:
                for r in rows:
                    f.write(json.dumps(r) + '\n')

    def upsert(self, tick=10, state=None):
        return {'tick': tick, 'id': '32771', 'action': 'upsert', 'state': state or self.state}

    def test_ground_lifecycle_and_entity_serials(self):
        self.streams[FILES[0]] = [self.upsert(), {'tick': 12, 'id': '32771', 'action': 'pickup'}]
        self.write()
        self.assertEqual(validate_sidecars(self.root)['counts'][FILES[0]], 2)
        self.state['serial'] = 3
        self.streams[FILES[0]] = [self.upsert()]
        self.write()
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            validate_sidecars(self.root)

    def test_pickup_without_ground_entity_is_rejected(self):
        self.streams[FILES[0]] = [{'tick': 12, 'id': '32771', 'action': 'pickup'}]
        self.write()
        with self.assertRaisesRegex(ValueError, 'removal without'):
            validate_sidecars(self.root)

    def test_window_and_monotonic_ticks(self):
        self.streams[FILES[0]] = [self.upsert(12), self.upsert(10)]
        self.write()
        with self.assertRaisesRegex(ValueError, 'unordered'):
            validate_sidecars(self.root)
        self.streams[FILES[0]] = [self.upsert(10)]
        self.write()
        with self.assertRaisesRegex(ValueError, 'unordered'):
            validate_sidecars(self.root, start=11)

    def test_smoke_bytes_are_preserved_and_checked(self):
        state = {**self.state, 'voxelBase64': base64.b64encode(b'\x00\xff\x05').decode(), 'payloadBytes': 3}
        self.streams[FILES[2]] = [self.upsert(state=state)]
        self.write()
        self.assertTrue(validate_sidecars(self.root)['passed'])
        state['payloadBytes'] = 2
        self.write()
        with self.assertRaisesRegex(ValueError, 'byte count'):
            validate_sidecars(self.root)

    def test_fire_centers_and_burning_flags(self):
        state = {**self.state, 'fireCount': 2, 'patches': [
            {'index': 0, 'x': 1, 'y': 2, 'z': 3, 'burning': True},
            {'index': 1, 'x': 4, 'y': 5, 'z': 6, 'burning': False}]}
        self.streams[FILES[1]] = [self.upsert(state=state)]
        self.write()
        self.assertTrue(validate_sidecars(self.root)['passed'])
        state['patches'][1]['index'] = 0
        self.write()
        with self.assertRaisesRegex(ValueError, 'indices'):
            validate_sidecars(self.root)

    def test_round_selection(self):
        (self.root / 'rounds.csv').write_text('round,start_tick,freeze_end_tick,end_tick\n3,4,10,30\n')
        self.assertEqual(round_window(self.root, 3), (10, 30))
        with self.assertRaises(ValueError):
            round_window(self.root, 9)

    def test_alignment_records_network_position_difference_and_rejects_clock_shift(self):
        self.streams[FILES[2]] = [self.upsert()]
        self.write()
        events = self.root / 'events'
        events.mkdir()
        path = events / 'smokegrenade_detonate.csv.gz'
        with gzip.open(path, 'wt') as f:
            f.write('tick,x,y\n10,16.2,2\n')
        result = validate_sidecars(self.root, analysis=self.root)
        self.assertEqual(result['alignment']['matched'], 1)
        self.assertAlmostEqual(result['alignment']['maximum_observed_position_delta_units'], 3.7)
        with gzip.open(path, 'wt') as f:
            f.write('tick,x,y\n20,16.2,2\n')
        with self.assertRaisesRegex(ValueError, 'alignment failed'):
            validate_sidecars(self.root, analysis=self.root)

    def test_backend_failure_preserves_existing_sidecars(self):
        demo = self.root / 'sample.dem'
        demo.write_bytes(b'not parsed by the mocked backend')
        destination = self.root / 'viewer_v8'
        destination.mkdir()
        (destination / 'keep.txt').write_text('previous good export')
        with patch('viewer_entities_v8.build_backend'), patch('viewer_entities_v8.subprocess.run', side_effect=RuntimeError('backend failed')):
            with self.assertRaisesRegex(RuntimeError, 'backend failed'):
                extract_entities(demo, destination)
        self.assertEqual((destination / 'keep.txt').read_text(), 'previous good export')

    def test_success_publishes_decoder_report_and_hashes(self):
        demo = self.root / 'sample.dem'
        demo.write_bytes(b'mocked demo')
        destination = self.root / 'viewer_v8'
        def backend(command, **kwargs):
            stage = Path(command[3])
            stage.mkdir()
            for name in FILES:
                with gzip.open(stage / name, 'wt'): pass
            (stage / 'entity_meta.json').write_text(json.dumps({
                'counts': {'loot':0,'fire':0,'smoke':0}, 'capabilities':{}, 'files':list(FILES)}))
        with patch('viewer_entities_v8.build_backend'), patch('viewer_entities_v8.subprocess.run', side_effect=backend):
            meta = extract_entities(demo, destination)
        self.assertTrue(meta['validation']['passed'])
        self.assertEqual(meta['smoke_decoder']['status'], 'unavailable')
        self.assertTrue((destination / 'smoke_voxels.jsonl.gz').exists())
        self.assertEqual(len(meta['file_sha256']), 5)


if __name__ == '__main__':
    unittest.main()
