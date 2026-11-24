import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from types import MethodType, SimpleNamespace
from uuid import UUID

import downloads
from faceit_leagues import TeamLeagues, compare_rosters, season_label
from jobs import save_json
from sources import Resolver, SourceError, classify_link


def uid(value):
    return str(UUID(int=value))


TEAM, LEAGUE, S59, S58, C59, C58, PLAYOFF = [uid(n) for n in range(1, 8)]
LINK = f'https://www.faceit.com/en/teams/{TEAM}/leagues'
MID59, MID58, MIDPLAY = ['1-' + uid(n) for n in (59, 58, 580)]


def account(n, role='main', name=None):
    return {'player_id': uid(n), 'nickname': name or 'Player' + str(n), 'role': role,
            'steam_id64': '76561198000000000'}


def registered(n, role):
    return {'user_id': uid(n), 'user_name': 'Player' + str(n), 'game_role': role}


def summary():
    active = [registered(100, 'player'), registered(101, 'substitute'), registered(104, 'player')]
    def season(number, season_id, championships):
        return {'season_number': str(number), 'season_id': season_id,
                'team_members': deepcopy(active),  # Deliberately misleading old-season member copies.
                'season_standings': [{'championship_id': cid, 'division_name': 'Open9-10', 'region_name': 'North America'} for cid in championships]}
    return {'payload': [{'league_id': LEAGUE, 'league_name': 'ESEA League', 'game_id': 'cs2',
                         'active_members': active, 'league_seasons_info': [season(58, S58, [C58, PLAYOFF]), season(59, S59, [C59])]}]}


def listing(mid, championship, finished=True, team_id=TEAM):
    return {'championshipId': championship, 'status': 'finished' if finished else 'scheduled',
            'origin': {'id': mid, 'state': 'FINISHED' if finished else 'SCHEDULED'},
            'factions': [{'id': team_id}, {'id': uid(999)}]}


class FakeClient:
    def __init__(self):
        self.summary = summary()
        self.calls = []
        self.current = {'payload': {'league_id': LEAGUE, 'season_id': S59}}
        self.rows = {C59: [listing(MID59, C59)], C58: [listing(MID58, C58)],
                     PLAYOFF: [listing(MIDPLAY, PLAYOFF), listing('1-' + uid(581), PLAYOFF, False)]}

    def json(self, url):
        from urllib.parse import urlsplit, parse_qs
        self.calls.append(url)
        if url.endswith('/summary'):
            return deepcopy(self.summary)
        if url.endswith('/current'):
            return deepcopy(self.current)
        params = parse_qs(urlsplit(url).query)
        if params.get('participantId') != [TEAM] or params.get('participantType') != ['TEAM']:
            raise AssertionError('Incorrect public team filter')
        offset, limit = int(params['offset'][0]), int(params['limit'][0])
        rows = self.rows[params['championshipId'][0]][offset:offset + limit]
        return {'payload': {'start': offset, 'end': offset + limit, 'items': deepcopy(rows)}}


class FakeResolver:
    def __init__(self):
        self.resolved = []
        self.fail = set()

    def faceit(self, path):
        if path == 'teams/' + TEAM:
            return {'name': 'Fixture Team'}
        mid = path.removeprefix('matches/')
        if mid in self.fail:
            raise SourceError('Lineup unavailable')
        champ = {MID59: C59, MID58: C58, MIDPLAY: PLAYOFF}[mid]
        numbers = (100, 101, 104) if mid == MID59 else (100, 101, 103)
        return {'competition_id': champ, 'teams': {'faction1': {'faction_id': TEAM,
                'roster': [{'player_id': uid(n), 'nickname': 'Player' + str(n), 'game_player_id': '76561198000000000'} for n in numbers]}}}

    def faceit_match(self, mid, owner, *, team_id):
        if team_id != TEAM:
            raise AssertionError('Incorrect team-side identity')
        self.resolved.append(mid)
        return {'id': 'faceit:' + mid, 'source': 'faceit', 'owner': owner, 'label': owner + '-vs-Opponent',
                'date': '2026-10-31', 'maps': [{'map': 'anubis', 'score': [13, 7]}], 'downloads': [],
                'url': f'https://www.faceit.com/en/cs2/room/{mid}'}


class LeagueTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[2] / 'data/.desktop/tests'
        base.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.client, self.resolver = FakeClient(), FakeResolver()
        self.service = TeamLeagues(self.resolver, self.client, self.root, log=lambda _: None)
        capture = redirect_stdout(io.StringIO())
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)

    def test_team_link_and_automatic_numeric_season_discovery(self):
        self.assertEqual(classify_link(LINK)['kind'], 'team')
        catalog = self.service.scan(LINK)
        self.assertEqual([s['number'] for s in catalog['seasons']], [59, 58])
        latest, old = catalog['seasons']
        self.assertTrue(latest['latest'])
        self.assertIn('Open9-10', season_label(latest))
        self.assertEqual(latest['match_count'], 1)
        self.assertEqual(old['match_count'], 2)  # regular season + playoff; scheduled excluded

    def test_latest_season_is_numeric_and_not_hard_coded(self):
        rows = self.client.summary['payload'][0]['league_seasons_info']
        rows[0]['season_number'], rows[1]['season_number'] = '9', '10'
        seasons = self.service.scan(LINK)['seasons']
        self.assertEqual([s['number'] for s in seasons], [10, 9])
        self.assertEqual(seasons[1]['comparison']['latest'], 10)

    def test_old_summary_current_members_are_never_used_as_historical_roster(self):
        latest, old = self.service.scan(LINK)['seasons']
        self.assertEqual({p['player_id'] for p in old['roster']}, {uid(n) for n in (100, 101, 103)})
        self.assertTrue(all(p['role'] == 'unknown' for p in old['roster']))
        self.assertEqual(latest['roster_basis'], 'registration_snapshot')
        self.assertFalse(old['comparison']['roles_verified'])
        self.assertFalse(old['comparison']['registration_verified'])
        self.assertTrue(old['comparison']['different'])

    def test_newest_role_snapshot_is_saved_and_old_verified_snapshot_is_preserved(self):
        stored = {'version': 1, 'team_id': TEAM, 'snapshots': {LEAGUE + ':' + S58: {
            'captured_at': '2026-06-01T00:00:00+00:00',
            'roster': [account(100, 'sub'), account(101, 'main'), account(103, 'main')]}}}
        path = self.root / 'league-roster-snapshots' / (TEAM + '.json')
        save_json(path, stored)
        latest, old = self.service.scan(LINK)['seasons']
        changes = {p['player_id']: p for p in old['comparison']['items']}
        self.assertEqual((changes[uid(100)]['change'], changes[uid(100)]['prefix']), ('promoted', '+'))
        self.assertEqual((changes[uid(101)]['change'], changes[uid(101)]['prefix']), ('demoted', '−'))
        self.assertEqual(changes[uid(100)]['color'], changes[uid(101)]['color'])
        self.assertEqual(changes[uid(104)]['change'], 'added')
        self.assertEqual(changes[uid(103)]['change'], 'removed')
        self.assertTrue(old['comparison']['roles_verified'])
        saved = json.loads(path.read_text())['snapshots']
        self.assertIn(latest['key'], saved)
        self.assertEqual(saved[old['key']]['captured_at'], '2026-06-01T00:00:00+00:00')

    def test_corrupt_saved_roles_are_preserved_instead_of_silently_reset(self):
        path = self.root / 'league-roster-snapshots' / (TEAM + '.json')
        path.parent.mkdir(parents=True)
        path.write_text('broken saved history')
        with self.assertRaisesRegex(SourceError, 'preserved'):
            self.service.scan(LINK)
        self.assertEqual(path.read_text(), 'broken saved history')

    def test_rename_with_same_uuid_is_shared_grey_not_added_removed(self):
        old = {'number': 58, 'roster': [account(100, name='OldNickname')], 'roster_complete': True, 'roster_basis': 'registration_snapshot'}
        latest = {**old, 'number': 59, 'roster': [account(100, name='NewNickname')]}
        comparison = compare_rosters(old, latest)
        self.assertFalse(comparison['different'])
        self.assertEqual(comparison['items'][0]['prefix'], '•')
        self.assertIn('OldNickname', comparison['items'][0]['description'])
        self.assertEqual(comparison['items'][0]['player_id'], uid(100))

    def test_missing_lineup_data_is_unknown_instead_of_false_membership_changes(self):
        self.resolver.fail.add(MID58)
        _, old = self.service.scan(LINK)['seasons']
        self.assertFalse(old['roster_complete'])
        self.assertFalse(old['comparison']['different'])
        self.assertTrue(old['errors'])
        self.assertTrue(all(p['change'] == 'unknown' for p in old['comparison']['items']))

    def test_current_registration_must_match_season_before_roles_are_trusted(self):
        self.client.current['payload']['season_id'] = uid(99999)
        latest = self.service.scan(LINK)['seasons'][0]
        self.assertEqual(latest['roster_basis'], 'finished_match_lineups')
        self.assertFalse(latest['comparison']['roles_verified'])

    def test_pagination_fetches_every_team_match_without_wrong_league_team_id(self):
        self.client.rows[C59] = [listing('1-' + uid(1000 + n), C59) for n in range(101)]
        found = self.service.season_matches(TEAM, {'championship_ids': [C59]})
        self.assertEqual(len(found), 101)
        self.assertEqual(len(self.client.calls), 2)
        self.assertIn('offset=100', self.client.calls[1])

    def test_wrong_team_or_season_filters_fail_scan(self):
        self.client.rows[C59][0]['factions'][0]['id'] = uid(9999)
        with self.assertRaisesRegex(SourceError, 'outside the selected'):
            self.service.season_matches(TEAM, {'championship_ids': [C59]})

    def test_season_plan_includes_regular_season_and_playoff_matches_only(self):
        catalog = self.service.scan(LINK)
        old = catalog['seasons'][1]
        plan = self.service.resolve_season(LINK, catalog, old['key'])
        self.assertEqual(set(self.resolver.resolved), {MID58, MIDPLAY})
        self.assertEqual(plan['not_finished'], 1)
        self.assertTrue(all(m['owner'] == 'Fixture Team' for m in plan['matches']))
        self.assertTrue(all('S58' in m['event'] for m in plan['matches']))
        self.assertTrue(all('vs-Opponent' in m['label'] for m in plan['matches']))
        self.assertEqual(plan['league_season']['number'], 58)

    def test_changed_team_link_cannot_reuse_another_teams_catalog(self):
        catalog = self.service.scan(LINK)
        with self.assertRaises(SourceError):
            self.service.resolve_season(LINK.replace(TEAM, uid(99999)), catalog, catalog['seasons'][0]['key'])

    def test_team_score_order_is_selected_team_not_player_or_faction_order(self):
        class TeamResolver(Resolver):
            def faceit(self, path):
                if path.endswith('/stats'):
                    return {'rounds': [{'round_stats': {'Map': 'de_anubis', 'Score': '13 / 7'}, 'teams': [
                        {'team_id': uid(999), 'team_stats': {'Final Score': '13'}},
                        {'team_id': TEAM, 'team_stats': {'Final Score': '7'}}]}]}
                return {'status': 'FINISHED', 'finished_at': 1793404800, 'demo_url': [], 'teams': {
                    'faction1': {'faction_id': uid(999), 'name': 'Opponent'},
                    'faction2': {'faction_id': TEAM, 'name': 'HistoricalTeamName'}}}
        match = TeamResolver().faceit_match(MID58, 'Fixture Team', team_id=TEAM)
        self.assertEqual(match['maps'][0]['score'], [7, 13])
        self.assertEqual(match['owner'], 'Fixture Team')
        self.assertEqual(match['label'], 'HistoricalTeamName-vs-Opponent')

    def test_worker_uses_selected_season_instead_of_player_history(self):
        catalog = self.service.scan(LINK)
        path, output = self.root / 'catalog.json', self.root / 'plan.json'
        save_json(path, catalog)
        args = ['downloads.py', '--resolve', LINK, '--catalog', str(path), '--season', catalog['seasons'][0]['key'], '--plan', str(output)]
        with patch('sys.argv', args), patch('faceit_leagues.TeamLeagues', return_value=self.service):
            self.assertEqual(downloads.main(), 0)
        self.assertEqual(json.loads(output.read_text())['league_season']['number'], 59)

    def interface(self, catalog):
        from main import Toolbox
        class Variable:
            def __init__(self, value=''):
                self.value = value
            def get(self):
                return self.value
            def set(self, value):
                self.value = value
        class Widget:
            def __init__(self):
                self.properties, self.visible = {}, False
            def configure(self, **properties):
                self.properties.update(properties)
            def pack(self, **_):
                self.visible = True
            def pack_forget(self):
                self.visible = False
        fields = {key: Variable(value) for key, value in [('download_link', LINK), ('download_season', '')]}
        state = SimpleNamespace(page='download', runner=SimpleNamespace(busy=False), closing=False,
                                team_catalog=catalog, team_scan_pending=None, team_scan_failed=None,
                                team_scan_timer=None, roster_hint=SimpleNamespace(set=lambda _: None),
                                var=lambda key: fields[key], after=lambda *_: 'scheduled', after_cancel=lambda *_: None,
                                scan_team=lambda *_: None)
        for name in ('download_count', 'roster_badge', 'season_row', 'count_row', 'season_combo', 'link_detail', 'download_button'):
            setattr(state, name, Widget())
        state.update_download_link = MethodType(Toolbox.update_download_link, state)
        state.download_pasted = MethodType(Toolbox.download_pasted, state)
        return state

    def test_team_ui_season_selection_warning_and_player_count_scope(self):
        state = self.interface(self.service.scan(LINK))
        state.update_download_link()
        self.assertTrue(state.season_row.visible)
        self.assertEqual(state.download_count.properties['state'], 'disabled')
        self.assertEqual(state.download_button.properties['state'], 'normal')
        self.assertEqual(state.roster_badge.properties['text'], '● roster')
        state.var('download_season').set(season_label(state.team_catalog['seasons'][1]))
        state.update_download_link()
        self.assertEqual(state.roster_badge.properties['text'], '● different rosters')
        self.assertEqual(state.roster_badge.properties['fg'], '#f17474')
        state.var('download_link').set('https://www.faceit.com/en/players/Someone')
        state.update_download_link()
        self.assertFalse(state.season_row.visible)
        self.assertFalse(state.roster_badge.visible)
        self.assertEqual(state.download_count.properties['state'], 'normal')

    def test_paste_triggers_new_scan_and_unknown_roles_are_not_an_all_clear(self):
        catalog = self.service.scan(LINK)
        catalog['seasons'][1]['comparison']['different'] = False
        state = self.interface(catalog)
        state.var('download_season').set(season_label(catalog['seasons'][1]))
        state.update_download_link()
        self.assertEqual(state.roster_badge.properties['text'], '● roster not verified')
        state.download_pasted()
        self.assertIsNone(state.team_catalog)
        self.assertEqual(state.team_scan_timer, 'scheduled')
        self.assertEqual(state.download_button.properties['state'], 'disabled')


if __name__ == '__main__':
    unittest.main()
