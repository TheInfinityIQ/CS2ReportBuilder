"""Small validity fixtures for consequential report eligibility and timing rules."""
import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from analyze import analyze_game, date_for, select, ROOT
from build import json_script, opening_summary, verify

IDS = [str(76561198000000000+i) for i in range(10)]


class ReportingTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'reports').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'reports')
        self.addCleanup(self.temp.cleanup)
        self.analysis = Path(self.temp.name)
        self.folder = self.analysis/'sample'
        (self.folder/'events').mkdir(parents=True)
        self.entry = dict(source='sample', sha='abc', game='abc', name='Analysis_Oct-02-2026', date='2026-10-02', date_basis='fixture',map='de_mirage')
        for name, value in {
            'match_summary.json':dict(valid=True, coaching_valid=True, round_table_valid=True,contains_full_match_likely=True,tickrate=64),
            'integrity_checks.json':dict(integrity_ok=True,warnings=[]),
            'source_capabilities.json':dict(event_streams={'player_death':dict(parsed=True)}),
            'viewer_tracks_meta.json':dict(demo_sha256='abc')}.items():
            (self.folder/name).write_text(json.dumps(value))
        self.csv('rounds.csv',[dict(round=1,start_tick=0,freeze_end_tick=100,end_tick=1000,winner='T',round_observation_complete='True')])
        self.roster('CT')
        self.deaths([dict(tick=200,user_steamid=IDS[5],attacker_steamid=IDS[0]),dict(tick=264,user_steamid=IDS[0],attacker_steamid=IDS[6])])

    def csv(self,name,values):
        with (self.folder/name).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(values[0]));writer.writeheader();writer.writerows(values)

    def roster(self,own):
        self.csv('player_rounds.csv',[dict(round=1,steamid=sid,side=(own if i<5 else 'T' if own=='CT' else 'CT'),result='WIN' if (own=='T' if i<5 else own!='T') else 'LOSS') for i,sid in enumerate(IDS)])

    def deaths(self,values):
        with gzip.open(self.folder/'events/player_death.csv.gz','wt',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(values[0]));writer.writeheader();writer.writerows(values)

    def catalog(self):
        return dict(version=3,analysis=str(self.analysis),entries=[self.entry],targets=[dict(steamid=IDS[0],games=['sample'],name='Player')])

    def test_tick_interval_and_halftime_side_from_each_round(self):
        g=analyze_game(self.entry,self.analysis,IDS[0]);r=g['rounds'][0]
        self.assertEqual(r['opening'],'kill');self.assertEqual(r['death']['before'],[5,4]);self.assertFalse(r['win'])
        self.assertEqual(opening_summary(dict(target={'steamid':IDS[0]},games=[g])),dict(total=1,within2=1,twoToTen=0,later=0,survived=0))
        self.roster('T');r=analyze_game(self.entry,self.analysis,IDS[0])['rounds'][0]
        self.assertEqual(r['side'],'T');self.assertTrue(r['win']);self.assertEqual(r['death']['before'],[5,4])

    def test_missing_stream_is_excluded_not_zero(self):
        (self.folder/'source_capabilities.json').write_text('{"event_streams":{"player_death":{"parsed":false}}}')
        with self.assertRaisesRegex(ValueError,'No eligible'):select(self.catalog(),IDS[0],50)

    def test_cap_and_recording_deduplication(self):
        with self.assertRaisesRegex(ValueError,'1–50'):select(self.catalog(),IDS[0],51)
        c=self.catalog();c['entries'].append(dict(self.entry));_,games,exclusions=select(c,IDS[0],50)
        self.assertEqual(len(games),1);self.assertEqual(len(exclusions),1)

    def test_missing_attacker_column_is_not_zero_kills(self):
        self.deaths([dict(tick=200,user_steamid=IDS[5])])
        with self.assertRaisesRegex(ValueError,'Required CSV'):analyze_game(self.entry,self.analysis,IDS[0])

    def test_simultaneous_first_events_are_unknown(self):
        self.deaths([dict(tick=200,user_steamid=IDS[5],attacker_steamid=IDS[0]),dict(tick=200,user_steamid=IDS[0],attacker_steamid=IDS[6])])
        self.assertEqual(analyze_game(self.entry,self.analysis,IDS[0])['rounds'][0]['opening'],'unknown')

    def test_duplicate_deaths_withhold_round(self):
        self.deaths([dict(tick=200,user_steamid=IDS[5],attacker_steamid=IDS[0]),dict(tick=201,user_steamid=IDS[5],attacker_steamid=IDS[0])])
        g=analyze_game(self.entry,self.analysis,IDS[0]);self.assertFalse(g['rounds']);self.assertEqual(len(g['excluded_rounds']),1)

    def test_input_change_blocks_rebuild(self):
        g=analyze_game(self.entry,self.analysis,IDS[0]);s=dict(version='1.0',analysis=str(self.analysis),games=[g]);verify(s)
        (self.folder/'rounds.csv').write_text('changed')
        with self.assertRaisesRegex(ValueError,'Evidence input changed'):verify(s)

    def test_bad_date_and_embedded_script_escaping(self):
        self.assertEqual(date_for(dict(name='Analysis_Oct-99-2026')),(None,None))
        self.assertNotIn('<',json_script({'text':'</script><script>alert(1)</script>'}))


if __name__=='__main__':unittest.main()
