"""The optional fast cache must preserve source identity and bound its input."""
import io
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import native_resource_cache as native
from backend import save
from fingerprints import stamp


class ResourceCacheTests(unittest.TestCase):
    def test_bounded_compressed_layout(self):
        header = b'RSCC'+struct.pack('<IIII', 2, 4096, 100, 20)
        self.assertEqual(native.layout(io.BytesIO(header)), (4096, 100, (20,)))
        for data in [b'', header[:10], header[:-1],
                     b'RSCC'+struct.pack('<IIII', 2, 0, 100, 20),
                     b'RSCC'+struct.pack('<IIII', 2, 4096, 2**31, 20),
                     b'RSCC'+struct.pack('<IIII', 2, 4096, 100, 100000)]:
            with self.subTest(data=data), self.assertRaises(ValueError):native.layout(io.BytesIO(data))

    def test_selected_sources_are_shared_and_deduplicated(self):
        meta = {'stock': {'players': {'ct': 'ct.scn'},
                         'aliases': {'Glock-18': 'glock'},
                         'weapons': {'glock': {'scene': 'glock.scn'},
                                     'awp': {'scene': 'unrequested.scn'}}},
                'actor_assets': {'arms': {'ct': {'scene': 'arms.scn'}}},
                'weapons': ['Glock-18', 'glock'],
                'grenades': {'models': {'smoke': 'smoke.scn', 'alias': 'smoke.scn'}}}
        self.assertEqual({p.name for p in native.sources(meta)}, {'ct.scn', 'glock.scn', 'arms.scn', 'smoke.scn'})

    def test_only_private_stock_is_eligible_and_unchanged_receipts_reuse(self):
        scratch=native.CACHE/'test-fixtures';scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary, patch.object(native, 'CACHE', Path(temporary)):
            root=Path(temporary);source=root/'stock/glock.scn';source.parent.mkdir();source.write_bytes(b'unchanged original')
            target=root/'native-resources'/(native.fingerprint(source)+'.scn');target.parent.mkdir();target.write_bytes(b'RSRCprepared')
            receipt={'schema':4,'source_stamp':stamp(source),'bytes':target.stat().st_size,
                     'modified':target.stat().st_mtime_ns//1_000_000_000}
            save(target.with_suffix('.json'),receipt)
            with patch.object(native,'repack') as repack:
                self.assertEqual(native.prepare_one(source),receipt);repack.assert_not_called()
                with self.assertRaises(ValueError):native.prepare_one(root/'maps/world.scn')
            source.write_bytes(b'new source revision')
            with patch.object(native,'repack',side_effect=ValueError('new preparation required')):
                with self.assertRaisesRegex(ValueError,'new preparation'):native.prepare_one(source)


if __name__=='__main__':unittest.main()
