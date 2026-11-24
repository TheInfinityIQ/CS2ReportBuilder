import gzip
import io
import json
import os
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import downloads
from credentials import get_secret
from downloads import Library, analyze, asset_key, filename, library_lock, run_plan, safe_name, unpack
from sources import AccessError, Resolver, SourceError, classify_link, hltv_match, parse_html


MATCH = {'id': 'hltv:123', 'source': 'hltv', 'url': 'https://www.hltv.org/matches/123/a-vs-b',
         'teams': ['G2', 'Vitality'], 'owner': 'G2', 'label': 'G2-vs-Vitality',
         'event': 'Test Cup', 'date': '2026-10-31',
         'maps': [{'map': 'anubis', 'score': [13, 9]}, {'map': 'dust2', 'score': [7, 13]}],
         'downloads': ['https://www.hltv.org/download/demo/42']}


class FakeClient:
    def __init__(self, content):
        self.content, self.opens, self.posts = content, 0, []

    def open(self, url):
        self.opens += 1
        value = io.BytesIO(self.content)
        value.headers = {'Content-Length': str(len(self.content))}
        return value

    def json(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return {'payload': {'download_url': 'https://cdn.example/demo.gz?temporary=secret'}}


def bundle(maps=('anubis', 'dust2')):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name in maps:
            archive.writestr(name + '.dem', b'PBDEMS2\0' + name.encode())
    return output.getvalue()


def fixture_map(path):
    return path.read_bytes()[8:].decode()


class DownloadTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[2] / 'data/.desktop/tests'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        capture = redirect_stdout(io.StringIO())
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)

    def test_five_link_types_and_count_scope(self):
        links = [('faceit.com/en/players/CanadianIQ/stats/cs2', 'player'),
                 ('https://www.faceit.com/en/cs2/room/1-12345678-1234-1234-1234-123456789abc/scoreboard', 'match'),
                 ('https://www.hltv.org/events/42/test', 'tournament'),
                 ('https://www.hltv.org/matches/42/test', 'match'),
                 ('https://www.hltv.org/team/5995/g2', 'team')]
        for link, kind in links:
            self.assertEqual(classify_link(link)['kind'], kind)
        for link in ('https://hltv.org.evil.test/team/1/a', 'https://faceit.com@evil.test/en/players/a',
                     'file:///etc/passwd', 'http://faceit.com/en/players/a', 'https://hltv.org:8443/team/1/a',
                     'http://hltv.org:8080/matches/42/a', 'http://hltv.org.evil.test/matches/42/a',
                     'http://name@hltv.org/matches/42/a', 'http://@hltv.org/matches/42/a'):
            with self.assertRaises(ValueError):
                classify_link(link)

    def test_legacy_hltv_match_downloads_every_map_in_the_series(self):
        path = '/matches/2399737/vitality-vs-fut-pgl-masters-bucharest-2026'
        canonical = 'https://www.hltv.org' + path
        html = '''<div class="teamsBox"><div class="teamName">Vitality</div><div class="teamName">FUT</div>
        <div class="date" data-unix="1793013600000"></div><div class="timeAndEvent">
        <a href="/events/42/test">PGL Masters Bucharest 2026</a></div></div>'''
        for name, left, right in [('Mirage', 13, 9), ('Dust 2', 9, 13), ('Anubis', 10, 13)]:
            html += f'''<div class="mapholder"><div class="mapname">{name}</div>
            <div class="results-left"><span class="results-team-score">{left}</span></div>
            <div class="results-right"><span class="results-team-score">{right}</span></div></div>'''
        html += '<a data-demo-link="/download/demo/42">Demo download</a>'
        pages = SimpleNamespace(html=lambda url: self.assertEqual(url, canonical) or parse_html(html))
        resolver = Resolver(client=pages)
        for prefix in ('hltv.org', 'http://www.hltv.org', 'http://hltv.org:80', 'https://hltv.org'):
            self.assertEqual(classify_link(prefix + path)['url'], canonical)
        plan = resolver.resolve('http://hltv.org' + path)
        maps = ('mirage', 'dust2', 'anubis')
        client = FakeClient(bundle(maps))
        self.assertEqual(run_plan(plan, self.root, client=client, inspect=fixture_map), 0)
        library = Library(self.root)
        match = library.data['matches']['hltv:2399737']
        self.assertTrue(match['download_complete'])
        self.assertEqual({library.data['files'][key]['map'] for key in match['files']}, set(maps))
        self.assertEqual(run_plan(resolver.resolve(canonical), self.root, client=client, inspect=fixture_map), 0)
        self.assertEqual(client.opens, 1)

    def test_filename_map_score_and_windows_sanitizing(self):
        self.assertEqual(filename(MATCH, MATCH['maps'][0]), '[13-9]_G2-vs-Vitality_Oct-31-2026_anubis_Test Cup.dem')
        self.assertEqual(safe_name('NUL'), '_NUL')
        self.assertNotIn('/', safe_name('player/with:bad?characters'))

    def test_full_series_index_and_second_run_does_not_download(self):
        client = FakeClient(bundle())
        plan = {'matches': [deepcopy(MATCH)], 'unavailable': []}
        self.assertEqual(run_plan(plan, self.root, client=client, inspect=fixture_map), 0)
        library = Library(self.root)
        series = library.data['matches']['hltv:123']
        self.assertEqual(len(series['files']), 2)
        paths = [library.path(library.data['files'][digest]) for digest in series['files']]
        self.assertEqual({path.parent.parent.name for path in paths}, {'anubis', 'dust2'})
        self.assertTrue(all(path.parent.name == 'G2' for path in paths))
        plan['matches'][0]['owner'] = 'Vitality'
        self.assertEqual(run_plan(plan, self.root, client=client, inspect=fixture_map), 0)
        self.assertEqual(client.opens, 1)
        self.assertIn('Vitality', Library(self.root).data['matches']['hltv:123']['contexts'])

    def test_deleted_or_changed_file_is_not_treated_as_downloaded(self):
        client = FakeClient(bundle())
        plan = {'matches': [deepcopy(MATCH)]}
        run_plan(plan, self.root, client=client, inspect=fixture_map)
        lib = Library(self.root)
        digest = next(iter(lib.data['files']))
        path = lib.path(lib.data['files'][digest])
        path.write_bytes(b'corrupt')
        self.assertFalse(lib.asset_files(asset_key(MATCH, MATCH['downloads'][0])))
        self.assertEqual(run_plan(plan, self.root, client=client, inspect=fixture_map), 0)
        self.assertEqual(client.opens, 2)
        self.assertEqual(path.read_bytes(), b'corrupt')  # never replace an existing file
        self.assertTrue(Library(self.root).valid(digest))

    def test_unindexed_duplicate_is_adopted_without_second_copy(self):
        old = self.root / 'old-name.dem'
        old.write_bytes(b'PBDEMS2\0anubis')
        match = deepcopy(MATCH)
        match['maps'] = match['maps'][:1]
        self.assertEqual(run_plan({'matches': [match]}, self.root, client=FakeClient(bundle(('anubis',))), inspect=fixture_map), 0)
        self.assertEqual(list(self.root.rglob('*.dem')), [old])
        self.assertEqual(len(Library(self.root).data['files']), 1)

    def test_same_filename_different_content_does_not_replace(self):
        library = Library(self.root)
        target = self.root / 'anubis/G2' / filename(MATCH, MATCH['maps'][0])
        target.parent.mkdir(parents=True)
        target.write_bytes(b'existing different demo')
        staged = self.root / 'new.part'
        staged.write_bytes(b'PBDEMS2\0new content')
        library.add(MATCH, staged, MATCH['maps'][0], 'a.dem')
        self.assertEqual(target.read_bytes(), b'existing different demo')
        self.assertEqual(len(list(self.root.rglob('*.dem'))), 2)

    def test_archive_traversal_never_writes_outside_staging(self):
        archive = self.root / 'unsafe.zip'
        with zipfile.ZipFile(archive, 'w') as output:
            output.writestr('../escape.dem', b'fake')
        with self.assertRaises(SourceError):
            unpack(archive, self.root / 'unpacked')
        self.assertFalse((self.root.parent / 'escape.dem').exists())

    def test_gzip_and_html_response(self):
        archive = self.root / 'demo.gz'
        archive.write_bytes(gzip.compress(b'PBDEMS2\0anubis'))
        demos = unpack(archive, self.root / 'gz')
        self.assertEqual(demos[0][0].read_bytes(), b'PBDEMS2\0anubis')
        archive.write_text('<html>login required</html>')
        with self.assertRaises(SourceError):
            unpack(archive, self.root / 'html')

    def test_missing_map_and_unavailable_match_fail_the_job(self):
        self.assertEqual(run_plan({'matches': [MATCH]}, self.root, client=FakeClient(bundle(('anubis',))), inspect=fixture_map), 1)
        self.assertEqual(len(Library(self.root).data['matches']['hltv:123']['files']), 1)
        self.assertEqual(run_plan({'matches': [], 'unavailable': [{'reason': 'expired'}]}, self.root), 1)

    def test_corrupt_index_is_preserved(self):
        index = self.root / 'replay-library.json'
        index.write_text('bad json')
        with self.assertRaises(SourceError):
            Library(self.root)
        self.assertEqual(index.read_text(), 'bad json')

    def test_library_lock_releases(self):
        with library_lock(self.root):
            with self.assertRaises(SourceError):
                with library_lock(self.root):
                    self.fail('Concurrent writer was allowed')
        with library_lock(self.root):
            pass

    def test_faceit_private_resource_exchanged_only_at_download(self):
        match = deepcopy(MATCH)
        match['source'], match['id'] = 'faceit', 'faceit:1-test'
        client = FakeClient(b'PBDEMS2\0anubis')
        with patch('downloads.get_secret', return_value='fake-token'):
            downloads.download(client, match, 'https://demos.faceit.com/private.dem.gz', self.root / 'download.part')
        self.assertEqual(client.posts[0][0], 'https://open.faceit.com/download/v2/demos/download')
        self.assertEqual(client.posts[0][1]['data']['resource_url'], 'https://demos.faceit.com/private.dem.gz')
        self.assertNotIn('temporary', json.dumps(match))

    def test_analysis_only_selected_demos_and_reports_integrity_failure(self):
        library = Library(self.root)
        staged = self.root / 'fixture.part'
        staged.write_bytes(b'PBDEMS2\0anubis')
        digest = library.add(MATCH, staged, MATCH['maps'][0], 'a.dem')
        calls = []
        def failed(command, **kwargs):
            calls.append(command)
            output = Path(command[command.index('--output') + 1])
            output.mkdir(parents=True)
            (output / 'batch_run_summary.json').write_text(json.dumps({'demo_count': 1, 'success_count': 0, 'invalid_count': 1}))
            return SimpleNamespace(returncode=0)
        with patch.object(downloads, 'ANALYSIS', self.root / 'analysis'):
            errors = analyze(library, [digest, digest], run=failed)
        self.assertEqual(len(calls), 1)
        self.assertIn('--demo', calls[0])
        self.assertNotIn('--demos', calls[0])
        self.assertNotIn('--replace', calls[0])
        self.assertEqual(len(errors), 1)
        self.assertEqual(library.data['files'][digest]['analysis']['status'], 'failed')

    def test_successful_analysis_is_skipped_and_other_existing_analysis_preserved(self):
        library = Library(self.root)
        staged = self.root / 'fixture.part'
        staged.write_bytes(b'PBDEMS2\0anubis')
        digest = library.add(MATCH, staged, MATCH['maps'][0], 'a.dem')
        calls = []
        def success(command, **kwargs):
            calls.append(command)
            output = Path(command[command.index('--output') + 1])
            source = Path(command[command.index('--demo') + 1])
            destination = output / command[command.index('--analysis-name') + 1]
            destination.mkdir(parents=True)
            (destination / 'match_summary.json').write_text('{"valid":true}')
            (destination / 'viewer_tracks_meta.json').write_text(json.dumps({'demo_sha256': digest}))
            (destination / 'analysis_run.json').write_text(json.dumps({'demo_count': 1, 'success_count': 1,
                                                                      'results': [{'demo': source.name}]}))
            return SimpleNamespace(returncode=0)
        with patch.object(downloads, 'ANALYSIS', self.root / 'analysis'):
            self.assertEqual(analyze(library, [digest], run=success), [])
            self.assertEqual(analyze(library, [digest], run=success), [])
            self.assertEqual(len(calls), 1)
            # A different sample rate requires explicit review, never replacement.
            self.assertEqual(len(analyze(library, [digest], hz='32', run=success)), 1)
            self.assertEqual(len(calls), 1)

    def test_interrupted_download_publishes_no_demo_and_can_retry(self):
        class Interrupted(FakeClient):
            def open(self, url):
                response = super().open(url)
                response.headers['Content-Length'] = str(len(self.content) + 10)
                return response
        self.assertEqual(run_plan({'matches': [MATCH]}, self.root, client=Interrupted(bundle()), inspect=fixture_map), 1)
        self.assertEqual(list(self.root.rglob('*.dem')), [])
        self.assertEqual(run_plan({'matches': [MATCH]}, self.root, client=FakeClient(bundle()), inspect=fixture_map), 0)

    def test_wrong_map_never_publishes_unmatched_demo(self):
        self.assertEqual(run_plan({'matches': [MATCH]}, self.root, client=FakeClient(bundle(('inferno',))), inspect=fixture_map), 1)
        self.assertEqual(list(self.root.rglob('*.dem')), [])

    def test_hltv_completed_maps_and_all_demo_links(self):
        html = '''<div class="teamName">Unrelated sidebar team</div><div class="teamsBox">
        <div class="teamName">G2</div><div class="teamName">Vitality</div>
        <div class="date" data-unix="1793404800000"></div><div class="event">Test Cup</div></div>'''
        for name in ('Anubis', 'Dust2'):
            html += f'''<div class="mapholder"><div class="mapname">{name}</div>
            <div class="results-left"><span class="results-team-score">13</span></div>
            <div class="results-right"><span class="results-team-score">9</span></div></div>'''
        html += '''<div class="mapholder"><div class="mapname">Inferno</div></div>
        <a data-demo-link="/download/demo/42">Demo download</a><a href="/download/demo/43">Part 2</a>'''
        parsed = hltv_match(parse_html(html), classify_link(MATCH['url']))
        self.assertEqual([m['map'] for m in parsed['maps']], ['anubis', 'dust2'])
        self.assertEqual(len(parsed['downloads']), 2)
        self.assertEqual(parsed['owner'], 'G2-vs-Vitality')

    def test_hltv_tournament_paginates_beyond_first_hundred(self):
        class Pages:
            def html(self, url):
                if '/events/' in url:
                    return parse_html('<h1>Event</h1>')
                if 'offset=0' in url:
                    ids = range(1, 101)
                elif 'offset=100' in url:
                    ids = range(101, 103)
                else:
                    ids = []
                return parse_html('<div class="results-holder">' + ''.join(
                    f'<div class="result-con"><a href="/matches/{i}/a-vs-b">Match</a></div>' for i in ids) + '</div>')
        resolver = Resolver(Pages(), log=lambda _: None)
        def parsed(_, item, owner):
            match = deepcopy(MATCH)
            match['id'] = 'hltv:' + item['id']
            return match
        with patch('sources.hltv_match', side_effect=parsed):
            plan = resolver.resolve('https://www.hltv.org/events/42/test')
        self.assertEqual(len(plan['matches']), 102)

    def test_secret_environment_override(self):
        with patch.dict(os.environ, {'FACEIT_API_KEY': 'test-env-key'}), patch('credentials.read_secret') as read:
            self.assertEqual(get_secret('FACEIT_API_KEY'), 'test-env-key')
            read.assert_not_called()

    def test_faceit_stats_are_aligned_to_player_team_not_score_text_order(self):
        class FaceitResolver(Resolver):
            def faceit(self, path):
                if path.endswith('/stats'):
                    return {'rounds': [{'round_stats': {'Map': 'de_cache', 'Score': '13 / 7'}, 'teams': [
                        {'team_id': 'a', 'team_stats': {'Final Score': '13'}},
                        {'team_id': 'b', 'team_stats': {'Final Score': '7'}}]}]}
                return {'status': 'FINISHED', 'finished_at': 1793404800, 'demo_url': ['https://demos.faceit.com/a.dem.gz'],
                        'teams': {'faction1': {'faction_id': 'a', 'name': 'Alpha', 'roster': []},
                                  'faction2': {'faction_id': 'b', 'name': 'Bravo', 'roster': [{'nickname': 'CanadianIQ'}]}}}
        match = FaceitResolver().faceit_match('1-fixture', 'CanadianIQ')
        self.assertEqual(match['maps'][0], {'map': 'cache', 'score': [7, 13]})
        self.assertEqual(match['label'], 'CanadianIQ')
        self.assertEqual(match['teams'], ['Bravo', 'Alpha'])
        self.assertTrue(filename(match, match['maps'][0]).startswith('[7-vs-13]_CanadianIQ_'))

    def test_faceit_player_id_orders_wins_and_losses_despite_changed_nickname(self):
        class FaceitResolver(Resolver):
            def faceit(self, path):
                if path.endswith('/stats'):
                    return {'rounds': [{'round_stats': {'Map': 'de_anubis', 'Score': '13 / 7'}, 'teams': [
                        {'team_id': 'b', 'team_stats': {'Final Score': '7'}},
                        {'team_id': 'a', 'team_stats': {'Final Score': '13'}}]}]}
                return {'status': 'FINISHED', 'finished_at': 1793404800, 'demo_url': [], 'teams': {
                    'faction1': {'faction_id': 'a', 'name': 'Alpha', 'roster': [{'player_id': 'player-a', 'nickname': 'OldNameA'}]},
                    'faction2': {'faction_id': 'b', 'name': 'Bravo', 'roster': [{'player_id': 'player-b', 'nickname': 'OldNameB'}]}}}
        resolver = FaceitResolver()
        for player_id, expected in [('player-a', '[13-vs-7]'), ('player-b', '[7-vs-13]')]:
            match = resolver.faceit_match('1-fixture', 'CurrentName', player_id=player_id)
            self.assertTrue(filename(match, match['maps'][0]).startswith(expected + '_CurrentName_'))
        with self.assertRaisesRegex(SourceError, 'Refusing to guess'):
            resolver.faceit_match('1-fixture', 'CurrentName', player_id='missing-player')
        with self.assertRaisesRegex(SourceError, 'Refusing to guess'):
            resolver.faceit_match('1-fixture', 'UnknownNickname')

    def test_faceit_player_history_pages_and_keeps_latest_requested_games(self):
        class FaceitResolver(Resolver):
            def faceit(self, path):
                if path.startswith('players?'):
                    return {'player_id': 'player-id', 'nickname': 'CanadianIQ'}
                if 'offset=0&limit=100' in path:
                    return {'items': [{'match_id': f'1-{i}'} for i in range(100)]}
                if 'offset=100&limit=2' in path:
                    return {'items': [{'match_id': '1-100'}, {'match_id': '1-101'}]}
                raise AssertionError('Unexpected request: ' + path)
            def faceit_match(self, mid, owner, *, player_id=''):
                if player_id != 'player-id':
                    raise AssertionError('Player identity was not passed from profile lookup')
                result = deepcopy(MATCH)
                result.update(id='faceit:' + mid, owner=owner)
                return result
        with patch('sources.get_secret', return_value='fake-token'):
            plan = FaceitResolver(log=lambda _: None).resolve('https://www.faceit.com/en/players/CanadianIQ', 102)
        self.assertEqual(len(plan['matches']), 102)
        self.assertEqual(plan['matches'][0]['id'], 'faceit:1-0')
        self.assertEqual(plan['matches'][-1]['id'], 'faceit:1-101')

    def test_provider_access_failure_stops_before_requesting_other_matches(self):
        class FaceitResolver(Resolver):
            requests = 0
            def faceit(self, path):
                if path.startswith('players?'):
                    return {'player_id': 'player-id', 'nickname': 'CanadianIQ'}
                return {'items': [{'match_id': f'1-{i}'} for i in range(5)]}
            def faceit_match(self, mid, owner, *, player_id=''):
                self.requests += 1
                raise AccessError('Access revoked')
        resolver = FaceitResolver(log=lambda _: None)
        with patch('sources.get_secret', return_value='fake-token'):
            with self.assertRaises(AccessError):
                resolver.resolve('https://www.faceit.com/en/players/CanadianIQ', 5)
        self.assertEqual(resolver.requests, 1)


if __name__ == '__main__':
    unittest.main()
