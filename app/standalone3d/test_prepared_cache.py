import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import CACHE
from backend import read,save
import launcher
import prepared_cache as ready

class PreparedCacheTests(unittest.TestCase):
    def test_changed_demo_map_runtime_or_companion_cannot_reuse_ready_data(self):
        base=CACHE/'test-fixtures';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temporary:
            root=Path(temporary);folder=root/'replays'/('a'*64+'_decoded');folder.mkdir(parents=True)
            for name in ['replay.json','tracks','world.scn','states','inventory','network','punch','travel','gait','source.dem','graph-pose.bin','deaths','fire.json','fire.blocks']:(folder/name).write_bytes(b'fixture')
            save(folder/'graph-clip.json',{'variants':[{'data':str(folder/'graph-pose.bin')}]})
            meta={'sha256':'a'*64,'map':'de_anubis','source':str(folder/'source.dem'),'asset_info':{'fingerprint':'map-a'},'step':1,'info':{'tickrate':64},
                  'tracks':str(folder/'tracks'),'native_scene':str(folder/'world.scn'),'gameplay':{'states':str(folder/'states')},
                  'inventory':str(folder/'inventory'),'network_presentation':str(folder/'network'),
                  'death_presentation':str(folder/'deaths'),'particle_assets':{'fire_bank':str(folder/'fire.json')},
                  'presentation':{k:str(folder/k) for k in ['punch','travel']},
                  'actor_assets':{'weapon_graphs':{'glock':{'clips':{'original':str(folder/'graph-clip.json')}}}}}
            with patch.object(ready,'CACHE',root),patch.object(ready,'revision',return_value='code-a') as revision,\
                 patch.object(ready,'fingerprint',return_value='a'*64),patch.object(ready,'asset_identity',return_value=(None,'map-a',{})) as asset,\
                 patch.object(launcher,'find_godot',return_value='godot'),patch.object(launcher,'runtime_version',return_value='4.7') as runtime:
                ready.write_receipt(meta,folder)
                self.assertEqual(ready.find_ready(meta['source'],root,'godot'),folder/'replay.json')
                (folder/'fire.blocks').unlink();self.assertIsNone(ready.find_ready(meta['source'],root,'godot'))
                (folder/'fire.blocks').write_bytes(b'fixture');ready.write_receipt(meta,folder)
                (folder/'deaths').unlink();self.assertIsNone(ready.find_ready(meta['source'],root,'godot'))
                (folder/'deaths').write_bytes(b'fixture');ready.write_receipt(meta,folder)
                receipt=read(folder/'prepared.json',{});save(folder/'prepared.json',{**receipt,'step':8})
                self.assertIsNone(ready.find_ready(meta['source'],root,'godot'));save(folder/'prepared.json',receipt)
                asset.return_value=(None,'map-b',{});self.assertIsNone(ready.find_ready(meta['source'],root,'godot'));asset.return_value=(None,'map-a',{})
                runtime.return_value='4.8';self.assertIsNone(ready.find_ready(meta['source'],root,'godot'));runtime.return_value='4.7'
                revision.return_value='code-b';self.assertIsNone(ready.find_ready(meta['source'],root,'godot'));revision.return_value='code-a'
                (folder/'source.dem').write_bytes(b'changed demo');self.assertIsNone(ready.find_ready(meta['source'],root,'godot'))
                ready.write_receipt(meta,folder)
                (folder/'graph-pose.bin').unlink();self.assertIsNone(ready.find_ready(meta['source'],root,'godot'))
                (folder/'graph-pose.bin').write_bytes(b'fixture');ready.write_receipt(meta,folder)
                (folder/'network').unlink();self.assertIsNone(ready.find_ready(meta['source'],root,'godot'))

if __name__=='__main__':unittest.main()
