"""FACEIT team-season discovery and evidence-aware roster comparisons.

The web summary's old-season team_members can repeat today's membership. Never
treat it as an archived registration. Use saved observations or match lineups.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from uuid import UUID

from jobs import STATE, save_json
from sources import AccessError, Client, Resolver, SourceError, classify_link


def identity(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise SourceError('FACEIT returned a missing or invalid stable account/team ID.') from None


def member(record, *, roles=False):
    uid = identity(record.get('player_id') or record.get('user_id'))
    name = record.get('nickname') or record.get('user_name') or uid
    role = {'player': 'main', 'substitute': 'sub'}.get(record.get('game_role'), 'unknown') if roles else 'unknown'
    steam = str(record.get('game_player_id') or '')
    return {'player_id': uid, 'nickname': str(name), 'role': role,
            'steam_id64': steam if steam.isdigit() and len(steam) == 17 else None}


def roster(records, *, roles=False):
    found = {}
    for record in records:
        if roles and record.get('game_role') not in ('player', 'substitute'):
            continue  # Coaches and managers are not playing roster members.
        value = member(record, roles=roles)
        if value['player_id'] in found and found[value['player_id']]['role'] != value['role']:
            raise SourceError('FACEIT supplied conflicting roles for one account.')
        found[value['player_id']] = value
    return sorted(found.values(), key=lambda p: (p['nickname'].casefold(), p['player_id']))


def season_label(season):
    return f"{season['league_name']} · S{season['number']} · {season['division']} · {season['region']}"


def compare_rosters(selected, latest):
    old = {p['player_id']: p for p in selected.get('roster', [])}
    new = {p['player_id']: p for p in latest.get('roster', [])}
    complete = bool(selected.get('roster_complete') and latest.get('roster_complete') and old and new)
    exact = selected.get('roster_basis') == 'registration_snapshot' and latest.get('roster_basis') == 'registration_snapshot'
    items = []
    for uid in old.keys() | new.keys():
        before, after = old.get(uid), new.get(uid)
        current = after or before
        role = current.get('role', 'unknown')
        change, prefix, color = 'same', '•', '#a5b3bf'
        description = 'Same account in both seasons.'
        if before and after and before.get('role') != after.get('role') and before.get('role') in ('main', 'sub') and after.get('role') in ('main', 'sub'):
            change, prefix, color = ('promoted', '+', '#75c7fb') if role == 'main' else ('demoted', '−', '#75c7fb')
            description = 'Moved from subs to main roster.' if role == 'main' else 'Moved from main roster to subs.'
        elif not before:
            change, prefix, color = 'added', '+', '#8cd5b3'
            description = 'Added to team.' if exact else 'Listed in the latest roster; absent from the older season’s observed match lineups. Historical registration is unverified.'
        elif not after:
            change, prefix, color = 'removed', '−', '#f17474'
            description = 'Removed from team.' if exact else 'Listed in older season match lineups; absent from the latest roster. Historical registration is unverified.'
        if not complete:
            change, prefix, color = 'unknown', '•', '#a5b3bf'
            description = 'Incomplete roster evidence; membership or role changes cannot be confirmed.'
        elif before and after and ('unknown' in (before.get('role'), after.get('role'))):
            description += ' Historical main/sub role is unverified.'
        if before and after and before['nickname'] != after['nickname']:
            description += f" Previously named {before['nickname']}; the FACEIT account ID is unchanged."
        items.append({**current, 'change': change, 'prefix': prefix, 'color': color,
                      'description': description, 'old_role': before.get('role') if before else None,
                      'new_role': after.get('role') if after else None})
    changed = complete and any(p['change'] in ('added', 'removed', 'promoted', 'demoted') for p in items)
    roles_known = complete and all(p.get('role') in ('main', 'sub') for p in old.values()) and all(p.get('role') in ('main', 'sub') for p in new.values())
    return {'selected': selected['number'], 'latest': latest['number'], 'different': bool(changed),
            'complete': complete, 'roles_verified': bool(roles_known), 'registration_verified': exact,
            'items': sorted(items, key=lambda p: ({'main': 0, 'sub': 1, 'unknown': 2}.get(p['role'], 2), p['nickname'].casefold())),
            'basis_note': ('Registered roster observations; snapshots are dated when scanned.' if exact
                           else 'Historical comparison uses match-listed players. Unplayed substitutes and past main/sub roles may be unavailable.')}


class TeamLeagues:
    def __init__(self, resolver=None, client=None, state=STATE, log=print):
        self.resolver = resolver or Resolver()
        self.client = client or Client()
        self.state, self.log = Path(state), log

    def web(self, path, **query):
        return self.client.json('https://www.faceit.com/api/' + path + ('?' + urlencode(query) if query else ''))

    def season_matches(self, team_id, season):
        matches, seen = [], set()
        for championship in season['championship_ids']:
            offset = 0
            while offset < 5000:
                response = self.web('championships/v1/matches', championshipId=championship,
                                    participantId=team_id, participantType='TEAM', offset=offset, limit=100)
                payload = response.get('payload', {})
                rows = payload.get('items')
                if not isinstance(rows, list) or payload.get('start', offset) != offset:
                    raise SourceError('FACEIT league match pagination was not recognized.')
                page_ids = set()
                for row in rows:
                    if row.get('championshipId') != championship or team_id not in {p.get('id') for p in row.get('factions', [])}:
                        raise SourceError('FACEIT returned matches outside the selected team/season. Scan stopped.')
                    origin = row.get('origin', {})
                    mid = origin.get('id', '')
                    if not mid.startswith('1-'):
                        raise SourceError('A league match has no recognized match ID.')
                    identity(mid[2:])
                    page_ids.add(mid)
                    if mid not in seen:
                        seen.add(mid)
                        matches.append({'id': mid, 'championship_id': championship,
                                        'finished': row.get('status', '').lower() == 'finished' and origin.get('state', '').upper() == 'FINISHED'})
                if len(rows) < 100:
                    break
                if not page_ids or (offset and page_ids <= previous):
                    raise SourceError('FACEIT repeated a match page. Scan stopped before claiming full coverage.')
                previous = page_ids
                offset += len(rows)
            else:
                raise SourceError('Season match listings exceeded the metadata scan limit.')
        return matches

    def scan(self, value):
        link = classify_link(value)
        if link['source'] != 'faceit' or link['kind'] != 'team':
            raise SourceError('Paste a FACEIT team league link.')
        team_id = identity(link['id'])
        profile = self.resolver.faceit('teams/' + team_id)
        summary = self.web(f'team-leagues/v1/teams/{team_id}/profile/leagues/summary')
        leagues = summary.get('payload')
        if not isinstance(leagues, list):
            raise SourceError('FACEIT team league summary format changed.')
        seasons, active = [], {}
        for league in leagues:
            if league.get('game_id') != 'cs2':
                continue
            league_id = identity(league.get('league_id'))
            active[league_id] = league.get('active_members', [])
            for entry in league.get('league_seasons_info', []):
                number = int(entry.get('season_number', 0))
                if number <= 0:
                    raise SourceError('FACEIT supplied an invalid season number.')
                season_id = identity(entry.get('season_id'))
                standings = entry.get('season_standings', [])
                seasons.append({'key': league_id + ':' + season_id, 'league_id': league_id, 'id': season_id,
                                'number': number, 'league_name': str(league.get('league_name') or 'League'),
                                'division': ' / '.join(dict.fromkeys(s.get('division_name', '') for s in standings if s.get('division_name'))) or 'Division unavailable',
                                'region': ' / '.join(dict.fromkeys(s.get('region_name', '') for s in standings if s.get('region_name'))) or 'Region unavailable',
                                'championship_ids': list(dict.fromkeys(identity(s['championship_id']) for s in standings if s.get('championship_id'))),
                                'roster': [], 'roster_complete': False, 'roster_basis': 'unavailable', 'errors': []})
        if not seasons:
            raise SourceError('This team has no published CS2 league seasons.')
        current = {}
        try:
            registration = self.web(f'team-leagues/v1/teams/{team_id}/profile/leagues/current').get('payload', {})
            if isinstance(registration, dict):
                current = registration
        except (OSError, ValueError):
            pass  # Missing current registration cannot turn an old roster into a verified one.
        if len({s['key'] for s in seasons}) != len(seasons):
            raise SourceError('FACEIT returned duplicate season registrations; scan stopped.')
        seasons.sort(key=lambda s: (not s['league_name'].lower().startswith('esea'), -s['number'], s['key']))
        latest = {s['league_id']: max(t['number'] for t in seasons if t['league_id'] == s['league_id']) for s in seasons}
        snapshot_file = self.state / 'league-roster-snapshots' / (team_id + '.json')
        saved = {'version': 1, 'team_id': team_id, 'snapshots': {}}
        if snapshot_file.exists():
            try:
                saved = json.loads(snapshot_file.read_text(encoding='utf-8'))
                if saved['version'] != 1 or saved['team_id'] != team_id or not isinstance(saved['snapshots'], dict):
                    raise ValueError()
                for key, snapshot in saved['snapshots'].items():
                    league_key, season_key = key.split(':')
                    identity(league_key)
                    identity(season_key)
                    if not isinstance(snapshot['roster'], list) or not snapshot.get('captured_at'):
                        raise ValueError()
                    seen = set()
                    for player in snapshot['roster']:
                        pid = identity(player['player_id'])
                        if pid in seen or not isinstance(player['nickname'], str) or player['role'] not in ('main', 'sub', 'unknown'):
                            raise ValueError()
                        seen.add(pid)
            except (ValueError, TypeError, KeyError):
                raise SourceError('Saved roster observations are invalid. Restore the roster snapshot file before scanning; it has been preserved.') from None
        snapshots = saved.get('snapshots', {})
        now = datetime.now(timezone.utc).isoformat(timespec='seconds')
        details = {}
        for season in seasons:
            self.log(f"Scanning {profile['name']} · {season_label(season)} (metadata only)")
            season['latest'] = season['number'] == latest[season['league_id']]
            season['matches'] = self.season_matches(team_id, season)
            finished = [m for m in season['matches'] if m['finished']]
            listed, failures = {}, []
            needed = [m['id'] for m in finished if m['id'] not in details]
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {pool.submit(self.resolver.faceit, 'matches/' + mid): mid for mid in needed}
                for future in as_completed(futures):
                    mid = futures[future]
                    try:
                        details[mid] = future.result()
                    except AccessError:
                        for pending in futures:
                            pending.cancel()
                        raise
                    except (OSError, ValueError, KeyError) as exc:
                        failures.append(f'{mid}: {exc}')
            for match in finished:
                data = details.get(match['id'])
                if not data:
                    continue
                try:
                    if data.get('competition_id') not in season['championship_ids']:
                        raise SourceError('Match competition does not match the selected season.')
                    sides = [t for t in data.get('teams', {}).values() if t.get('faction_id') == team_id]
                    if len(sides) != 1 or not sides[0].get('roster'):
                        raise SourceError('Season match is missing this team’s lineup.')
                    for player in roster(sides[0]['roster']):
                        listed[player['player_id']] = player
                except (ValueError, KeyError, TypeError) as exc:
                    failures.append(f"{match['id']}: {exc}")
            season['roster'] = list(listed.values())
            season['roster_basis'] = 'finished_match_lineups'
            season['roster_complete'] = bool(finished and listed and not failures)
            season['errors'] = failures
            if (season['latest'] and current.get('league_id') == season['league_id']
                    and current.get('season_id') == season['id'] and active.get(season['league_id'])):
                registered = roster(active[season['league_id']], roles=True)
                if registered:
                    # Current registration is useful only for the newest season.
                    # Never copy it into older season records.
                    for player in registered:
                        player['steam_id64'] = listed.get(player['player_id'], {}).get('steam_id64')
                    season.update(roster=registered, roster_basis='registration_snapshot', roster_complete=True, captured_at=now)
                    snapshots[season['key']] = {'roster': registered, 'captured_at': now}
            elif season['key'] in snapshots:
                snapshot = snapshots[season['key']]
                season.update(roster=snapshot['roster'], roster_basis='registration_snapshot', roster_complete=True,
                              captured_at=snapshot['captured_at'])
            season['match_count'] = len(finished)
            self.log(f"S{season['number']}: {len(finished)} finished matches, {len(season['roster'])} roster accounts; {season['roster_basis']}")
        save_json(snapshot_file, {'version': 1, 'team_id': team_id, 'snapshots': snapshots})
        for season in seasons:
            baseline = next(s for s in seasons if s['league_id'] == season['league_id'] and s['latest'])
            season['comparison'] = compare_rosters(season, baseline)
        return {'version': 1, 'team_id': team_id, 'team_name': profile['name'], 'url': link['url'],
                'scanned_at': now, 'seasons': seasons}

    def resolve_season(self, value, catalog, key):
        link = classify_link(value)
        if link.get('source') != 'faceit' or link.get('kind') != 'team' or catalog.get('team_id') != link['id']:
            raise SourceError('Team selection changed. Scan its seasons again.')
        found = [s for s in catalog.get('seasons', []) if s['key'] == key]
        if len(found) != 1:
            raise SourceError('Choose a discovered season first.')
        season = found[0]
        # Refresh listings at review time, rather than downloading a stale subset.
        matches = self.season_matches(link['id'], season)
        plan = {'version': 1, 'link': link, 'matches': [], 'unavailable': [],
                'league_season': {k: season[k] for k in ('key', 'number', 'id', 'league_id', 'league_name', 'division', 'region')},
                'roster_comparison': season['comparison'], 'team_id': link['id'], 'team_name': catalog['team_name']}
        finished = [m for m in matches if m['finished']]
        for index, item in enumerate(finished, 1):
            self.log(f"Reviewing S{season['number']} match {index}/{len(finished)}: {item['id']}")
            try:
                match = self.resolver.faceit_match(item['id'], catalog['team_name'], team_id=link['id'])
                match['event'] = f"{season['league_name']} S{season['number']} {season['division']}"
                match['league_season'] = plan['league_season']
                match['selected_team_id'] = link['id']
                plan['matches'].append(match)
            except AccessError:
                raise
            except (OSError, ValueError, KeyError, TypeError) as exc:
                plan['unavailable'].append({'url': f"https://www.faceit.com/en/cs2/room/{item['id']}", 'reason': str(exc)})
        plan['requested_matches'] = len(finished)
        plan['not_finished'] = len(matches) - len(finished)
        return plan
