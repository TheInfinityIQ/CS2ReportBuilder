import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

import review_model as model
from viewer_service import selected_url


class ReviewTests(unittest.TestCase):
    def setUp(self):
        base=model.ROOT/'data/.desktop/tests';base.mkdir(parents=True,exist_ok=True)
        temp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.entry=dict(sha='a'*64,source='Tournament/map/part2',title='Alpha vs Beta',map='de_ancient',folder=self.root,
                        search='alpha beta renamed_player 76561198000000001 tournament',game='series:map')
        (self.root/'events').mkdir()
        (self.root/'viewer_tracks_meta.json').write_text(json.dumps({'demo_sha256':self.entry['sha'],'tickrate':64}))
        rounds=[dict(round=13,start_tick=100,freeze_end_tick=200,end_tick=1000,ct_score_before=6,t_score_before=6,ct_team_clan_name='Alpha',t_team_clan_name='Beta',winner='CT',round_observation_complete='True'),
                dict(round=14,start_tick=1100,freeze_end_tick=1200,end_tick=2000,ct_score_before=7,t_score_before=6,ct_team_clan_name='Beta',t_team_clan_name='Alpha',winner='T',round_observation_complete='True')]
        with (self.root/'rounds.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rounds[0]));w.writeheader();w.writerows(rounds)
        with gzip.open(self.root/'events/player_death.csv.gz','wt',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['tick','user_name','attacker_name','user_steamid','attacker_steamid','weapon']);w.writeheader()
            w.writerow(dict(tick=500,user_name='B',attacker_name='A',user_steamid='2',attacker_steamid='1',weapon='ak47'))
            w.writerow(dict(tick=1500,user_name='A',attacker_name='B',user_steamid='1',attacker_steamid='2'))

    def test_search_keeps_steam_id_exact_and_requires_each_term(self):
        self.assertEqual(model.filter_library([self.entry],'renamed_player 76561198000000001','de_ancient'),[self.entry])
        self.assertEqual(model.filter_library([self.entry],'Alpha nonexistent'),[])
        self.assertEqual(model.filter_library([self.entry],'Alpha','de_mirage'),[])

    def test_continued_rounds_sides_event_alignment_and_context_clipping(self):
        match=model.load_match(self.entry)
        self.assertEqual([r['number'] for r in match['rounds']],[13,14])
        self.assertEqual(match['rounds'][1]['ct'],'Beta')
        self.assertEqual([e['round'] for e in match['events']],[13,14])
        self.assertEqual(model.event_target(match,match['events'][0],3),308)
        self.assertEqual(model.event_target(match,match['events'][0],30),100)
        self.assertEqual(model.event_target(match,match['events'][0],0),500)
        for lead in ('nan',-1,31):
            with self.assertRaises(ValueError):model.event_target(match,match['events'][0],lead)
        self.assertEqual(len(match['missing']),3)
        self.assertEqual(len(model.event_filter(match['events'],14,'Kills','1')),1)
        self.assertEqual(model.event_filter(match['events'],kind='Bomb events'),[])

    def test_changed_analysis_rejected(self):
        (self.root/'viewer_tracks_meta.json').write_text('{"demo_sha256":"different","tickrate":64}')
        with self.assertRaisesRegex(ValueError,'analysis changed'):model.load_match(self.entry)

    def test_saved_moments_survive_folder_renames_and_update_without_duplication(self):
        store=model.Moments(self.root/'moments.json')
        a=store.save(self.entry,500,13,'Review opening')
        b=store.save({**self.entry,'source':'Moved/map/match'},500,13,'Updated coaching note')
        self.assertEqual(a['id'],b['id']);self.assertEqual(len(store.read()),1)
        self.assertEqual(store.read()[0]['sha'],self.entry['sha'])
        store.save(self.entry,1500,14,'Second moment');store.remove(a['id'])
        self.assertEqual([v['tick'] for v in store.read()],[1500])

    def test_corrupt_notes_never_overwritten(self):
        path=self.root/'moments.json';path.write_text('{invalid')
        store=model.Moments(path)
        with self.assertRaises(ValueError):store.save(self.entry,500,13,'Note')
        self.assertEqual(path.read_text(),'{invalid')
        path.write_text('[{"id":"x","sha":"a","tick":5,"note":"incomplete"}]')
        with self.assertRaisesRegex(ValueError,'unreadable'):store.read()

    def test_companion_link_preserves_source_round_and_native_tick(self):
        url=selected_url('http://127.0.0.1:8766/modules/viewer2d/',dict(source='Tournament/map/[13-9] a & b',round=13,tick=45000))
        query=parse_qs(urlsplit(url).query)
        self.assertEqual(query,dict(source=['Tournament/map/[13-9] a & b'],round=['13'],tick=['45000']))


if __name__=='__main__':unittest.main()
