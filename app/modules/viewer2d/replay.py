"""Convert extractor CSV sidecars into a portable, round-scoped replay. Stdlib only."""
from __future__ import annotations

import argparse
import ast
import csv
import gzip
import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ANALYSIS = ROOT / 'data' / 'analysis'
HERE = Path(__file__).resolve().parent


def number(value, default=0):
    try:
        result = float(value)
        return result if result == result and abs(result) != float('inf') else default
    except (TypeError, ValueError):
        return default


def truth(value):
    return str(value).lower() in ('true', '1', '1.0')


def rows(folder, name):
    file = folder / name
    if not file.exists():
        return []
    opener = gzip.open if name.endswith('.gz') else open
    with opener(file, 'rt', encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def inventory(value):
    try:
        result = ast.literal_eval(value or '[]')
        return result if isinstance(result, list) else []
    except (ValueError, SyntaxError):
        return []


def safe_source(source):
    path = (ANALYSIS / source).resolve()
    if not path.is_relative_to(ANALYSIS.resolve()) or not (path / 'rounds.csv').is_file():
        raise ValueError('Choose an analysis folder containing rounds.csv.')
    return path


@lru_cache(maxsize=2)
def read_match(source):
    folder = safe_source(source)
    names = ['rounds.csv', 'player_rounds.csv', 'player_positions.csv.gz',
             'viewer_tracks.csv.gz', 'economy.csv', 'grenade_throws.csv.gz', 'grenade_paths.csv.gz']
    data = {name: rows(folder, name) for name in names}
    data['events'] = {p.name.removesuffix('.csv.gz'): rows(folder, 'events/' + p.name)
                      for p in sorted((folder / 'events').glob('*.csv.gz'))}
    data['header'] = json.loads((folder / 'header.json').read_text(encoding='utf-8-sig'))
    meta = folder / 'viewer_tracks_meta.json'
    data['meta'] = json.loads(meta.read_text(encoding='utf-8-sig')) if meta.exists() else {}
    return data


def entity_window(path, start, end):
    """Include state already alive at the window boundary, without future leakage."""
    active = {}
    result = []
    with gzip.open(path, 'rt', encoding='utf-8-sig') as stream:
        initial_written = False
        for line in stream:
            row = json.loads(line)
            if row['tick'] > end:
                break
            if row['tick'] < start:
                if row['action'] == 'upsert': active[row['id']] = row['state']
                else: active.pop(row['id'], None)
                continue
            if not initial_written:
                result.extend({'tick': start, 'id': identity, 'action': 'upsert', 'state': state}
                              for identity, state in active.items())
                initial_written = True
            result.append(row)
        if not initial_written:
            result.extend({'tick': start, 'id': identity, 'action': 'upsert', 'state': state}
                          for identity, state in active.items())
    return result


def load_entities(folder, start, end, demo_hash):
    metadata = folder / 'entity_meta.json'
    if not metadata.exists(): return None
    meta = json.loads(metadata.read_text(encoding='utf-8-sig'))
    if not meta.get('validation', {}).get('passed'):
        raise ValueError('The v8 entity dataset has not passed validation.')
    if not demo_hash or meta.get('demo_sha256') != demo_hash:
        raise ValueError('The v8 entity dataset belongs to a different demo.')
    if meta.get('startTick', 0) > start or (meta.get('endTick') is not None and meta['endTick'] < end):
        raise ValueError('The v8 entity dataset does not cover this round.')
    result = {'fire': entity_window(folder / 'inferno_patches.jsonl.gz', start, end),
              'loot': entity_window(folder / 'loot_tracks.jsonl.gz', start, end), 'smoke': [], 'smokeDecoded': False}
    decode_meta = folder / 'smoke_decode_meta.json'
    if decode_meta.exists():
        report = json.loads(decode_meta.read_text(encoding='utf-8-sig'))
        if report.get('status') == 'decoded':
            result['smoke'] = entity_window(folder / 'smoke_voxels.jsonl.gz', start, end)
            result['smokeDecoded'] = True
    result['engineVisualParityVerified'] = False
    return result


def build_shots(events):
    """Only recorded impacts become ray endpoints; missing impacts stay missing."""
    shots = []
    def xyz(e, keys):
        values = [number(e.get(k), None) for k in keys]
        return values if all(v is not None for v in values) else None
    for e in events:
        if e['kind'] != 'fire_bullets': continue
        origin = xyz(e, ('origin_x', 'origin_y', 'origin_z'))
        if origin:
            shots.append({'tick':e['tick'], 'shooter':e.get('user_steamid'),
                          'origin':origin, 'angles':xyz(e, ('angles_x','angles_y')),
                          'source':'fire_bullets', 'impact':None})
    for e in events:
        if e['kind'] != 'weapon_fire': continue
        weapon = e.get('weapon', '').removeprefix('weapon_')
        if not weapon or weapon in ('knife','smokegrenade','flashbang','hegrenade','molotov','incgrenade','c4','decoy') or weapon.startswith('knife'): continue
        if any(s['shooter'] == e.get('user_steamid') and abs(s['tick']-e['tick']) <= 1 for s in shots): continue
        origin = xyz(e, ('user_X', 'user_Y', 'user_Z'))
        if origin:
            shots.append({'tick':e['tick'], 'shooter':e.get('user_steamid'),
                          'origin':origin, 'source':'weapon_fire_position', 'impact':None})
    impacts, matched = [], set()
    for e in events:
        if e['kind'] != 'bullet_impact' or not e.get('user_steamid'): continue
        endpoint = xyz(e, ('x','y','z'))
        candidates = [s for s in shots if s['shooter'] == e['user_steamid'] and 0 <= e['tick']-s['tick'] <= 2]
        if endpoint and candidates:
            shot = min(candidates,key=lambda s:e['tick']-s['tick'])
            matched.add(id(shot))
            impacts.append({**shot,'tick':e['tick'],'impact':endpoint,'source':'recorded_bullet_impact'})
    # Preserve multiple endpoints for pellets/penetration; never guess their order.
    return sorted([s for s in shots if id(s) not in matched]+impacts,key=lambda s:s['tick'])


def build_replay(source, round_number, entity_folder=None):
    data = read_match(source)
    rnd = next((r for r in data['rounds.csv'] if int(number(r['round'])) == round_number), None)
    if rnd is None:
        raise ValueError('Round not found.')
    rate = number(data['meta'].get('tickrate'), 64)
    start, end = int(number(rnd['freeze_end_tick'])), int(number(rnd['end_tick']))
    roster = [r for r in data['player_rounds.csv'] if int(number(r['round'])) == round_number]
    players = {r['steamid']: {'id': r['steamid'], 'name': r['name'], 'side': 'CT' if r['side'] == 'CT' else 'T',
                              'track': [], 'states': []} for r in roster}
    state_rows = []
    for row in data['player_positions.csv.gz']:
        tick = number(row['tick'])
        if start - rate * 3 <= tick <= end and row['steamid'] in players:
            state_rows.append((tick, row['steamid'], row, ''))
    events = []
    for kind, stream in data['events'].items():
        for row in stream:
            tick = number(row.get('tick'))
            if not start <= tick <= end:
                continue
            # Actor snapshots supplement the low-rate health/weapon samples.
            for prefix in ('user_', 'attacker_', 'assister_'):
                sid = row.get(prefix + 'steamid')
                if sid in players and row.get(prefix + 'health'):
                    state_rows.append((tick, sid, row, prefix))
            event = {'kind': kind, 'tick': tick}
            keys = ['user_steamid', 'user_name', 'attacker_steamid', 'attacker_name',
                    'user_X', 'user_Y', 'user_Z', 'user_yaw', 'user_pitch', 'weapon',
                    'item', 'blind_duration', 'headshot', 'health', 'entityid', 'x', 'y', 'z',
                    'origin_x', 'origin_y', 'origin_z', 'angles_x', 'angles_y', 'site']
            for key in keys:
                if row.get(key) not in (None, ''):
                    event[key] = row[key] if key.endswith(('steamid', 'name')) or key in ('weapon', 'item', 'site', 'headshot') else number(row[key])
            events.append(event)
    for tick, sid, row, prefix in sorted(state_rows, key=lambda r: r[0]):
        player = players[sid]
        prev = player['states'][-1].copy() if player['states'] else {'health': 100, 'weapon': 'knife', 'armor': 0, 'money': None, 'inventory': []}
        prev['tick'] = tick
        fields = {'health': 'health', 'weapon': 'active_weapon_name', 'armor': 'armor_value', 'money': 'balance'}
        for target, field in fields.items():
            value = row.get(prefix + field)
            if value not in (None, ''):
                prev[target] = value if target == 'weapon' else number(value)
        if row.get(prefix + 'inventory'):
            prev['inventory'] = inventory(row[prefix + 'inventory'])
        player['states'].append(prev)
    for row in data['economy.csv']:
        sid = row.get('steamid')
        if sid in players and abs(number(row['tick']) - start) <= rate * 2:
            for state in players[sid]['states']:
                if state['money'] is None:
                    state['money'] = number(row.get('balance'))
                if not state['inventory']:
                    state['inventory'] = inventory(row.get('inventory'))
    for row in data['viewer_tracks.csv.gz']:
        if int(number(row['round'])) == round_number and row['steamid'] in players and start <= number(row['tick']) <= end:
            sample = [number(row[k]) for k in ('tick', 'x', 'y', 'z', 'yaw', 'pitch', 'flags')]
            sample[0], sample[6] = int(sample[0]), int(sample[6])
            players[row['steamid']]['track'].append(sample)
    for player in players.values():
        player['track'].sort(key=lambda r: r[0])
    if not any(p['track'] for p in players.values()):
        raise ValueError('This analysis has no viewer_tracks. Generate viewer sidecars first.')
    grenades = []
    for row in data['grenade_throws.csv.gz']:
        if int(number(row['round'])) != round_number:
            continue
        grenade = {k: row[k] for k in ('throw_id', 'steamid', 'kind')}
        grenade.update({k: number(row.get(k)) for k in ('throw_tick', 'det_tick', 'land_x', 'land_y', 'land_z')})
        grenade['detonated'] = truth(row.get('detonated'))
        grenade['path'] = [[number(r[k]) for k in ('tick', 'x', 'y', 'z')]
                           for r in data['grenade_paths.csv.gz'] if r['throw_id'] == row['throw_id']]
        grenade['path'].sort(key=lambda r: r[0])
        grenades.append(grenade)
    map_name = data['header']['map_name']
    calibration = json.loads((ROOT / 'app/assets/maps/map-data.json').read_text())[map_name]
    events.sort(key=lambda r: r['tick'])
    entity_folder = Path(entity_folder) if entity_folder else safe_source(source) / 'viewer_v8'
    entities = load_entities(entity_folder, start, end, data['meta'].get('demo_sha256'))
    shots = build_shots(events)
    notes = ['Shot lines require recorded bullet-impact endpoints. Shots without impacts show only a firing flash; aim angles are never rendered as bullet paths.',
             'Health and held weapons update at saved snapshots/events; positions interpolate at 16 Hz.']
    if entities:
        notes += ['Fire uses recorded patch centers and burning flags. Nearby centers are joined into one footprint; its interpolated edge is artwork, not engine collision geometry.',
                  'Ground loot uses recorded entity positions and ownership transitions.']
        notes += (['Smoke uses decoded network voxel masks with enclosed-interior fill. Grid placement is reverse engineered; engine visual parity is unverified.',
                   'HE holes are not fabricated for decoded smoke. Visible HE clearing has not been reproduced in the tested round.']
                  if entities['smokeDecoded'] else ['Smoke and HE clearing use the original illustrative effects; raw voxel bytes are not decoded for this source.'])
    else:
        notes += ['Smoke/fire footprints and HE smoke clearing are illustrative, not exact game geometry.',
                  'Ground weapons are inferred from death inventories; only the bomb has explicit drop/pickup events.']
    checks = []
    if entities:
        for label, kind, delay in [('Smoke bloom', 'smokegrenade_detonate', 2), ('Molotov spread', 'inferno_startburn', 2)]:
            event = next((e for e in events if e['kind'] == kind), None)
            if event: checks.append({'label': label, 'tick': min(end, event['tick'] + rate * delay)})
        pairs = [(h,s) for h in grenades if h['kind']=='he' for s in grenades if s['kind']=='smoke'
                 and 0 < (h['det_tick']-s['det_tick'])/rate < 18
                 and ((h['land_x']-s['land_x'])**2+(h['land_y']-s['land_y'])**2)**.5 < 350]
        if pairs:
            h,s = min(pairs, key=lambda pair: pair[0]['det_tick'])
            checks.append({'label': 'HE near smoke', 'tick': min(end,h['det_tick']+rate*.5)})
        if shots:
            checks.append({'label':'Recorded shot','tick':min(end,shots[0]['tick']+rate*.04)})
    return {'schema': 1, 'source': source.replace('\\', '/'), 'map': map_name,
            'calibration': calibration, 'tickrate': rate, 'sampleHz': data['meta'].get('sample_hz', 16),
            'round': round_number, 'start': start, 'end': end, 'roundInfo': rnd,
            'rounds': [{'round': int(number(r['round'])), 'winner': r['winner']} for r in data['rounds.csv']],
            'players': list(players.values()), 'grenades': grenades, 'events': events,
            'entities': entities, 'utilityChecks': checks, 'shots': shots, 'notes': notes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, help='Folder relative to data/analysis')
    parser.add_argument('--round', type=int, default=13)
    parser.add_argument('--output', type=Path, default=HERE / 'example-round.json')
    parser.add_argument('--entities', type=Path, help='Optional validated viewer_v8 directory from this same demo')
    args = parser.parse_args()
    replay = build_replay(args.source, args.round, args.entities)
    args.output.write_text(json.dumps(replay, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    print(f"Exported {replay['map']} round {args.round}: {len(replay['players'])} players, {len(replay['grenades'])} grenades, {len(replay['events'])} events to {args.output}")


if __name__ == '__main__':
    main()
