import copy
import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from heatmap import aggregate, passages, Heatmaps, identity

A, B, C = '76561198062530225', '76561198000000002', '76561198000000003'
CAL = {'scale':1,'pos_x':0,'pos_y':1024}


def path(duration=40, hz=4, speed=16, offset=0):
    return [[i/hz,offset+speed*i/hz,900,0] for i in range(int(duration*hz)+1)]


def rnd(number=1, side='CT', deaths=None, duration=40, sid=A, track=None):
    return {'id':str(number),'start':0,'end':duration,'valid':True,'deaths_available':True,
            'deaths':deaths or [],'players':[{'id':sid,'side':side,'track':path() if track is None else track}]}


def game(rounds=None, key='a'):
    return {'game':key,'rate':1,'calibration':CAL,'rounds':rounds or [rnd()]}


class MovementTests(unittest.TestCase):
    def test_first_death_unselected_global_before_and_after_window(self):
        source=game([rnd(deaths=[{'id':B,'tick':17}])])
        actual=aggregate([source],{A})
        expected=aggregate([game([rnd(duration=17)])],{A})
        self.assertEqual(actual['layers'],expected['layers'])
        self.assertGreater(sum(aggregate([source],{A},cutoff=False)['layers']['CT']),sum(actual['layers']['CT']))
        late=game([rnd(deaths=[{'id':B,'tick':45}],duration=60)])
        self.assertEqual(aggregate([late],{A})['layers'],aggregate([game()],{A})['layers'])

    def test_both_teams_share_cutoff_world_death_and_own_death(self):
        r=rnd(deaths=[{'id':B,'tick':17}]);r['players'].append({'id':C,'side':'T','track':path()})
        cut=aggregate([game([r])],{A,C})
        self.assertEqual(cut['layers']['CT'],cut['layers']['T'])
        r['deaths']=[{'id':None,'tick':17}]
        self.assertEqual(cut['layers'],aggregate([game([r])],{A,C})['layers'])
        r['deaths']=[{'id':A,'tick':17}]
        full=aggregate([game([r])],{A,C},cutoff=False)
        self.assertGreater(sum(full['layers']['T']),sum(full['layers']['CT']))

    def test_no_death_early_end_missing_stream(self):
        self.assertEqual(aggregate([game([rnd(duration=10)])],{A})['layers'],
                         aggregate([game()],{A},seconds=10)['layers'])
        r=rnd();r['deaths_available']=False
        result=aggregate([game([r])],{A},cutoff=False)
        self.assertEqual(result['samples']['CT']['rounds'],0)
        self.assertEqual(result['exclusions']['missing_death_stream'],1)

    def test_stationary_jitter_sampling_reentry_clipping_gaps_teleports(self):
        stationary=[[i/4,100+(i%2),900,0] for i in range(161)]
        self.assertEqual(passages(stationary,0,40,1,CAL)[0],{})
        self.assertTrue(passages(stationary,0,40,1,CAL)[1])
        p4=passages(path(hz=4),0,17.3,1,CAL)[0]
        p8=passages(path(hz=8),0,17.3,1,CAL)[0]
        self.assertEqual(p4,p8)
        one=passages(path(10),0,10,1,CAL)[0]
        twice=path(10)+[[10+i/4,160-4*i,900,0] for i in range(1,41)]
        self.assertGreater(sum(passages(twice,0,20,1,CAL)[0].values()),sum(one.values()))
        self.assertEqual(passages([[0,0,900,0],[10,160,900,0]],0,10,1,CAL)[0],{})
        self.assertEqual(passages([[0,0,900,0],[.25,900,900,0]],0,1,1,CAL)[0],{})
        self.assertEqual(passages([],0,10,1,CAL),({},False))

    def test_equal_game_weight_overtime_actual_sides_duplicates_missing(self):
        first=game([rnd(i,side='CT' if i%2 else 'T') for i in range(1,29)],'long')
        second=game([rnd(1,side='T',track=path(offset=160)),rnd(2,side='CT',track=path(offset=160))],'short')
        result=aggregate([first,second],{A})
        a=aggregate([first],{A});b=aggregate([second],{A})
        for side in ('CT','T'):
            self.assertEqual(result['samples'][side],{'games':2,'rounds':15})
            self.assertEqual(result['layers'][side],[(x+y)/2 for x,y in zip(a['layers'][side],b['layers'][side])])
        self.assertEqual(aggregate([first,copy.deepcopy(first)],{A})['layers'],a['layers'])
        self.assertEqual(aggregate([first,game([rnd(sid=B)],'absent')],{A})['layers'],a['layers'])
        missing=game([rnd(track=[])],'missing')
        self.assertEqual(aggregate([first,missing],{A})['layers'],a['layers'])
        incomplete=copy.deepcopy(first)
        for r in incomplete['rounds']:r['players'][0]['track']=[]
        self.assertEqual(aggregate([incomplete,first],{A})['layers'],a['layers'])
        partial=rnd();partial['players'].append({'id':B,'side':'CT','track':[]})
        self.assertEqual(aggregate([game([partial])],{A,B})['samples']['CT']['rounds'],0)
        self.assertEqual(aggregate([first,second],{A},side='CT')['scale'],result['scale'])
        self.assertEqual(sum(aggregate([first],set())['layers']['CT']),0)


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path.cwd());self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.folder=self.root/'nested'/'map'/'demo';self.folder.mkdir(parents=True)
        self.folder.joinpath('rounds.csv').write_text('round\n1\n')
        self.service=Heatmaps(self.root,{'de_ancient':CAL})
        self.addCleanup(self.service.executor.shutdown)

    def test_unknown_identity_and_pug_no_upgrade_or_other_player(self):
        self.assertIsNone(identity(self.folder,{})[0])
        (self.folder/'analysis_source.json').write_text(json.dumps({'context':{'collection_kind':'player'}}))
        (self.folder/'heatmap_identity.json').write_text(json.dumps({'mode':'team','tracked_player_id':A}))
        info,error=identity(self.folder,{})
        self.assertEqual(info['mode'],'player');self.assertIsNone(error)
        entry={'source':'nested/map/demo','identity':info,'map':'de_ancient','game':'hash'}
        self.service.catalog=lambda:[entry]
        for request in ({'players':[B]},{'players':[A,B]},{'players':[A],'opponents':['other']}):
            with self.assertRaises(ValueError):self.service.submit({'source':entry['source'],**request})

    def test_team_roster_stable_ids_substitutes_and_ambiguous_rejection(self):
        teams=[{'id':'team-a','name':'Alpha','players':[A,B]},{'id':'team-b','name':'Beta','players':[C]}]
        binding={'mode':'team','selected_team_id':'team-a','teams':teams}
        (self.folder/'heatmap_identity.json').write_text(json.dumps(binding))
        info,error=identity(self.folder,{})
        self.assertIsNone(error);self.assertEqual(info['membership'][A],'team-a')
        self.assertEqual(info['opponent'],'team-b')
        teams[1]['players'].append(A)
        (self.folder/'heatmap_identity.json').write_text(json.dumps(binding))
        self.assertIsNone(identity(self.folder,{})[0])

    def test_hltv_verified_team_ids_require_exact_canonical_clan_link(self):
        self.folder.joinpath('rounds.csv').write_text('round,ct_team_clan_name,t_team_clan_name\n1,Alpha,Beta\n2,Beta,Alpha\n')
        self.folder.joinpath('player_rounds.csv').write_text(f'round,steamid,side\n1,{A},CT\n2,{A},TERRORIST\n1,{B},TERRORIST\n2,{B},CT\n')
        binding={'mode':'team','selected_team_id':'hltv:1','teams':[
            {'id':'hltv:1','name':'Alpha','clan_names':['Alpha']},
            {'id':'hltv:2','name':'Beta','clan_names':['Beta']}]}
        (self.folder/'heatmap_identity.json').write_text(json.dumps(binding))
        info,error=identity(self.folder,{})
        self.assertIsNone(error);self.assertEqual(info['membership'][A],'hltv:1')
        binding['teams'][0]['clan_names']=['Different Alias']
        (self.folder/'heatmap_identity.json').write_text(json.dumps(binding))
        self.assertIsNone(identity(self.folder,{})[0])

    def test_source_path_boundary(self):
        with self.assertRaises(ValueError):self.service.safe('../escape')

    def test_prepare_normalizes_recorded_terrorist_side_and_missing_capability(self):
        def write(name,value):
            p=self.folder/name;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(json.dumps(value))
        write('match_summary.json',{'valid':True,'tickrate':1})
        write('integrity_checks.json',{'integrity_ok':True})
        write('viewer_tracks_meta.json',{'tickrate':1})
        write('source_capabilities.json',{'event_streams':{'player_death':{'parsed':True}}})
        self.folder.joinpath('rounds.csv').write_text('round,parser_round,freeze_end_tick,end_tick,winner,round_observation_complete\n1,0,0,40,T,True\n')
        self.folder.joinpath('player_rounds.csv').write_text(f'round,steamid,side,name\n1,{A},TERRORIST,Original\n')
        with gzip.open(self.folder/'viewer_tracks.csv.gz','wt') as stream:
            stream.write('round,steamid,tick,x,y,z\n')
            for t,x,y,z in path():stream.write(f'1,{A},{t},{x},{y},{z}\n')
        (self.folder/'events').mkdir(exist_ok=True)
        with gzip.open(self.folder/'events/player_death.csv.gz','wt') as stream:
            stream.write(f'tick,user_steamid\n17,{B}\n')
        entry={'source':'nested/map/demo','identity':{'mode':'player','tracked':A},'map':'de_ancient','game':'hash'}
        prepared=self.service.prepare(entry)
        self.assertEqual(prepared['rounds'][0]['players'][0]['side'],'T')
        result=aggregate([prepared],{A})
        self.assertEqual(result['samples']['T']['rounds'],1)
        self.assertEqual(result['samples']['CT']['rounds'],0)
        self.assertEqual(result['layers'],aggregate([game([rnd(side='T',duration=17)])],{A})['layers'])

    def test_team_context_substitutes_aliases_and_filter_contract(self):
        self.folder.joinpath('player_rounds.csv').write_text(f'round,parser_round,steamid,name,side\n1,0,{A},OldName,CT\n2,1,{B},Substitute,CT\n')
        second=self.root/'other';second.mkdir();second.joinpath('rounds.csv').write_text('round\n1\n')
        second.joinpath('player_rounds.csv').write_text(f'round,parser_round,steamid,name,side\n1,0,{A},NewName,TERRORIST\n1,0,{C},Opponent,CT\n')
        base={'mode':'team','tracked':None,'bundle':'team:alpha','selected_team':'alpha',
              'teams':{'alpha':'Alpha','beta':'Beta'},'membership':{A:'alpha',B:'alpha',C:'beta'},'opponent':'beta'}
        entries=[{'source':'nested/map/demo','name':'first','identity':base,'map':'de_ancient','game':'one'},
                 {'source':'other','name':'second','identity':{**base,'opponent':'gamma','teams':{'alpha':'Alpha','gamma':'Gamma'}},'map':'de_ancient','game':'two'}]
        # C is unrelated to the second match's verified teams: it cannot join the roster.
        self.service.catalog=lambda:entries
        context=self.service.context('nested/map/demo')
        player=next(p for p in context['players'] if p['id']==A)
        self.assertEqual(player['names'],['NewName','OldName'])
        self.assertEqual(player['games'],2)
        self.assertEqual(len(context['opponents']),2)
        with self.assertRaises(ValueError):
            self.service.submit({'source':'nested/map/demo','players':[A],'opponents':['alien']})
        with self.assertRaises(ValueError):
            self.service.submit({'source':'nested/map/demo','game':'elsewhere','players':[A]})

    def test_cached_revision_changes_and_cancelled_job_can_be_retried(self):
        info={'mode':'player','tracked':A,'bundle':'player:'+A}
        entry={'source':'nested/map/demo','identity':info,'map':'de_ancient','game':'hash'}
        self.service.catalog=lambda:[entry]
        self.service.prepare=lambda _:game()
        request={'source':entry['source'],'players':[A]}
        job=self.service.submit(request)['job'];self.service.executor.submit(lambda:None).result(timeout=5)
        self.assertEqual(self.service.status(job)['status'],'complete')
        cached=self.service.submit(request)['job']
        self.assertNotEqual(cached,job)
        self.assertEqual(self.service.status(cached)['phase'],'Ready (cached)')
        self.folder.joinpath('heatmap_identity.json').write_text('{"version":1}')
        changed=self.service.submit(request)['job'];self.assertNotEqual(job,changed)
        self.service.executor.submit(lambda:None).result(timeout=5)

    def test_streaming_job_matches_equal_game_reference_and_deduplicates(self):
        info={'mode':'player','tracked':A,'bundle':'player:'+A}
        entries=[];prepared={}
        for source,key,rounds in [('nested/map/demo','long',[rnd(i) for i in range(1,11)]),
                                  ('copy','long',[rnd(i) for i in range(1,11)]),
                                  ('short','short',[rnd(track=path(offset=160))])]:
            folder=self.root/source;folder.mkdir(exist_ok=True,parents=True)
            (folder/'rounds.csv').write_text('round\n1\n')
            entries.append({'source':source,'identity':info,'map':'de_ancient','game':key})
            prepared[source]=game(rounds,key)
        self.service.catalog=lambda:entries
        self.service.prepare=lambda entry:prepared[entry['source']]
        job=self.service.submit({'source':'nested/map/demo','players':[A]})['job']
        self.service.executor.submit(lambda:None).result(timeout=5)
        result=self.service.status(job)['result']
        reference=aggregate(list(prepared.values()),{A})
        self.assertEqual(result['layers'],reference['layers'])
        self.assertEqual(result['samples'],reference['samples'])
        self.assertEqual(result['exclusions']['duplicate_rounds'],10)


if __name__=='__main__':unittest.main()
