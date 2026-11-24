import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import native_demo_compat as compat


class CopyTests(unittest.TestCase):
    def setUp(self):
        base=compat.STATE/'demo-compat-tests';base.mkdir(parents=True,exist_ok=True)
        temp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.replays=self.root/'replays';self.replays.mkdir();self.source=self.replays/'original.dem'
        self.source.write_bytes(b'original replay fixture');self.sha=compat.checksum(self.source)
        self.state=self.root/'state';self.state.mkdir()
        patches=[patch.object(compat,'STATE',self.state),patch.object(compat.replays,'DEFAULT_REPLAYS',self.replays),
                 patch.object(compat.shutil,'which',return_value='node.exe')]
        for p in patches:p.start();self.addCleanup(p.stop)

    def processor(self,needed=True,proof=True):
        def run(args,**kwargs):
            data={'source_sha256':self.sha,'report':{'crashFix':{'needed':needed}}}
            if needed:
                destination=Path(args[-1]);destination.write_bytes(b'private compatibility fixture')
                data.update(playback_sha256=compat.checksum(destination),verification={'gameplay_messages_identical':proof})
            return Mock(returncode=0,stdout=json.dumps(data),stderr='')
        return run

    def test_original_download_is_the_only_accepted_input(self):
        with patch.object(compat.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'original downloads'):compat.prepare(self.root/'other.dem',self.sha,'runtime')
            run.assert_not_called()

    def test_unaffected_recording_uses_original_and_caches_the_inspection(self):
        with patch.object(compat.subprocess,'run',side_effect=self.processor(False)) as run:
            a=compat.prepare(self.source,self.sha,'runtime');b=compat.prepare(self.source,self.sha,'runtime')
            self.assertEqual(a['path'],self.source.resolve());self.assertFalse(b['applied']);self.assertEqual(run.call_count,1)

    def test_copy_preserves_original_and_requires_separate_game_validation(self):
        with patch.object(compat.subprocess,'run',side_effect=self.processor()) as run:
            result=compat.prepare(self.source,self.sha,'runtime',allow_unverified=True)
            self.assertNotEqual(result['path'],self.source);self.assertEqual(compat.checksum(self.source),self.sha)
            with self.assertRaisesRegex(ValueError,'not been validated'):compat.prepare(self.source,self.sha,'runtime')
            self.assertEqual(run.call_count,1)

    def test_bad_gameplay_proof_never_publishes_or_launches_a_copy(self):
        with patch.object(compat.subprocess,'run',side_effect=self.processor(proof=False)):
            with self.assertRaisesRegex(ValueError,'gameplay-preservation'):compat.prepare(self.source,self.sha,'runtime',allow_unverified=True)
        self.assertFalse(list(self.state.rglob('manifest.json')));self.assertFalse(list(self.state.rglob('pending-*.dem')))
        self.assertEqual(compat.checksum(self.source),self.sha)

    def test_tampered_cache_is_rejected_and_original_is_unchanged(self):
        with patch.object(compat.subprocess,'run',side_effect=self.processor()):
            result=compat.prepare(self.source,self.sha,'runtime',allow_unverified=True)
            result['path'].write_bytes(b'changed copy')
            with self.assertRaisesRegex(ValueError,'copy changed'):compat.prepare(self.source,self.sha,'runtime',allow_unverified=True)
        self.assertEqual(compat.checksum(self.source),self.sha)

    def test_crashed_copy_is_not_relaunched_for_the_same_demo_build_and_adapter(self):
        with patch.object(compat.subprocess,'run',side_effect=self.processor()):
            result=compat.prepare(self.source,self.sha,'runtime',allow_unverified=True)
        compat.record_crash('runtime',result)
        with self.assertRaisesRegex(ValueError,'already crashed'):compat.prepare(self.source,self.sha,'runtime',allow_unverified=True)


if __name__=='__main__':unittest.main()
