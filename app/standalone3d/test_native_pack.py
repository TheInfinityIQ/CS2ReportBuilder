import tempfile
import unittest
from pathlib import Path
from backend import CACHE,save
from native_pack import replay_mount

class PackMountTests(unittest.TestCase):
    def test_only_matching_complete_map_package_can_be_mounted(self):
        root=CACHE/'test-fixtures';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            folder=Path(temporary);scene=folder/'world.scn';pack=folder/'world.pck';pack.write_bytes(b'GDPCexample')
            receipt={'schema':1,'fingerprint':'map-revision','bytes':pack.stat().st_size,'pack':str(pack),'scene':'res://prepared/test/world.scn'}
            save(scene.with_suffix('.pack.json'),receipt)
            meta={'native_scene':str(scene),'sha256':'demo-id','asset_info':{'fingerprint':'map-revision'}}
            self.assertEqual(replay_mount(meta)['source_demo'],'demo-id')
            self.assertIsNone(replay_mount({**meta,'asset_info':{'fingerprint':'changed-map'}}))
            pack.write_bytes(b'BAD!example');self.assertIsNone(replay_mount(meta))
            pack.write_bytes(b'GDPCtruncated')
            self.assertIsNone(replay_mount(meta))
            pack.unlink();self.assertIsNone(replay_mount(meta))
        self.assertIsNone(replay_mount({}))

if __name__=='__main__':unittest.main()
