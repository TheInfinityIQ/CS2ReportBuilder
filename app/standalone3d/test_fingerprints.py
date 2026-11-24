import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import backend
import fingerprints


class FingerprintTests(unittest.TestCase):
    def setUp(self):
        base = backend.CACHE/'test-fixtures'; base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        change = patch.object(fingerprints, 'CACHE', self.root)
        change.start(); self.addCleanup(change.stop)
        self.file = self.root/'demo.dem'; self.file.write_bytes(b'original')

    def test_unchanged_file_reuses_verified_sha(self):
        with patch.object(fingerprints, 'digest', wraps=backend.digest) as digest:
            first = fingerprints.fingerprint(self.file)
            self.assertEqual(first, fingerprints.fingerprint(self.file))
            self.assertEqual(digest.call_count, 1)

    def test_in_place_write_with_preserved_size_and_mtime_invalidates(self):
        first = fingerprints.fingerprint(self.file); before = self.file.stat()
        self.file.write_bytes(b'replaced')
        os.utime(self.file, ns=(before.st_atime_ns,before.st_mtime_ns))
        self.assertNotEqual(first, fingerprints.fingerprint(self.file))

    def test_replaced_file_with_preserved_mtime_invalidates(self):
        first = fingerprints.fingerprint(self.file); before = self.file.stat()
        replacement = self.root/'new.dem'; replacement.write_bytes(b'replaced')
        os.utime(replacement, ns=(before.st_atime_ns,before.st_mtime_ns))
        replacement.replace(self.file)
        self.assertNotEqual(first, fingerprints.fingerprint(self.file))

    def test_file_changing_during_hash_is_rejected(self):
        def mutate(path):
            value = backend.digest(path); path.write_bytes(b'different size'); return value
        with patch.object(fingerprints, 'digest', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'changed while'): fingerprints.fingerprint(self.file)


if __name__ == '__main__': unittest.main()
