import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import validate_pool


class MapValidationTests(unittest.TestCase):
    def test_failed_run_cannot_reuse_an_earlier_success(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            old = cache/'embedded-check'
            old.mkdir()
            (old/'result.json').write_text('{"ok": true}', encoding='utf-8')
            fixture = cache/'validation/pool/de_anubis/fixture.json'
            fixture.parent.mkdir(parents=True)
            process = subprocess.CompletedProcess([], 1, '', 'Renderer failed')
            with patch.object(validate_pool, 'CACHE', cache), patch.object(validate_pool, 'fixtures', return_value=[fixture]):
                with patch.object(validate_pool.subprocess, 'run', return_value=process) as run:
                    with patch('sys.argv', ['validate_pool.py']):
                        self.assertEqual(validate_pool.main(), 1)
            argv = run.call_args.args[0]
            output = Path(argv[argv.index('--output-dir') + 1])
            self.assertEqual(output.parent, fixture.parent)
            self.assertTrue(output.is_dir())
            result = json.loads((fixture.parent/'result.json').read_text(encoding='utf-8'))
            self.assertFalse(result['ok'])
            self.assertIn('without a validation report', result['error'])
