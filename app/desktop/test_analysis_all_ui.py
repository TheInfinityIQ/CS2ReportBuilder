"""Application-owned command/confirmation checks without desktop automation."""
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
import main


class AnalyzeAllControls(TestCase):
    def fixture(self):
        return SimpleNamespace(launch_job=Mock(), var=lambda *args: SimpleNamespace(get=lambda: args[-1]),
                               analysis_all_plan=Path('review.json'))

    def test_preview_uses_background_job_and_cannot_start_analysis(self):
        app = self.fixture()
        main.Toolbox.preview_analysis_all(app)
        args, kwargs = app.launch_job.call_args
        self.assertIn('--preview', args[1]);self.assertNotIn('--execute', args[1])
        self.assertEqual(kwargs['callback'], 'analysis_all_review')

    def test_review_decline_does_nothing_and_accept_executes_reviewed_plan(self):
        app = self.fixture()
        plan = {'replays': 'replays', 'analysis': 'analysis', 'issues': [],
                'counts': {'recordings': 2, 'references': 3, 'analysis_needed': 1, 'download_needed': 1}}
        with patch.object(main, 'read_json', return_value=plan), patch.object(main.messagebox, 'askyesno', return_value=False):
            main.Toolbox.confirm_analysis_all(app)
        app.launch_job.assert_not_called()
        with patch.object(main, 'read_json', return_value=plan), patch.object(main.messagebox, 'askyesno', return_value=True) as confirm:
            main.Toolbox.confirm_analysis_all(app)
        command = app.launch_job.call_args.args[1]
        self.assertIn('--execute', command)
        self.assertEqual(command[command.index('--execute')+1], str(app.analysis_all_plan))
        self.assertIn('1 need analysis', confirm.call_args.args[1])
