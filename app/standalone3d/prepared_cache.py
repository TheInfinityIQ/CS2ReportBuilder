"""Reuse a complete selected-demo preparation at unchanged input revisions."""
import hashlib
from pathlib import Path
if __package__:
    from .backend import CACHE,HERE,asset_identity,read,save
    from .fingerprints import fingerprint,stamp
else:
    from backend import CACHE,HERE,asset_identity,read,save
    from fingerprints import fingerprint,stamp

def revision():
    value=hashlib.sha256(b'prepared-viewer-1')
    files=[p for p in HERE.glob('*.py') if not p.name.startswith(('test_','validate_'))]
    files += list(HERE.glob('prepare*.gd'))+list(HERE.glob('*/*.cs'))+list(HERE.glob('*/*.csproj'))
    files += list((HERE.parent/'extractor/entity_v8/bin/Release/net9.0').glob('DemoFile*.dll'))
    for path in sorted(files):value.update(path.name.encode());value.update(path.read_bytes())
    return value.hexdigest()

def write_receipt(meta,folder):
    if __package__:
        from .launcher import find_godot,runtime_version
    else:
        from launcher import find_godot,runtime_version
    paths=[Path(folder)/'replay.json',meta['tracks'],meta['native_scene'],meta['gameplay']['states'],meta['inventory'],meta['network_presentation']]
    paths += [meta['presentation'][key] for key in ['punch','travel','gait_phase'] if meta['presentation'].get(key)]
    if meta.get('death_presentation'):paths.append(meta['death_presentation'])
    paths += list(meta.get('replay_audio',{}).get('sounds',{}).values())
    fire_bank=meta.get('particle_assets',{}).get('fire_bank')
    if fire_bank:paths += [fire_bank,str(Path(fire_bank).with_suffix('.blocks'))]
    material_receipt=Path(meta['native_scene']).parent/'source-materials.json'
    if material_receipt.is_file():
        paths.append(material_receipt)
        for material in read(material_receipt,{}).get('materials',{}).values():
            paths += list(material.get('native_textures',{}).values())
    for graph in meta.get('actor_assets',{}).get('weapon_graphs',{}).values():
        for clip_path in graph.get('clips',{}).values():
            paths.append(clip_path)
            paths += [variant['data'] for variant in read(clip_path,{}).get('variants',[])]
    pack_receipt=Path(meta['native_scene']).with_suffix('.pack.json')
    if pack_receipt.is_file():paths += [pack_receipt,read(pack_receipt,{})['pack']]
    dependencies={}
    for path in paths:
        key=str(Path(path).resolve());state=stamp(Path(key))
        if state is None:return
        dependencies[key]=state
    save(Path(folder)/'prepared.json',{'schema':1,'revision':revision(),'source':meta['sha256'],
        'source_path':str(Path(meta['source']).resolve()),'source_stamp':stamp(Path(meta['source'])),
        'map':meta['map'],'map_revision':meta['asset_info']['fingerprint'],'step':meta['step'],'tickrate':meta['info']['tickrate'],
        'godot':runtime_version(find_godot()),'dependencies':dependencies})

def find_ready(demo,game,runtime):
    """A cache miss always returns to the existing approval/preparation path."""
    if __package__:
        from .launcher import runtime_version
    else:
        from launcher import runtime_version
    demo=Path(demo).resolve()
    if not demo.is_file():return None
    sha=fingerprint(demo);source_stamp=stamp(demo)
    if source_stamp is None:return None
    current=revision()
    for folder in (CACHE/'replays').glob(sha+'_*'):
        receipt=read(folder/'prepared.json',{})
        if not isinstance(receipt,dict):continue
        if receipt.get('schema')!=1 or receipt.get('revision')!=current or receipt.get('source_stamp')!=source_stamp or receipt.get('source')!=sha:continue
        try:
            if receipt.get('step')!=max(1,round(float(receipt.get('tickrate',0))/64)):continue
        except (ValueError,TypeError,OverflowError):continue
        if receipt.get('source_path','').casefold()!=str(demo).casefold() or receipt.get('godot')!=runtime_version(runtime):continue
        try:
            if asset_identity(game,receipt['map'])[1]!=receipt.get('map_revision'):continue
            if not receipt.get('dependencies') or any(stamp(Path(path))!=state for path,state in receipt['dependencies'].items()):continue
        except (OSError,ValueError,KeyError):continue
        return folder/'replay.json'
    return None
