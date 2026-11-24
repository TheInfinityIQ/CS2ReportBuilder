"""Select ambient beds from the installed map's declared sound events."""
import re
from pathlib import Path

if __package__:
    from .backend import CACHE, CONVERTER, read
    from .stock_assets import _run
else:
    from backend import CACHE, CONVERTER, read
    from stock_assets import _run


def bed_events(text):
    # Read only the event and track forms emitted by the pinned converter.
    # Positional/transient child events and audio operators are separate work.
    events = {}
    sections = re.finditer(r'^\t("?[-\w.]+"?)\s*=\s*\n\t\{(.*?)^\t\}', text, re.M | re.S)
    for section in sections:
        name, body = section.groups()
        fields = {}
        for key, value in re.findall(r'^\t\t(\w+)\s*=\s*\n\t\t\[([^\[\]]*)\]',body,re.M):
            fields[key] = re.findall(r'"([^"]+)"',value)
        tracks = [v for key,values in fields.items() if key.startswith('vsnd_files_track_') for v in values]
        children = [v for key,values in fields.items() if key.startswith('soundevent_') for v in values]
        transient = 'retrigger_interval_' in body or 'use_world_position = true' in body
        tracks = [v for v in tracks if re.fullmatch(r'sounds/ambient/[a-zA-Z0-9_./-]+\.vsnd',v)
                  and re.search(r'interior|exterior|ambience|_lp|roomtone|room_tone|wind_tunnel',Path(v).stem)]
        events[name.strip('"')] = ([] if transient else tracks,children)
    return events


def resolve_bed(name, events, entries, visited=frozenset()):
    if name in visited or len(visited)>=12:
        return None
    samples, children = events.get(name,([],[]))
    for sample in samples:
        if sample+'_c' in entries:
            return sample
    for child in children:
        sample = resolve_bed(child,events,entries,visited|{name})
        if sample:
            return sample
    return None


def prepare_zones(meta, game, directory, entries):
    asset = Path(meta.get('map_asset','')).parent.name
    fingerprint = meta.get('asset_info',{}).get('fingerprint')
    authored = read(CACHE/'environment'/asset/'soundscapes.json',{})
    if not fingerprint or authored.get('schema')!=1 or authored.get('map_revision')!=fingerprint:
        return [],{}
    name = meta['map'].removeprefix('de_')
    if not re.fullmatch(r'[a-z0-9_]+',name):
        return [],{}
    resource = f'soundevents/ambience/game_sounds_{name}.vsndevts'
    script = directory/resource
    if not script.is_file():
        _run([CONVERTER,'-i',Path(game)/'csgo/pak01_dir.vpk','-f',resource+'_c','-d','-o',directory],
             directory,'soundscapes.log',limit=4*1024**2,timeout=30,incremental=True)
    if not script.is_file() or script.stat().st_size > 4*1024**2:
        return [],{}
    events = bed_events(script.read_text(encoding='utf-8-sig'))
    zones, sounds = [], {}
    for zone in authored.get('zones',[])[:512]:
        event = zone['name']
        if not event:
            continue
        key = 'zone:'+event
        if key not in sounds:
            sounds[key] = resolve_bed(event,events,entries)
        if sounds[key]:
            radius = zone['radius']
            zones.append({'sound':key,'origin':zone['origin'],'radius':radius if radius>0 else 256})
    return zones,{key:value for key,value in sounds.items() if value}
