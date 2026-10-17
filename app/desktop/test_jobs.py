import json
import queue
import tempfile
import unittest
from pathlib import Path

from jobs import JobRunner, build_extraction, build_viewer_export, python_executable


class DesktopTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[2] / 'data/.desktop/tests'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.demo = self.root / 'demo with spaces.dem'
        self.demo.write_bytes(b'command-validation fixture')

    def test_demo_path_with_spaces_stays_one_argument(self):
        cmd = build_extraction(source=str(self.demo), output=str(self.root / 'output folder'))
        self.assertEqual(cmd[cmd.index('--demo') + 1], str(self.demo))
        self.assertNotIn('--replace', cmd)

    def test_blank_input_cannot_silently_select_working_directory(self):
        for source, output in [('', str(self.root)), (str(self.demo), '')]:
            with self.assertRaises(ValueError):
                build_extraction(source=source, output=output, folder=True)

    def test_one_round_requires_matching_analysis_selection(self):
        with self.assertRaises(ValueError):
            build_extraction(source=str(self.demo), output=str(self.root), entities=True, round_number='24')
        analysis = self.root / 'analysis'
        analysis.mkdir()
        (analysis / 'rounds.csv').write_text('round\n24\n')
        cmd = build_extraction(source=str(self.demo), output=str(self.root), entities=True,
                               round_number='24', analysis=str(analysis), replace=True)
        self.assertIn('--entities-only', cmd)
        self.assertIn('--replace', cmd)
        self.assertEqual(cmd[-3:-1], ['--round', '24'])

    def test_viewer_cannot_export_outside_analysis_root(self):
        (self.root / 'rounds.csv').write_text('round\n1\n')
        (self.root / 'viewer_tracks.csv.gz').write_bytes(b'fixture')
        with self.assertRaises(ValueError):
            build_viewer_export(self.root, '1')

    def finish(self, events):
        while True:
            kind, value = events.get(timeout=15)
            if kind == 'finished':
                return value[0]

    def test_failed_job_saves_exit_code_and_full_log(self):
        events = queue.Queue()
        runner = JobRunner(events, self.root)
        runner.start('Failure fixture', [python_executable(), '-c', "print('test output');raise SystemExit(7)"])
        record = self.finish(events)
        self.assertEqual(record['status'], 'Failed')
        self.assertEqual(record['returncode'], 7)
        self.assertIn('test output', Path(record['log']).read_text())
        self.assertEqual(json.loads((self.root / 'history.json').read_text())[0]['status'], 'Failed')

    def test_successful_job_and_single_job_guard(self):
        events = queue.Queue()
        runner = JobRunner(events, self.root)
        runner.start('Success fixture', [python_executable(), '-c', "import time;print('ready',flush=True);time.sleep(.2)"])
        with self.assertRaises(RuntimeError):
            runner.start('Second task', [python_executable(), '-c', 'pass'])
        self.assertEqual(self.finish(events)['status'], 'Completed')

    def test_stop_cancels_a_running_job(self):
        events = queue.Queue()
        runner = JobRunner(events, self.root)
        runner.start('Cancellation fixture', [python_executable(), '-c', "import time;print('ready',flush=True);time.sleep(30)"])
        while True:
            kind, line = events.get(timeout=15)
            if kind == 'line' and 'ready' in line:
                break
        runner.stop()
        self.assertEqual(self.finish(events)['status'], 'Stopped')


if __name__ == '__main__':
    unittest.main()
