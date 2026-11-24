import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from backend import CACHE
from prepare_direct_lighting import validate_direct
from prepare_reflections import validate_reflections
from prepare_lightmap_uv import remap_primitive


class LightingCompanionTests(unittest.TestCase):
    def setUp(self):
        root=CACHE/'test-fixtures/lighting-integrity'
        root.mkdir(parents=True,exist_ok=True)
        temporary=tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(temporary.cleanup)
        self.folder=Path(temporary.name)
        raw=bytes(16)
        self.texture=dict(width=4,height=4,depth=1,format='BC7',bytes=16,sha256=hashlib.sha256(raw).hexdigest())
        self.direct=dict(schema=1,source_fingerprint='revision',sun_channel=0,lights=[],textures={
            name:copy.deepcopy(self.texture) for name in ['direct_light_shadows','env_light_probe_volume_atlas_dlshd']})
        for name in self.direct['textures']:(self.folder/(name+'.blocks')).write_bytes(raw)
        self.reflection=dict(schema=1,source_fingerprint='revision',width=4,height=4,cubes=1,bytes=96,
                             sha256=hashlib.sha256(bytes(96)).hexdigest(),levels=[dict(level=0,width=4,height=4,offset=0,bytes=96)])
        (self.folder/'radiance.blocks').write_bytes(bytes(96))
        self.save()

    def save(self):
        (self.folder/'direct.json').write_text(json.dumps(self.direct))
        (self.folder/'reflections.json').write_text(json.dumps(self.reflection))

    def test_valid_native_compressed_dependencies(self):
        self.assertEqual(validate_direct(self.folder,'revision')['sun_channel'],0)
        self.assertEqual(validate_reflections(self.folder,'revision')['cubes'],1)

    def test_revision_change_rejects_both_caches(self):
        for validate in [validate_direct,validate_reflections]:
            with self.assertRaisesRegex(ValueError,'revision'):validate(self.folder,'different')

    def test_shadow_corruption_rejected(self):
        (self.folder/'direct_light_shadows.blocks').write_bytes(bytes([1])*16)
        with self.assertRaisesRegex(ValueError,'integrity'):validate_direct(self.folder,'revision')

    def test_shadow_dependency_cannot_escape_folder(self):
        self.direct['textures']['../escape']=self.texture;self.save()
        with self.assertRaisesRegex(ValueError,'dependencies'):validate_direct(self.folder,'revision')

    def test_invalid_channel_rejected(self):
        self.direct['sun_channel']=4;self.save()
        with self.assertRaisesRegex(ValueError,'dependencies'):validate_direct(self.folder,'revision')

    def test_shadow_dimensions_checked_before_reading(self):
        self.direct['textures']['direct_light_shadows']['depth']=3000;self.save()
        with self.assertRaisesRegex(ValueError,'layout'):validate_direct(self.folder,'revision')

    def test_reflection_corruption_rejected(self):
        (self.folder/'radiance.blocks').write_bytes(bytes([1])*96)
        with self.assertRaisesRegex(ValueError,'integrity'):validate_reflections(self.folder,'revision')

    def test_reflection_mip_offset_rejected(self):
        self.reflection['levels'][0]['offset']=16;self.save()
        with self.assertRaisesRegex(ValueError,'layout'):validate_reflections(self.folder,'revision')

    def test_three_uv_sets_preserve_lightmap_and_base_uv(self):
        primitive={'attributes':{'POSITION':0,'TEXCOORD_0':1,'TEXCOORD_1':2,'TEXCOORD_2':3,'COLOR_0':4}}
        remap_primitive(primitive,'TEXCOORD_2')
        self.assertEqual(primitive['attributes'],{'POSITION':0,'TEXCOORD_0':1,'TEXCOORD_1':3,'COLOR_0':4})

    def test_two_channel_draw_is_unchanged(self):
        primitive={'attributes':{'POSITION':0,'TEXCOORD_0':1,'TEXCOORD_1':2}}
        original=copy.deepcopy(primitive)
        remap_primitive(primitive,'TEXCOORD_1')
        self.assertEqual(primitive,original)

    def test_missing_extra_channel_stops_import(self):
        with self.assertRaisesRegex(ValueError,'missing'):
            remap_primitive({'attributes':{'TEXCOORD_1':2}},'TEXCOORD_2')


if __name__=='__main__':unittest.main()
