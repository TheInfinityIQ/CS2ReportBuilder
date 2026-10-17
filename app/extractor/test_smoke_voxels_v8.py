import struct
import unittest
from smoke_voxels_v8 import SmokeDecoder, fill_interior, demorton


def chunk(kind, masks, seed=False):
    payload = bytes((0, kind))
    if kind == 3:
        payload += bytes((int(seed),))
        if seed: payload += bytes((16,16,16,255,0,0,0,0))
    payload += struct.pack('<H', len(masks))
    payload += b''.join(struct.pack('<HQ', cell, mask) for cell, mask in masks)
    payload += b'\x00'
    return struct.pack('<HH', 0, len(payload)) + payload


class SmokeTests(unittest.TestCase):
    def test_incremental_chunk_and_zero_mask_clear(self):
        decoder = SmokeDecoder()
        first = chunk(3, [(0, 1)])
        self.assertFalse(decoder.ingest(first[:5], 5))
        self.assertTrue(decoder.ingest(first, len(first)))
        self.assertEqual(sum(decoder.occupancy()), 1)
        stream = first + chunk(2, [(0, 0)])
        decoder.ingest(stream, len(stream))
        self.assertEqual(sum(decoder.occupancy()), 0)

    def test_seed_and_morton_coordinates(self):
        decoder = SmokeDecoder()
        raw = chunk(3, [(1, 1 << 1)], seed=True)
        decoder.ingest(raw, len(raw))
        grid = decoder.occupancy()
        self.assertEqual(grid[16 | 16<<5 | 16<<10], 1)
        self.assertEqual(grid[5], 1)
        self.assertEqual(demorton(7, 3), (1,1,1))

    def test_rewrite_shrink_and_invalid_payload_rejected(self):
        decoder = SmokeDecoder()
        raw = chunk(3, [(0,1)])
        decoder.ingest(raw, len(raw))
        with self.assertRaisesRegex(ValueError, 'shrank'):
            decoder.ingest(raw, len(raw)-1)
        with self.assertRaisesRegex(ValueError, 'rewrote'):
            decoder.ingest(b'\xff'+raw[1:],len(raw))
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            SmokeDecoder().ingest(raw, len(raw)+1)
        with self.assertRaisesRegex(ValueError, 'outside grid'):
            bad = chunk(3, [(512, 1)])
            SmokeDecoder().ingest(bad, len(bad))

    def test_only_enclosed_interior_fills(self):
        grid = bytearray(32768)
        for x in range(10,13):
            for y in range(10,13):
                for z in range(10,13):
                    if (x,y,z) != (11,11,11): grid[x | y<<5 | z<<10]=1
        center = 11 | 11<<5 | 11<<10
        self.assertEqual(fill_interior(grid)[center],1)
        grid[10 | 11<<5 | 11<<10]=0
        self.assertEqual(fill_interior(grid)[center],0)


if __name__ == '__main__': unittest.main()
