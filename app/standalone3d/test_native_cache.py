"""Regressions for oversized RSCC files and native texture-part references."""
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

import backend
import launcher
import native_cache


class NativeMapCacheTests(unittest.TestCase):
    def setUp(self):
        base=backend.CACHE/'test-fixtures';base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_compressed_length_table_must_account_for_the_entire_file(self):
        file=self.root/'native.scn'
        good=b'RSCC'+struct.pack('<III',2,4,8)+struct.pack('<III',3,4,0)+b'1234567'+b'RSCC'
        file.write_bytes(good)
        self.assertTrue(native_cache.valid_container(file))
        # An overflowed raw-length header understates the real block table.
        file.write_bytes(good[:-4]+b'extra-blocks'+b'RSCC')
        self.assertFalse(native_cache.valid_container(file))
        file.write_bytes(b'RSCC'+b'\0'*12)
        self.assertFalse(native_cache.valid_container(file))

    def test_missing_or_truncated_texture_parts_invalidate_reuse(self):
        scene=self.root/'world.scn';part=self.root/'texture.res';part.write_bytes(b'12345')
        read=lambda *args:{'files':{'texture.res':5}}
        self.assertTrue(native_cache.valid_parts(scene,read))
        part.write_bytes(b'12');self.assertFalse(native_cache.valid_parts(scene,read))
        part.unlink();self.assertFalse(native_cache.valid_parts(scene,read))

    def test_native_texture_parts_roundtrip_outside_the_godot_project(self):
        try:runtime=launcher.find_godot()
        except ValueError:self.skipTest('Godot runtime is unavailable')
        source=self.root/'fixture.glb';scene=self.root/'fixture.scn';report=self.root/'report.json'
        jobs=[('native_map_fixture.gd',[source]),('prepare_scene.gd',[source,scene,'gpu','parts']),
              ('inspect_map.gd',[scene,report])]
        for script,args in jobs:
            process=subprocess.run([str(runtime),'--headless','--path',str(backend.HERE),'--log-file',str(self.root/(script+'.log')),
                '--script',script,'--',*[str(x) for x in args]],capture_output=True,text=True,timeout=30)
            self.assertEqual(process.returncode,0,process.stderr[-1500:])
            self.assertNotIn('SCRIPT ERROR',process.stderr)
        result=json.loads(report.read_text())
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['native_texture_parts'],1)
        self.assertFalse(result['missing_dependencies'])
        self.assertFalse(result['unsafe_dependencies'])
        self.assertTrue(native_cache.valid_container(scene))


if __name__=='__main__':unittest.main()
