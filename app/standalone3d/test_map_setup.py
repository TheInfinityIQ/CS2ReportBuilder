"""No silent map import, exact seven-map scope, and version-bound approvals."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'extractor/.deps'))
import backend
import fingerprints
import map_setup


class MapSetupTests(unittest.TestCase):
    def setUp(self):
        base=backend.CACHE/'test-fixtures';base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.game=self.root/'game';self.cache=self.root/'cache'
        (self.game/'csgo/maps').mkdir(parents=True)
        for name in ['de_ancient','de_overpass']:(self.game/'csgo/maps'/f'{name}.vpk').write_bytes(b'map')
        (self.game/'csgo/pak01_dir.vpk').write_bytes(b'index')
        (self.game/'csgo/steam.inf').write_text('build=1')
        self.version='4.7.fixture'
        for p in [patch.object(backend,'CACHE',self.cache),patch.object(fingerprints,'CACHE',self.cache),
                  patch.object(map_setup,'valid_container',return_value=True),
                  patch.object(map_setup.launcher,'find_godot',return_value='fixture'),
                  patch.object(map_setup.launcher,'runtime_version',side_effect=lambda _:self.version)]:
            p.start();self.addCleanup(p.stop)

    def test_pool_matches_user_list_exactly(self):
        self.assertEqual(set(map_setup.SUPPORTED_MAPS),{'de_ancient','de_anubis','de_dust2','de_mirage','de_inferno','de_cache','de_nuke'})
        self.assertNotIn('de_overpass',map_setup.SUPPORTED_MAPS)

    def test_unprepared_map_inside_or_outside_pool_needs_permission(self):
        for name in ['de_ancient','de_overpass']:
            with self.subTest(map=name):
                with self.assertRaises(map_setup.MapSetupRequired) as error:map_setup.require_setup(self.game,name)
                self.assertEqual(error.exception.map_setup['in_pool'],name=='de_ancient')
        self.assertFalse((self.cache/'maps').exists())
        self.assertFalse((self.cache/'settings.json').exists())

    def test_explicit_approval_permits_only_the_requested_map_revision(self):
        request=map_setup.inspect(self.game,'de_overpass');map_setup.approve(self.game,request)
        self.assertEqual(map_setup.require_setup(self.game,'de_overpass')['map'],'de_overpass')
        with self.assertRaises(map_setup.MapSetupRequired):map_setup.require_setup(self.game,'de_ancient')
        (self.game/'csgo/maps/de_overpass.vpk').write_bytes(b'updated')
        with self.assertRaises(map_setup.MapSetupRequired):map_setup.require_setup(self.game,'de_overpass')

    def test_changed_renderer_needs_new_permission(self):
        request=map_setup.inspect(self.game,'de_ancient');map_setup.approve(self.game,request)
        self.version='4.8.fixture'
        with self.assertRaises(map_setup.MapSetupRequired):map_setup.require_setup(self.game,'de_ancient')

    def test_uninstalled_map_shows_actionable_warning_without_an_import(self):
        with self.assertRaises(map_setup.MapSetupRequired) as error:map_setup.require_setup(self.game,'de_missing')
        self.assertFalse(error.exception.map_setup['installed'])
        self.assertIn('not installed',str(error.exception))
        with self.assertRaisesRegex(ValueError,'not installed'):map_setup.approve(self.game,error.exception.map_setup)

    def test_removed_prepared_cache_needs_a_new_explicit_approval(self):
        details=map_setup.inspect(self.game,'de_ancient');map_setup.approve(self.game,details)
        map_setup.mark_prepared(details)
        with self.assertRaises(map_setup.MapSetupRequired):map_setup.require_setup(self.game,'de_ancient')

    def test_stale_approval_request_never_grants_changed_assets(self):
        request=map_setup.inspect(self.game,'de_ancient')
        (self.game/'csgo/steam.inf').write_text('build=2')
        with self.assertRaisesRegex(ValueError,'changed'):map_setup.approve(self.game,request)
        self.assertFalse((self.cache/'settings.json').exists())

    def test_prepared_native_revision_reuses_without_import_or_new_prompt(self):
        request=map_setup.inspect(self.game,'de_ancient')
        folder=Path(request['folder']);folder.mkdir(parents=True)
        _,_,evidence=backend.asset_identity(self.game,'de_ancient')
        key=backend.asset_key(evidence,True)
        backend.save(folder/'manifest.json',{'fingerprint':key,'geometry_only':False})
        (folder/'world.glb').write_bytes(b'fixture')
        scene=Path(request['native_scene']);scene.write_bytes(b'fixture')
        backend.save(scene.with_suffix('.json'),{'source':key,'godot':self.version,'adapter':2,'textures':'s3tc'})
        self.assertTrue(map_setup.require_setup(self.game,'de_ancient')['ready'])
        self.assertFalse((self.cache/'settings.json').exists())

    def test_demo_preparation_stops_before_export_if_user_has_not_approved(self):
        import demoparser2
        demo=self.root/'sample.dem';demo.write_bytes(b'fixture')
        parser=Mock();parser.parse_header.return_value={'map_name':'de_overpass'}
        with patch.object(demoparser2,'DemoParser',return_value=parser), \
             patch.object(backend,'file_info',return_value={'ticks':100,'seconds':2,'tickrate':50}), \
             patch.object(backend,'export_map') as export:
            with self.assertRaises(map_setup.MapSetupRequired):backend.prepare(demo,self.game,self.root/'job')
            export.assert_not_called();parser.parse_ticks.assert_not_called()


if __name__=='__main__':unittest.main()
