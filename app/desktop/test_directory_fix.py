import csv
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch

from jobs import ROOT, save_json
from directory_fix import DirectoryFix, PathRemapper, inventory, load_json, remap_json
from extractor.game_catalog import Catalog, signature
from extractor.job_lock import exclusive
from sources import SourceError

UID = '12345678-1234-1234-1234-123456789abc'
STEAM = '76561198000000001'
STEM = '[9-vs-13]_OldName_Oct-15-2026_inferno_FaceIt'


class Profiles:
    def __init__(self):
        self.calls = []

    def faceit(self, path):
        self.calls.append(path)
        return {'player_id': UID, 'nickname': 'CurrentName', 'games': {'cs2': {'game_player_id': STEAM}}}


class DirectoryFixTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'data/.desktop/tests'
        base.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / 'analysis'
        self.root.mkdir()
        self.state = self.base / 'state'
        self.state.mkdir()
        self.index = self.base / 'replays/replay-library.json'
        self.profiles = Profiles()
        self.fixer = DirectoryFix(self.root, self.state, resolver=self.profiles,
                                  replay_indices=[self.index], log=lambda _: None)

    def dataset(self, name=STEM, collection='analyzed_OldName_demos', context=None, sha='fixture'):
        path = self.root / collection / name
        path.mkdir(parents=True)
        save_json(path / 'match_summary.json', {'valid': True, 'map_name': 'de_inferno',
                  'demo_source_family': 'faceit_sourcetv', 'contains_full_match_likely': True, 'map_complete_likely': True})
        save_json(path / 'viewer_tracks_meta.json', {'demo_file': name + '.dem', 'demo_sha256': sha})
        (path / 'players.csv').write_text('steamid,name\n' + STEAM + ',OldName\n')
        (path / 'viewer_tracks.csv.gz').write_bytes(b'large binary evidence is never decoded or rewritten')
        if context is not None:
            save_json(path / 'analysis_source.json', {'demo': name + '.dem', 'sha256': sha, 'context': context})
        return path

    def test_preview_is_read_only_and_uses_stable_id_current_name(self):
        old = self.dataset()
        before = inventory(old)
        plan = self.fixer.plan()
        target = Path(plan['moves'][0]['new'])
        self.assertEqual(target.relative_to(self.root).parts, ('Analysis_CurrentName', 'inferno', 'Analysis_' + STEM))
        self.assertEqual(plan['moves'][0]['player']['player_id'], UID)
        self.assertIn('game_player_id=' + STEAM, self.profiles.calls[0])
        self.assertEqual(inventory(old), before)
        self.assertFalse(target.exists())
        self.assertTrue((self.state / 'directory-fixes' / plan['id'] / 'preview.html').is_file())

    def test_legacy_player_filename_is_rebuilt_from_verified_team_score(self):
        old = self.dataset('OldName_10-15-2026_1dot20_Inferno_LOSS')
        (old / 'scoreboard.csv').write_text('steamid,team_clan_name\n' + STEAM + ',team_OldName\n')
        (old / 'rounds.csv').write_text('ct_team_clan_name,t_team_clan_name,ct_score_after,t_score_after,round_observation_complete\n'
                                        'team_Opponent,team_OldName,13,9,True\n')
        plan = self.fixer.plan()
        self.assertEqual(Path(plan['moves'][0]['new']).name, 'Analysis_' + STEM)

    def test_missing_or_ambiguous_identity_is_skipped(self):
        old = self.dataset(collection='analyzed_SomeoneElse_demos')
        (old / 'players.csv').write_text('steamid,name\n' + STEAM + ',OldName\n76561198000000002,SomeoneElse\n')
        plan = self.fixer.plan()
        self.assertFalse(plan['moves'])
        self.assertIn('different accounts', plan['skipped'][0]['reason'])
        self.assertTrue(old.is_dir())
        self.assertFalse(self.profiles.calls)

    def test_api_unavailable_or_wrong_identity_never_falls_back_to_nickname(self):
        old = self.dataset()
        for response in [SourceError('API unavailable'), {'player_id': UID, 'nickname': 'Wrong', 'games': {'cs2': {'game_player_id': '76561198000000002'}}}]:
            self.fixer.profiles.clear()
            with patch.object(self.profiles, 'faceit', side_effect=response if isinstance(response, Exception) else None,
                              return_value=response):
                plan = self.fixer.plan()
            self.assertFalse(plan['moves'])
            self.assertEqual(len(plan['skipped']), 1)
        self.assertTrue(old.is_dir())

    def test_uuid_provenance_survives_unrecognized_old_nickname(self):
        self.dataset(collection='old unknown collection', context={'source': 'faceit', 'collection_kind': 'player',
                     'owner': 'LongGoneName', 'selected_player_id': UID})
        plan = self.fixer.plan()
        self.assertEqual(len(plan['moves']), 1)
        self.assertEqual(self.profiles.calls, ['players/' + UID])

    def test_apply_and_undo_update_references_catalog_and_nested_folders(self):
        old = self.dataset()
        child = old / 'nested folder/sub folder'
        child.mkdir(parents=True)
        (child / 'evidence.csv').write_bytes(b'preserve exactly')
        save_json(old / 'links.json', {'path': str(child / 'evidence.csv'), 'source': old.relative_to(self.root).as_posix()})
        report = old.parent / 'manifest.json'
        save_json(report, {'analysis': str(old)})
        save_json(self.state / 'settings.json', {'viewer_analysis': str(old)})
        save_json(self.state / 'history.json', [{'output': str(old)}])
        save_json(self.index, {'files': {'sha': {'analysis_outputs': {str(old): {'output': str(old)}}}}})
        catalog = Catalog(self.fixer.catalog)
        catalog.put(old, 'fixture', signature(old), {'core_ready': True})
        outside = self.base / 'outside-analysis'
        outside.mkdir()
        (outside / 'players.csv').write_text('steamid,name\n')
        catalog.put(outside, 'outside', signature(outside), {'core_ready': True})
        with closing(sqlite3.connect(self.fixer.catalog)) as db:
            original_outside = db.execute('SELECT * FROM games WHERE analysis=?', (str(outside),)).fetchone()
        original_files = {p.relative_to(old): p.read_bytes() for p in old.rglob('*') if p.is_file()}
        plan = self.fixer.plan()
        # The preview job itself adds history. Applying must preserve that newer record.
        save_json(self.state / 'history.json', [{'title': 'Preview', 'output': 'report'}, {'output': str(old)}])
        journal = self.fixer.apply(plan)
        target = Path(plan['moves'][0]['new'])
        self.assertFalse(old.exists())
        self.assertEqual((target / 'nested_folder/sub_folder/evidence.csv').read_bytes(), b'preserve exactly')
        self.assertEqual(load_json(target / 'viewer_tracks_meta.json')['demo_file'], STEM + '.dem')
        self.assertEqual(load_json(target / 'links.json')['path'], str(target / 'nested_folder/sub_folder/evidence.csv'))
        self.assertEqual(load_json(self.state / 'settings.json')['viewer_analysis'], str(target))
        self.assertIn(str(target), load_json(self.index)['files']['sha']['analysis_outputs'])
        self.assertFalse(report.exists())
        with closing(sqlite3.connect(self.fixer.catalog)) as db:
            self.assertEqual(db.execute('SELECT verified FROM games WHERE analysis=?', (str(target),)).fetchone(), (0,))
            self.assertEqual(db.execute('SELECT analysis FROM players WHERE steamid=?', (STEAM,)).fetchone(), (str(target),))
            self.assertEqual(db.execute('SELECT * FROM games WHERE analysis=?', (str(outside),)).fetchone(), original_outside)
        self.fixer.undo(self.state / 'directory-fixes' / plan['id'] / 'journal.json')
        self.assertTrue(old.is_dir())
        for rel, content in original_files.items():
            self.assertEqual((old / rel).read_bytes(), content)
        self.assertEqual(load_json(report), {'analysis': str(old)})
        self.assertEqual(load_json(self.state / 'settings.json')['viewer_analysis'], str(old))
        self.assertEqual(load_json(self.state / 'history.json')[0]['title'], 'Preview')
        with closing(sqlite3.connect(self.fixer.catalog)) as db:
            self.assertTrue(db.execute('SELECT 1 FROM games WHERE analysis=?', (str(old),)).fetchone())
        self.assertEqual(journal['status'], 'completed')

    def test_team_layout_uses_tournament_map_match_without_team_folder(self):
        name = '[13-9]_G2-vs-Vitality_Oct-15-2026_inferno_Test Cup'
        old = self.dataset(name, collection='old tournament', context={'source': 'hltv', 'collection_kind': 'team', 'owner': 'G2', 'event': 'Test Cup'})
        plan = self.fixer.plan()
        self.assertEqual(Path(plan['moves'][0]['new']).relative_to(self.root).parts[:2], ('Test_Cup', 'inferno'))
        self.assertFalse(self.profiles.calls)
        self.assertTrue(old.exists())

    def test_unknown_tournament_date_is_reported_instead_of_fabricated(self):
        self.dataset('g2-vs-vitality-m1-inferno', collection='analyzed_TestCup')
        plan = self.fixer.plan()
        self.assertFalse(plan['moves'])
        self.assertIn('date/score', plan['skipped'][0]['reason'])

    def test_removing_team_layer_preserves_map_and_collection_selections(self):
        name = '[13-9]_G2-vs-Vitality_Oct-15-2026_inferno_Test Cup'
        old = self.dataset(name, collection='Test_Cup/G2/inferno',
                           context={'source': 'hltv', 'collection_kind': 'team', 'owner': 'G2', 'event': 'Test Cup'})
        save_json(self.state / 'settings.json', {'output': str(old.parent), 'collection': str(old.parent.parent)})
        plan = self.fixer.plan()
        self.fixer.apply(plan)
        settings = load_json(self.state / 'settings.json')
        self.assertEqual(settings['output'], str(self.root / 'Test_Cup/inferno'))
        self.assertEqual(settings['collection'], str(self.root / 'Test_Cup'))
        self.assertFalse(old.exists())
        self.assertTrue((self.root / 'Test_Cup/inferno' / ('Analysis_' + name.replace(' ', '_'))).is_dir())

    def test_duplicate_versions_are_retained_and_second_preview_is_idempotent(self):
        self.dataset()
        other = self.dataset(collection='analyzed_OldName_demos_v8')
        plan = self.fixer.plan()
        targets = [Path(m['new']) for m in plan['moves']]
        self.assertEqual(len(set(targets)), 2)
        self.fixer.apply(plan)
        self.assertTrue(all(p.is_dir() for p in targets))
        self.assertFalse(other.exists())
        self.assertFalse(self.fixer.plan()['moves'])

    def test_stale_preview_or_occupied_destination_makes_no_changes(self):
        old = self.dataset()
        plan = self.fixer.plan()
        target = Path(plan['moves'][0]['new'])
        target.mkdir(parents=True)
        with self.assertRaisesRegex(SourceError, 'destination'):
            self.fixer.apply(plan)
        self.assertTrue(old.is_dir())
        target.rmdir()
        (old / 'new-file.csv').write_text('later evidence')
        with self.assertRaisesRegex(SourceError, 'changed after preview'):
            self.fixer.apply(plan)
        self.assertTrue(old.is_dir())

    def test_invalid_nested_move_rejected_before_any_rename(self):
        old = self.dataset()
        plan = self.fixer.plan()
        plan['moves'][0]['nested'].append({'old': '../other', 'new': '../other'})
        with self.assertRaisesRegex(SourceError, 'Invalid internal'):
            self.fixer.apply(plan)
        self.assertTrue(old.is_dir())

    def test_active_extraction_blocks_repair(self):
        old = self.dataset()
        plan = self.fixer.plan()
        with exclusive(self.fixer.lock):
            with self.assertRaisesRegex(RuntimeError, 'another job'):
                self.fixer.apply(plan)
        self.assertTrue(old.is_dir())

    def test_new_foreign_output_lock_or_reference_blocks_a_stale_preview(self):
        old = self.dataset()
        plan = self.fixer.plan()
        locks = old.parent / '.cs2di_locks'
        locks.mkdir()
        lock = locks / 'foreign.lock'
        lock.write_text('owned by another extractor')
        with self.assertRaisesRegex(SourceError, 'job started'):
            self.fixer.apply(plan)
        lock.unlink()
        save_json(self.state / 'new-viewer-selection.json', {'analysis': str(old)})
        with self.assertRaisesRegex(SourceError, 'new stored reference'):
            self.fixer.apply(plan)
        self.assertTrue(old.is_dir())

    def test_undo_refuses_changed_analysis_and_occupied_original_path(self):
        old = self.dataset()
        plan = self.fixer.plan()
        self.fixer.apply(plan)
        target = Path(plan['moves'][0]['new'])
        journal_path = self.state / 'directory-fixes' / plan['id'] / 'journal.json'
        later = target / 'later.json'
        later.write_text('{}')
        with self.assertRaisesRegex(SourceError, 'changed since'):
            self.fixer.undo(journal_path)
        later.unlink()
        old.mkdir(parents=True)
        with self.assertRaisesRegex(SourceError, 'occupied'):
            self.fixer.undo(journal_path)
        self.assertTrue(target.is_dir())
        self.assertEqual(load_json(journal_path)['status'], 'completed')

    def test_interrupted_apply_can_be_undone(self):
        old = self.dataset()
        save_json(self.state / 'settings.json', {'viewer_analysis': str(old)})
        plan = self.fixer.plan()
        with patch.object(self.fixer, '_catalog_update', side_effect=OSError('simulated interruption')):
            with self.assertRaises(OSError):
                self.fixer.apply(plan)
        path = self.state / 'directory-fixes' / plan['id'] / 'journal.json'
        self.assertEqual(load_json(path)['status'], 'needs_rollback')
        self.assertTrue(self.fixer.plan()['errors'])
        self.fixer.undo(path)
        self.assertTrue(old.is_dir())
        self.assertEqual(load_json(self.state / 'settings.json')['viewer_analysis'], str(old))

    def test_undo_preserves_new_preferences_and_restores_original_collection_selection(self):
        old = self.dataset()
        save_json(self.state / 'settings.json', {'extract_output': str(old.parent), 'viewer_analysis': str(old), 'hz': '16'})
        plan = self.fixer.plan()
        self.fixer.apply(plan)
        settings = load_json(self.state / 'settings.json')
        settings['hz'] = '32'
        settings['new_preference'] = 'keep me'
        save_json(self.state / 'settings.json', settings)
        self.fixer.undo(self.state / 'directory-fixes' / plan['id'] / 'journal.json')
        restored = load_json(self.state / 'settings.json')
        self.assertEqual(restored, {'extract_output': str(old.parent), 'viewer_analysis': str(old), 'hz': '32', 'new_preference': 'keep me'})

    def test_internal_normalization_collision_is_skipped_before_any_move(self):
        old = self.dataset()
        (old / 'sub folder').mkdir()
        (old / 'sub_folder').mkdir()
        plan = self.fixer.plan()
        self.assertFalse(plan['moves'])
        self.assertIn('collide', plan['skipped'][0]['reason'])

    def test_reference_key_merges_are_rejected_in_preview(self):
        self.dataset()
        self.dataset(collection='analyzed_OldName_demos_v8')
        save_json(self.state / 'collection-index.json', {str(self.root / 'analyzed_OldName_demos'): 1,
                                                       str(self.root / 'analyzed_OldName_demos_v8'): 2})
        plan = self.fixer.plan()
        self.assertTrue(any('metadata keys' in e for e in plan['errors']))
        with self.assertRaises(SourceError):
            self.fixer.apply(plan)

    def test_relative_reference_boundaries_and_dict_keys(self):
        old = self.root / 'legacy/game'
        new = self.root / 'Tournament/Team/map/Analysis_game'
        mapping = [{'old': str(old), 'new': str(new)}]
        data = {'source': 'legacy/game', 'other': 'legacy/game2', str(old): {'path': str(old / 'rounds.csv')}}
        result = remap_json(data, mapping, self.root)
        self.assertEqual(result['source'], new.relative_to(self.root).as_posix())
        self.assertEqual(result['other'], 'legacy/game2')
        self.assertEqual(result[str(new)]['path'], str(new / 'rounds.csv'))

    def test_replay_strings_do_not_rescan_the_folder_mapping_list(self):
        class CountedMappings(list):
            iterations = 0
            def __iter__(self):
                self.iterations += 1
                return super().__iter__()
        mappings = CountedMappings({'old': str(self.root / f'old/game{i}'),
                                    'new': str(self.root / f'new/Analysis_game{i}')} for i in range(500))
        samples = [{'type': 'player', 'name': 'OldName', 'weapon': 'ak47', 'tick': i} for i in range(2000)]
        data = {'source': 'old/game123', 'samples': samples}
        result = remap_json(data, mappings, self.root)
        self.assertEqual(result['source'], 'new/Analysis_game123')
        self.assertEqual(result['samples'], samples)
        self.assertEqual(mappings.iterations, 1)

    def test_compiled_lookup_preserves_longest_prefix_exact_rules_and_slash_style(self):
        mappings = [
            {'old': str(self.root / 'legacy'), 'new': str(self.root / 'collection')},
            {'old': str(self.root / 'legacy/game'), 'new': str(self.root / 'other/Analysis_game')},
            {'old': str(self.root / 'legacy/game/report'), 'new': str(self.root / 'report-selection'), 'exact': True},
        ]
        mapper = PathRemapper(mappings, self.root)
        self.assertEqual(mapper.text('legacy', 'label'), 'legacy')
        self.assertEqual(mapper.text('legacy', 'source'), 'collection')
        self.assertEqual(mapper.text('legacy/game/report', 'source'), 'report-selection')
        self.assertEqual(mapper.text('legacy/game/report/file.csv'), 'other/Analysis_game/report/file.csv')
        self.assertEqual(mapper.text('legacy/game2', 'source'), 'collection/game2')
        self.assertEqual(mapper.text(str(self.root / 'LEGACY/GAME/rounds.csv')), str(self.root / 'other/Analysis_game/rounds.csv'))
        for i in range(9000):
            mapper.text('label' + str(i))
        self.assertLessEqual(mapper.cached_text.cache_info().currsize, 8192)

    def test_preview_reports_reference_stage_progress_before_completion(self):
        self.dataset()
        messages = []
        self.fixer.log = messages.append
        self.fixer.plan()
        updates = [json.loads(m.removeprefix('TOOLBOX_PROGRESS ')) for m in messages if m.startswith('TOOLBOX_PROGRESS ')]
        self.assertTrue(any('Checking saved references 1/' in u['detail'] for u in updates))
        self.assertEqual(updates[-1]['percent'], 100)
        self.assertEqual([u['percent'] for u in updates], sorted(u['percent'] for u in updates))


if __name__ == '__main__':
    unittest.main()
