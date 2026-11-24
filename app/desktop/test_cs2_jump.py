import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import cs2_jump as jump


class JumpTests(unittest.TestCase):
    def setUp(self):
        base=Path(__file__).parent/'.test_cs2_jump_tmp';base.mkdir(exist_ok=True)
        t=tempfile.TemporaryDirectory(dir=base);self.addCleanup(t.cleanup);self.root=Path(t.name)
        self.index=self.root/'index.json'
        patcher=patch.object(jump.replays,'DEFAULT_REPLAYS',self.root);patcher.start();self.addCleanup(patcher.stop)
        patcher=patch.object(jump.replays,'CACHE',self.root/'replay-cache.json');patcher.start();self.addCleanup(patcher.stop)
        patcher=patch.object(jump,'INDEX',self.index);patcher.start();self.addCleanup(patcher.stop)
        patcher=patch.object(jump,'STATE',self.root);patcher.start();self.addCleanup(patcher.stop)
        self.demo=self.root/'[13-10]_a-vs-b.dem';self.demo.write_bytes(b'PBDEMS2\0fixture')
        self.sha=hashlib.sha256(self.demo.read_bytes()).hexdigest()
        self.folder=self.root/'analysis';self.folder.mkdir()
        (self.folder/'viewer_tracks_meta.json').write_text(json.dumps({'demo_sha256':self.sha}))
        (self.folder/'match_summary.json').write_text('{"end_tick":50000}')
        self.assertTrue(jump.register_analysis(self.folder,self.sha))

    def test_link_only_accepts_registered_hash_and_integer_tick_shape(self):
        self.assertEqual(jump.parse_link(f'cs2toolbox://watch?demo={self.sha}&tick=42000'),(self.sha,42000))
        for suffix in ['&path=C:/x.dem','&tick=3',';quit','%0Aquit']:
            with self.assertRaises(ValueError):jump.parse_link(f'cs2toolbox://watch?demo={self.sha}&tick=42'+suffix)
        for link in ['file:///a.dem',f'cs2toolbox://watch?demo={self.sha}&tick=-1',f'cs2toolbox://watch?demo={self.sha}&tick=4.2']:
            with self.assertRaises(ValueError):jump.parse_link(link)

    def test_correct_download_found_and_missing_demo_never_opens_a_picker(self):
        with patch.object(jump,'candidates',return_value=[self.demo]):
            self.assertEqual(jump.resolve_demo(self.sha,42000),self.demo)
        chooser=Mock(return_value=str(self.demo))
        with patch.object(jump,'candidates',return_value=[]):
            with self.assertRaisesRegex(ValueError,'not downloaded in replays'):jump.resolve_demo(self.sha,42000,chooser)
        chooser.assert_not_called()

    def test_outside_known_tick_range_or_unregistered_hash_rejected(self):
        with self.assertRaisesRegex(ValueError,'outside'):jump.resolve_demo(self.sha,50001)
        with self.assertRaisesRegex(ValueError,'not registered'):jump.resolve_demo('a'*64,42)

    def test_unsafe_console_paths_and_ticks_rejected(self):
        for name in ['x;quit.dem','x"quit.dem','x\nquit.dem','caf\u00e9.dem']:
            with self.assertRaises(ValueError):jump.console_path(self.root/name)
        self.assertIn('[13-10]',jump.console_path(self.demo))
        for n in [True,-1,1.5,1000000000]:
            with self.assertRaises(ValueError):jump.jump_command(n)

    def test_already_running_game_is_never_restarted(self):
        with patch.object(jump,'is_running',return_value=True),patch.object(jump.subprocess,'Popen') as start:
            with self.assertRaisesRegex(ValueError,'already running'):jump.launch(self.demo,42000,lambda _:None)
            start.assert_not_called()

    def test_unverified_launch_does_not_start_game_or_write_settings(self):
        game=self.root/'game';(game/'bin/win64').mkdir(parents=True);(game/'bin/win64/cs2.exe').touch()
        steam=self.root/'steam.exe';steam.touch()
        (self.root/'settings.json').write_text(json.dumps({'steam_executable':str(steam)}))
        before={str(p.relative_to(game)):p.read_bytes() for p in game.rglob('*') if p.is_file()};states=[]
        with patch.object(jump,'is_running',return_value=False),patch.object(jump.subprocess,'Popen') as start:
            with self.assertRaisesRegex(ValueError,'settings preservation'):
                jump.launch(self.demo,42000,states.append,game=game)
            start.assert_not_called()
        self.assertEqual({str(p.relative_to(game)):p.read_bytes() for p in game.rglob('*') if p.is_file()},before)


if __name__=='__main__':unittest.main()
