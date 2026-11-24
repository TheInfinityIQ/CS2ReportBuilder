"""Read-only, deterministic evidence preparation; no demo parsing or AI calls."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'app/desktop'))
import reports as toolbox_reports

VERSION = '1.0'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def rows(path, required=()):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not set(required) <= set(reader.fieldnames or []):
            raise ValueError('Required CSV fields are unavailable: ' + str(path))
        yield from reader


def number(value, default=None):
    try:
        result = float(value)
        return result if abs(result) != float('inf') and result == result else default
    except (ValueError, TypeError):
        return default


def truth(value):
    return value is True or str(value).lower() in ('true', '1', '1.0')


def side(value):
    return 'T' if value in ('T', 'TERRORIST', 'Terrorist') else 'CT' if value == 'CT' else None


def date_for(entry):
    """Provider date first, otherwise explicit canonical filename date. Never mtime."""
    date = entry.get('date', '')
    if date:
        try:
            return datetime.fromisoformat(date.replace('Z', '+00:00')).date().isoformat(), 'provider'
        except (ValueError, TypeError):
            pass
    match = re.search(r'([A-Z][a-z]{2}-\d{2}-\d{4})', entry['name'])
    if match:
        try:
            return datetime.strptime(match[1], '%b-%d-%Y').date().isoformat(), 'canonical filename (day only)'
        except ValueError:
            pass
    return None, None


def safe_folder(analysis, source):
    folder = (Path(analysis) / source).resolve()
    if not folder.is_relative_to(Path(analysis).resolve()):
        raise ValueError('Analysis source escapes its library.')
    return folder


def select(catalog, steamid, limit):
    if not 1 <= limit <= 50:
        raise ValueError('A report must contain 1–50 games for one player.')
    if catalog.get('version') != toolbox_reports.CATALOG_VERSION:
        raise ValueError('Refresh the Toolbox report catalog first.')
    target = next((t for t in catalog['targets'] if t.get('steamid') == steamid), None)
    if not target:
        raise ValueError('Player Steam ID is absent from the Toolbox catalog.')
    candidates, exclusions, seen = [], [], set()
    for entry in catalog['entries']:
        if entry['source'] not in target['games']:
            continue
        folder = safe_folder(catalog['analysis'], entry['source'])
        summary = read_json(folder / 'match_summary.json')
        integrity = read_json(folder / 'integrity_checks.json')
        caps = read_json(folder / 'source_capabilities.json')
        date, date_basis = date_for(entry)
        reason = None
        if summary.get('valid') is not True or summary.get('coaching_valid') is not True or summary.get('round_table_valid') is not True or integrity.get('integrity_ok') is not True:
            reason = 'Validity / coaching / integrity gate failed or unknown'
        elif summary.get('contains_full_match_likely') is not True or summary.get('is_continued_segment') is True:
            reason = 'Incomplete or split recording; no automatic segment stitching'
        elif caps.get('event_streams', {}).get('player_death', {}).get('parsed') is not True or not (folder / 'events/player_death.csv.gz').is_file():
            reason = 'Death stream unavailable; never interpreted as zero'
        elif not date:
            reason = 'No defensible match date; modification time not used'
        elif entry.get('revision') and [list(r) for r in toolbox_reports.revision(folder)] != [list(r) for r in entry['revision']]:
            reason = 'Analysis changed since Toolbox catalog; refresh catalog'
        if reason:
            exclusions.append(dict(source=entry['source'], reason=reason))
        else:
            candidates.append(dict(entry, date=date, date_basis=date_basis))
    candidates.sort(key=lambda e: (e['date'], e['game'], e['sha']), reverse=True)
    selected = []
    for entry in candidates:
        if entry['sha'] in seen or entry['game'] in seen:
            exclusions.append(dict(source=entry['source'], reason='Duplicate demo hash or canonical game'))
            continue
        seen.update((entry['sha'], entry['game']))
        if len(selected) < limit:
            selected.append(entry)
        else:
            exclusions.append(dict(source=entry['source'], reason='Outside requested most-recent-game cap'))
    if not selected:
        raise ValueError('No eligible complete games remain.')
    return target, selected, exclusions


def analyze_game(entry, analysis, steamid):
    folder = safe_folder(analysis, entry['source'])
    files = ['match_summary.json', 'integrity_checks.json', 'source_capabilities.json',
             'viewer_tracks_meta.json', 'rounds.csv', 'player_rounds.csv', 'events/player_death.csv.gz']
    input_hashes_before = {f: hashlib.sha256((folder / f).read_bytes()).hexdigest() for f in files}
    summary, integrity, caps = (read_json(folder / f) for f in files[:3])
    if any(summary.get(k) is not True for k in ('valid','coaching_valid','round_table_valid','contains_full_match_likely')) or integrity.get('integrity_ok') is not True or summary.get('is_continued_segment') is True or caps.get('event_streams',{}).get('player_death',{}).get('parsed') is not True:
        raise ValueError('Selected analysis no longer meets the evidence contract: '+entry['source'])
    meta = read_json(folder / 'viewer_tracks_meta.json')
    rate = number(summary.get('tickrate'))
    if not rate or rate <= 0 or meta.get('demo_sha256') != entry['sha']:
        raise ValueError('Missing tick rate or demo hash mismatch: ' + entry['source'])
    roster = defaultdict(list)
    for row in rows(folder / 'player_rounds.csv', ('round','steamid','side','result')):
        roster[row['round']].append(row)
    deaths = sorted(rows(folder / 'events/player_death.csv.gz', ('tick','user_steamid','attacker_steamid')), key=lambda d: number(d.get('tick'), -1))
    if any(number(d['tick']) is None or not d['user_steamid'] for d in deaths):
        raise ValueError('Unusable death identity or tick: '+entry['source'])
    records, excluded = [], []
    for rnd in rows(folder / 'rounds.csv', ('round','start_tick','freeze_end_tick','end_tick','winner','round_observation_complete')):
        rid = rnd['round']
        members = {p['steamid']: side(p['side']) for p in roster[rid]}
        player = next((p for p in roster[rid] if p['steamid'] == steamid), None)
        start, freeze, end = (number(rnd.get(k)) for k in ('start_tick', 'freeze_end_tick', 'end_tick'))
        if not truth(rnd.get('round_observation_complete')) or len(members) != 10 or Counter(members.values()) != {'CT': 5, 'T': 5} or len(roster[rid]) != 10 or not player or any(v is None for v in (start, freeze, end)) or not start <= freeze < end:
            excluded.append(dict(round=rid, reason='Incomplete round, ambiguous roster, or invalid bounds'))
            continue
        own_side = members[steamid]
        if side(rnd.get('winner')) is None or player.get('result') not in ('WIN', 'LOSS') or (side(rnd['winner']) == own_side) != (player['result'] == 'WIN'):
            excluded.append(dict(round=rid, reason='Round result cannot be reconciled with recorded side'))
            continue
        alive = set(members)
        events, first_pvp, anomalous, tied = [], None, False, set()
        window = [d for d in deaths if freeze <= number(d.get('tick'), -1) <= end]
        tick_counts = Counter(number(d.get('tick')) for d in window)
        for d in window:
            victim, attacker = d.get('user_steamid'), d.get('attacker_steamid')
            dt = int(number(d['tick']))
            if victim not in alive:
                anomalous = True
                continue
            before = [sum(p in alive and s == own_side for p, s in members.items()),
                      sum(p in alive and s != own_side for p, s in members.items())]
            enemy = attacker in members and members[attacker] != members[victim]
            if tick_counts[dt] > 1:
                tied.add(dt)
            item = dict(tick=dt, seconds=round((dt-freeze)/rate, 2), attacker=attacker, victim=victim,
                        attacker_name=d.get('attacker_name'), victim_name=d.get('user_name'),
                        enemy=enemy, before=before, weapon=d.get('weapon'),
                        place=d.get('user_last_place_name'), attacker_place=d.get('attacker_last_place_name'),
                        victim_inventory=d.get('user_inventory'), victim_weapon=d.get('user_active_weapon_name'),
                        victim_equip=number(d.get('user_current_equip_value')),
                        attacker_equip=number(d.get('attacker_current_equip_value')),
                        plant=number(rnd.get('bomb_plant_tick')),
                        same_tick_ambiguous=tick_counts[dt] > 1)
            if enemy and first_pvp is None:
                first_pvp = item
            alive.remove(victim)
            item['after'] = [sum(p in alive and s == own_side for p, s in members.items()),
                             sum(p in alive and s != own_side for p, s in members.items())]
            events.append(item)
        # A malformed death sequence cannot establish alive-count coaching.
        if anomalous:
            excluded.append(dict(round=rid, reason='Duplicate / non-roster death event; alive timeline withheld'))
            continue
        kills = [e for e in events if e['enemy'] and e['attacker'] == steamid]
        own_death = next((e for e in events if e['victim'] == steamid), None)
        opening = 'kill' if first_pvp and first_pvp['attacker'] == steamid else 'death' if first_pvp and first_pvp['victim'] == steamid else 'other'
        if first_pvp and first_pvp['same_tick_ambiguous']:
            opening = 'unknown'
        records.append(dict(id=entry['sha'][:12]+':'+rid, source=entry['source'], sha=entry['sha'],
                            round=int(rid), parser_round=rnd.get('parser_round'), map=entry['map'], date=entry['date'],
                            side=own_side, win=player['result']=='WIN', start=start, freeze=freeze, end=end,
                            tickrate=rate, plant=number(rnd.get('bomb_plant_tick')), reason=rnd.get('reason'),
                            opening=opening, kills=kills, death=own_death, events=events,
                            score_before=[number(rnd.get('ct_score_before')), number(rnd.get('t_score_before'))]))
    # Hash precisely the inputs that supplied claims; replay inputs are recorded at bundling.
    fingerprints = {f: hashlib.sha256((folder / f).read_bytes()).hexdigest() for f in files}
    if fingerprints != input_hashes_before:
        raise ValueError('Analysis changed during evidence preparation: '+entry['source'])
    return dict(source=entry['source'], sha=entry['sha'], game=entry['game'], name=entry['name'],
                date=entry['date'], date_basis=entry['date_basis'], map=entry['map'],
                schema=summary.get('schema_version'), tickrate=rate,
                warnings=integrity.get('warnings', []), capabilities={'player_death':caps['event_streams']['player_death']},
                inputs=fingerprints, rounds=records, excluded_rounds=excluded)


def prepare(catalog, steamid, limit=50):
    target, selected, exclusions = select(catalog, steamid, limit)
    games = []
    for i, entry in enumerate(selected):
        print(f'Preparing evidence {i+1}/{len(selected)}: {entry["map"]} {entry["date"]}', flush=True)
        games.append(analyze_game(entry, catalog['analysis'], steamid))
    rounds = [r for g in games for r in g['rounds']]
    return dict(version=VERSION, target={k:v for k,v in target.items() if k!='games'},
                analysis=catalog['analysis'], selection={'limit':limit,'order':'date descending, canonical game ID and hash tie-break within a day',
                'eligible_games':len(selected),'exclusions':exclusions}, games=games,
                totals=dict(games=len(games), rounds=len(rounds), wins=sum(r['win'] for r in rounds),
                            kills=sum(len(r['kills']) for r in rounds), deaths=sum(r['death'] is not None for r in rounds),
                            opening=Counter(r['opening'] for r in rounds),
                            maps=Counter(r['map'] for r in rounds), sides=Counter(r['side'] for r in rounds)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--steamid', required=True)
    p.add_argument('--limit', type=int, default=50)
    p.add_argument('--catalog', type=Path, default=ROOT/'data/.desktop/report-catalog.json')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = prepare(read_json(args.catalog), args.steamid, args.limit)
    output = args.output.resolve()
    if output.is_relative_to(Path(result['analysis']).resolve()):
        raise ValueError('Reports must be saved outside the analysis library.')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(result['totals']))


if __name__ == '__main__':
    main()
