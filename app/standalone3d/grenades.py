"""Recorded utility companion. No game simulation, analysis rebuild or per-demo assets."""
from bisect import bisect_right
from collections import Counter, defaultdict
import gzip
import json
import math
from pathlib import Path
import sys

if __package__:
    from .backend import ROOT, read, save, digest
else:
    from backend import ROOT, read, save, digest

VERSION = 3
TYPES = {'CSmokeGrenadeProjectile': 'smoke', 'CHEGrenadeProjectile': 'he',
         'CFlashbangProjectile': 'flash', 'CMolotovProjectile': 'molotov',
         'CIncendiaryGrenadeProjectile': 'incendiary', 'CDecoyProjectile': 'decoy'}
DETONATIONS = {'smokegrenade_detonate': 'smoke', 'hegrenade_detonate': 'he',
               'flashbang_detonate': 'flash', 'inferno_startburn': 'fire', 'decoy_started': 'decoy'}
EVENTS = [*DETONATIONS, 'inferno_expire', 'smokegrenade_expired', 'decoy_detonate',
          'molotov_detonate', 'player_blind', 'round_start', 'weapon_fire']
WEAPON_KINDS = {'smokegrenade':'smoke', 'hegrenade':'he', 'flashbang':'flash',
                'molotov':'molotov', 'incgrenade':'incendiary', 'decoy':'decoy'}


def point(row):
    try: result = [float(row[axis]) for axis in ('x', 'y', 'z')]
    except (KeyError, TypeError, ValueError): return None
    return result if all(math.isfinite(x) for x in result) else None


def rows(table):
    return [] if table is None else table.to_dict('records')


def reconstruct(projectiles, tables, meta):
    """Use the existing time-aware simplifier, with tighter (2-unit) tolerance.

    Entity indices alone are NOT throw identities. Separate runs before joining
    detonations, and associate fire's new entity by owner, time AND location.
    """
    import numpy as np
    sys.path.insert(0, str(ROOT/'app/extractor'))
    from extract_viewer_tracks import simplify
    rate = float(meta['info']['tickrate']); end = int(meta['info']['ticks'])
    rounds = sorted({int(r['tick']) for r in rows(tables.get('round_start'))} | {end+1})
    def round_end(tick):
        index = bisect_right(rounds, tick)
        return rounds[index] if index < len(rounds) else end+1
    effects = []; by_kind = defaultdict(list)
    for name, kind in DETONATIONS.items():
        for row in rows(tables.get(name)):
            pos = point(row); tick = int(row['tick'])
            if pos is None or not 0 <= tick <= end: continue
            expire = {'smoke': 'smokegrenade_expired', 'fire': 'inferno_expire', 'decoy': 'decoy_detonate'}.get(kind)
            # A subsequent detonation of the same recycled index is a hard limit.
            next_spawn = min((int(r['tick']) for r in rows(tables.get(name))
                              if r.get('entityid') == row.get('entityid') and int(r['tick']) > tick), default=end+1)
            candidates = [int(r['tick']) for r in rows(tables.get(expire))
                          if r.get('entityid') == row.get('entityid') and tick < int(r['tick']) < next_spawn]
            lifetime = {'smoke': 20, 'fire': 7, 'decoy': 15, 'he': .65, 'flash': .20}[kind]
            stop = min(min(candidates, default=tick+math.ceil(lifetime*rate)), round_end(tick), next_spawn)
            item = {'id': f'{kind}:{row.get("entityid",-1)}:{tick}', 'kind': kind,
                    'entity': int(row.get('entityid', -1)), 'start': tick, 'end': stop,
                    'position': pos, 'owner': str(row.get('user_steamid', '')),
                    'expiry_recorded': bool(candidates), 'frames': [], 'geometry': 'event_approximation'}
            effects.append(item); by_kind[kind].append(item)
    fire_used = set(); throws = []; bounce_audio = []
    fires = rows(tables.get('weapon_fire'))
    required = {'grenade_type','grenade_entity_id','steamid','tick','x','y','z'}
    if not required <= set(projectiles.columns):
        if projectiles.empty:
            import pandas as pd
            projectiles = pd.DataFrame(columns=sorted(required))
        else: raise ValueError('This recording did not provide grenade projectile fields. The installed parser may not support its demo version.')
    g = projectiles[projectiles['grenade_type'].isin(TYPES)].copy()
    g = g.replace([np.inf, -np.inf], np.nan).dropna(subset=['tick', 'x', 'y', 'z'])
    g = g.sort_values(['grenade_entity_id', 'grenade_type', 'tick']).drop_duplicates(
        ['grenade_entity_id', 'grenade_type', 'tick'])
    gap = g.groupby(['grenade_entity_id', 'grenade_type'])['tick'].diff()
    g['run'] = (gap.isna() | (gap > 2)).astype(int).groupby(
        [g['grenade_entity_id'], g['grenade_type']]).cumsum()
    for (eid, typ, _), group in g.groupby(['grenade_entity_id', 'grenade_type', 'run'], sort=False):
        begin, last = int(group['tick'].iloc[0]), int(group['tick'].iloc[-1])
        if not 0 <= begin <= end: continue
        owner = str(group['steamid'].iloc[0]); kind = TYPES[typ]
        # Source 2 also represents CT incendiaries as CMolotovProjectile.
        if kind == 'molotov':
            releases = [r for r in fires if str(r.get('user_steamid')) == owner
                        and begin-24 <= int(r['tick']) <= begin
                        and r.get('weapon') in ('weapon_molotov', 'weapon_incgrenade')]
            if releases and max(releases, key=lambda r: r['tick'])['weapon'] == 'weapon_incgrenade': kind = 'incendiary'
        effect_kind = 'fire' if kind in ('molotov', 'incendiary') else kind
        candidates = [e for e in by_kind[effect_kind] if begin <= e['start'] <= last+8]
        if effect_kind == 'fire':
            p = group[['x', 'y', 'z']].iloc[-1].to_numpy(dtype=float)
            candidates = [e for e in candidates if e['id'] not in fire_used and abs(e['start']-last) <= 8
                          and e['owner'] == owner and np.linalg.norm(p-np.array(e['position'])) < 256]
            effect = min(candidates, key=lambda e: np.linalg.norm(p-np.array(e['position']))+abs(e['start']-last)*4, default=None)
        else:
            effect = min((e for e in candidates if e['entity'] == int(eid)), key=lambda e: e['start'], default=None)
        stop = min(effect['start'] if effect else last+1, round_end(begin), end+1)
        group = group[group['tick'] < stop]
        if group.empty: continue
        tk = group['tick'].to_numpy(dtype=float); xyz = group[['x', 'y', 'z']].to_numpy(dtype=float)
        # Contact sounds follow abrupt recorded velocity changes. They are
        # labelled derived cues, never a second physics simulation or hit event.
        if len(tk) >= 3:
            velocity = np.diff(xyz, axis=0)/np.diff(tk)[:,None]*rate
            previous_bounce = -rate
            for i in range(1,len(velocity)):
                a,b = velocity[i-1],velocity[i]; speed = float(np.linalg.norm(a)); after = float(np.linalg.norm(b))
                change = float(np.linalg.norm(b-a)); cosine = float(np.dot(a,b))/max(1,speed*after)
                if (speed >= 140 and change > max(140,speed*.35) and (cosine < .82 or after < speed*.55)
                        and tk[i]-previous_bounce > rate*.08):
                    bounce_audio.append({'kind':'grenade','tick':int(tk[i]),'position':xyz[i].tolist(),
                                         'sound':'grenade:bounce','derived':'recorded_path_velocity_change'})
                    previous_bounce = tk[i]
        keep = simplify(tk, xyz, 2.0)
        path = [[int(tk[i]), *[round(float(v), 3) for v in xyz[i]]] for i in keep]
        if effect and effect['start'] == stop:
            path.append([stop, *effect['position']])
            effect['grenade'] = kind; effect['throw'] = f'{eid}:{typ}:{begin}'
            if effect_kind == 'fire': fire_used.add(effect['id'])
        throws.append({'id': f'{eid}:{typ}:{begin}', 'kind': kind, 'owner': owner,
                       'start': begin, 'end': stop, 'path': path,
                       'effect': effect['id'] if effect else None})
    blinds = []
    for row in rows(tables.get('player_blind')):
        tick = int(row['tick']); duration = float(row.get('blind_duration', 0))
        if not math.isfinite(duration) or duration <= 0 or not 0 <= tick <= end: continue
        blinds.append({'player': str(row.get('user_steamid', '')), 'start': tick,
                       'end': min(tick+duration*rate, round_end(tick))})
    audio = bounce_audio+[{'kind': 'grenade', 'tick': e['start'], 'position': e['position'],
                          'sound': 'grenade:'+e.get('grenade', e['kind'])} for e in effects]
    # Decoy bursts are an explicit approximation: the demo gives active/expiry,
    # not a weapon_fire event for every imitated shot.
    for effect in by_kind['decoy']:
        audio += [{'kind': 'grenade', 'tick': tick, 'position': effect['position'], 'sound': 'decoy:shot'}
                  for tick in range(effect['start']+int(rate), effect['end'], int(rate))]
    for row in rows(tables.get('decoy_detonate')):
        pos = point(row); tick = int(row['tick'])
        if pos is None: continue
        effects.append({'id':f'decoy_end:{row.get("entityid",-1)}:{tick}', 'kind':'decoy_end',
                        'start':tick, 'end':min(tick+math.ceil(rate*.25), round_end(tick)),
                        'position':pos, 'frames':[], 'geometry':'event_approximation'})
        audio.append({'kind':'grenade','tick':tick,'position':pos,'sound':'grenade:decoy_end'})
    return {'throws': sorted(throws, key=lambda e: e['start']),
            'effects': sorted(effects, key=lambda e: e['start']), 'blinds': sorted(blinds, key=lambda e: e['start']),
            'audio': sorted(audio, key=lambda e: e['tick']), 'tickrate': rate,
            'summary': {'throws': dict(Counter(t['kind'] for t in throws)),
                        'effects': dict(Counter(e['kind'] for e in effects)), 'blinds': len(blinds)}}


def attach_geometry(result, folder):
    """Retain recorded shape changes; no invented circular fire footprints."""
    effects = result['effects']
    for filename, kind in [('inferno_patches.jsonl.gz', 'fire'), ('smoke_voxels.jsonl.gz', 'smoke')]:
        path = folder/filename
        if not path.is_file(): continue
        active = {}
        with gzip.open(path, 'rt', encoding='utf-8-sig') as stream:
            for line in stream:
                row = json.loads(line); tick = int(row['tick']); identity = row['id']
                if row['action'] != 'upsert':
                    effect = active.pop(identity, None)
                    if effect: effect['end'] = min(effect['end'], tick)
                    continue
                state = row['state']; effect = active.get(identity)
                if effect is None:
                    p = point(state)
                    if p is None: continue
                    matches = [e for e in effects if e['kind'] == kind and e['start'] <= tick < e['end']
                               and sum((a-b)**2 for a,b in zip(e['position'], p)) < 96**2
                               and (kind == 'smoke' or e['entity'] == int(state['entityIndex']))]
                    effect = min(matches, key=lambda e: tick-e['start'], default=None)
                    if effect is None: continue
                    active[identity] = effect
                if not effect['start'] <= tick < effect['end']: continue
                if kind == 'fire':
                    patches = [[round(float(p[a]), 3) for a in ('x', 'y', 'z')]
                               for p in state['patches'] if p['burning']]
                    frame = {'tick': tick, 'patches': patches}
                else:
                    # Grid is deliberately not relabeled engine-authentic.
                    frame = {'tick': tick, 'position': point(state), 'occupied': state['occupied'],
                             'cell': state['cell'], 'grid': state['grid'], 'fading': state['fading']}
                previous = effect['frames'][-1] if effect['frames'] else None
                if previous and {k:v for k,v in frame.items() if k!='tick'} == {k:v for k,v in previous.items() if k!='tick'}: continue
                effect['frames'].append(frame)
                effect['geometry'] = 'recorded_patches' if kind == 'fire' else 'decoded_network_voxels'
    result['summary']['recorded_fire'] = sum(e['geometry']=='recorded_patches' for e in effects)
    result['summary']['decoded_smoke'] = sum(e['geometry']=='decoded_network_voxels' for e in effects)


def prepare_grenades(parser, meta, folder, game, stock, progress):
    folder = Path(folder); receipt = folder/'grenades.json'; recording = folder/'grenade_recording.json'
    cached = read(receipt, {})
    sys.path.insert(0, str(ROOT/'app/extractor'))
    from viewer_entities_v8 import extract_entities, PROJECT
    adapter = digest(PROJECT.parent/'Program.cs')+':'+digest(ROOT/'app/extractor/smoke_voxels_v8.py')
    if (cached.get('version') == VERSION and cached.get('source') == meta['sha256']
            and cached.get('parser') == meta['parser'] and cached.get('entity_adapter') == adapter and recording.is_file()
            and recording.stat().st_size == cached.get('bytes')):
        if (cached.get('assets') == stock['identity'] and all(Path(p).is_file() for p in
                [*cached.get('sounds', {}).values(), *cached.get('models', {}).values()])): return cached
        # A game/runtime update changes shared art, not the demo's recorded paths.
        cached.update(sounds=prepare_sounds(game,folder,stock),models=prepare_models(game,stock,progress),assets=stock['identity'])
        save(receipt,cached)
        return cached
    progress('grenades', 87, 'Preparing recorded grenade paths, detonations and flash timings once…')
    result = reconstruct(parser.parse_grenades(), dict(parser.parse_events(EVENTS, player=['steamid'])), meta)
    entity_folder = folder/'grenade_entities'; entity_meta = read(entity_folder/'entity_meta.json', {})
    # The already-installed entity reader is reused only for this selected demo.
    if entity_meta.get('demo_sha256') != meta['sha256']:
        progress('grenades', 89, 'Reading this demo’s smoke shapes and burning fire patches once…')
        entity_meta = extract_entities(meta['source'], entity_folder, hz=8)
    attach_geometry(result, entity_folder)
    result['limitations'] = ['Simplified effects, not Valve shaders.',
        'Smoke grid placement/interior fill are reverse engineered; no engine parity claim.',
        'Fallback event-only smoke/fire shapes and lifetimes are marked when geometry/expiry is missing.',
        'Decoy shot cadence and flash fade are approximate; blind duration and effect windows are recorded.']
    sounds = prepare_sounds(game, folder, stock)
    models = prepare_models(game, stock, progress)
    save(recording, result)
    result = {'version': VERSION, 'source': meta['sha256'], 'parser': meta['parser'],
              'recording': str(recording), 'bytes': recording.stat().st_size,
              'sounds': sounds, 'models': models, 'summary': result['summary'], 'entity_adapter': adapter, 'assets':stock['identity']}
    save(receipt, result)
    return result


def prepare_sounds(game, folder, stock):
    if __package__:
        from .stock_assets import catalog, _run, CONVERTER, CACHE
    else:
        from stock_assets import catalog, _run, CONVERTER, CACHE
    # One bank per installed asset revision, shared by all demos.
    key = stock['identity']['pak_index'][:20]; directory = CACHE/'utility_audio'/key
    directory.mkdir(parents=True, exist_ok=True)
    chosen = {'grenade:he': 'hegrenade_detonate_02', 'grenade:flash': 'flashbang_explode1',
              'grenade:smoke': 'smoke_emit', 'grenade:molotov': 'molotov_detonate_1',
              'grenade:incendiary': 'inc_grenade_detonate_1', 'grenade:fire': 'fire_ignite_1',
              'grenade:decoy': 'grenade_hit1', 'grenade:decoy_end': 'grenade_hit1', 'grenade:bounce':'grenade_hit1',
              'loop:fire': 'fire_loop_1', 'loop:smoke': 'smoke_emit'}
    entries = catalog(Path(game)); result = {}
    for sound, stem in chosen.items():
        asset = next((p for p in sorted(entries) if p.startswith('sounds/weapons/') and Path(p).stem == stem), None)
        if not asset: continue
        outputs = list(directory.rglob(stem+'.wav'))+list(directory.rglob(stem+'.mp3'))
        if not outputs:
            _run([CONVERTER, '-i', Path(game)/'csgo/pak01_dir.vpk', '-f', asset, '-d', '-o', directory],
                 directory, 'export.log', limit=100_000_000, timeout=30)
            outputs = list(directory.rglob(stem+'.wav'))+list(directory.rglob(stem+'.mp3'))
        if outputs: result[sound] = str(outputs[0])
    if stock['sounds'].get('fire:ak47'): result['decoy:shot'] = stock['sounds']['fire:ak47']
    return result


def prepare_models(game, stock, progress):
    if __package__:
        from .stock_assets import _run, CONVERTER, CACHE, gltf_info
        from .launcher import find_godot
    else:
        from stock_assets import _run, CONVERTER, CACHE, gltf_info
        from launcher import find_godot
    import hashlib
    key = hashlib.sha256(json.dumps(stock['identity'], sort_keys=True).encode()).hexdigest()[:20]
    root = CACHE/'utility_models'/key; root.mkdir(parents=True, exist_ok=True)
    result = {}
    definitions = {'smoke': ('smokegrenade', 'smokegrenade'), 'he': ('hegrenade', 'hegrenade'),
                   'flash': ('flashbang', 'flashbang'), 'molotov': ('molotov', 'molotov'),
                   'incendiary': ('incendiary', 'incendiarygrenade'), 'decoy': ('decoy', 'decoy')}
    for kind, (sub, name) in definitions.items():
        directory = root/kind; directory.mkdir(exist_ok=True)
        native = directory/'model.scn'; glb = directory/'model.glb'
        if not native.is_file():
            progress('grenades', 94, 'Preparing shared stock '+kind+' model…')
            _run([CONVERTER, '-i', Path(game)/'csgo/pak01_dir.vpk', '-f',
                  f'weapons/models/grenade/{sub}/weapon_{name}.vmdl_c', '-d', '--gltf_export_format', 'glb',
                  '--gltf_export_materials', '--gltf_textures_adapt', '--gltf_export_animations',
                  '--gltf_animation_list', '__pose_only__', '--game', Path(game)/'csgo/gameinfo.gi',
                  '-o', glb, '--threads', '1'], directory, 'export.log', limit=300_000_000)
            info = gltf_info(glb)
            if not info.get('meshes'): raise ValueError('Stock grenade model has no mesh: '+kind)
            _run([find_godot(), '--headless', '--path', ROOT/'app/standalone3d', '--log-file', directory/'prepare.log',
                  '--script', ROOT/'app/standalone3d/prepare_scene.gd', '--', glb, native, 'stock', 'gpu'],
                 directory, 'native.log', limit=400_000_000)
            # Delete only intermediates produced inside this model's private folder.
            for path in [glb, *directory.rglob('*.png')]:
                if path.is_file() and path.resolve().is_relative_to(directory.resolve()): path.unlink()
        result[kind] = str(native)
    return result
