"""Opening movement passages, v1. Local deterministic analysis; no replay/AI calls.

Cells measure route entries, not dwell time. Samples are simplified with a 12-world-
unit deadband, then clipped and rasterized on a 64x64 radar grid. A conservative
gap/speed gate excludes unobserved movement. See README for eligibility/limits.
"""
import csv
import gzip
import hashlib
import json
import math
import threading
import time
import uuid
from collections import OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VERSION = 'opening-passages-1'
GRID = 64
FILES = ('header.json', 'match_summary.json', 'source_capabilities.json',
         'integrity_checks.json', 'viewer_tracks_meta.json', 'rounds.csv',
         'player_rounds.csv', 'viewer_tracks.csv.gz', 'events/player_death.csv.gz',
         'analysis_source.json', 'heatmap_identity.json')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}


def rows(path):
    if not path.is_file():
        return
    with (gzip.open if path.suffix == '.gz' else open)(path, 'rt', encoding='utf-8-sig', newline='') as stream:
        yield from csv.DictReader(stream)


def numeric(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def steam(value):
    # Keep account IDs out of floating-point conversion, including CSV joins.
    return isinstance(value, str) and len(value) == 17 and value.isdigit()


def round_quality(rnd, selected):
    tracks=[p['track'] for p in rnd['players'] if p['id'] in selected]
    return (rnd.get('valid',True),rnd.get('deaths_available',True),
            sum(len(t)>1 for t in tracks),sum(len(t) for t in tracks))


def revision(folder):
    paths = [folder/f for f in FILES] + [p/'heatmap_identity.json' for p in list(folder.parents)[:3]]
    return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths if p.is_file())


def identity(folder, summary):
    """Only explicit metadata can authorize identities; names/folders never do."""
    source = read_json(folder / 'analysis_source.json')
    context = source.get('context') or {}
    info = read_json(folder / 'heatmap_identity.json') or context.get('heatmap_identity') or {}
    for parent in list(folder.parents)[:3]:
        binding = read_json(parent / 'heatmap_identity.json')
        if binding:
            info = info or binding
            break
    kind = context.get('collection_kind')
    # A declared player collection cannot be upgraded to team mode by a sidecar.
    mode = 'player' if kind == 'player' else info.get('mode')
    if mode is None and steam(summary.get('target_steamid')):
        mode = 'player'
    if mode == 'player':
        target = info.get('tracked_player_id') or summary.get('target_steamid')
        if not steam(target):
            return None, 'Tracked player SteamID is unavailable; heat map disabled.'
        return {'mode': mode, 'tracked': target, 'bundle': 'player:' + target,
                'teams': {}, 'selected_team': None}, None
    if mode == 'team':
        selected = info.get('selected_team_id') or context.get('selected_team_id')
        teams = info.get('teams', [])
        if not selected or len(teams) != 2 or len({t.get('id') for t in teams}) != 2:
            return None, 'Verified team IDs and roster membership are unavailable.'
        mapping = {}
        clans = {}
        for team in teams:
            if not isinstance(team.get('id'), str) or not team['id']:
                return None, 'Invalid team identity.'
            for sid in team.get('players', []):
                if not steam(sid) or sid in mapping:
                    return None, 'Ambiguous team roster identity.'
                mapping[sid] = team['id']
            for clan in team.get('clan_names', []):
                if not isinstance(clan,str) or not clan or clan in clans:
                    return None, 'Ambiguous canonical team-name linkage.'
                clans[clan]=team['id']
        if not mapping and clans:
            canonical={r['round']:r for r in rows(folder/'rounds.csv')}
            for player in rows(folder/'player_rounds.csv'):
                rnd=canonical.get(player.get('round'),{})
                side=player.get('side')
                clan=rnd.get('ct_team_clan_name' if side=='CT' else 't_team_clan_name' if side in ('T','TERRORIST') else '')
                team_id=clans.get(clan)
                sid=player.get('steamid')
                if not steam(sid) or not team_id or (sid in mapping and mapping[sid]!=team_id):
                    return None, 'Canonical round team cannot be linked unambiguously to verified team IDs.'
                mapping[sid]=team_id
        if selected not in {t['id'] for t in teams} or not mapping:
            return None, 'Selected team is not present in verified metadata.'
        return {'mode': mode, 'tracked': None, 'bundle': 'team:' + selected,
                'teams': {t['id']: t.get('name') or t['id'] for t in teams},
                'membership': mapping, 'selected_team': selected,
                'opponent': next(t['id'] for t in teams if t['id'] != selected)}, None
    return None, 'Bundle type or tracked-player identity is unavailable; heat map disabled.'


def passages(track, start, end, rate, calibration, own_death=None):
    """Return sparse cell entries. No stationary heat; one entry per uninterrupted visit.

    End clipping happens AFTER the deadband, avoiding sampling-rate-specific jitter.
    Death clipping never includes a sample after the player's recorded death.
    """
    if own_death is not None:
        end = min(end, own_death)
    if end <= start:
        return {}, False
    scale = calibration['scale']
    def cell(x, y):
        u = (x - calibration['pos_x']) / scale / 16
        v = (calibration['pos_y'] - y) / scale / 16
        return (math.floor(u), math.floor(v))
    result, last_cell, anchor, previous = defaultdict(float), None, None, None
    observed = False
    for point in track:
        t, x, y, z = point
        if previous is None:
            anchor = previous = point
            continue
        dt = t - previous[0]
        valid = (0 < dt <= rate * .5 and
                 math.dist(previous[1:4], point[1:4]) <= 400 * dt / rate + 24)
        if not valid:
            anchor, previous, last_cell = point, point, None
            continue
        # A valid pair establishes observation even when the player never moves.
        if t >= start and previous[0] <= end:
            observed = True
        previous = point
        if math.dist(anchor[1:4], point[1:4]) < 12:
            continue
        a, b = anchor, point
        anchor = point
        lo, hi = max(start, a[0]), min(end, b[0])
        if hi <= lo:
            continue
        f0, f1 = (lo-a[0])/(b[0]-a[0]), (hi-a[0])/(b[0]-a[0])
        p = [a[i] + (b[i]-a[i])*f0 for i in (1, 2)]
        q = [a[i] + (b[i]-a[i])*f1 for i in (1, 2)]
        # Amanatides-style grid traversal via exact cell-boundary crossings.
        u0 = (p[0]-calibration['pos_x'])/scale/16
        v0 = (calibration['pos_y']-p[1])/scale/16
        u1 = (q[0]-calibration['pos_x'])/scale/16
        v1 = (calibration['pos_y']-q[1])/scale/16
        cuts = {0., 1.}
        for x0, x1 in ((u0, u1), (v0, v1)):
            if x1 != x0:
                for boundary in range(math.floor(min(x0, x1))+1, math.ceil(max(x0, x1))):
                    cuts.add((boundary-x0)/(x1-x0))
        cuts = sorted(cuts)
        for left, right in zip(cuts, cuts[1:]):
            f = (left+right)/2
            c = (math.floor(u0+(u1-u0)*f), math.floor(v0+(v1-v0)*f))
            if c != last_cell:
                if 0 <= c[0] < GRID and 0 <= c[1] < GRID:
                    result[c[1]*GRID+c[0]] += 1
                last_cell = c
    return dict(result), observed


def aggregate(games, selected, seconds=40, cutoff=True, side='both', progress=None, cancelled=None):
    """Games have canonical round IDs, all-round deaths, and actual per-round sides."""
    if not isinstance(seconds, int) or not 1 <= seconds <= 120 or side not in ('both', 'CT', 'T'):
        raise ValueError('Invalid heat map timing or side.')
    layers, eligible, excluded = {}, {}, defaultdict(int)
    seen, best = set(), {}
    for game in games:
        for rnd in game['rounds']:
            key=(game['game'],rnd['id'])
            if key not in best or round_quality(rnd,selected)>round_quality(best[key],selected):best[key]=rnd
    for index, game in enumerate(games):
        if cancelled and cancelled():
            raise ValueError('Heat map request cancelled.')
        sums = {'CT': defaultdict(float), 'T': defaultdict(float)}
        counts = {'CT': 0, 'T': 0}
        for rnd in game['rounds']:
            key = (game['game'], rnd['id'])
            if key in seen or best[key] is not rnd:
                excluded['duplicate_rounds'] += 1
                continue
            seen.add(key)
            if not rnd.get('valid', True):
                excluded['invalid_rounds'] += 1
                continue
            start, end, rate = rnd['start'], rnd['end'], game['rate']
            if not rnd.get('deaths_available', True):
                excluded['missing_death_stream'] += 1
                continue
            death_ticks = [d['tick'] for d in rnd['deaths'] if start <= d['tick'] <= end]
            stop = min(end, start+seconds*rate, min(death_ticks) if cutoff and death_ticks else end)
            per_side = {'CT': defaultdict(float), 'T': defaultdict(float)}
            present, unknown = set(), set()
            for player in rnd['players']:
                if player['id'] not in selected or player['side'] not in ('CT', 'T'):
                    continue
                own = [d['tick'] for d in rnd['deaths'] if d['id'] == player['id'] and start <= d['tick'] <= end]
                grid, observed = passages(player['track'], start, stop, rate, game['calibration'], min(own) if own else None)
                if not observed:
                    excluded['missing_player_windows'] += 1
                    unknown.add(player['side'])
                    continue
                present.add(player['side'])
                for cell, value in grid.items():
                    per_side[player['side']][cell] += value
            if not present:
                excluded['absent_selection_rounds'] += 1
            for bucket in present - unknown:
                counts[bucket] += 1
                for cell, value in per_side[bucket].items():
                    sums[bucket][cell] += value
        # Merge segments/copies of one logical game before applying equal-game weight.
        key = game['game']
        if key not in layers:
            layers[key] = {'CT': defaultdict(float), 'T': defaultdict(float)}
            eligible[key] = {'CT': 0, 'T': 0}
        for bucket in ('CT', 'T'):
            eligible[key][bucket] += counts[bucket]
            for cell, value in sums[bucket].items():
                layers[key][bucket][cell] += value
        if progress:
            progress(index+1, len(games))
    output, samples = {}, {}
    for bucket in ('CT', 'T'):
        grid, n_games, n_rounds = [0.]*(GRID*GRID), 0, 0
        for key, game in layers.items():
            n = eligible[key][bucket]
            if not n:
                continue
            n_games += 1
            n_rounds += n
            for cell, value in game[bucket].items():
                grid[cell] += value/n
        if n_games:
            grid = [v/n_games for v in grid]
        output[bucket] = grid if side in ('both', bucket) else [0.]*(GRID*GRID)
        samples[bucket] = {'games': n_games, 'rounds': n_rounds}
    return {'version': VERSION, 'grid': GRID, 'layers': output, 'samples': samples,
            'exclusions': dict(excluded), 'scale': .5, 'projection': 'All-level projection',
            'unit': 'mean route entries per eligible round, equal weight per game'}


class Heatmaps:
    """Single background worker, bounded prepared/result caches and cancellable jobs."""
    def __init__(self, analysis, calibration):
        self.root = Path(analysis).resolve()
        self.calibration = calibration
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='heatmap')
        self.lock = threading.RLock()
        self.catalog_time, self.catalog_data = 0, []
        self.prepared, self.results, self.jobs = OrderedDict(), OrderedDict(), OrderedDict()

    def safe(self, source):
        folder = (self.root / source).resolve()
        if not folder.is_relative_to(self.root) or not (folder/'rounds.csv').is_file():
            raise ValueError('Unknown analysis source.')
        return folder

    def catalog(self):
        with self.lock:
            if time.monotonic()-self.catalog_time < 5:
                return self.catalog_data
            found = []
            for meta in sorted(self.root.rglob('viewer_tracks_meta.json')):
                folder = meta.parent
                if not folder.resolve().is_relative_to(self.root) or not (folder/'rounds.csv').is_file():
                    continue
                try:
                    summary = read_json(folder/'match_summary.json')
                    info, reason = identity(folder, summary)
                    header = read_json(folder/'header.json')
                    m = read_json(meta)
                    source = read_json(folder/'analysis_source.json')
                    context = source.get('context') or {}
                    sha = m.get('demo_sha256') or source.get('sha256')
                    if context.get('id'):
                        sha = context['id'] + ':' + (summary.get('map_name') or header.get('map_name') or '')
                    found.append({'source': folder.relative_to(self.root).as_posix(), 'name': folder.name,
                                  'map': summary.get('map_name') or header.get('map_name'),
                                  'game': sha, 'identity': info, 'unavailable': reason,
                                  'revision': revision(folder)})
                except (ValueError, OSError, KeyError, TypeError):
                    continue
            self.catalog_data, self.catalog_time = found, time.monotonic()
            return found

    def context(self, source):
        self.safe(source)
        catalog = self.catalog()
        anchor = next((g for g in catalog if g['source'] == source), None)
        if not anchor or not anchor['identity']:
            return {'available': False, 'reason': (anchor or {}).get('unavailable') or 'Movement metadata unavailable.'}
        info = anchor['identity']
        games = [g for g in catalog if g['identity'] and g['identity']['bundle'] == info['bundle'] and g['map'] == anchor['map']]
        roster, opponents = {}, {}
        for game in games:
            gi = game['identity']
            if gi['mode'] == 'team':
                opponent = opponents.setdefault(gi['opponent'], {'id':gi['opponent'], 'name':gi['teams'][gi['opponent']], 'games':set()})
                opponent['games'].add(game['game'] or game['source'])
            for row in rows(self.safe(game['source'])/'player_rounds.csv'):
                sid = row.get('steamid')
                if gi['mode'] == 'player' and sid != info['tracked']:
                    continue
                team = gi.get('membership', {}).get(sid)
                if gi['mode'] == 'team' and team not in gi['teams']:
                    continue
                entry = roster.setdefault(sid, {'id': sid, 'names': set(), 'games': set(), 'rounds': set(),
                                                'coverage': {},
                                                'group': 'Team A' if team == info['selected_team'] else 'Opponents'})
                entry['names'].add(row.get('name') or sid)
                entry['games'].add(game['game'] or game['source'])
                entry['rounds'].add((game['game'] or game['source'], row.get('parser_round') or row.get('round')))
                covered = entry['coverage'].setdefault(game['game'] or game['source'],
                          {'rounds':set(), 'opponent':gi.get('opponent')})
                covered['rounds'].add(row.get('parser_round') or row.get('round'))
        menu = {g['game'] or g['source']:{'source':g['source'], 'name':g['name'], 'game':g['game']} for g in games}
        menu[anchor['game'] or anchor['source']] = {'source':anchor['source'], 'name':anchor['name'], 'game':anchor['game']}
        return {'available': True, 'mode': info['mode'], 'tracked': info['tracked'], 'map': anchor['map'],
                'teamName': info.get('teams', {}).get(info['selected_team'], 'Tracked player'),
                'games': list(menu.values()),
                'opponents': [{**o,'games':len(o['games'])} for o in opponents.values()],
                'players': [{**v, 'names': sorted(v['names']), 'games':len(v['games']), 'rounds':len(v['rounds']),
                             'coverage':{k:{**c,'rounds':len(c['rounds'])} for k,c in v['coverage'].items()}}
                            for v in roster.values()]}

    def prepare(self, entry):
        folder = self.safe(entry['source'])
        key = (entry['source'], revision(folder))
        if key in self.prepared:
            self.prepared.move_to_end(key)
            return self.prepared[key]
        summary, integrity = read_json(folder/'match_summary.json'), read_json(folder/'integrity_checks.json')
        meta, caps = read_json(folder/'viewer_tracks_meta.json'), read_json(folder/'source_capabilities.json')
        if summary.get('valid') is not True or summary.get('round_table_valid') is False or integrity.get('integrity_ok') is not True:
            raise ValueError('Analysis failed canonical validity/integrity checks.')
        rate = numeric(meta.get('tickrate') or summary.get('tickrate'))
        if not rate or entry['map'] not in self.calibration or not entry['game']:
            raise ValueError('Tickrate, calibration or canonical demo identity unavailable.')
        result = {'game': entry['game'], 'rate':rate, 'calibration':self.calibration[entry['map']], 'rounds':[]}
        rounds = {}
        for row in rows(folder/'rounds.csv'):
            start, end = numeric(row.get('freeze_end_tick')), numeric(row.get('end_tick'))
            if start is None or end is None or end <= start:
                continue
            ct_score, t_score = numeric(row.get('ct_score_before')), numeric(row.get('t_score_before'))
            # Total completed competitive rounds is invariant to halftime/OT side
            # swaps. It joins logical segments without assuming a 12-round switch.
            if ct_score is not None and t_score is not None and ct_score>=0 and t_score>=0:
                rid = 'completed-round:' + str(int(ct_score+t_score))
            else:
                demo = meta.get('demo_sha256') or entry['game']
                rid = demo + ':' + (row.get('parser_round') or row['round'])
            valid = (row.get('round_observation_complete', '').lower() == 'true' and row.get('winner') in ('CT','T')
                     and str(row.get('is_warmup','false')).lower() not in ('true','1')
                     and str(row.get('competitive','true')).lower() not in ('false','0'))
            rnd = {'id':rid, 'start':start, 'end':end, 'valid':valid,
                   'deaths_available':caps.get('event_streams', {}).get('player_death', {}).get('parsed') is True
                     and (folder/'events/player_death.csv.gz').is_file(),
                   'players':[], 'deaths':[]}
            rounds[row['round']] = rnd
            result['rounds'].append(rnd)
        memberships = {}
        for row in rows(folder/'player_rounds.csv'):
            if row['round'] not in rounds or not steam(row.get('steamid')):
                continue
            gi = entry['identity']
            if gi['mode']=='player' and row['steamid']!=gi['tracked']:
                continue
            if gi['mode'] == 'team' and row['steamid'] not in gi['membership']:
                raise ValueError('Canonical participant lacks verified team membership.')
            recorded_side = row.get('side')
            side = 'T' if recorded_side in ('T','TERRORIST') else 'CT' if recorded_side == 'CT' else None
            player = {'id':row['steamid'], 'side':side, 'track':[]}
            memberships[(row['round'],row['steamid'])] = player
            rounds[row['round']]['players'].append(player)
        sample_count = 0
        for row in rows(folder/'viewer_tracks.csv.gz'):
            player = memberships.get((row.get('round'),row.get('steamid')))
            if player is None:
                continue
            values = [numeric(row.get(k)) for k in ('tick','x','y','z')]
            if all(v is not None for v in values):
                player['track'].append(values)
                sample_count += 1
                if sample_count > 1000000:
                    raise ValueError('Movement exceeds the one-million-sample per-game memory limit.')
        for rnd in result['rounds']:
            for player in rnd['players']:
                player['track'].sort(key=lambda p:p[0])
        # Death stream is read independently of the selected heat contributors.
        for row in rows(folder/'events/player_death.csv.gz'):
            tick = numeric(row.get('tick'))
            if tick is None:
                continue
            for rnd in result['rounds']:
                if rnd['start'] <= tick <= rnd['end']:
                    rnd['deaths'].append({'tick':tick, 'id':row.get('user_steamid')})
        self.prepared[key] = result
        while len(self.prepared) > 2:
            self.prepared.popitem(last=False)
        return result

    def submit(self, request):
        source = request.get('source', '')
        anchor = next((g for g in self.catalog() if g['source'] == source), None)
        if not anchor or not anchor['identity']:
            raise ValueError('Heat map identity is unavailable.')
        info = anchor['identity']
        selected = request.get('players', [])
        if not isinstance(selected, list) or len(selected)>100 or not all(steam(s) for s in selected):
            raise ValueError('Invalid player selection.')
        if info['mode']=='player' and any(s != info['tracked'] for s in selected):
            raise ValueError('PUG heat maps are restricted to the tracked player.')
        opponents = request.get('opponents', [])
        if not isinstance(opponents,list) or len(opponents)>100 or not all(isinstance(s,str) for s in opponents):
            raise ValueError('Invalid opponent selection.')
        if info['mode']=='player' and opponents:
            raise ValueError('Opponent filters are unavailable for PUG heat maps.')
        scope = request.get('game','all')
        entries = [g for g in self.catalog() if g['map']==anchor['map'] and g['identity'] and g['identity']['bundle']==info['bundle']]
        known_opponents = {g['identity'].get('opponent') for g in entries}
        allowed = {s for g in entries for s in (g['identity'].get('membership',{}) if info['mode']=='team' else [info['tracked']])}
        if not set(selected)<=allowed:
            raise ValueError('Player does not belong to this bundle.')
        if scope!='all':
            target = next((g for g in entries if g['source']==scope),None)
            if not target:
                raise ValueError('Game is outside the selected map/bundle.')
            entries = [g for g in entries if g['game']==target['game']]
        if info['mode']=='team':
            if not set(opponents)<=known_opponents:
                raise ValueError('Opponent is outside this scope.')
            entries = [g for g in entries if g['identity']['opponent'] in opponents]
        seconds, cutoff, side = request.get('seconds',40), request.get('cutoff',True), request.get('side','both')
        if type(seconds) is not int or not 1<=seconds<=120 or type(cutoff) is not bool or side not in ('both','CT','T'):
            raise ValueError('Invalid heat map controls.')
        fingerprint = hashlib.sha256(repr((VERSION,[(e['source'],revision(self.safe(e['source']))) for e in entries],
                           sorted(selected),seconds,cutoff,side)).encode()).hexdigest()
        key = uuid.uuid4().hex
        with self.lock:
            active = sum(j['status'] in ('queued','working') for j in self.jobs.values())
            if active>=3:
                raise ValueError('Heat map worker is busy. Please retry after the current request.')
            job={'status':'queued','phase':'Preparing movement','completed':0,'total':len(entries),'cancel':False}
            self.jobs[key]=job
            cached=self.results.get(fingerprint)
            if cached is not None:
                job.update(status='complete',result=cached,phase='Ready (cached)')
            while len(self.jobs)>12:
                old=next((k for k,v in self.jobs.items() if v['status'] not in ('queued','working')),None)
                if old is None:break
                self.jobs.pop(old)
            if cached is not None:return {'job':key}
            def run():
                try:
                    job['status']='working'
                    groups=defaultdict(list)
                    for entry in entries:groups[entry['game']].append(entry)
                    result=aggregate([],set(selected),seconds,cutoff,side)
                    failures,exclusions=[],defaultdict(int)
                    job.update(total=len(groups))
                    # Retain one logical game's best round windows at a time.
                    # The full library is never accumulated in worker memory.
                    for i,copies in enumerate(groups.values()):
                        merged,best=None,{}
                        for entry in copies:
                            if job['cancel']:raise ValueError('Cancelled')
                            try:
                                prepared=self.prepare(entry)
                                merged={k:v for k,v in prepared.items() if k!='rounds'}
                                for rnd in prepared['rounds']:
                                    key=rnd['id']
                                    if key in best:exclusions['duplicate_rounds']+=1
                                    if key not in best or round_quality(rnd,set(selected))>round_quality(best[key],set(selected)):
                                        best[key]=rnd
                            except (ValueError,OSError,KeyError,TypeError) as exc:failures.append(str(exc))
                        if merged:
                            samples=sum(len(p['track']) for r in best.values() for p in r['players'])
                            if samples>1000000 or len(best)>256:
                                failures.append('Logical game exceeds bounded movement/round limits.')
                            else:
                                merged['rounds']=list(best.values())
                                job['phase']='Averaging movement'
                                single=aggregate([merged],set(selected),seconds,cutoff,side,cancelled=lambda:job['cancel'])
                                for bucket in ('CT','T'):
                                    n=single['samples'][bucket]['rounds']
                                    if n:
                                        result['samples'][bucket]['games']+=1
                                        result['samples'][bucket]['rounds']+=n
                                        result['layers'][bucket]=[a+b for a,b in zip(result['layers'][bucket],single['layers'][bucket])]
                                for reason,n in single['exclusions'].items():exclusions[reason]+=n
                        job.update(completed=i+1,phase='Preparing movement')
                    for bucket in ('CT','T'):
                        n=result['samples'][bucket]['games']
                        if n:result['layers'][bucket]=[v/n for v in result['layers'][bucket]]
                    result['exclusions']=dict(exclusions)
                    result.update(map=anchor['map'],excludedGames=failures,inputRevision=fingerprint)
                    with self.lock:
                        self.results[fingerprint]=result
                        while len(self.results)>8:self.results.popitem(last=False)
                    job.update(status='complete',result=result,phase='Ready')
                except Exception as exc:
                    job.update(status='cancelled' if job['cancel'] else 'error',error=str(exc))
            self.executor.submit(run)
        return {'job':key}

    def status(self, key, cancel=False):
        with self.lock:
            job=self.jobs.get(key)
            if not job:raise ValueError('Heat map job expired. Request it again.')
            if cancel and job['status'] in ('queued','working'):job['cancel']=True
            return {k:v for k,v in job.items() if k!='cancel'}
