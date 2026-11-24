import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import browser_bridge
import downloads
from browser_bridge import (BrowserBridge, BrowserCancelled, canonical, import_archives,
                            ready_downloads, request_archives, run_in_browser)
from downloads import Library, run_plan, unpack
from sources import AccessError, SourceError
from test_downloads import FakeClient, MATCH, bundle, fixture_map

MID = '1-12345678-1234-1234-1234-123456789abc'
OWNER = '12345678-1234-1234-1234-123456789abc'


class FakeBridge:
    def __init__(self):
        self.calls = []
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass
    def ask(self, mode, url):
        self.calls.append((mode, url))
        return {'claimed_at': time.time()}
    def check(self):
        pass


class BrowserTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[2] / 'data/.desktop/tests'
        base.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.watch = self.root / 'browser downloads'
        self.watch.mkdir()
        capture = redirect_stdout(io.StringIO())
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)

    def body(self, bridge, **extra):
        return {'version': 1, 'owner': OWNER, 'id': bridge.task['id'], 'url': bridge.task['url'], **extra}

    def task(self, bridge, mode='download'):
        bridge.task = {'id': 'task-id', 'mode': mode, 'url': canonical(MATCH['url']), 'status': 'pending'}

    def test_navigation_allowlist_and_filters_are_exact(self):
        self.assertEqual(canonical('https://hltv.org/results?team=5995&offset=100#anything'),
                         'https://www.hltv.org/results?offset=100&team=5995')
        for url in ['https://evil.test/matches/1/a', 'https://hltv.org.evil.test/matches/1/a',
                    'http://hltv.org/results', 'https://hltv.org:8766/results',
                    'https://www.faceit.com/api/secret', 'https://hltv.org/download/demo/42']:
            with self.assertRaises(SourceError):
                canonical(url)

    def test_authenticated_loopback_requests_and_host_validation(self):
        with BrowserBridge(opener=lambda _: None) as bridge:
            self.task(bridge)
            data = json.dumps(self.body(bridge)).encode()
            def request(token, host=None):
                headers = {'X-CS2-Token': token, 'Content-Type': 'application/json'}
                if host:
                    headers['Host'] = host
                return urlopen(Request(f'http://127.0.0.1:{bridge.port}/state', data=data, headers=headers), timeout=3)
            for token, host in [('wrong', None), (bridge.token, 'attacker.example')]:
                with self.assertRaises(HTTPError) as caught:
                    request(token, host)
                self.assertEqual(caught.exception.code, 403)
            with request(bridge.token) as response:
                self.assertEqual(json.load(response)['task']['id'], 'task-id')

    def test_duplicate_claim_stale_id_and_wrong_page_are_rejected(self):
        with BrowserBridge(opener=lambda _: None) as bridge:
            self.task(bridge)
            with self.assertRaises(SourceError):
                bridge.dispatch('/claim', self.body(bridge, id='old-task'))
            with self.assertRaises(SourceError):
                bridge.dispatch('/claim', self.body(bridge, url=MATCH['url'] + '?extraFilter=1'))
            bridge.dispatch('/claim', self.body(bridge))
            self.assertEqual(bridge.task['status'], 'claimed')
            with self.assertRaises(SourceError):
                bridge.dispatch('/claim', self.body(bridge))

    def test_second_tab_and_protocol_mismatch_fail_without_changing_task(self):
        with BrowserBridge(opener=lambda _: None) as bridge:
            self.task(bridge)
            bridge.dispatch('/state', self.body(bridge))
            with self.assertRaises(SourceError):
                bridge.dispatch('/claim', self.body(bridge, owner='another-tab-1234567890'))
            with self.assertRaises(SourceError):
                bridge.dispatch('/claim', self.body(bridge, version=99))
            self.assertEqual(bridge.task['status'], 'pending')

    def test_browser_login_or_connection_problem_stops_batch_without_skipping_other_matches(self):
        bridge = FakeBridge()
        def blocked(*_):
            raise browser_bridge.BrowserStopped('Login required')
        bridge.ask = blocked
        library_root = self.root / 'replays'
        with self.assertRaises(browser_bridge.BrowserStopped):
            run_in_browser({'matches': [MATCH, MATCH]}, library_root, self.watch,
                           bridge_factory=lambda: bridge, inspect=fixture_map)
        self.assertEqual(Library(library_root).data['matches'], {})

    def test_missing_companion_times_out_without_any_download(self):
        opened = []
        with BrowserBridge(opener=opened.append, timeout=.01) as bridge:
            with self.assertRaisesRegex(SourceError, 'did not respond'):
                bridge.ask('download', MATCH['url'])
        self.assertEqual(len(opened), 1)
        self.assertIn('#cs2toolbox=1&port=', opened[0])

    def test_only_completed_stable_identity_files_are_auto_selected(self):
        since = time.time() - 5
        unrelated = self.watch / 'unrelated.dem'
        unrelated.write_bytes(b'anything')
        actual = self.watch / (MID + '-1-1.dem.gz')
        actual.write_bytes(b'archive')
        partial = self.watch / (actual.name + '.crdownload')
        partial.write_bytes(b'partial')
        stable = {}
        self.assertEqual(ready_downloads(self.watch, {}, since, [MID], stable, now=0), [])
        partial.unlink()
        self.assertEqual(ready_downloads(self.watch, {}, since, [MID], stable, now=1), [])
        self.assertEqual(ready_downloads(self.watch, {}, since, [MID], stable, now=4.1), [actual])
        self.assertEqual(ready_downloads(self.watch, {}, since, [], stable, now=5), [])

    def test_start_detection_includes_partials_but_not_old_or_unrelated_completed_files(self):
        since = time.time() - 1
        unrelated = self.watch/'unrelated.zip';unrelated.write_bytes(b'archive')
        self.assertFalse(browser_bridge.download_activity(self.watch, {}, since, [MID]))
        partial = self.watch/'Unconfirmed 123.crdownload';partial.write_bytes(b'')
        self.assertTrue(browser_bridge.download_activity(self.watch, {}, since, [MID]))
        before = browser_bridge.files_snapshot(self.watch)
        self.assertFalse(browser_bridge.download_activity(self.watch, before, since, [MID]))
        partial.unlink()
        (self.watch/(MID+'.dem.gz.part')).write_bytes(b'')
        self.assertTrue(browser_bridge.download_activity(self.watch, before, since, [MID]))

    def test_retry_has_new_identity_and_late_download_prevents_second_click(self):
        with BrowserBridge(opener=lambda _: None) as bridge:
            self.task(bridge);bridge.dispatch('/claim', self.body(bridge, capabilities=['download-retry-v1']))
            self.assertIsNone(bridge.click_at)
            bridge.dispatch('/clicked', self.body(bridge, capabilities=['download-retry-v1']))
            old_id = bridge.task['id']
            bridge.watch_download(self.watch, {}, [MID])
            response = []
            def wait(_):
                self.assertNotEqual(bridge.task['id'], old_id)
                self.assertEqual(bridge.task['attempt'], 2)
                self.assertTrue(bridge.task['reload'])
                (self.watch/(MID+'.dem.gz.crdownload')).write_bytes(b'late start')
                response.append(bridge.dispatch('/claim', self.body(bridge, capabilities=['download-retry-v1'])))
                return True
            with patch.object(bridge.ready, 'wait', side_effect=wait):
                claim = bridge.retry_download()
            self.assertFalse(response[0]['click'])
            self.assertTrue(claim['download_observed'])
            self.assertIsNone(bridge.retry_download())

    def test_no_activity_retries_twice_then_requests_manual_help(self):
        from unittest.mock import Mock
        bridge = FakeBridge();bridge.retry_download = Mock(return_value={'claimed_at': time.time()});bridge.retry_capable = True
        match = {**MATCH, 'source': 'faceit', 'id': 'faceit:'+MID}
        clock = [0.0];select = Mock(return_value=[])
        def sleep(seconds):clock[0] += seconds
        with patch('browser_bridge.time.monotonic', side_effect=lambda: clock[0]), \
             patch('browser_bridge.time.sleep', side_effect=sleep):
            result = browser_bridge.await_archives(bridge, match, self.watch, {}, time.time(), select, timeout=30)
        self.assertEqual(result, [])
        self.assertEqual(bridge.retry_download.call_count, 2)
        self.assertIn('three attempts', select.call_args.args[2])

    def test_ongoing_partial_never_triggers_refresh(self):
        from unittest.mock import Mock
        bridge = FakeBridge();bridge.retry_download = Mock();bridge.retry_capable = True
        match = {**MATCH, 'source': 'faceit', 'id': 'faceit:'+MID}
        (self.watch/(MID+'.dem.gz.crdownload')).write_bytes(b'in progress')
        clock = [0.0]
        def sleep(seconds):clock[0] += seconds
        with patch('browser_bridge.time.monotonic', side_effect=lambda: clock[0]), \
             patch('browser_bridge.time.sleep', side_effect=sleep):
            browser_bridge.await_archives(bridge, match, self.watch, {}, time.time(), lambda *args: [], timeout=5)
        bridge.retry_download.assert_not_called()

    def test_import_preserves_original_and_records_all_series_maps(self):
        first, second = self.watch / 'map one.zip', self.watch / 'map two.zip'
        first.write_bytes(bundle(('anubis',)))
        second.write_bytes(bundle(('dust2',)))
        bridge = FakeBridge()
        selections = []
        def select(match, watch, reason):
            selections.append(reason)
            return [second]
        library_root = self.root / 'replays'
        with patch('browser_bridge.await_archives', return_value=[first]):
            code = run_in_browser({'matches': [deepcopy(MATCH)]}, library_root, self.watch,
                                  bridge_factory=lambda: bridge, select=select, inspect=fixture_map)
        self.assertEqual(code, 0)
        self.assertEqual(len(bridge.calls), 1)
        self.assertIn('dust2', selections[0])
        self.assertEqual(first.read_bytes(), bundle(('anubis',)))
        self.assertTrue(second.exists())
        library = Library(library_root)
        record = library.data['matches']['hltv:123']
        self.assertEqual(len(record['files']), 2)
        self.assertTrue(record['download_complete'])
        self.assertEqual(record['archive_provenance'], 'user_selected')
        # Repeating through either method must reuse the same library receipt.
        bridge.calls.clear()
        self.assertEqual(run_in_browser({'matches': [MATCH]}, library_root, self.watch,
                                        bridge_factory=lambda: bridge, inspect=fixture_map), 0)
        self.assertEqual(bridge.calls, [])
        client = FakeClient(bundle())
        self.assertEqual(run_plan({'matches': [MATCH]}, library_root, client=client, inspect=fixture_map), 0)
        self.assertEqual(client.opens, 0)

    def test_cancel_missing_map_preserves_partial_library_but_not_completion(self):
        archive = self.watch / 'only-map-one.zip'
        archive.write_bytes(bundle(('anubis',)))
        library_root = self.root / 'replays'
        with patch('browser_bridge.await_archives', return_value=[archive]):
            with self.assertRaises(BrowserCancelled):
                run_in_browser({'matches': [MATCH]}, library_root, self.watch, bridge_factory=FakeBridge,
                               select=lambda *_: (_ for _ in ()).throw(BrowserCancelled('Cancelled')), inspect=fixture_map)
        library = Library(library_root)
        self.assertFalse(library.data['matches']['hltv:123'].get('download_complete'))
        self.assertEqual(len(library.data['files']), 1)
        self.assertTrue(archive.exists())

    def test_manual_selection_cannot_import_partial_download(self):
        original = self.watch / 'demo.crdownload'
        original.write_bytes(b'partial')
        library = Library(self.root)
        staging = self.root / 'staging'
        staging.mkdir()
        with self.assertRaises(SourceError):
            import_archives(library, MATCH, [original], staging, fixture_map)
        self.assertEqual(library.data['files'], {})

    def test_zstandard_uses_existing_extraction_dependency(self):
        deps = str(Path(__file__).resolve().parents[2] / 'app/extractor/.deps')
        with patch.object(sys, 'path', [deps, *sys.path]):
            import pyarrow
            original = b'PBDEMS2\0anubis'
            compressed = bytes(pyarrow.Codec('zstd').compress(original))
            archive = self.root / 'demo.dem.zst'
            archive.write_bytes(compressed)
            result = unpack(archive, self.root / 'unpacked')
        self.assertEqual(result[0][0].read_bytes(), original)

    def test_api_signing_failure_enters_the_browser_fallback_class(self):
        client = FakeClient(b'anything')
        client.json = lambda *_args, **_kwargs: (_ for _ in ()).throw(SourceError('Service unavailable'))
        match = deepcopy(MATCH)
        match['source'] = 'faceit'
        with patch('downloads.get_secret', return_value='fake-token'):
            with self.assertRaises(AccessError):
                downloads.download(client, match, 'https://demos.faceit.com/resource', self.root / 'download.part')
        self.assertEqual(client.opens, 0)

    def test_automatic_worker_falls_back_but_direct_only_does_not(self):
        plan = self.root / 'plan.json'
        plan.write_text(json.dumps({'matches': [MATCH]}))
        for method in ('auto', 'direct'):
            args = ['downloads.py', '--run', str(plan), '--method', method, '--watch', str(self.watch)]
            with patch.object(sys, 'argv', args), patch('downloads.run_plan', side_effect=AccessError('Blocked')):
                with patch('browser_bridge.run_in_browser', return_value=0) as fallback:
                    code = downloads.main()
            self.assertEqual(code, 0 if method == 'auto' else 1)
            self.assertEqual(fallback.call_count, 1 if method == 'auto' else 0)


if __name__ == '__main__':
    unittest.main()
