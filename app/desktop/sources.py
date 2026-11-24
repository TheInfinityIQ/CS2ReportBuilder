"""Link classification and source metadata. No demo downloads happen here."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from credentials import get_secret


class SourceError(ValueError):
    pass


class AccessError(SourceError):
    """Provider-wide access failure: stop, rather than retry every match."""


def classify_link(value):
    value = value.strip()
    if '://' not in value:
        value = 'https://' + value
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise SourceError('Paste a valid FACEIT or HLTV link.') from exc
    host = (parts.hostname or '').lower().removeprefix('www.')
    legacy_hltv = host == 'hltv.org' and parts.scheme == 'http' and port in (None, 80)
    secure = parts.scheme == 'https' and port in (None, 443)
    if parts.username is not None or parts.password is not None or not (secure or legacy_hltv):
        raise SourceError('Paste an HTTPS FACEIT or an HLTV link.')
    path = unquote(parts.path).strip('/')
    if host == 'faceit.com':
        player = re.fullmatch(r'(?:[a-z]{2}/)?players/([^/]+)(?:/.*)?', path)
        match = re.fullmatch(r'(?:[a-z]{2}/)?cs2/room/(1-[0-9a-fA-F-]{36})(?:/.*)?', path)
        team = re.fullmatch(r'(?:[a-z]{2}/)?teams/([0-9a-fA-F-]{36})(?:/leagues)?', path)
        if player:
            return dict(source='faceit', kind='player', id=player[1], url=value)
        if match:
            return dict(source='faceit', kind='match', id=match[1], url=value)
        if team:
            from uuid import UUID
            return dict(source='faceit', kind='team', id=str(UUID(team[1])), url=value)
    if host == 'hltv.org':
        match = re.fullmatch(r'(matches|events|team)/(\d+)(?:/[^/]+)?', path)
        if match:
            # Upgrade before the resolver or browser sees the URL.
            url = parts._replace(scheme='https', netloc='www.hltv.org', fragment='').geturl()
            return dict(source='hltv', kind={'matches': 'match', 'events': 'tournament', 'team': 'team'}[match[1]],
                        id=match[2], url=url)
    raise SourceError('Use a FACEIT player, CS2 match, or team league link; or an HLTV team/match/event link.')


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != 'https':
            raise SourceError('The source redirected to an insecure download.')
        if req.has_header('Authorization') and urlsplit(req.full_url).netloc != urlsplit(newurl).netloc:
            raise SourceError('The source tried to redirect account credentials to another host.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Client:
    def __init__(self):
        self.opener = build_opener(SafeRedirect())
        self.last_hltv = 0

    def open(self, url, *, token='', data=None):
        if urlsplit(url).scheme != 'https':
            raise SourceError('The source did not provide an HTTPS download URL.')
        headers = {'User-Agent': 'CS2Toolbox/1.0', 'Accept-Encoding': 'identity'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if data is not None:
            headers['Content-Type'] = 'application/json'
        for attempt in range(3):
            if urlsplit(url).hostname == 'www.hltv.org':
                time.sleep(max(0, 1.5 - (time.monotonic() - self.last_hltv)))
                self.last_hltv = time.monotonic()
            try:
                return self.opener.open(Request(url, headers=headers, data=json.dumps(data).encode() if data is not None else None), timeout=45)
            except HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    delay = exc.headers.get('Retry-After', '')
                    time.sleep(min(30, int(delay)) if delay.isdigit() else 2 ** (attempt + 1))
                    continue
                host = urlsplit(url).hostname
                if host in ('hltv.org', 'www.hltv.org') and exc.code in (403, 503):
                    raise AccessError('HLTV blocked automated access. Open the link in your browser; download demos there and use Local analysis. No challenge bypass is attempted.') from None
                if exc.code in (401, 403):
                    raise AccessError(f'{host}: access denied. Check the Data API key and separate Downloads API token for FACEIT.') from None
                raise SourceError(f'{host}: HTTP {exc.code}. The demo may be unavailable or expired.') from None
            except (URLError, TimeoutError) as exc:
                if attempt == 2:
                    raise SourceError(f'{urlsplit(url).hostname}: connection failed. Check internet access and try again.') from None
                time.sleep(2 ** (attempt + 1))

    def json(self, url, **kwargs):
        with self.open(url, **kwargs) as response:
            return json.load(response)

    def html(self, url):
        with self.open(url) as response:
            page = response.read(8 * 1024 * 1024).decode('utf-8', 'replace')
        if 'Just a moment...' in page or 'cf-chl-' in page:
            raise AccessError('HLTV requires a browser check. Download in your browser and use Local analysis.')
        return parse_html(page)


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    @property
    def text(self):
        return ' '.join(' '.join(c.text if isinstance(c, Node) else c for c in self.children).split())

    def all(self, cls=None, tag=None):
        found = []
        for child in self.children:
            if isinstance(child, Node):
                if (cls is None or cls in child.attrs.get('class', '').split()) and (tag is None or tag == child.tag):
                    found.append(child)
                found.extend(child.all(cls, tag))
        return found

    def first(self, cls=None, tag=None):
        nodes = self.all(cls, tag)
        if not nodes:
            raise SourceError(f'HLTV page is missing {cls or tag}. The page format may have changed.')
        return nodes[0]


class PageParser(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_html(page):
    parser = PageParser()
    parser.feed(page)
    return parser.root


def map_name(value):
    return re.sub(r'[^a-z0-9_-]', '', str(value).lower().removeprefix('de_').replace(' ', ''))


def hltv_match(page, link, owner=''):
    header = page.first('teamsBox')
    teams = header.all('teamName')
    if len(teams) != 2:
        raise SourceError('HLTV did not provide two team names. No downloads started.')
    teams = [node.text for node in teams]
    date = header.first('date').attrs.get('data-unix')
    if not date or not date.isdigit():
        raise SourceError('HLTV match date is unavailable.')
    maps = []
    for holder in page.all('mapholder'):
        name = map_name(holder.first('mapname').text)
        left, right = holder.all('results-left'), holder.all('results-right')
        if not left or not right:
            continue  # unplayed decider
        scores = [side[0].first('results-team-score').text for side in (left, right)]
        if not all(s.isdigit() for s in scores):
            continue
        maps.append({'map': name, 'score': [int(s) for s in scores]})
    downloads = []
    for anchor in page.all(tag='a'):
        href = anchor.attrs.get('data-demo-link') or anchor.attrs.get('href', '')
        if re.match(r'^(?:https://www\.hltv\.org)?/download/demo/\d+', href):
            url = urljoin('https://www.hltv.org', href)
            if url not in downloads:
                downloads.append(url)
    events = header.all('event')
    event = events[0].text if events else ''
    if not event:
        # Current HLTV puts the event link inside .timeAndEvent.
        for node in header.all('timeAndEvent'):
            event = next((a.text for a in node.all(tag='a') if '/events/' in a.attrs.get('href', '')), '')
    if not event or not maps:
        raise SourceError('HLTV match has no completed maps or tournament metadata.')
    linked_teams = {}
    for anchor in header.all(tag='a'):
        team_link = re.match(r'^(?:https://www\.hltv\.org)?/team/(\d+)(?:/|$)', anchor.attrs.get('href', ''))
        names = [node.text for node in anchor.all('teamName')]
        if team_link and len(names) == 1 and names[0] in teams:
            linked_teams[names[0]] = 'hltv:' + team_link[1]
    heatmap_identity = None
    if len(linked_teams) == 2 and owner in linked_teams:
        heatmap_identity = {'version':1, 'mode':'team', 'selected_team_id':linked_teams[owner],
            'teams':[{'id':linked_teams[name], 'name':name, 'clan_names':[name]} for name in teams]}
    return {'id': 'hltv:' + link['id'], 'url': link['url'], 'source': 'hltv', 'teams': teams,
            'heatmap_identity':heatmap_identity,
            'owner': owner or '-vs-'.join(teams), 'label': '-vs-'.join(teams), 'event': event,
            'date': datetime.fromtimestamp(int(date) / 1000, timezone.utc).date().isoformat(),
            'maps': maps, 'downloads': downloads}


class Resolver:
    def __init__(self, client=None, log=print):
        self.client = client or Client()
        self.log = log

    def faceit(self, path):
        key = get_secret('FACEIT_API_KEY')
        if not key:
            raise SourceError('Add a FACEIT Data API key in Tools & setup first.')
        return self.client.json('https://open.faceit.com/data/v4/' + path, token=key)

    def faceit_match(self, mid, owner='', *, player_id='', team_id=''):
        data = self.faceit('matches/' + quote(mid, safe=''))
        if data.get('status', '').upper() != 'FINISHED':
            raise SourceError('Match is not finished.')
        stats = self.faceit('matches/' + quote(mid, safe='') + '/stats')
        factions = ('faction1', 'faction2')
        if team_id:
            sides = [key for key in factions if data['teams'][key].get('faction_id') == team_id]
            if len(sides) != 1:
                raise SourceError('The selected team ID is not uniquely present in this match.')
            factions = (sides[0], next(key for key in factions if key != sides[0]))
        elif owner or player_id:
            def is_target(player):
                return (player.get('player_id') == player_id if player_id
                        else player.get('nickname', '').casefold() == owner.casefold())
            sides = [key for key in factions if any(is_target(p) for p in data['teams'][key].get('roster', []))]
            if len(sides) != 1:
                raise SourceError('Cannot uniquely identify the selected player’s team. Refusing to guess the score order.')
            factions = (sides[0], next(key for key in factions if key != sides[0]))
        teams = [data['teams'][key]['name'] for key in factions]
        maps = []
        for rnd in stats.get('rounds', []):
            info = rnd.get('round_stats', {})
            score = re.fullmatch(r'\s*(\d+)\s*/\s*(\d+)\s*', info.get('Score', ''))
            if not score or not info.get('Map'):
                raise SourceError('FACEIT did not provide per-map scores and names.')
            # FACEIT stats list teams explicitly; align score with metadata faction order.
            by_id = {team['team_id']: team.get('team_stats', {}).get('Final Score') for team in rnd.get('teams', [])}
            aligned = [by_id.get(data['teams'][key]['faction_id']) for key in factions]
            if not all(str(s).isdigit() for s in aligned):
                raise SourceError('FACEIT did not provide scores aligned to both teams. Refusing to guess the filename score.')
            scores = [int(s) for s in aligned]
            maps.append({'map': map_name(info['Map']), 'score': scores})
        if not maps:
            raise SourceError('FACEIT map statistics are not available yet.')
        demos = data.get('demo_url', [])
        if isinstance(demos, str):
            demos = [demos]
        # Preserve the observed account linkage and team membership for downstream
        # heat maps. Never resolve the tracked account from a display nickname.
        heatmap_identity = None
        roster_teams = []
        for key in factions:
            team = data['teams'][key]
            roster_teams.append({'id': team.get('faction_id'), 'name': team.get('name'),
                'players': list(dict.fromkeys(p.get('game_player_id') for p in team.get('roster', [])
                    if isinstance(p.get('game_player_id'), str) and len(p['game_player_id']) == 17 and p['game_player_id'].isdigit()))})
        if team_id and all(t['id'] and t['players'] for t in roster_teams):
            heatmap_identity = {'version': 1, 'mode': 'team', 'selected_team_id': team_id, 'teams': roster_teams}
        elif player_id:
            accounts = {p.get('game_player_id') for key in factions for p in data['teams'][key].get('roster', [])
                        if p.get('player_id') == player_id and isinstance(p.get('game_player_id'), str)
                        and len(p['game_player_id']) == 17 and p['game_player_id'].isdigit()}
            if len(accounts) == 1:
                heatmap_identity = {'version': 1, 'mode': 'player', 'tracked_player_id': accounts.pop()}
        return {'id': 'faceit:' + mid, 'source': 'faceit', 'url': f'https://www.faceit.com/en/cs2/room/{mid}',
                'collection_kind': 'team' if team_id else 'player' if owner or player_id else 'match',
                'selected_player_id': player_id, 'selected_team_id': team_id,
                'heatmap_identity': heatmap_identity,
                'teams': teams, 'owner': owner or '-vs-'.join(teams), 'label': '-vs-'.join(teams) if team_id else owner or '-vs-'.join(teams),
                'event': 'FaceIt', 'date': datetime.fromtimestamp(data['finished_at'], timezone.utc).date().isoformat(),
                'maps': maps, 'downloads': list(dict.fromkeys(demos))}

    def resolve(self, value, count=10):
        link = classify_link(value)
        if link['source'] == 'faceit' and link['kind'] == 'team':
            raise SourceError('Scan this team’s league seasons and select a season first.')
        if link['kind'] in ('player', 'team') and not 1 <= int(count) <= 1000:
            raise SourceError('Choose between 1 and 1000 recent games.')
        plan = {'version': 1, 'link': link, 'matches': [], 'unavailable': []}
        owner = ''
        target_player_id = ''
        if link['source'] == 'faceit':
            if link['kind'] == 'player':
                player = self.faceit('players?' + urlencode({'nickname': link['id'], 'game': 'cs2'}))
                owner = player['nickname']
                target_player_id = player['player_id']
                ids, offset = [], 0
                while len(ids) < count:
                    items = self.faceit(f"players/{quote(player['player_id'], safe='')}/history?game=cs2&offset={offset}&limit={min(100, count-len(ids))}").get('items', [])
                    if not items:
                        break
                    ids.extend(item['match_id'] for item in items)
                    offset += len(items)
                ids = list(dict.fromkeys(ids))[:count]
            else:
                ids = [link['id']]
            match_links = [{'id': mid, 'url': f'https://www.faceit.com/en/cs2/room/{mid}'} for mid in ids]
        elif link['kind'] == 'match':
            match_links = [link]
        else:
            if link['kind'] == 'team':
                owner = self.client.html(link['url']).first('profile-team-name').text
            query = {'team' if link['kind'] == 'team' else 'event': link['id']}
            match_links, seen, offset = [], set(), 0
            while True:
                page = self.client.html('https://www.hltv.org/results?' + urlencode({**query, 'offset': offset}))
                found = []
                for result in page.all('result-con'):
                    for anchor in result.all(tag='a'):
                        href = anchor.attrs.get('href', '')
                        if re.fullmatch(r'/matches/\d+/[^/]+', href):
                            candidate = classify_link(urljoin('https://www.hltv.org', href))
                            if candidate['id'] not in seen:
                                found.append(candidate)
                                seen.add(candidate['id'])
                if not found:
                    # An empty results page is valid; populated unfamiliar markup is not.
                    if not page.all('results-holder'):
                        raise SourceError('HLTV results format was not recognized. No partial tournament will be downloaded.')
                    break
                match_links.extend(found)
                if link['kind'] == 'team' and len(match_links) >= count:
                    match_links = match_links[:count]
                    break
                offset += len(found)
                if offset >= 10000:
                    raise SourceError('HLTV results exceeded the safety limit. Use a smaller event.')
        for index, item in enumerate(match_links, 1):
            self.log(f"Reviewing match {index}/{len(match_links)}: {link['source']}:{item['id']}")
            try:
                match = self.faceit_match(item['id'], owner, player_id=target_player_id) if link['source'] == 'faceit' else hltv_match(self.client.html(item['url']), item, owner)
                if not match['downloads'] and link['source'] != 'faceit':
                    raise SourceError('No demo download is published (it may be expired).')
                plan['matches'].append(match)
            except AccessError:
                raise
            except (KeyError, TypeError, ValueError) as exc:
                plan['unavailable'].append({'url': item['url'], 'reason': str(exc)})
                self.log(f"Unavailable: {item['url']} — {exc}")
        if not match_links:
            raise SourceError('No completed matches were found for this link.')
        plan['requested_matches'] = len(match_links)
        return plan
