import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from analyze import ROOT, toolbox_reports
from session_bundle import create, validate


class SessionBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'reports');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.analysis=self.root/'analysis';self.folder=self.analysis/'sample';self.folder.mkdir(parents=True)
        self.state=patch.object(toolbox_reports,'STATE',self.root/'state');self.state.start();self.addCleanup(self.state.stop)
        for name,value in [('match_summary.json',{'schema_version':'fixture','tickrate':64}),('viewer_tracks_meta.json',{'demo_sha256':'demo'})]:
            (self.folder/name).write_text(json.dumps(value))
        (self.folder/'not-used-in-report.bin').write_bytes(b'\x00\xffcomplete raw data')
        self.snapshot={'version':'1.0','analysis':str(self.analysis),'target':{'steamid':'76561198000000000','name':'Fixture'},
                       'selection':{'limit':1},'totals':{},'games':[{'sha':'demo','game':'game','source':'sample','rounds':[],'excluded_rounds':[],
                         'inputs':{'match_summary.json':hashlib.sha256((self.folder/'match_summary.json').read_bytes()).hexdigest()}}]}
        self.evidence=self.root/'evidence.json';self.evidence.write_text(json.dumps(self.snapshot))
        self.coaching=self.root/'coaching.json';self.coaching.write_text('{"practice":"fixture"}')
        self.report=self.root/'report.html';self.report.write_text('<html>Fixture</html>')
        self.build={'summary':{'total':0,'within2':0,'twoToTen':0,'later':0,'survived':0},'evidence_digest':'fixture'}
        for key,path in [('analysis_sha256',self.evidence),('coaching_sha256',self.coaching),('report_sha256',self.report)]:self.build[key]=hashlib.sha256(path.read_bytes()).hexdigest()
        self.report.with_suffix('.build.json').write_text(json.dumps(self.build));self.output=self.root/'session.zip'

    def export(self):return create(self.evidence,self.coaching,self.report,self.output)

    def test_complete_source_round_trip_and_identity(self):
        result=self.export();self.assertEqual(result['source_files'],3)
        with zipfile.ZipFile(self.output) as z:
            self.assertEqual(z.read('analysis/0001/not-used-in-report.bin'),b'\x00\xffcomplete raw data')
            self.assertEqual(json.loads(z.read('session.json'))['player']['steamid'],'76561198000000000')
        self.assertEqual(validate(self.output)['source_files'],3)

    def test_editorial_revision_keeps_prior_session_relationship(self):
        self.coaching.write_text(json.dumps(dict(previous_session_ids=['session-old'],
                         session_relationship='Same games; editorial revision, not progress')))
        self.build['coaching_sha256']=hashlib.sha256(self.coaching.read_bytes()).hexdigest()
        self.report.with_suffix('.build.json').write_text(json.dumps(self.build))
        self.export()
        with zipfile.ZipFile(self.output) as z:
            session=json.loads(z.read('session.json'))
        self.assertEqual(session['previous_session_ids'],['session-old'])
        self.assertIn('not progress',session['session_relationship'])

    def test_changed_editorial_input_and_existing_output_are_preserved(self):
        self.export();original=self.output.read_bytes()
        with self.assertRaisesRegex(ValueError,'Archive exists'):self.export()
        self.coaching.write_text('changed')
        with self.assertRaisesRegex(ValueError,'fingerprints differ'):create(self.evidence,self.coaching,self.report,self.output,True)
        self.assertEqual(self.output.read_bytes(),original)

    def test_unlisted_extra_member_and_traversal_are_rejected(self):
        self.export()
        with zipfile.ZipFile(self.output,'a') as z:z.writestr('unlisted.txt','bad')
        with self.assertRaisesRegex(ValueError,'membership'):validate(self.output)
        bad=self.root/'unsafe.zip'
        with zipfile.ZipFile(bad,'w') as z:z.writestr('../escape','bad')
        with self.assertRaisesRegex(ValueError,'Unsafe'):validate(bad)

    def test_mutation_of_unused_source_aborts_without_publishing(self):
        import session_bundle
        original=session_bundle.shutil.copyfile
        def changing(src,dst):
            result=original(src,dst)
            if Path(src).name=='not-used-in-report.bin':Path(src).write_bytes(b'changed concurrently')
            return result
        with patch.object(session_bundle.shutil,'copyfile',side_effect=changing):
            with self.assertRaisesRegex(ValueError,'changed during snapshot'):self.export()
        self.assertFalse(self.output.exists())

    def test_changed_directory_membership_aborts(self):
        import session_bundle
        original=session_bundle.shutil.copyfile
        def adding(src,dst):
            result=original(src,dst)
            if Path(src).name=='not-used-in-report.bin':(Path(src).parent/'new-file').write_text('new')
            return result
        with patch.object(session_bundle.shutil,'copyfile',side_effect=adding):
            with self.assertRaisesRegex(ValueError,'changed during snapshot'):self.export()
        self.assertFalse(self.output.exists())


if __name__=='__main__':unittest.main()
