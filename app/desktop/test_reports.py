import copy
import csv
import gzip
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import reports
from heatmap import aggregate

A, B = '76561198062530225', '76561198000000002'
CAL = dict(scale=1,pos_x=0,pos_y=1024)


class ReportTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(dir=reports.ROOT/'data/.desktop/tests')
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.analysis=self.root/'analysis';self.analysis.mkdir()

    def dataset(self,name='match',sha='a',competition=True,renamed=False):
        folder=self.analysis/name;folder.mkdir()
        documents={
            'viewer_tracks_meta.json':dict(demo_sha256=sha,tickrate=64,sample_hz=16),
            'match_summary.json':dict(valid=True,round_table_valid=True,map_name='de_ancient',
                                      demo_source_family='tournament_sourcetv' if competition else 'faceit'),
            'integrity_checks.json':dict(integrity_ok=True),
            'source_capabilities.json':dict(event_streams=dict(player_death=dict(parsed=True))),
            'header.json':dict(map_name='de_ancient')}
        for file,value in documents.items():(folder/file).write_text(json.dumps(value))
        with gzip.open(folder/'viewer_tracks.csv.gz','wt') as f:f.write('round,steamid,tick,x,y,z\n')
        (folder/'events').mkdir()
        with gzip.open(folder/'events/player_death.csv.gz','wt') as f:f.write('tick,user_steamid\n')
        rounds=[dict(round=1,ct_team_clan_name='Team Alpha',t_team_clan_name='Beta',ct_score_before=0,t_score_before=0)]
        players=[dict(round=1,steamid=A,name='NewName' if renamed else 'OldName',side='CT'),dict(round=1,steamid=B,name='Rival',side='T')]
        for filename,values in [('rounds.csv',rounds),('player_rounds.csv',players)]:
            with (folder/filename).open('w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=list(values[0]));writer.writeheader();writer.writerows(values)
        return folder

    def test_catalog_identity_renames_shared_teams_and_copy_deduplication(self):
        self.dataset();self.dataset('copy',competition=True);self.dataset('second','b',renamed=True)
        self.dataset('pug','c',competition=False)
        c=reports.scan(self.analysis,lambda *_:None)
        self.assertEqual(len(c['entries']),3)
        player=next(t for t in c['targets'] if t['id']=='player:'+A)
        self.assertEqual(player['aliases'],['NewName','OldName'])
        self.assertEqual(len(player['games']),3)
        teams=[t for t in c['targets'] if t['mode']=='team']
        self.assertEqual({t['name'] for t in teams},{'Team Alpha','Beta'})
        self.assertTrue(all(len(t['games'])==2 for t in teams))
        info=reports.entry_identity(next(e for e in c['entries'] if e['team']),teams[1])
        self.assertEqual(info['selected_team'],teams[1]['team_id'])
        self.assertNotEqual(info['opponent'],info['selected_team'])

    def test_invalid_analysis_and_ambiguous_side_membership_are_not_team_reports(self):
        folder=self.dataset()
        with (folder/'player_rounds.csv').open('a') as f:f.write('1,'+A+',OldName,T\n')
        self.dataset('invalid','b')
        (self.analysis/'invalid/integrity_checks.json').write_text('{"integrity_ok":false}')
        c=reports.scan(self.analysis,lambda *_:None)
        self.assertEqual(len(c['skipped']),1)
        self.assertFalse(any(t['mode']=='team' for t in c['targets']))

    def test_build_bundles_assets_and_preserves_existing_report_on_failure(self):
        folder=self.dataset()
        c=reports.scan(self.analysis,lambda *_:None);target=next(t for t in c['targets'] if t['id']=='player:'+A)
        output=self.root/'report.html';request=dict(target=target['id'],sources=target['games'],output=str(output))
        movement=dict(game='a',rate=64,calibration=CAL,rounds=[])
        packet=dict(source='match',round=1,players=[],notes=['</script><script>bad()'])
        with patch.object(reports.Heatmaps,'prepare',return_value=movement),patch.object(reports.replay,'build_replay',return_value=packet):
            result=reports.build(request,c,lambda *_:None)
        text=output.read_text(encoding='utf-8')
        self.assertEqual(result['rounds'],1)
        self.assertIn('data:image/png;base64,',text)
        self.assertNotIn('<script type="module"',text)
        self.assertNotIn('<link rel="stylesheet"',text)
        self.assertIn('installWorker',text)
        original=output.read_bytes()
        with self.assertRaisesRegex(ValueError,'already exists'):
            reports.build(request,c,lambda *_:None)
        request['replace_stamp']=[output.stat().st_size,output.stat().st_mtime_ns]
        (folder/'integrity_checks.json').write_text('{"integrity_ok":false}')
        with self.assertRaisesRegex(ValueError,'changed since selection'):
            reports.build(request,c,lambda *_:None)
        self.assertEqual(output.read_bytes(),original)
        self.assertFalse(list(self.root.glob('*.part')))

    def test_outside_target_and_analysis_output_rejected(self):
        self.dataset();c=reports.scan(self.analysis,lambda *_:None)
        target=next(t for t in c['targets'] if t['mode']=='player')
        request=dict(target=target['id'],sources=['../other'],output=str(self.root/'report.html'))
        with self.assertRaisesRegex(ValueError,'Choose a team/player'):
            reports.build(request,c,lambda *_:None)
        request.update(sources=target['games'],output=str(self.analysis/'report.html'))
        with self.assertRaisesRegex(ValueError,'outside the analysis'):
            reports.build(request,c,lambda *_:None)

    def test_split_recordings_context_coverage_counts_unique_rounds(self):
        self.dataset();c=reports.scan(self.analysis,lambda *_:None)
        target=next(t for t in c['targets'] if t['id']=='player:'+A)
        e=c['entries'][0];other=copy.deepcopy(e);other['source']='part2'
        other['coverage'][A]=['completed-round:0','completed-round:1']
        context=reports.report_context([e,other],target)
        self.assertEqual(len(context['games']),1)
        self.assertEqual(len(context['players']),1)
        self.assertEqual(context['players'][0]['rounds'],2)

    def test_legacy_league_requires_exact_saved_name_and_recorded_rosters(self):
        self.dataset(competition=False)
        match=dict(id='faceit:match-id',source='faceit',teams=['Team Alpha','Beta'],owner='Team Alpha',
                   selected_team_id='persistent-team-id',date='2026-10-01',league_season={'number':59})
        with patch.object(reports,'saved_contexts',return_value=({}, {'match':[match]})):
            c=reports.scan(self.analysis,lambda *_:None)
        target=next(t for t in c['targets'] if t['mode']=='team' and t['name']=='Team Alpha')
        self.assertEqual(target['team_id'],'faceit:team:persistent-team-id')
        self.assertEqual(c['entries'][0]['game'],'faceit:match-id:de_ancient')
        mismatch={**match,'teams':['Unrelated','Beta']}
        with patch.object(reports,'saved_contexts',return_value=({}, {'match':[mismatch]})):
            c=reports.scan(self.analysis,lambda *_:None)
        self.assertFalse(any(t['mode']=='team' for t in c['targets']))

    def test_missing_death_validation_is_replay_only_and_cannot_fake_a_heat_report(self):
        folder=self.dataset();(folder/'source_capabilities.json').unlink()
        c=reports.scan(self.analysis,lambda *_:None)
        self.assertFalse(c['entries'][0]['heat_ready'])
        target=c['targets'][0]
        with self.assertRaisesRegex(ValueError,'Choose games marked Ready'):
            reports.build(dict(target=target['id'],sources=target['games'],output=str(self.root/'report.html')),c,lambda *_:None)


@unittest.skipUnless(shutil.which('node'),'Node is required for browser algorithm parity checks')
class PortableParityTests(unittest.TestCase):
    def test_offline_averages_match_python_reference(self):
        def path(duration=40,offset=0):return [[i/4,offset+4*i,900,0] for i in range(duration*4+1)]
        def rnd(key='1',side='CT',sid=A,track=None):
            return dict(id=key,start=0,end=40,valid=True,deaths_available=True,deaths=[dict(id=B,tick=17.3)],
                        players=[dict(id=sid,side=side,track=path() if track is None else track)])
        first=dict(game='a',rate=1,calibration=CAL,rounds=[rnd(str(i),'CT' if i%2 else 'T') for i in range(28)])
        other=dict(game='b',rate=1,calibration=CAL,rounds=[rnd('1','T',track=path(offset=160)),rnd('2')])
        cases=[]
        for seconds in (1,17,40,120):
            for cutoff in (True,False):
                cases.append(dict(games=[first,other],players=[A],seconds=seconds,cutoff=cutoff,side='both'))
        partial=copy.deepcopy(first);partial['rounds'][0]['players'].append(dict(id=B,side='CT',track=[]))
        stationary=copy.deepcopy(first);stationary['rounds']=[rnd(track=[[i/4,100+i%2,900,0] for i in range(161)])]
        cases += [dict(games=[first,copy.deepcopy(first),other],players=[A],seconds=40,cutoff=True,side='CT'),
                  dict(games=[partial],players=[A,B],seconds=40,cutoff=False,side='both'),
                  dict(games=[stationary],players=[A],seconds=40,cutoff=True,side='both'),
                  dict(games=[first],players=[],seconds=40,cutoff=True,side='both')]
        source="import {aggregate} from "+json.dumps((reports.VIEWER/'portable-heatmap.mjs').as_uri())+";let text='';for await(const chunk of process.stdin)text+=chunk;console.log(JSON.stringify(JSON.parse(text).map(c=>aggregate(c.games,new Set(c.players),c.seconds,c.cutoff,c.side))));"
        run=subprocess.run([shutil.which('node'),'--input-type=module','-e',source],input=json.dumps(cases),text=True,capture_output=True,check=True)
        for case,actual in zip(cases,json.loads(run.stdout)):
            expected=aggregate(case['games'],set(case['players']),case['seconds'],case['cutoff'],case['side'])
            self.assertEqual(actual['samples'],expected['samples'])
            self.assertEqual(actual['exclusions'],expected['exclusions'])
            for side in ('CT','T'):
                self.assertEqual(len(actual['layers'][side]),4096)
                for a,b in zip(actual['layers'][side],expected['layers'][side]):self.assertAlmostEqual(a,b,places=12)


if __name__ == '__main__':unittest.main()
