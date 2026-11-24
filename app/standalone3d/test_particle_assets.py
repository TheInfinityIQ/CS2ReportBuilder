import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import CACHE,save,digest
from particle_assets import prepare_retained_fire

class RetainedParticleTests(unittest.TestCase):
    def fixture(self,folder):
        (folder/'sequence.mks').write_text('sequence 0\nframe a.png 1\nframe b.png 1\n')
        for name in ['a.png','b.png']:(folder/name).write_bytes(name.encode())
        return {'identity':[4,'retained-pak','godot'],'textures':{'fire':str(folder/'fire-v4.res')},'source':{'fire':'sequence.vtex'},'frames':{'fire':2}}
    def test_reuses_identical_bank_and_repairs_corruption(self):
        base=CACHE/'test-fixtures';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temporary:
            folder=Path(temporary);cached=self.fixture(folder)
            def prepare(*args,**kwargs):
                blocks=folder/'fire-layers-v1.blocks';blocks.write_bytes(b'compressed-image-data')
                save(folder/'fire-layers-v1.json',{'layers':2,'sha256':digest(blocks)})
            with patch('particle_assets._run',side_effect=prepare) as run,patch('particle_assets.find_godot',return_value='retained-runtime'):
                first=prepare_retained_fire(cached);self.assertEqual(prepare_retained_fire(cached),first);self.assertEqual(run.call_count,1)
                (folder/'fire-layers-v1.blocks').write_bytes(b'broken');prepare_retained_fire(cached);self.assertEqual(run.call_count,2)
                (folder/'a.png').write_bytes(b'new pixels');prepare_retained_fire(cached);self.assertEqual(run.call_count,3)
            self.assertEqual(cached['identity'],[4,'retained-pak','godot'])
    def test_incomplete_or_escaping_sequence_is_rejected(self):
        base=CACHE/'test-fixtures';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temporary:
            folder=Path(temporary);cached=self.fixture(folder);(folder/'b.png').unlink()
            with self.assertRaises(ValueError):prepare_retained_fire(cached)
            (folder/'sequence.mks').write_text('sequence 0\nframe ../outside.png 1\nframe a.png 1\n')
            with self.assertRaises(ValueError):prepare_retained_fire(cached)

if __name__=='__main__':unittest.main()
