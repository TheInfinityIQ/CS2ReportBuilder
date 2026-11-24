import hashlib
import json
from pathlib import Path
import tempfile
import struct
import unittest

from prepare_bounce import validate_companion, verify_uv_witness
from backend import CACHE


class CompanionIntegrityTests(unittest.TestCase):
    def setUp(self):
        root = (CACHE/'test-fixtures/bounce-integrity').resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.assertTrue(self.folder.resolve().is_relative_to(root))
        self.raw = bytes(96)
        (self.folder/'atlas.bc6h').write_bytes(self.raw)
        self.data = dict(schema=1, source_fingerprint='revision', width=4, height=4,
                         depth=6, atlas_sha256=hashlib.sha256(self.raw).hexdigest(),
                         lightmaps={}, lightmap_version=8, lightmap_game_version=2,
                         lightmap_eligibility={'source-mesh':[True]})
        self.write()

    def write(self):
        (self.folder/'probes.json').write_text(json.dumps(self.data))

    def test_valid_companion(self):
        self.assertEqual(validate_companion(self.folder, 'revision')['depth'], 6)

    def test_changed_map_revision_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'revision'):
            validate_companion(self.folder, 'new-revision')

    def test_corrupt_hdr_data_is_rejected(self):
        (self.folder/'atlas.bc6h').write_bytes(bytes([1])+self.raw[1:])
        with self.assertRaisesRegex(ValueError, 'integrity'):
            validate_companion(self.folder, 'revision')

    def test_face_layout_must_have_six_groups(self):
        self.data['depth']=7;self.write()
        with self.assertRaisesRegex(ValueError, 'dimensions'):
            validate_companion(self.folder, 'revision')

    def test_unknown_lighting_version_is_rejected(self):
        self.data['lightmap_game_version']=3;self.write()
        with self.assertRaisesRegex(ValueError, '8.2'):
            validate_companion(self.folder, 'revision')

    def test_no_lightmaps_without_source_draw_provenance(self):
        self.data['lightmap_eligibility']={};self.write()
        with self.assertRaisesRegex(ValueError, 'provenance'):
            validate_companion(self.folder, 'revision')

    def test_dependency_cannot_escape_cache(self):
        self.data['lightmaps']={'../outside':{'bytes':0,'sha256':''}};self.write()
        with self.assertRaisesRegex(ValueError, 'dependency'):
            validate_companion(self.folder, 'revision')

    def uv_fixture(self, wrong_scale=False):
        pairs=[(1200,2000),(1400,2200),(1600,2300),(1800,2400)]
        witness={'mesh':'source.meshset_0','samples':[{'index':3,'format':'R16G16_UNORM','stride':4,'offset':0,'bytes':b''.join(struct.pack('<2H',*pair) for pair in pairs).hex()}]}
        (self.folder/'uv-witness.json').write_text(json.dumps(witness))
        raw=b''.join(struct.pack('<2f',*(value/65535*(1 if wrong_scale else 1.25) for value in pair)) for pair in pairs)
        document={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(raw)}],
                  'bufferViews':[{'buffer':0,'byteLength':len(raw)}],
                  'accessors':[{'bufferView':0,'componentType':5126,'count':4,'type':'VEC2'}],
                  'meshes':[{'name':'source.meshset_0','primitives':[{'attributes':{'TEXCOORD_1':0}}]}]}
        metadata=json.dumps(document).encode();metadata+=b' '*((-len(metadata))%4)
        contents=struct.pack('<III',0x46546c67,2,12+8+len(metadata)+8+len(raw))+struct.pack('<II',len(metadata),0x4e4f534a)+metadata+struct.pack('<II',len(raw),0x004e4942)+raw
        path=self.folder/'witness.glb';path.write_bytes(contents)
        return path

    def test_exported_lightmap_scale_is_verified_against_source_vertices(self):
        result=verify_uv_witness(self.folder,self.uv_fixture(),{'uv_scale':[1.25,1.25]})
        self.assertTrue(result['export_scale_already_applied'])

    def test_exporter_scale_regression_stops_preparation(self):
        with self.assertRaisesRegex(ValueError, 'UV scale'):
            verify_uv_witness(self.folder,self.uv_fixture(True),{'uv_scale':[1.25,1.25]})


if __name__=='__main__':unittest.main()
