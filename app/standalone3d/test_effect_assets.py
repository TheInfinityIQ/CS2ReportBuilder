import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import effect_assets as effects
from backend import CACHE,save


class EffectAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (CACHE/'test-fixtures').mkdir(parents=True,exist_ok=True)

    def fixture(self,folder):
        glb=folder/'world.glb';glb.write_bytes(b'retained map')
        game=folder/'game';save(folder/'manifest.json',{'source_files':{str(game/'csgo/pak01_dir.vpk'):'revision'}})
        mask='materials/effects/smoke/stock_mask.vtex'
        material={'name':'steam_not_in_an_old_allowlist','extras':{'vmat':{
            'ShaderName':'csgo_effects.vfx','TextureParams':{f'g_tMask{i}':mask for i in range(1,4)},'VectorParams':{}}}}
        return glb,game,material

    def export(self,args,*rest,**kwargs):
        resource=args[args.index('-f')+1].removesuffix('_c')
        target=Path(args[args.index('-o')+1])/Path(resource).with_suffix('.png')
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b'prepared mask')

    def test_shader_contract_prepares_steam_and_deduplicates_shared_masks(self):
        with tempfile.TemporaryDirectory(dir=CACHE/'test-fixtures') as temporary:
            glb,game,material=self.fixture(Path(temporary))
            with patch.object(effects,'digest',return_value='revision'),patch.object(effects,'gltf_info',return_value={'materials':[material]}),patch.object(effects,'_run',side_effect=self.export) as export:
                result=effects.ensure_effects(glb,game,lambda *args:None)
            self.assertEqual(export.call_count,1)
            self.assertEqual(len(result['materials'][material['name']]['masks']),3)
            self.assertEqual(result['schema'],2)

    def test_cached_setup_reads_no_geometry_and_imports_only_a_missing_mask(self):
        with tempfile.TemporaryDirectory(dir=CACHE/'test-fixtures') as temporary:
            glb,game,material=self.fixture(Path(temporary))
            with patch.object(effects,'digest',return_value='revision'),patch.object(effects,'gltf_info',return_value={'materials':[material]}),patch.object(effects,'_run',side_effect=self.export):
                result=effects.ensure_effects(glb,game,lambda *args:None)
            with patch.object(effects,'digest',return_value='revision'),patch.object(effects,'gltf_info',side_effect=AssertionError('Cached masks must not re-read geometry')),patch.object(effects,'_run',side_effect=AssertionError('Cached masks must not import again')):
                self.assertEqual(effects.ensure_effects(glb,game,lambda *args:None),result)
            Path(result['materials'][material['name']]['masks'][0]).unlink()
            with patch.object(effects,'digest',return_value='revision'),patch.object(effects,'gltf_info',return_value={'materials':[material]}),patch.object(effects,'_run',side_effect=self.export) as export:
                effects.ensure_effects(glb,game,lambda *args:None)
            self.assertEqual(export.call_count,1)

    def test_new_game_revision_cannot_supply_an_old_map_dependency(self):
        with tempfile.TemporaryDirectory(dir=CACHE/'test-fixtures') as temporary:
            glb,game,_=self.fixture(Path(temporary))
            with patch.object(effects,'digest',return_value='updated'),patch.object(effects,'_run') as export:
                with self.assertRaisesRegex(ValueError,'different game revision'):
                    effects.ensure_effects(glb,game,lambda *args:None)
            export.assert_not_called()

    def test_effect_mask_paths_cannot_escape_the_private_cache(self):
        with tempfile.TemporaryDirectory(dir=CACHE/'test-fixtures') as temporary:
            glb,game,material=self.fixture(Path(temporary));material['extras']['vmat']['TextureParams']['g_tMask1']='../outside.vtex'
            with patch.object(effects,'digest',return_value='revision'),patch.object(effects,'gltf_info',return_value={'materials':[material]}),patch.object(effects,'_run') as export:
                with self.assertRaisesRegex(ValueError,'mask path'):
                    effects.ensure_effects(glb,game,lambda *args:None)
            export.assert_not_called()

    def test_regular_materials_are_not_mistaken_for_atmospheric_effects(self):
        with tempfile.TemporaryDirectory(dir=CACHE/'test-fixtures') as temporary:
            glb,game,material=self.fixture(Path(temporary));material['name']='orange_prop'
            material['extras']['vmat']['ShaderName']='csgo_vertexlitgeneric.vfx'
            with patch.object(effects,'digest',return_value='revision'),patch.object(effects,'gltf_info',return_value={'materials':[material]}),patch.object(effects,'_run') as export:
                result=effects.ensure_effects(glb,game,lambda *args:None)
            self.assertEqual(result['materials'],{})
            export.assert_not_called()

    def test_authored_shared_default_and_particle_masks_remain_in_scope(self):
        with tempfile.TemporaryDirectory(dir=CACHE/'test-fixtures') as temporary:
            glb,game,material=self.fixture(Path(temporary))
            material['extras']['vmat']['TextureParams'].update({'g_tMask2':'materials/default/default_mask.vtex','g_tMask3':'materials/particle/scan_lines.vtex'})
            with patch.object(effects,'digest',return_value='revision'),patch.object(effects,'gltf_info',return_value={'materials':[material]}),patch.object(effects,'_run',side_effect=self.export) as export:
                result=effects.ensure_effects(glb,game,lambda *args:None)
            self.assertEqual(export.call_count,3)
            self.assertTrue(all(Path(p).is_file() for p in result['materials'][material['name']]['masks']))

    def test_source_change_refreshes_dependencies_and_retains_old_masks(self):
        with tempfile.TemporaryDirectory(dir=CACHE/'test-fixtures') as temporary:
            glb,game,material=self.fixture(Path(temporary))
            with patch.object(effects,'digest',return_value='revision'),patch.object(effects,'gltf_info',return_value={'materials':[material]}),patch.object(effects,'_run',side_effect=self.export):
                result=effects.ensure_effects(glb,game,lambda *args:None)
            old=Path(result['materials'][material['name']]['masks'][0]);old_data=old.read_bytes()
            glb.write_bytes(b'updated retained map metadata')
            material['extras']['vmat']['TextureParams']['g_tMask1']='materials/effects/smoke/another_mask.vtex'
            with patch.object(effects,'digest',return_value='revision'),patch.object(effects,'gltf_info',return_value={'materials':[material]}),patch.object(effects,'_run',side_effect=self.export) as export:
                updated=effects.ensure_effects(glb,game,lambda *args:None)
            self.assertEqual(export.call_count,1)
            self.assertNotEqual(updated['identity'],result['identity'])
            self.assertEqual(old.read_bytes(),old_data)

    def test_update_during_preparation_cannot_publish_a_mixed_revision(self):
        with tempfile.TemporaryDirectory(dir=CACHE/'test-fixtures') as temporary:
            glb,game,material=self.fixture(Path(temporary))
            with patch.object(effects,'digest',side_effect=['revision','updated']),patch.object(effects,'gltf_info',return_value={'materials':[material]}),patch.object(effects,'_run',side_effect=self.export):
                with self.assertRaisesRegex(ValueError,'changed while'):
                    effects.ensure_effects(glb,game,lambda *args:None)
            self.assertFalse((glb.parent/'effects.json').exists())


if __name__=='__main__':unittest.main()
