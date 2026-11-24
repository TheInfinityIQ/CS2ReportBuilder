import hashlib
import json
from pathlib import Path
import tempfile
import os
import shutil
import unittest
from unittest.mock import Mock, patch
import analysis_references as refs
import analysis_all
import downloads
from downloads import Library
from test_downloads import MATCH


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);self.analysis = self.root/'analysis';self.analysis.mkdir()
        self.sha = hashlib.sha256(b'PBDEMS2\0anubis').hexdigest()
        self.primary = self.analysis/'A'/'map'/'original';self.primary.mkdir(parents=True)
        self.complete(self.primary)

    def put(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True);path.write_text(json.dumps(value))

    def complete(self, folder):
        folder.mkdir(parents=True, exist_ok=True)
        for name in ('header.json', 'rounds.csv', 'player_rounds.csv', 'player_positions.csv.gz',
                     'economy.csv', 'grenade_throws.csv.gz', 'grenade_paths.csv.gz'):
            (folder/name).write_bytes(b'fixture')
        (folder/'events').mkdir(exist_ok=True)
        self.put(folder/'match_summary.json', {'valid': True, 'schema_version': '4.0'})
        self.put(folder/'integrity_checks.json', {'integrity_ok': True})
        self.put(folder/'viewer_tracks_meta.json', {'demo_sha256': self.sha, 'interpolation_check': {'ok': True}})
        (folder/'viewer_tracks.csv.gz').write_bytes(b'fixture')

    def test_reference_only_folder_and_wrong_identity_or_user_files_rejected(self):
        alias = self.analysis/'B'/'map'/'accurate_name'
        refs.write(self.analysis, alias, self.primary, self.sha, {'owner': 'B'}, 'anubis')
        self.assertEqual([p.name for p in alias.iterdir()], [refs.REFERENCE])
        self.assertEqual(refs.resolve(self.analysis, alias, self.sha), self.primary)
        with self.assertRaises(ValueError):refs.resolve(self.analysis, alias, '0'*64)
        (alias/'notes.txt').write_text('retain')
        with self.assertRaises(ValueError):refs.write(self.analysis, alias, self.primary, self.sha, {}, 'anubis')

    def test_cycles_escape_missing_and_moved_targets(self):
        alias = self.analysis/'alias';refs.write(self.analysis, alias, self.primary, self.sha, {}, 'anubis')
        moved = self.analysis/'moved';self.primary.rename(moved)
        self.assertFalse(refs.resolve(self.analysis, alias).exists())
        self.assertEqual(refs.find(self.analysis, self.sha), moved)
        refs.write(self.analysis, alias, moved, self.sha, {}, 'anubis')
        self.assertEqual(refs.resolve(self.analysis, alias), moved)
        value = refs.read(alias/refs.REFERENCE);value['target'] = 'alias';self.put(alias/refs.REFERENCE, value)
        with self.assertRaisesRegex(ValueError, 'cycle'):refs.resolve(self.analysis, alias)
        value['target'] = '../outside';self.put(alias/refs.REFERENCE, value)
        with self.assertRaisesRegex(ValueError, 'escapes'):refs.resolve(self.analysis, alias)

    def test_invalid_analysis_and_wrong_rate_are_not_reused(self):
        (self.primary/'rounds.csv').unlink()
        self.assertFalse(refs.complete(self.primary, self.sha))
        self.complete(self.primary)
        self.put(self.primary/'integrity_checks.json', {'integrity_ok': False})
        self.assertFalse(refs.complete(self.primary, self.sha))
        self.complete(self.primary)
        self.put(self.primary/'viewer_v8/entity_meta.json', {'demo_sha256': self.sha, 'sampleHz': 32, 'validation': {'passed': True}})
        self.assertFalse(refs.complete(self.primary, self.sha, 16))
        self.assertTrue(refs.complete(self.primary, self.sha, 32))

    def test_second_collection_reuses_analysis_without_running_extraction(self):
        replay = self.root/'replays';replay.mkdir();library = Library(replay)
        staged = self.root/'demo';staged.write_bytes(b'PBDEMS2\0anubis')
        sha = library.add(MATCH, staged, MATCH['maps'][0], 'demo.dem')
        other = {**MATCH, 'owner': 'OtherPlayer', 'label': 'OtherPlayer'}
        run = Mock(side_effect=AssertionError('Duplicate analysis must not execute'))
        with patch.object(downloads, 'ANALYSIS', self.analysis), patch.object(downloads, 'STATE', self.root/'state'):
            self.assertEqual(downloads.analyze(library, [sha], contexts={sha: other}, run=run), [])
        run.assert_not_called()
        aliases = list(self.analysis.rglob(refs.REFERENCE));self.assertEqual(len(aliases), 1)
        self.assertIn('OtherPlayer', str(aliases[0].parent))
        self.assertEqual(refs.resolve(self.analysis, aliases[0].parent), self.primary)

    def test_preview_follows_references_without_requiring_an_unneeded_demo_download(self):
        alias = self.analysis/'alias';refs.write(self.analysis, alias, self.primary, self.sha, {'owner': 'A'}, 'anubis')
        replay = self.root/'replays';replay.mkdir()
        with patch.object(analysis_all, 'STATE', self.root/'state'):
            result = analysis_all.preview(replay, self.analysis)
        self.assertEqual(result['counts']['recordings'], 1)
        self.assertEqual(result['counts']['references'], 1)
        self.assertFalse(result['items'][0]['analysis_needed'])
        self.assertFalse(result['items'][0]['download_needed'])

    def library(self):
        replay = self.root/'replays';replay.mkdir(exist_ok=True)
        library = Library(replay, log=lambda *_: None)
        staged = self.root/'demo';staged.write_bytes(b'PBDEMS2\0anubis')
        library.add(MATCH, staged, MATCH['maps'][0], 'demo.dem')
        return library

    def test_checksums_and_schema_changes_are_not_silently_reused(self):
        track = self.primary/'viewer_tracks.csv.gz'
        meta = refs.read(self.primary/'viewer_tracks_meta.json')
        meta['sha256_files'] = {track.name: hashlib.sha256(track.read_bytes()).hexdigest()}
        self.put(self.primary/'viewer_tracks_meta.json', meta)
        self.assertTrue(refs.complete(self.primary, self.sha))
        track.write_bytes(b'changed')
        self.assertFalse(refs.complete(self.primary, self.sha))
        self.complete(self.primary)
        alias = self.analysis/'alias';refs.write(self.analysis, alias, self.primary, self.sha, {}, 'anubis')
        self.put(self.primary/'match_summary.json', {'valid': True, 'schema_version': 'new'})
        with self.assertRaisesRegex(ValueError, 'schema'):refs.resolve(self.analysis, alias)
        self.assertIsNone(refs.find(self.analysis, self.sha, schema='4.0'))

    def test_source_replacement_with_same_size_and_timestamp_is_not_valid(self):
        library = self.library();path = library.path(library.data['files'][self.sha])
        stamp = path.stat()
        replacement = self.root/'replacement';replacement.write_bytes(b'X'*stamp.st_size)
        os.utime(replacement, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        os.replace(replacement, path)
        self.assertFalse(library.valid(self.sha))

    def test_analyze_all_rebuilds_missing_canonical_once_and_keeps_aliases(self):
        library = self.library()
        for name in ['Player_A', 'Player_B']:
            refs.write(self.analysis, self.analysis/name, self.primary, self.sha, MATCH, 'anubis')
        shutil.rmtree(self.primary)
        def recover(lib, digests, **kwargs):
            self.assertEqual(digests, [self.sha])
            self.assertEqual(kwargs['destinations'][self.sha], self.primary)
            self.complete(self.primary)
            return []
        with patch.object(analysis_all, 'STATE', self.root/'state'), patch.object(downloads, 'ANALYSIS', self.analysis):
            plan = analysis_all.preview(library.root, self.analysis)
            self.assertEqual(plan['counts']['analysis_needed'], 1)
            self.assertEqual(plan['counts']['download_needed'], 0)
            with patch.object(downloads, 'analyze', side_effect=recover) as run, patch.object(downloads, 'acquire_plan') as acquire:
                self.assertEqual(analysis_all.execute(plan, self.root/'Downloads'), 0)
            run.assert_called_once();acquire.assert_not_called()
        for name in ['Player_A', 'Player_B']:
            self.assertEqual(refs.resolve(self.analysis, self.analysis/name), self.primary)

    def test_analyze_all_downloads_missing_demo_then_verifies_exact_hash(self):
        library = self.library()
        refs.write(self.analysis, self.analysis/'alias', self.primary, self.sha, MATCH, 'anubis')
        library.path(library.data['files'][self.sha]).unlink();shutil.rmtree(self.primary)
        def restore(*args, **kwargs):
            library.path(library.data['files'][self.sha]).write_bytes(b'PBDEMS2\0anubis')
            return 0
        def recover(*args, **kwargs):self.complete(self.primary);return []
        with patch.object(analysis_all, 'STATE', self.root/'state'), patch.object(downloads, 'ANALYSIS', self.analysis):
            plan = analysis_all.preview(library.root, self.analysis)
            self.assertEqual(plan['counts']['download_needed'], 1)
            with patch.object(downloads, 'Resolver') as resolver, patch.object(downloads, 'acquire_plan', side_effect=restore) as acquire, patch.object(downloads, 'analyze', side_effect=recover) as run:
                self.assertEqual(analysis_all.execute(plan, self.root/'Downloads'), 0)
                acquire.assert_called_once();run.assert_called_once()
                self.assertIn('/matches/123', resolver.return_value.resolve.call_args.args[0])
            shutil.rmtree(self.primary);library.path(library.data['files'][self.sha]).unlink()
            with patch.object(downloads, 'Resolver'), patch.object(downloads, 'acquire_plan', return_value=0), patch.object(downloads, 'analyze') as run:
                self.assertEqual(analysis_all.execute(plan, self.root/'Downloads'), 1)
                run.assert_not_called()
            self.assertTrue((self.analysis/'alias'/refs.REFERENCE).is_file())

    def test_moved_canonical_is_healed_without_running_analysis(self):
        library = self.library()
        alias = self.analysis/'alias';refs.write(self.analysis, alias, self.primary, self.sha, MATCH, 'anubis')
        moved = self.analysis/'moved';self.primary.rename(moved)
        with patch.object(analysis_all, 'STATE', self.root/'state'), patch.object(downloads, 'ANALYSIS', self.analysis):
            plan = analysis_all.preview(library.root, self.analysis)
            with patch.object(downloads, 'analyze') as run:
                self.assertEqual(analysis_all.execute(plan, self.root/'Downloads'), 0)
                run.assert_not_called()
        self.assertEqual(refs.resolve(self.analysis, alias), moved)


if __name__ == '__main__':unittest.main()
