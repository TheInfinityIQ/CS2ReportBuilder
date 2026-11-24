"""Recorded utility identity, interpolation and lifetime regressions."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'extractor/.deps'))
import pandas as pd
import grenades


class GrenadeTests(unittest.TestCase):
    def meta(self): return {'info': {'ticks': 3000, 'tickrate': 64}}

    def table(self, points):
        return pd.DataFrame([{'grenade_entity_id': 15, 'grenade_type': 'CSmokeGrenadeProjectile',
                              'steamid': 76561198000000001, 'tick': tick, 'x': x, 'y': 0, 'z': 10}
                             for tick, x in points])

    def test_recycled_entity_is_two_throws_with_separate_expiry(self):
        g = self.table([(100, 1), (101, 2), (102, 3), (900, 4), (901, 5)])
        tables = {'smokegrenade_detonate': pd.DataFrame([
            {'tick': 103, 'entityid': 15, 'x': 3, 'y': 0, 'z': 10},
            {'tick': 902, 'entityid': 15, 'x': 5, 'y': 0, 'z': 10}]),
            'smokegrenade_expired': pd.DataFrame([{'tick': 600, 'entityid': 15}, {'tick': 1900, 'entityid': 15}])}
        result = grenades.reconstruct(g, tables, self.meta())
        self.assertEqual(len(result['throws']), 2)
        self.assertEqual([e['end'] for e in result['effects']], [600, 1900])
        self.assertEqual([e['end'] for e in result['throws']], [103, 902])
        self.assertNotEqual(result['throws'][0]['id'], result['throws'][1]['id'])
        self.assertEqual(result['throws'][0]['owner'], '76561198000000001')

    def test_round_reset_caps_effect_and_blindness(self):
        tables = {'smokegrenade_detonate': pd.DataFrame([{'tick': 103, 'entityid': 15, 'x': 3, 'y': 0, 'z': 10}]),
                  'round_start': pd.DataFrame([{'tick': 1}, {'tick': 200}]),
                  'player_blind': pd.DataFrame([{'tick': 199, 'blind_duration': 4, 'user_steamid': 'player'}])}
        result = grenades.reconstruct(self.table([(100, 1), (101, 2)]), tables, self.meta())
        self.assertEqual(result['effects'][0]['end'], 200)
        self.assertEqual(result['blinds'][0]['end'], 200)

    def test_fire_join_uses_owner_location_and_ct_weapon(self):
        g = self.table([(100, 1), (101, 2)]); g['grenade_type'] = 'CMolotovProjectile'
        tables = {'weapon_fire': pd.DataFrame([{'tick': 94, 'user_steamid': '76561198000000001', 'weapon': 'weapon_incgrenade'}]),
                  'inferno_startburn': pd.DataFrame([
                      {'tick': 103, 'entityid': 18, 'user_steamid': 'other', 'x': 500, 'y': 0, 'z': 10},
                      {'tick': 102, 'entityid': 20, 'user_steamid': '76561198000000001', 'x': 2, 'y': 0, 'z': 10}])}
        result = grenades.reconstruct(g, tables, self.meta())
        self.assertEqual(result['throws'][0]['kind'], 'incendiary')
        self.assertEqual(result['throws'][0]['effect'], 'fire:20:102')

    def test_stationary_smoke_samples_stop_at_detonation(self):
        tables = {'smokegrenade_detonate': pd.DataFrame([{'tick': 103, 'entityid': 15, 'x': 3, 'y': 0, 'z': 10}])}
        g = self.table([(tick, min(tick-99, 3)) for tick in range(100, 600)])
        result = grenades.reconstruct(g, tables, self.meta())
        self.assertEqual(result['throws'][0]['path'][-1][0], 103)
        self.assertEqual(result['throws'][0]['end'], 103)

    def test_empty_utility_demo_does_not_block_playback(self):
        result = grenades.reconstruct(pd.DataFrame(), {}, self.meta())
        self.assertEqual(result['throws'], [])
        self.assertEqual(result['effects'], [])

    def test_contact_cue_follows_a_recorded_bounce_without_added_motion(self):
        g = self.table([(100,0),(101,10),(102,20),(103,15),(104,10)])
        result = grenades.reconstruct(g, {}, self.meta())
        cues = [e for e in result['audio'] if e['sound']=='grenade:bounce']
        self.assertEqual([c['tick'] for c in cues], [102])
        self.assertEqual(cues[0]['position'], [20,0,10])

    def test_geometry_updates_extinguish_and_remove_without_leak(self):
        base = grenades.ROOT/'data/.desktop/standalone3d/test-fixtures'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            p = Path(tmp)/'inferno_patches.jsonl.gz'
            records = [{'id': '42', 'tick': 104, 'action': 'upsert',
                        'state': {'entityIndex': 12, 'x': 1, 'y': 0, 'z': 10,
                                  'patches': [{'x': 1, 'y': 0, 'z': 10, 'burning': True},
                                              {'x': 2, 'y': 0, 'z': 10, 'burning': False}]}},
                       {'id': '42', 'tick': 150, 'action': 'removed'}]
            with gzip.open(p, 'wt') as stream:
                for record in records: stream.write(json.dumps(record)+'\n')
            result = {'effects': [{'id': 'fire:12:103', 'entity': 12, 'kind': 'fire', 'start': 103, 'end': 500,
                                   'position': [1, 0, 10], 'frames': [], 'geometry': 'event_approximation'}], 'summary': {}}
            grenades.attach_geometry(result, Path(tmp))
            self.assertEqual(result['effects'][0]['end'], 150)
            self.assertEqual(result['effects'][0]['frames'][0]['patches'], [[1, 0, 10]])
            self.assertEqual(result['summary']['recorded_fire'], 1)

    def test_local_recording_paths_have_no_cross_throw_or_lifetime_leaks(self):
        files = list((grenades.ROOT/'data/.desktop/standalone3d/replays').glob('45c070*_9ae*/grenade_recording.json'))
        if not files: self.skipTest('Local utility fixture not prepared')
        data = json.loads(files[0].read_text())
        self.assertEqual(set(t['kind'] for t in data['throws']), set(grenades.TYPES.values()))
        self.assertEqual(len({t['id'] for t in data['throws']}), len(data['throws']))
        for throw in data['throws']:
            self.assertLess(throw['start'], throw['end'])
            self.assertTrue(all(throw['start'] <= p[0] <= throw['end'] for p in throw['path']))
        self.assertEqual(data['summary']['recorded_fire'], 68)
        self.assertEqual(data['summary']['decoded_smoke'], 72)
        for effect in data['effects']:
            self.assertTrue(all(effect['start'] <= f['tick'] < effect['end'] for f in effect['frames']))

    def test_prepared_utility_reuses_recording_and_updates_art_independently(self):
        base = grenades.ROOT/'data/.desktop/standalone3d/test-fixtures'; base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            folder = Path(tmp); recording = folder/'grenade_recording.json'; recording.write_text('{}')
            model = folder/'model.scn'; model.write_bytes(b'fixture')
            from viewer_entities_v8 import PROJECT
            adapter = grenades.digest(PROJECT.parent/'Program.cs')+':'+grenades.digest(grenades.ROOT/'app/extractor/smoke_voxels_v8.py')
            stock = {'identity': {'pak_index': 'one'}}
            meta = {'sha256': 'demo', 'parser': {'version': 'test'}}
            cached = {'version': grenades.VERSION, 'source': 'demo', 'parser': meta['parser'],
                      'entity_adapter': adapter, 'recording': str(recording), 'bytes':2, 'assets':stock['identity'],
                      'models':{'smoke':str(model)}, 'sounds':{}}
            grenades.save(folder/'grenades.json', cached)
            parser = Mock()
            self.assertEqual(grenades.prepare_grenades(parser,meta,folder,None,stock,Mock()), cached)
            parser.parse_grenades.assert_not_called(); parser.parse_events.assert_not_called()
            stock['identity'] = {'pak_index':'two'}
            with patch.object(grenades,'prepare_models',return_value={'smoke':str(model)}) as models, \
                 patch.object(grenades,'prepare_sounds',return_value={}):
                result = grenades.prepare_grenades(parser,meta,folder,None,stock,Mock())
                self.assertEqual(result['assets'],stock['identity']); models.assert_called_once()
            parser.parse_grenades.assert_not_called(); parser.parse_events.assert_not_called()


if __name__ == '__main__': unittest.main()
