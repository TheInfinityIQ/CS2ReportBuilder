"""Recorded non-weapon cues and an additive bank of installed sound samples."""
import hashlib
import math
from pathlib import Path

if __package__:
    from .backend import CACHE, read, save
    from .fingerprints import fingerprint
    from .soundscape_assets import prepare_zones
    from .stock_assets import CONVERTER, WEAPONS, _run, canonical, catalog
else:
    from backend import CACHE, read, save
    from fingerprints import fingerprint
    from soundscape_assets import prepare_zones
    from stock_assets import CONVERTER, WEAPONS, _run, canonical, catalog


C4 = 'sounds/weapons/c4/'
EVENT_SOUNDS = {
    'bomb_beginplant': ('plant_start', C4+'c4_initiate'),
    'bomb_planted': ('plant', C4+'c4_plant'),
    'bomb_begindefuse': ('defuse_start', C4+'c4_disarmstart'),
    'bomb_defused': ('defuse', C4+'c4_disarmfinish'),
    'bomb_exploded': ('explode', C4+'c4_explode1'),
    'player_hurt': ('hurt', 'sounds/player/damage1'),
    'player_death': ('death', 'sounds/player/death1'),
}
AMBIENCE = {'de_anubis':'sounds/ambient/anubis/anubis_palms_lp',
            'de_dust2':'sounds/ambient/dust2/wind_thin_01',
            'de_cache':'sounds/ambient/cache/cache_outside_air_01',
            'de_inferno':'sounds/ambient/inferno/exterior_01',
            'de_nuke':'sounds/ambient/nuke/exterior_01'}
PICKUP_SOUNDS = {
    'pickup_defuser':'sounds/items/defuser_equip',
    'pickup_grenade':'sounds/items/pickup_grenade_01',
    'pickup_pistol':'sounds/items/pickup_pistol',
    'pickup_weapon':'sounds/items/pickup_weapon_01',
}
SURFACE_SOUNDS = {
    'step:metal': 'sounds/player/footsteps/metal_auto_01',
    **{f'step:{name}':f'sounds/player/footsteps/{name}_01'
       for name in ('wood','dirt','gravel','grass','glass','tile')},
}


def pickup_sound(row):
    if str(row.get('silent','')).lower() in ('true','1','1.0'):
        return None
    item = canonical(row.get('item',''))
    if item in ('defuser','defusekit'):
        return 'pickup_defuser'
    if item in ('hegrenade','flashbang','smokegrenade','molotov','incgrenade','decoy'):
        return 'pickup_grenade'
    if item in WEAPONS and item != 'knife':
        return 'pickup_pistol' if WEAPONS[item][2] == 'pist' else 'pickup_weapon'
    return None


def point(row):
    try:
        coordinates = [float(row['user_'+axis]) for axis in 'XYZ']
    except (KeyError, TypeError, ValueError):
        return None
    return coordinates if all(math.isfinite(n) for n in coordinates) and any(coordinates) else None


def timeline(parser, meta):
    names = ['round_start', *EVENT_SOUNDS, 'item_pickup']
    rows = []
    for kind, table in parser.parse_events(names, player=['X','Y','Z']):
        if kind in names:
            rows.extend((int(row['tick']), names.index(kind), kind, row) for row in table.to_dict('records'))
    rows.sort(key=lambda entry: entry[:2])
    events = []
    planted = None
    planted_tick = None
    rate = max(1, int(meta['info'].get('tickrate',64)))
    for tick, _, kind, row in rows:
        if not 0 <= tick <= meta['info']['ticks']:
            continue
        if kind == 'round_start':
            planted = None
            planted_tick = None
            continue
        position = point(row)
        cue = pickup_sound(row) if kind == 'item_pickup' else EVENT_SOUNDS[kind][0]
        if kind == 'bomb_planted':
            planted = position
            planted_tick = tick
        if kind in ('bomb_defused','bomb_exploded'):
            # Approximate cadence, bounded by actual planted/terminal events.
            if planted is not None and planted_tick is not None:
                for beep in range(planted_tick+rate,min(tick,planted_tick+60*rate),rate):
                    events.append({'kind':'cue','tick':beep,'sound':'bomb_beep','position':planted})
            position, planted = planted, None
            planted_tick = None
        if position is not None and cue is not None:
            events.append({'kind':'cue', 'tick':tick, 'sound':cue, 'position':position})
    return sorted(events,key=lambda event:event['tick'])


def prepare(parser, meta, folder, game, progress):
    destination = Path(folder)/'audio-events.json'
    pak = fingerprint(Path(game)/'csgo/pak01_dir.vpk')
    revision = meta.get('asset_info',{}).get('fingerprint')
    acoustic = CACHE/'environment'/Path(meta.get('map_asset','')).parent.name/'soundscapes.json'
    identity = [7, meta['sha256'], meta['parser'], pak, revision,
                fingerprint(acoustic) if acoustic.is_file() else None]
    cached = read(destination,{})
    sounds = cached.get('sounds',{})
    if (cached.get('identity') == identity and not cached.get('missing')
            and all(Path(path).is_file() for path in sounds.values())):
        return cached
    progress('audio', 89, 'Preparing recorded objective and player sound cues…')
    events = timeline(parser, meta)
    assets = {key: asset for key, asset in EVENT_SOUNDS.values()}
    assets.update(PICKUP_SOUNDS)
    assets['bomb_beep'] = C4+'c4_beep2'
    wanted = {event['sound'] for event in events}
    if any(e.get('kind') == 'player_footstep' for e in meta.get('gameplay',{}).get('events',[])):
        assets.update(SURFACE_SOUNDS)
        wanted.update(SURFACE_SOUNDS)
    death = meta.get('death_presentation')
    if death and any(e.get('removed') for e in read(death,{}).get('world',[])):
        assets['glass_break'] = 'sounds/physics/glass/glass_sheet_break1'
        wanted.add('glass_break')
    if meta['map'] in AMBIENCE:
        assets['ambience'] = AMBIENCE[meta['map']]
        wanted.add('ambience')
    entries = catalog(Path(game))
    directory = CACHE/'replay_audio'/pak[:20]
    directory.mkdir(parents=True, exist_ok=True)
    try:
        zones, zone_sounds = prepare_zones(meta,game,directory,entries)
    except (ValueError, OSError, TimeoutError):
        zones, zone_sounds = [], {}
    assets.update({key:path.removesuffix('.vsnd') for key,path in zone_sounds.items()})
    wanted.update(zone_sounds)
    sounds = {}
    for key in sorted(wanted):
        asset = assets[key]+'.vsnd_c'
        if asset not in entries:
            continue
        stem = Path(asset).stem
        bank = directory/hashlib.sha256(asset.encode()).hexdigest()[:16]
        bank.mkdir(exist_ok=True)
        paths = sorted(bank.rglob(stem+'.wav')) + sorted(bank.rglob(stem+'.mp3'))
        if not paths:
            try:
                _run([CONVERTER,'-i',Path(game)/'csgo/pak01_dir.vpk','-f',asset,'-d','-o',bank],
                     bank,'export.log',limit=32*1024**2,timeout=30,incremental=True)
            except (OSError, ValueError, TimeoutError):
                continue
            paths = sorted(bank.rglob(stem+'.wav')) + sorted(bank.rglob(stem+'.mp3'))
        if paths:
            sounds[key] = str(paths[0])
    result = {'identity':identity,'events':events,'sounds':sounds,'missing':sorted(wanted-sounds.keys()),
              'zones':[zone for zone in zones if zone['sound'] in sounds]}
    save(destination,result)
    return result
