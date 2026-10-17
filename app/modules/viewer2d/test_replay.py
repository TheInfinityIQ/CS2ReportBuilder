import unittest
import gzip
import json
import tempfile
from pathlib import Path
from replay import build_replay, safe_source, ANALYSIS, entity_window, load_entities, build_shots


class ShotTests(unittest.TestCase):
    def fire(self, tick=10, shooter='a'):
        return {'kind':'fire_bullets','tick':tick,'user_steamid':shooter,'origin_x':1,'origin_y':2,'origin_z':3}

    def test_missing_impacts_never_fabricate_an_endpoint(self):
        shots=build_shots([self.fire(),{'kind':'weapon_fire','tick':10,'user_steamid':'a','weapon':'ak47','user_X':1,'user_Y':2,'user_Z':0,'user_yaw':180}])
        self.assertEqual(len(shots),1)
        self.assertIsNone(shots[0]['impact'])
        self.assertEqual(shots[0]['origin'],[1,2,3])

    def test_impacts_match_shooter_and_time_and_keep_multiple_endpoints(self):
        events=[self.fire(),self.fire(shooter='b')]
        for x in (100,200):events.append({'kind':'bullet_impact','tick':11,'user_steamid':'a','x':x,'y':4,'z':5})
        events.append({'kind':'bullet_impact','tick':30,'user_steamid':'b','x':900,'y':4,'z':5})
        shots=build_shots(events)
        self.assertEqual([s['impact'][0] for s in shots if s['impact']],[100,200])
        self.assertEqual(len(shots),3)
        self.assertIsNone(next(s for s in shots if s['shooter']=='b')['impact'])

    def test_grenades_and_invalid_origins_are_not_gunshots(self):
        self.assertEqual(build_shots([{'kind':'weapon_fire','tick':10,'weapon':'weapon_molotov','user_X':1,'user_Y':2,'user_Z':3},
                                      {**self.fire(),'origin_x':'nan'}]),[])


class EntityWindowTests(unittest.TestCase):
    def test_boundary_state_and_no_future_leakage(self):
        rows = [{'tick':1,'id':'a','action':'upsert','state':{'x':1}},
                {'tick':2,'id':'b','action':'upsert','state':{'x':2}},
                {'tick':3,'id':'b','action':'removed'},
                {'tick':15,'id':'a','action':'removed'},
                {'tick':25,'id':'c','action':'upsert','state':{'x':3}}]
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            path = Path(temp)/'stream.gz'
            with gzip.open(path,'wt') as f:
                f.writelines(json.dumps(r)+'\n' for r in rows)
            self.assertEqual(entity_window(path,10,20),[
                {'tick':10,'id':'a','action':'upsert','state':{'x':1}},rows[3]])

    def test_different_demo_and_incomplete_coverage_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            folder=Path(temp)
            meta={'validation':{'passed':True},'demo_sha256':'one','startTick':5,'endTick':15}
            (folder/'entity_meta.json').write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError,'different demo'):
                load_entities(folder,5,15,'two')
            with self.assertRaisesRegex(ValueError,'cover this round'):
                load_entities(folder,5,16,'one')


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = 'analyzed_CanadianIQ_demos/CanadianIQ_09-17-2026_0dot78_Ancient_LOSS'
        if not (ANALYSIS / cls.source).exists():
            raise unittest.SkipTest('Local analysis fixture is not installed.')
        cls.replay = build_replay(cls.source, 24)

    def test_round_boundaries_identity_and_teams(self):
        r = self.replay
        self.assertEqual(len(r['players']), 10)
        self.assertEqual({p['side'] for p in r['players']}, {'CT', 'T'})
        self.assertTrue(all(isinstance(p['id'], str) and len(p['id']) == 17 for p in r['players']))
        self.assertTrue(all(r['start'] <= t[0] <= r['end'] for p in r['players'] for t in p['track']))
        self.assertTrue(all(r['start'] <= e['tick'] <= r['end'] for e in r['events']))

    def test_rich_real_round_and_sorted_streams(self):
        r = self.replay
        self.assertTrue({'he', 'smoke', 'fire', 'flash'}.issubset({g['kind'] for g in r['grenades']}))
        self.assertIn('player_blind', {e['kind'] for e in r['events']})
        self.assertIn('bomb_planted', {e['kind'] for e in r['events']})
        self.assertTrue(any(t[6] & 1 for p in r['players'] for t in p['track']))
        self.assertTrue(any(t[6] & 8 for p in r['players'] for t in p['track']))
        for p in r['players']:
            self.assertEqual([s['tick'] for s in p['states']], sorted(s['tick'] for s in p['states']))
            self.assertTrue(p['track'])

    def test_analysis_path_cannot_escape(self):
        with self.assertRaises(ValueError):
            safe_source('../../app')
        with self.assertRaises(ValueError):
            build_replay(self.source, 999)


if __name__ == '__main__':
    unittest.main()
