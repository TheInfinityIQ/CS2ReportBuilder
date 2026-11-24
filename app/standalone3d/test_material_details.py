import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import material_assets as materials
from backend import CACHE, read, save


class MaterialDetailTests(unittest.TestCase):
    def test_cached_map_gets_only_missing_dependencies_and_keeps_its_geometry(self):
        base=CACHE/'test-fixtures';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temporary:
            folder=Path(temporary);glb=folder/'world.glb';glb.write_bytes(b'prepared map')
            geometry=folder/'original.scn';geometry.write_bytes(b'untouched geometry')
            state=glb.stat();identity=[materials.VERSION,state.st_size,state.st_mtime_ns,'4.7']
            receipt=folder/'source-materials.json'
            save(receipt,{'identity':identity,'geometry':str(geometry),'materials':{'wall':{
                'family':'layered','textures':{},'native_textures':{},'source':{'IntParams':{'F_DETAILTEXTURE':1},
                'TextureParams':{'g_tLayer1Detail':'materials/detail/rock.vtex'}}}}})
            private=folder/'material_textures'/'revision';png=private/'materials/detail/rock.png';png.parent.mkdir(parents=True);png.write_bytes(b'existing shared texture')
            with patch.object(materials,'CACHE',folder),patch.object(materials,'find_godot',return_value='godot'),\
                 patch.object(materials,'runtime_version',return_value='4.7'),patch.object(materials,'digest',return_value='revision'),\
                 patch.object(materials,'gltf_info',side_effect=AssertionError('Must not read/reexport map geometry')),\
                 patch.object(materials,'_run',side_effect=AssertionError('Must reuse existing shared texture')),\
                 patch.object(materials,'_prepare_gpu_textures') as gpu:
                result=materials.ensure_materials(glb,folder,lambda *args:None)
            self.assertEqual(geometry.read_bytes(),b'untouched geometry')
            self.assertEqual(result['geometry'],str(geometry))
            self.assertEqual(result['materials']['wall']['textures']['g_tLayer1Detail'],str(png))
            self.assertEqual(read(receipt,{})['detail_schema'],materials.DETAIL_SCHEMA)
            gpu.assert_called_once()

    def test_unsupported_two_layer_bump_is_reported_and_not_misrepresented_as_color_detail(self):
        definitions={'wall':{'family':'layered','textures':{},'source':{'IntParams':{'F_DETAILTEXTURE':2,'F_ADDBUMPMAPS':1},
            'TextureParams':{'g_tLayer1Detail':'do-not-decode-as-color','g_tLayer2Detail':'also-not-color'}}}}
        materials._add_material_details(definitions,lambda *args:self.fail('Unsupported bump detail must not be decoded as color'))
        self.assertTrue(definitions['wall']['detail_gap'])
        self.assertFalse(definitions['wall']['textures'])


if __name__=='__main__':unittest.main()
