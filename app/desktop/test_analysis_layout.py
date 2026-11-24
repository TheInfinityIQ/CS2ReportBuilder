import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jobs import ROOT, build_extraction, build_viewer_export
from analysis_layout import analysis_name, component, destination
from downloads import Library, analyze
import downloads
from test_downloads import MATCH


class LayoutTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'data/.desktop/tests'
        base.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.library = Library(self.root)
        staged = self.root / 'fixture.part'
        staged.write_bytes(b'PBDEMS2\0fixture')
        capture = redirect_stdout(io.StringIO())
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)
        self.digest = self.library.add(MATCH, staged, MATCH['maps'][0], 'fixture.dem')

    def complete(self, command, **_):
        source = Path(command[command.index('--demo') + 1])
        parent = Path(command[command.index('--output') + 1])
        output = parent / command[command.index('--analysis-name') + 1]
        output.mkdir(parents=True)
        (output / 'match_summary.json').write_text('{"valid":true}')
        (output / 'viewer_tracks_meta.json').write_text(json.dumps({'demo_sha256': self.digest}))
        (output / 'analysis_run.json').write_text(json.dumps({'demo_count': 1, 'success_count': 1,
                                                            'results': [{'demo': source.name}]}))
        return SimpleNamespace(returncode=0)

    def test_tournament_map_match_and_normalized_demo_name(self):
        result = destination(self.root, {'source': 'hltv', 'owner': 'Team A', 'event': 'Test Tournament'},
                             'de_inferno', '[13-9]_Team A-vs-Team B_Oct-31-2026_inferno_Test Tournament')
        self.assertEqual(result.relative_to(self.root).parts[:-1], ('Test_Tournament', 'inferno'))
        self.assertTrue(result.name.startswith('Analysis_[13-9]_Team_A-vs-Team_B_'))
        self.assertNotIn(' ', str(result))

    def test_player_layout_is_distinct_from_faceit_team_layout(self):
        player = {'source': 'faceit', 'owner': 'Player Name', 'label': 'Player Name', 'collection_kind': 'player'}
        result = destination(self.root, player, 'anubis', 'demo name')
        self.assertEqual(result.relative_to(self.root).parts, ('Analysis_Player_Name', 'anubis', 'Analysis_demo_name'))
        team = {**player, 'collection_kind': 'team', 'event': 'ESEA League S59 Open9-10'}
        result = destination(self.root, team, 'anubis', 'demo name')
        self.assertEqual(result.relative_to(self.root).parts[:-1], ('ESEA_League_S59_Open9-10', 'anubis'))

    def test_spaces_in_analysis_root_rejected_but_raw_demo_spaces_supported(self):
        source = self.root / 'raw demo with spaces.dem'
        source.write_bytes(b'fixture')
        with self.assertRaisesRegex(ValueError, 'cannot contain spaces'):
            build_extraction(source=str(source), output=str(self.root / 'bad output'))
        command = build_extraction(source=str(source), output=str(self.root / 'Analysis_Player'))
        self.assertIn('--organized-output', command)
        self.assertEqual(command[command.index('--demo') + 1], str(source))

    def test_sanitizing_names_handles_unicode_whitespace_and_reserved_names(self):
        self.assertEqual(component('Team\u00a0Name\tHere'), 'Team_Name_Here')
        self.assertEqual(component('NUL'), '_NUL')
        self.assertNotIn('/', component('../outside'))
        self.assertNotIn(' ', analysis_name('some demo'))
        self.assertNotEqual(component('a' * 200 + 'b'), component('a' * 200 + 'c'))

    def test_pipeline_uses_named_folders_and_individual_receipt(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            return self.complete(command, **kwargs)
        with patch.object(downloads, 'ANALYSIS', self.root / 'analysis'):
            self.assertEqual(analyze(self.library, [self.digest], run=run), [])
            path = Path(self.library.data['files'][self.digest]['analysis']['output'])
            self.assertEqual(path.relative_to(self.root / 'analysis').parts[:-1], ('Test_Cup', 'anubis'))
            self.assertTrue(path.name.startswith('Analysis_'))
            self.assertNotIn(' ', str(path))
            # A sibling's batch-level summary must not invalidate this demo's receipt.
            (path.parent / 'batch_run_summary.json').write_text('{"failure_count":1}')
            self.assertEqual(analyze(self.library, [self.digest], run=run), [])
        self.assertEqual(len(calls), 1)
        self.assertNotIn('--organized-output', calls[0])

    def test_both_team_selections_reuse_one_match_analysis(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            return self.complete(command, **kwargs)
        first = {**MATCH, 'collection_kind': 'team', 'owner': 'G2'}
        second = {**MATCH, 'collection_kind': 'team', 'owner': 'Vitality'}
        with patch.object(downloads, 'ANALYSIS', self.root / 'analysis'):
            self.assertEqual(analyze(self.library, [self.digest], run=run, contexts={self.digest: first}), [])
            original = self.library.data['files'][self.digest]['analysis']['output']
            self.assertEqual(analyze(self.library, [self.digest], run=run, contexts={self.digest: second}), [])
            self.assertEqual(self.library.data['files'][self.digest]['analysis']['output'], original)
        self.assertEqual(len(calls), 1)

    def test_active_download_context_controls_layout_when_demo_is_reused(self):
        player = {'id': 'faceit:fixture', 'source': 'faceit', 'owner': 'Player Name', 'label': 'Player Name',
                  'collection_kind': 'player', 'selected_player_id': '12345678-1234-1234-1234-123456789abc'}
        with patch.object(downloads, 'ANALYSIS', self.root / 'analysis'):
            self.assertEqual(analyze(self.library, [self.digest], run=self.complete, contexts={self.digest: player}), [])
        result = Path(self.library.data['files'][self.digest]['analysis']['output'])
        self.assertEqual(result.parts[-3:-1], ('Analysis_Player_Name', 'anubis'))
        provenance = json.loads((result / 'analysis_source.json').read_text())
        self.assertEqual(provenance['context']['selected_player_id'], player['selected_player_id'])
        self.assertEqual(provenance['context']['source'], 'faceit')

    def test_completed_output_from_a_different_demo_cannot_report_success(self):
        def wrong(command, **kwargs):
            self.complete(command, **kwargs)
            parent = Path(command[command.index('--output') + 1])
            folder = parent / command[command.index('--analysis-name') + 1]
            (folder / 'viewer_tracks_meta.json').write_text('{"demo_sha256":"another-demo"}')
            return SimpleNamespace(returncode=0)
        with patch.object(downloads, 'ANALYSIS', self.root / 'analysis'):
            self.assertEqual(len(analyze(self.library, [self.digest], run=wrong)), 1)

    def test_legacy_outputs_and_history_are_preserved(self):
        old = self.root / 'legacy analysis'
        old.mkdir()
        sentinel = old / 'original.json'
        sentinel.write_text('keep')
        self.library.data['files'][self.digest]['analysis'] = {'status': 'completed', 'output': str(old), 'hz': '16'}
        with patch.object(downloads, 'ANALYSIS', self.root / 'analysis'):
            self.assertEqual(analyze(self.library, [self.digest], run=self.complete), [])
        self.assertEqual(sentinel.read_text(), 'keep')
        self.assertIn(str(old), self.library.data['files'][self.digest]['analysis_outputs'])

    def test_viewer_command_accepts_new_nested_analysis_folders(self):
        base = ROOT / 'data/analysis'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='_layout_fixture_', dir=base) as temporary:
            path = Path(temporary) / 'Tournament' / 'inferno' / 'Analysis_demo'
            path.mkdir(parents=True)
            (path / 'rounds.csv').write_text('round\n1\n')
            (path / 'viewer_tracks.csv.gz').write_bytes(b'path-validation fixture')
            command = build_viewer_export(path, '1')
            self.assertTrue(command[command.index('--source') + 1].endswith('Tournament/inferno/Analysis_demo'))


class ExtractorNamingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'app/extractor/extract_demos_v8.py'
        sys.path.insert(0, str(path.parent))
        spec = importlib.util.spec_from_file_location('extractor_layout_fixture', path)
        cls.extractor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.extractor)

    def setUp(self):
        base = ROOT / 'data/.desktop/tests'
        base.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.demo = self.root / 'demo with spaces.dem'
        self.demo.write_bytes(b'CLI naming fixture, never parsed')

    def cli(self, flags):
        argv = ['extract_demos_v8.py', '--demo', str(self.demo), '--output', str(self.root / 'Analysis_Player'), *flags]
        parser = SimpleNamespace(parse_header=lambda: {'map_name': 'de_inferno'})
        with patch.object(self.extractor, 'PROJECT_ROOT', self.root), patch('sys.argv', argv), patch.object(self.extractor, 'DemoParser', return_value=parser), patch.object(self.extractor, 'main', return_value=0) as main:
            self.assertEqual(self.extractor.cli(), 0)
            main.assert_called_once()
        return self.extractor.demo_output(self.demo)

    def test_organized_cli_outputs_map_folder_without_copying_or_renaming_demo(self):
        target = self.cli(['--organized-output'])
        self.assertEqual(target.parts[-3:], ('Analysis_Player', 'inferno', 'Analysis_demo_with_spaces'))
        self.assertTrue(self.demo.is_file())
        self.assertFalse(target.exists())  # only naming/preflight ran, no extraction
        self.assertEqual(self.extractor.invalid_output(self.demo).name, 'Analysis_demo_with_spaces__INVALID_v8')

    def test_named_single_demo_target_is_used_by_all_passes(self):
        target = self.cli(['--analysis-name', 'Analysis_custom-demo'])
        self.assertEqual(target.name, 'Analysis_custom-demo')

    def test_extraction_waits_for_directory_maintenance_before_parsing(self):
        from extractor.job_lock import exclusive
        with patch.object(self.extractor, 'PROJECT_ROOT', self.root), exclusive(self.root / '.desktop/analysis-maintenance.lock'):
            with patch.object(self.extractor, 'DemoParser') as parser:
                with self.assertRaisesRegex(RuntimeError, 'another job'):
                    self.cli(['--organized-output'])
                parser.assert_not_called()

    def test_legacy_cli_remains_compatible_for_other_existing_workers(self):
        self.assertEqual(self.cli([]).name, 'demo with spaces')

    def test_invalid_named_targets_and_normalized_collisions_are_rejected_before_analysis(self):
        for name in ('bad name', '../outside'):
            argv = ['extract_demos_v8.py', '--demo', str(self.demo), '--output', str(self.root / 'output'), '--analysis-name', name]
            with patch('sys.argv', argv), patch.object(self.extractor, 'main') as main, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    self.extractor.cli()
                main.assert_not_called()
        (self.root / 'demo_with_spaces.dem').write_bytes(b'another naming fixture')
        argv = ['extract_demos_v8.py', '--demos', str(self.root), '--output', str(self.root / 'output'), '--organized-output']
        parser = SimpleNamespace(parse_header=lambda: {'map_name': 'de_inferno'})
        with patch.object(self.extractor, 'PROJECT_ROOT', self.root), patch('sys.argv', argv), patch.object(self.extractor, 'DemoParser', return_value=parser), patch.object(self.extractor, 'main') as main, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.extractor.cli()
            main.assert_not_called()


if __name__ == '__main__':
    unittest.main()
