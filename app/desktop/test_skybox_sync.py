import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import skybox_sync as s
from skybox_tools import catalog_players

MID='1-11111111-1111-1111-1111-111111111111'
DIGEST='a'*64
def inventory(**changes):
    return dict(complete=True,account='account-123',count=0,hashes=[],match_ids=[],pending_hashes=[],pending_ids=[],**changes)

class SkyboxTests(unittest.TestCase):
    def test_multi_match_download_precedes_upload_and_refills_missing_target(self):
        mids=[MID,MID.replace('11111111','22222222',1),MID.replace('11111111','33333333',1)]
        digests=['a'*64,'b'*64,'c'*64]
        class Resolver:
            def faceit(self,url):
                if url.startswith('players?'):return {'player_id':'11111111-1111-1111-1111-111111111111','nickname':'CanadianIQ'}
                return {'items':[{'match_id':m,'finished_at':30-i} for i,m in enumerate(mids)]}
            def faceit_match(self,mid,*args,**kwargs):return {'id':mid,'maps':[{'map':'ancient'}]}
        for variant in ('all_new','duplicate','partial'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as folder:
                events=[];available=set();batches=[]
                paths={d:Path(folder)/(d[0]+'.dem') for d in digests}
                class Library:
                    def __init__(self,*args,**kwargs):self.data={'files':{d:{'sha':d} for d in digests}}
                    def match_files(self,match):
                        d=digests[mids.index(match['id'])];return [d] if d in available else []
                    def path(self,record):return paths[record['sha']]
                class Bridge:
                    def register_file(self,path,sha,mid):self.current=sha;return {'bytes':path.stat().st_size}
                    def ask(self,mode,**kwargs):
                        if mode=='inventory':return dict(inventory(),hashes=[digests[0]],count=1) if variant=='duplicate' else inventory()
                        if mode=='hash':return {'hash':self.current}
                        events.append(('upload',self.current));return {'state':'accepted'}
                def download(plan,root,with_analysis,**kwargs):
                    self.assertFalse(with_analysis);batches.append([m['id'] for m in plan['matches']])
                    events.append(('download',len(plan['matches'])))
                    for match in plan['matches']:
                        d=digests[mids.index(match['id'])]
                        if variant=='partial' and d==digests[0]:continue
                        paths[d].write_bytes(b'PBDEMS2demo');available.add(d)
                    return 1 if variant=='partial' else 0
                with patch.object(s,'Library',Library),patch.object(s,'acquire_plan',side_effect=download):
                    result=s.sync_newest(profile='https://www.faceit.com/en/players/CanadianIQ',count=2,root=folder,
                        bridge=Bridge(),resolver=Resolver(),directory=Path(folder)/'state')
                self.assertEqual(batches[0],mids[:2]);self.assertEqual(events[0],('download',2))
                self.assertEqual(result['accepted'],2)
                self.assertEqual(len(batches),1 if variant=='all_new' else 2)
                if variant=='duplicate':self.assertEqual(result['existing'],1)
                if variant=='partial':self.assertEqual(result['unavailable'],1)
    def test_existing_catalog_player_ids_only(self):
        sid='76561198062530225'
        catalog={'version':3,'targets':[{'mode':'player','name':'CanadianIQ','steamid':sid},{'mode':'team','name':'team'},{'mode':'player','name':'bad','steamid':'bad'}]}
        self.assertEqual(catalog_players(catalog),{'CanadianIQ · '+sid:sid})
        self.assertFalse(catalog_players(dict(catalog,version=1)))
        command=s.build_command(root='.',steamid=sid)
        self.assertIn('--steamid',command);self.assertNotIn('--faceit',command)
    def test_selected_player_mismatch_stops_before_inventory(self):
        class Resolver:
            def faceit(self,url):return {'games':{'cs2':{'game_player_id':'76561198062530226'}}}
        with self.assertRaisesRegex(s.SourceError,'does not match'):
            s.sync_newest(profile='',steamid='76561198062530225',count=1,root='.',bridge=None,resolver=Resolver())
    def test_missing_local_demo_downloads_then_uploads_without_analysis(self):
        events=[]
        class Resolver:
            def faceit(self,url):
                if url.startswith('players?'):return {'player_id':'11111111-1111-1111-1111-111111111111','nickname':'CanadianIQ'}
                return {'items':[{'match_id':MID,'finished_at':20}]}
            def faceit_match(self,*args,**kwargs):return {'id':MID,'maps':[{'map':'ancient'}]}
        class Bridge:
            def ask(self,mode,**kwargs):
                events.append(mode)
                return inventory() if mode=='inventory' else {'hash':DIGEST} if mode=='hash' else {'state':'accepted'}
            def register_file(self,path,*args):
                self.path=path;return {'bytes':path.stat().st_size}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ancient'/'CanadianIQ'/'demo.dem'
            class Library:
                def __init__(self,*args,**kwargs):self.data={'files':{DIGEST:{}}}
                def match_files(self,match):return [DIGEST] if path.exists() else []
                def path(self,record):return path
            def download(plan,root,with_analysis,**kwargs):
                self.assertEqual(Path(root),Path(folder));self.assertFalse(with_analysis)
                self.assertEqual(kwargs['method'],'auto');self.assertEqual(kwargs['watch'],'browser-downloads')
                events.append('download');path.parent.mkdir(parents=True);path.write_bytes(b'PBDEMS2demo');return 0
            with patch.object(s,'Library',Library), patch.object(s,'acquire_plan',side_effect=download):
                result=s.sync_newest(profile='https://www.faceit.com/en/players/CanadianIQ',count=1,root=folder,
                    bridge=Bridge(),resolver=Resolver(),directory=Path(folder)/'state',watch='browser-downloads')
            self.assertEqual(events,['inventory','download','hash','upload']);self.assertEqual(result['accepted'],1)
    def test_inventory_requires_completeness_and_consistent_count(self):
        for value in ({},dict(inventory(),complete=False),dict(inventory(),count=1),dict(inventory(),hashes=['bad'])):
            with self.assertRaises(s.SourceError):s.Inventory.parse(value)
    def test_full_legacy_pending_identity(self):
        for key,value in [('hashes',DIGEST),('hashes',DIGEST[:16]),('pending_hashes',DIGEST)]:
            data=inventory();data[key]=[value];data['count']=len(data['hashes'])
            self.assertTrue(s.Inventory.parse(data).contains(DIGEST))
    def test_commands_validate_before_launch(self):
        with self.assertRaises(s.SourceError):s.build_command(root='')
        with self.assertRaises(s.SourceError):s.build_command(root='.',profile='https://www.faceit.com/en/players/CanadianIQ',method='browser',watch='')
        command=s.build_command(root='.',inventory=True)
        self.assertIn('--inventory',command);self.assertNotIn('--upload',command)
    def test_journal_is_scoped_and_corruption_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            a=s.Journal(folder,'a','p');a.data['attempts'][DIGEST]={'state':'uncertain'};a.save()
            self.assertEqual(s.Journal(folder,'a','p').data,a.data)
            self.assertFalse(s.Journal(folder,'b','p').data['attempts'])
            a.path.write_text('broken')
            with self.assertRaises(s.SourceError):s.Journal(folder,'a','p')
            self.assertEqual(a.path.read_text(),'broken')
    def test_history_sorts_and_deduplicates(self):
        class Resolver:
            def faceit(self,url):return {'items':[{'match_id':MID,'finished_at':3},{'match_id':MID,'finished_at':3}]}
        self.assertEqual(list(s.newest_history(Resolver(),'player')),[MID])
    def test_bridge_rejects_outside_files_and_changed_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'library';root.mkdir();outside=Path(folder)/'other.dem';outside.write_bytes(b'PBDEMS2demo')
            with s.SkyboxBridge(root) as bridge:
                with self.assertRaises(s.SourceError):bridge.register_file(outside,DIGEST,MID)
                path=root/'demo.dem';path.write_bytes(b'PBDEMS2demo');meta=bridge.register_file(path,DIGEST,MID)
                self.assertEqual(base64.b64decode(bridge.file_chunk(meta['ticket'],0)['bytes']),path.read_bytes())
                with self.assertRaises(s.SourceError):bridge.file_chunk('bad',0)
                path.write_bytes(b'PBDEMS2changed')
                with self.assertRaises(s.SourceError):bridge.file_chunk(meta['ticket'],0)
    def test_bridge_claim_is_single_use_and_tab_bound(self):
        with s.SkyboxBridge() as bridge:
            bridge.task={'id':'task','status':'pending'}
            body={'version':1,'owner':'x'*20,'id':'task'}
            bridge.dispatch('/claim',body)
            with self.assertRaises(s.SourceError):bridge.dispatch('/claim',body)
            with self.assertRaises(s.SourceError):bridge.dispatch('/state',dict(body,owner='y'*20))
    def test_newest_missing_and_uncertain_receipt_are_not_retried(self):
        second=MID.replace('11111111','22222222',1)
        class Resolver:
            def faceit(self,url):
                if url.startswith('players?'):return {'player_id':'1'*8+'-'+ '1'*4+'-'+ '1'*4+'-'+ '1'*4+'-'+ '1'*12,'nickname':'CanadianIQ'}
                return {'items':[{'match_id':MID,'finished_at':20},{'match_id':second,'finished_at':10}]}
            def faceit_match(self,mid,*args,**kwargs):return {'id':mid,'maps':[{'map':'ancient'}]}
        class Bridge:
            uploads=0
            fail=False
            def register_file(self,*args):return {'bytes':11}
            def ask(self,mode,**kwargs):
                if mode=='inventory':return dict(inventory(),match_ids=[MID])
                if mode=='hash':return {'hash':DIGEST}
                self.uploads+=1
                if self.fail:raise s.SourceError('Lost receipt')
                return {'state':'accepted'}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'demo.dem';path.write_bytes(b'PBDEMS2demo')
            class Library:
                def __init__(self,*args,**kwargs):self.data={'files':{DIGEST:{}}}
                def match_files(self,match):return [DIGEST]
                def path(self,record):return path
            kwargs=dict(profile='https://www.faceit.com/en/players/CanadianIQ',count=1,root=folder,resolver=Resolver(),directory=Path(folder)/'state')
            with patch.object(s,'Library',Library):
                bridge=Bridge();bridge.fail=True
                with self.assertRaises(s.SourceError):s.sync_newest(bridge=bridge,**kwargs)
                self.assertEqual(bridge.uploads,1)
                bridge.fail=False;result=s.sync_newest(bridge=bridge,**kwargs)
                self.assertEqual(bridge.uploads,1);self.assertEqual(result['review_required'],1)
                self.assertEqual(result['existing'],1)

if __name__=='__main__':unittest.main()
