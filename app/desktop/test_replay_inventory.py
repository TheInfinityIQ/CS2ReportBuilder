import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jobs import STATE
import replay_inventory as replays
import review_model as model


class ReplayInventoryTests(unittest.TestCase):
    def setUp(self):
        base=STATE/'replay-inventory-tests';base.mkdir(parents=True,exist_ok=True)
        temp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.replays=self.root/'replays';self.replays.mkdir();self.cache=self.root/'watch-cache.json'
        self.catalog=self.root/'catalog.json'
        for target,name,value in [(replays,'DEFAULT_REPLAYS',self.replays),(replays,'CACHE',self.cache),(model,'ROOT',self.root)]:
            p=patch.object(target,name,value);p.start();self.addCleanup(p.stop)

    def demo(self,relative,payload=b'fixture'):
        path=self.replays/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'PBDEMS2\0'+payload)
        return path,hashlib.sha256(path.read_bytes()).hexdigest()

    def analyze(self,sha,source='Event/mirage/Analysis_match'):
        folder=self.root/'data/analysis'/source;folder.mkdir(parents=True,exist_ok=True)
        (folder/'viewer_tracks_meta.json').write_text(json.dumps({'demo_sha256':sha,'tickrate':64}))
        entry=dict(source=source,name='A_vs_B',map='de_mirage',sha=sha,game='series:map',date='2026-11-01',players={})
        self.catalog.write_text(json.dumps({'version':3,'entries':[entry]}));return folder

    def test_analysis_only_record_is_not_watchable(self):
        self.analyze('a'*64)
        self.assertEqual(model.library(self.catalog),[])

    def test_download_without_analysis_is_watchable_with_filename_metadata(self):
        path,sha=self.demo('dust2/Player/[13-vs-8]_Player_Nov-01-2026_dust2_FaceIt.dem')
        entries=model.library(self.catalog)
        self.assertEqual(len(entries),1);entry=entries[0]
        self.assertEqual(entry['sha'],sha);self.assertEqual(entry['map'],'de_dust2')
        self.assertEqual(entry['date'],'2026-11-01');self.assertIsNone(entry['folder'])
        self.assertEqual(replays.resolve_entry(entry),path.resolve())

    def test_analysis_is_enrichment_not_an_availability_source(self):
        path,sha=self.demo('mirage/A-vs-B.dem');folder=self.analyze(sha)
        entry=model.library(self.catalog)[0]
        self.assertEqual(entry['folder'],folder.resolve());self.assertEqual(entry['demo_path'],path.resolve())
        path.unlink();self.assertEqual(model.library(self.catalog),[])

    def test_stale_and_outside_download_index_entries_are_ignored(self):
        self.demo('mirage/real.dem')
        outside=self.root/'outside.dem';outside.write_bytes(b'PBDEMS2\0outside')
        (self.replays/'replay-library.json').write_text(json.dumps({'files':{
            'a'*64:{'path':'mirage/missing.dem'},'b'*64:{'path':'../outside.dem'}}}))
        self.assertEqual(len(model.library(self.catalog)),1)
        with self.assertRaises(replays.UnavailableDemo): replays.verify(outside,replays.digest(outside))

    def test_duplicate_copies_are_one_watchable_recording(self):
        self.demo('mirage/PlayerA/copy.dem');self.demo('mirage/PlayerB/copy.dem')
        self.assertEqual(len(model.library(self.catalog)),1)

    def test_refresh_uses_real_files_even_when_index_has_no_entry(self):
        self.assertEqual(model.library(self.catalog),[])
        path,_=self.demo('cache/new.DEM')
        self.assertEqual(len(model.library(self.catalog)),1)
        path.unlink();self.assertEqual(model.library(self.catalog),[])

    def test_indexed_unchanged_files_and_cached_files_do_not_need_full_rehash(self):
        path,sha=self.demo('mirage/indexed.dem');info=path.stat()
        (self.replays/'replay-library.json').write_text(json.dumps({'files':{sha:{'path':'mirage/indexed.dem',
            'bytes':info.st_size,'mtime_ns':info.st_mtime_ns,'ctime_ns':info.st_ctime_ns,
            'inode':info.st_ino,'map':'mirage'}}}))
        with patch.object(replays,'digest',side_effect=AssertionError('unnecessary full-file hash')):
            self.assertEqual(replays.available()[0]['sha'],sha)
            self.assertEqual(replays.available()[0]['sha'],sha)

    def test_changed_file_is_rehashed_and_stale_analysis_not_attached(self):
        path,sha=self.demo('mirage/changed.dem');self.analyze(sha)
        self.assertIsNotNone(model.library(self.catalog)[0]['folder'])
        path.write_bytes(b'PBDEMS2\0new recording longer than before')
        entry=model.library(self.catalog)[0]
        self.assertNotEqual(entry['sha'],sha);self.assertIsNone(entry['folder'])

    def test_cold_inventory_rejects_replacement_with_same_size_and_mtime(self):
        path, sha = self.demo('mirage/changed.dem', b'old')
        original = path.stat()
        self.analyze(sha)
        (self.replays/'replay-library.json').write_text(json.dumps({'files': {sha: {
            'path': 'mirage/changed.dem', 'bytes': original.st_size,
            'mtime_ns': original.st_mtime_ns, 'ctime_ns': original.st_ctime_ns, 'inode': original.st_ino}}}))
        replacement = self.root/'replacement'
        replacement.write_bytes(b'PBDEMS2\0new')
        os.utime(replacement, ns=(original.st_atime_ns, original.st_mtime_ns))
        os.replace(replacement, path)
        entry = model.library(self.catalog)[0]
        self.assertEqual(entry['sha'], replays.digest(path))
        self.assertIsNone(entry['folder'])

    def test_partial_non_demo_and_corrupt_metadata_do_not_block_downloads(self):
        self.demo('mirage/real.dem')
        self.demo('.download-work/pending.dem');self.demo('mirage/.pending.dem')
        (self.replays/'mirage/error.dem').write_text('<html>Not a demo</html>')
        (self.replays/'replay-library.json').write_text('{bad')
        self.catalog.write_text('{bad');self.cache.write_text('{bad')
        self.assertEqual(len(model.library(self.catalog)),1)

    def test_disappearing_or_replaced_file_fails_without_a_picker(self):
        path,_=self.demo('mirage/real.dem');entry=model.library(self.catalog)[0]
        path.write_bytes(b'PBDEMS2\0different recording')
        with self.assertRaisesRegex(replays.UnavailableDemo,'changed'):replays.resolve_entry(entry)
        path.unlink()
        with self.assertRaisesRegex(replays.UnavailableDemo,'no longer available'):replays.resolve_entry(entry)

    def test_playback_hash_failure_repairs_stale_cache_identity(self):
        path,sha=self.demo('mirage/real.dem',b'old content')
        entry=model.library(self.catalog)[0]
        path.write_bytes(b'PBDEMS2\0new content')
        new_sha=replays.digest(path)
        # Simulate an out-of-date stat cache that incorrectly retained old identity.
        self.cache.write_text(json.dumps({'version':replays.CACHE_VERSION,'root':str(self.replays.resolve()),'files':{
            'mirage/real.dem':{'stamp':replays.stamp(path),'sha':sha}}}))
        with self.assertRaises(replays.UnavailableDemo):replays.resolve_entry(entry)
        self.assertEqual(model.library(self.catalog)[0]['sha'],new_sha)


if __name__=='__main__':unittest.main()
