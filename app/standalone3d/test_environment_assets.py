import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import environment_assets as assets
from backend import save
from environment_assets import normalization

class NormalizationTests(unittest.TestCase):
    def test_source_coefficient_order_and_luminance_weights(self):
        coefficients=[]
        for channel in range(3):coefficients.extend([1,2,3,4,0,0,0,0,0])
        result=normalization(coefficients,1)[0]
        for value,expected in zip(result,[4*.325735,2*.325735,3*.325735,.282095]):
            self.assertAlmostEqual(value,expected)

    def test_each_probe_uses_its_own_planar_coefficients(self):
        self.assertEqual(normalization([0]*27+[1]*27,2)[0],[0,0,0,0])
        self.assertAlmostEqual(normalization([0]*27+[1]*27,2)[1][3],.282095)

    def test_incomplete_and_nonfinite_tables_are_rejected(self):
        for values in [[],[0]*26,[float('nan')]*27,[float('inf')]*27,[1e30]*27]:
            with self.assertRaises(ValueError):normalization(values,1)

    def test_map_update_during_metadata_read_never_publishes_mixed_inputs(self):
        base=assets.CACHE/'test-fixtures';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temp, patch.object(assets,'CACHE',Path(temp)), \
                patch.object(assets,'build_bridge',return_value=('runtime','reader','revision')):
            root=Path(temp);scene=root/'maps/de_test_revision/world.scn';scene.parent.mkdir(parents=True);scene.write_bytes(b'original scene')
            archive=root/'game/csgo/maps/de_test.vpk';archive.parent.mkdir(parents=True);archive.write_bytes(b'original map')
            save(scene.parent/'manifest.json',{'map':'de_test','fingerprint':'map-revision','source_files':{str(archive):assets.fingerprint(archive)}})
            def changed_map(args,*unused,**kwargs):
                save(Path(args[-1])/'resource.json',{'suns':[{'angles':[61,75,0],'color':[1,.8,.6],'properties':{'brightness':'6.35','brightnessscale':'1'}}]})
                archive.write_bytes(b'changed while reading')
            with patch.object(assets,'_run',side_effect=changed_map):
                with self.assertRaisesRegex(ValueError,'changed during lighting'):assets.prepare_environment(root/'game',scene)
            self.assertFalse((root/'environment'/scene.parent.name/'environment.json').exists())

if __name__=='__main__':unittest.main()
