"""Offline .dem -> standalone replay data and read-only map import.

This module never imports the CS2 playback adapter or starts a game process.
Only the selected recording is parsed; existing analysis is not read/written.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time
import uuid

if __package__:
    from .asset_support import repair_optional_textures
else:
    from asset_support import repair_optional_textures

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).parent
CACHE=ROOT/'data/.desktop/standalone3d'
DEFAULT_GAME=Path(r'C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game')
CONVERTER=CACHE/'tools/Source2Viewer-20.1/Source2Viewer-CLI.exe'
REPLAYS=DEFAULT_GAME/'csgo/replays'
SCHEMA=1
DECODER_SCHEMA=1
FIELDS=['X','Y','Z','yaw','pitch','health','team_num','is_alive','duck_amount','present','weapon']


def downloaded_demos(root=REPLAYS):
    """List physical downloads without parsing or hashing the whole library."""
    root=Path(root).resolve();items=[]
    if not root.is_dir():return items
    for folder,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if not (Path(folder)/d).is_symlink()]
        for name in files:
            path=Path(folder)/name
            if path.suffix.casefold()!='.dem':continue
            try:
                resolved=path.resolve()
                if not resolved.is_relative_to(root) or not resolved.is_file():continue
                with resolved.open('rb') as stream:
                    if stream.read(8)!=b'PBDEMS2\0':continue
                items.append({'path':str(resolved),'label':str(path.relative_to(root)),
                              'modified':resolved.stat().st_mtime})
            except OSError:continue
    return sorted(items,key=lambda row:row['modified'],reverse=True)


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def save(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    os.replace(temporary,path)


def read(path,default=None):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return default


def variable(stream):
    value=0
    for shift in range(0,70,7):
        byte=stream.read(1)
        if not byte:raise ValueError('The demo is incomplete.')
        value|=(byte[0]&127)<<shift
        if not byte[0]&128:return value
    raise ValueError('Invalid demo integer.')


def file_info(path):
    import io
    with Path(path).open('rb') as f:
        header=f.read(16)
        if len(header)!=16 or header[:8]!=b'PBDEMS2\0':raise ValueError('Choose a CS2 .dem recording. CS:GO/CS 1.6 formats are not supported.')
        offset=struct.unpack_from('<I',header,8)[0]
        if not 16<=offset<Path(path).stat().st_size:raise ValueError('The recording is missing its duration metadata. Use a completed demo download.')
        f.seek(offset);command=variable(f);variable(f);size=variable(f)
        if command&~64!=2 or not 0<size<1024*1024:raise ValueError('Unsupported demo duration metadata.')
        payload=f.read(size)
        if len(payload)!=size:raise ValueError('Truncated demo duration metadata.')
        if command&64:
            import pyarrow
            uncompressed=variable(io.BytesIO(payload))
            if uncompressed>1024*1024:raise ValueError('Duration metadata is too large.')
            payload=pyarrow.decompress(payload,uncompressed,codec='snappy').to_pybytes()
    stream=io.BytesIO(payload);values={}
    while stream.tell()<len(payload):
        key=variable(stream);number,wire=key//8,key%8
        if wire==0:values[number]=variable(stream)
        elif wire==5:values[number]=struct.unpack('<f',stream.read(4))[0]
        elif wire==1:stream.read(8)
        elif wire==2:stream.read(variable(stream))
        else:raise ValueError('Unsupported duration field.')
    seconds=float(values.get(1,0));ticks=int(values.get(2,0))
    if not math.isfinite(seconds) or seconds<=0 or not 0<ticks<=1000000:raise ValueError('Invalid or excessively long recording.')
    rate=ticks/seconds
    if not 8<=rate<=256:raise ValueError('Unsupported recording tick rate.')
    return {'seconds':seconds,'ticks':ticks,'tickrate':rate}


def asset_identity(game,map_name):
    if __package__:
        from .fingerprints import fingerprint as file_fingerprint
    else:
        from fingerprints import fingerprint as file_fingerprint
    if not re.fullmatch(r'[a-z0-9_]{1,64}',map_name):raise ValueError('The recording has an unsupported map name.')
    game=Path(game).resolve();source=game/'csgo/maps'/f'{map_name}.vpk'
    if not source.is_file():raise ValueError(f'{map_name} is not installed. Install that map through Steam before opening this recording.')
    evidence={}
    for path in [source,game/'csgo/pak01_dir.vpk',game/'csgo/steam.inf']:
        if path.is_file():
            evidence[str(path)]=file_fingerprint(path)
    return source,asset_key(evidence,texture_granted(map_name,evidence)),evidence


def asset_key(evidence,textured):
    key=hashlib.sha256(b'standalone-glb-geometry-v1-vrf20.1')
    for fingerprint in evidence.values():key.update(fingerprint.encode())
    key.update(b'textured' if textured else b'geometry')
    return key.hexdigest()


def asset_stamp(evidence):return hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest()


def texture_granted(map_name,evidence):
    return read(CACHE/'settings.json',{}).get('texture_grants',{}).get(map_name)==asset_stamp(evidence)


def export_map(game,map_name,progress,cache_limit=3_000_000_000):
    source,key,evidence=asset_identity(game,map_name)
    textured=texture_granted(map_name,evidence)
    folder=CACHE/'maps'/f'{map_name}_{key[:20]}'
    meta=read(folder/'manifest.json',{})
    if meta.get('fingerprint')==key and (folder/'world.glb').is_file():
        repair_optional_textures(folder/'world.glb')
        return folder/'world.glb',meta
    if not CONVERTER.is_file():raise ValueError('The standalone map reader is missing. Run the standalone tool setup first.')
    folder.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(folder).free<(5 if textured else 1)*1024**3:raise ValueError('Not enough free cache space for this map import.')
    progress('map',20,f'Importing {map_name} geometry from your installed assets…')
    sys.path.insert(0,str(ROOT/'app/desktop'))
    from jobs import WindowsProcessGroup,hidden_options
    args=[str(CONVERTER),'-i',str(source),'--vpk_filepath',f'maps/{map_name}/world.vwrld_c','-d',
          '--gltf_export_format','glb','--game',str(Path(game)/'csgo/gameinfo.gi'),'-o',str(folder/'world.glb'),'--threads','1']
    if textured:args.extend(['--gltf_export_materials','--gltf_textures_adapt'])
    with (folder/'import.log').open('wb') as log:
        process=subprocess.Popen(args,cwd=folder,stdout=log,stderr=subprocess.STDOUT,**hidden_options())
        group=WindowsProcessGroup(process)
        try:
            if os.name=='nt' and not group.handle:raise ValueError('Could not supervise the map reader.')
            started=time.monotonic();last_report=started
            while process.poll() is None:
                time.sleep(.5)
                written=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
                if written>cache_limit:raise ValueError(f'This map reached its approved {cache_limit/1e9:g} GB import limit. Original assets are unchanged.')
                if time.monotonic()-started>600:raise TimeoutError('The single-map import exceeded ten minutes.')
                if time.monotonic()-last_report>3:
                    progress('map',20,f'Importing {map_name} · {written//(1024**2)} MB cached · Original assets unchanged')
                    last_report=time.monotonic()
            code=process.returncode
            if code or not (folder/'world.glb').is_file():raise ValueError('Map import failed. See '+str(folder/'import.log'))
        finally:
            if process.poll() is None:group.terminate();process.wait(timeout=10)
            group.close()
    repaired=repair_optional_textures(folder/'world.glb')
    meta={'fingerprint':key,'map':map_name,'source_files':evidence,'converter':'Source2Viewer 20.1',
          'geometry_only':not textured,'glb_bytes':(folder/'world.glb').stat().st_size,
          'map_revision_verified_against_demo':False,'optional_texture_fallbacks':repaired}
    save(folder/'manifest.json',meta)
    return folder/'world.glb',meta


def prepare(demo,game,job,sample_hz=64):
    demo=Path(demo).resolve();game=Path(game).resolve();job=Path(job).resolve()
    if not demo.is_file() or demo.suffix.casefold()!='.dem':raise ValueError('Choose an existing .dem file.')
    if demo.stat().st_size>2*1024**3:raise ValueError('This first version supports recordings up to 2 GB.')
    def progress(stage,percent,message):save(job/'progress.json',{'state':'running','stage':stage,'percent':percent,'message':message})
    if sample_hz==64:
        if __package__:
            from .prepared_cache import find_ready
            from .launcher import find_godot
        else:
            from prepared_cache import find_ready
            from launcher import find_godot
        ready=find_ready(demo,game,find_godot())
        if ready:
            save(job/'progress.json',{'state':'complete','percent':100,'message':'Ready','replay':str(ready)});return read(ready,{})
    from demoparser2 import DemoParser
    progress('inspect',3,'Reading the selected demo…')
    if __package__:
        from .fingerprints import fingerprint
    else:
        from fingerprints import fingerprint
    sha=fingerprint(demo);info=file_info(demo);parser=DemoParser(str(demo));header=parser.parse_header()
    map_name=header.get('map_name','')
    if __package__:
        from .native_cache import ensure_scene
        from .map_setup import require_setup,mark_prepared
    else:
        from native_cache import ensure_scene
        from map_setup import require_setup,mark_prepared
    setup=require_setup(game,map_name)
    glb,map_meta=export_map(game,map_name,progress,setup['cache_limit'])
    if __package__:
        from .effect_assets import ensure_effects
    else:
        from effect_assets import ensure_effects
    ensure_effects(glb,game,progress)
    if __package__:
        from .material_assets import ensure_materials
    else:
        from material_assets import ensure_materials
    ensure_materials(glb,game,progress)
    if __package__:
        from .fidelity_audit import ensure_audit
    else:
        from fidelity_audit import ensure_audit
    ensure_audit(glb)
    native_scene=ensure_scene(glb,map_meta,progress,setup['cache_limit'])
    if __package__:
        from .map_companions import ensure_companions
    else:
        from map_companions import ensure_companions
    companion_warnings=ensure_companions(game,native_scene,map_meta,progress)
    if native_scene.with_suffix('.parts.json').is_file():
        if __package__:
            from .native_pack import prepare_pack
        else:
            from native_pack import prepare_pack
        prepare_pack(native_scene,map_meta,progress)
    mark_prepared(setup)
    parser_version=importlib.metadata.version('demoparser2')
    # Logging/UI edits must not duplicate or reparse a recording. Bump this
    # explicit decoder schema when the meaning of the decoded tracks changes.
    signature=hashlib.sha256(json.dumps([DECODER_SCHEMA,parser_version,sample_hz,FIELDS]).encode()).hexdigest()[:20]
    folder=CACHE/'replays'/f'{sha}_{signature}';meta=read(folder/'replay.json',{})
    if not meta:
        for candidate in (CACHE/'replays').glob(f'{sha}_*/replay.json'):
            old=read(candidate,{})
            track=Path(old.get('tracks',''))
            expected=24+old.get('frames',0)*len(old.get('players',[]))*len(FIELDS)*4
            if (old.get('sha256')==sha and old.get('decoder_schema',1)==DECODER_SCHEMA
                    and old.get('parser',{}).get('version')==parser_version and old.get('fields')==FIELDS
                    and old.get('step')==max(1,round(info['tickrate']/sample_hz))
                    and track.is_file() and track.stat().st_size==expected):
                folder=candidate.parent;meta=old;break
    if meta.get('sha256')==sha and (folder/'tracks.bin').is_file():
        meta.update(source=str(demo),map_asset=str(glb),asset_info=map_meta,native_scene=str(native_scene),decoder_schema=DECODER_SCHEMA,
                    map_in_selected_pool=setup['in_pool']);save(folder/'replay.json',meta)
        meta['warnings']=list(dict.fromkeys([*meta.get('warnings',[]),*companion_warnings]))
        meta['map_preparation_warnings']=companion_warnings
        enrich_gameplay(parser,meta,folder,game,progress)
        save(job/'progress.json',{'state':'complete','percent':100,'message':'Ready','replay':str(folder/'replay.json')});return meta
    import numpy as np
    import pandas as pd
    progress('players',40,'Decoding player positions, aim, teams and equipment…')
    step=max(1,round(info['tickrate']/sample_hz));ticks=np.arange(0,info['ticks']+1,step,dtype=np.int32)
    properties=['X','Y','Z','yaw','pitch','health','team_num','is_alive','duck_amount','active_weapon_name']
    data=parser.parse_ticks(properties,ticks=ticks.tolist())
    data=data[data['steamid'].notna() & data['tick'].isin(ticks)].copy()
    # Steam identities stay strings; only compact roster indices enter the binary.
    identifiers=list(pd.unique(data['steamid']))
    if not 1<=len(identifiers)<=64:raise ValueError('Unsupported player count in this recording.')
    if len(ticks)*len(identifiers)*len(FIELDS)*4>512*1024**2:raise ValueError('This recording exceeds the first-version memory limit.')
    players=[]
    for identifier in identifiers:
        rows=data[data['steamid']==identifier]
        names=rows['name'].dropna().astype(str)
        players.append({'id':str(identifier),'name':names.iloc[-1] if len(names) else str(identifier)})
    slots={identifier:i for i,identifier in enumerate(identifiers)}
    weapons=sorted(str(w) for w in pd.unique(data['active_weapon_name'].dropna()))
    weapon_slots={w:i+1 for i,w in enumerate(weapons)}
    output=np.zeros((len(ticks),len(players),len(FIELDS)),dtype='<f4')
    frame=(data['tick'].to_numpy(dtype=np.int64)//step).astype(np.intp)
    player=data['steamid'].map(slots).to_numpy(dtype=np.intp)
    for index,field in enumerate(FIELDS):
        if field=='present':values=np.ones(len(data),dtype=np.float32)
        elif field=='weapon':values=data['active_weapon_name'].map(weapon_slots).fillna(0).to_numpy(dtype=np.float32)
        else:values=pd.to_numeric(data[field],errors='coerce').fillna(0).to_numpy(dtype=np.float32)
        output[frame,player,index]=np.nan_to_num(values,nan=0,posinf=0,neginf=0)
    progress('events',80,'Reading rounds and kills…')
    warnings=[('Geometry-only map rendering; ' if map_meta['geometry_only'] else 'Textured map; ')+'players are simplified 3D figures.',
              'Installed map revision may differ from the recording. Animations, smoke, lighting and audio are not engine-identical.']
    rounds=[];kills=[]
    try:
        events=parser.parse_event('round_freeze_end',other=['total_rounds_played','is_warmup_period'])
        if isinstance(events,pd.DataFrame):
            for row in events.to_dict('records'):
                if row.get('is_warmup_period'):continue
                tick=int(row['tick']);number=int(row.get('total_rounds_played',0))+1
                if 0<=tick<=info['ticks']:rounds.append({'number':number,'tick':tick})
            rounds=list({r['number']:r for r in rounds}.values())
    except Exception as exc:warnings.append('Round markers unavailable: '+str(exc)[:180])
    try:
        events=parser.parse_event('player_death')
        if isinstance(events,pd.DataFrame):
            for row in events.to_dict('records'):
                kills.append({'tick':int(row['tick']),'attacker':str(row.get('attacker_name') or 'World'),
                              'victim':str(row.get('user_name') or 'Player'),'weapon':str(row.get('weapon') or '')})
    except Exception as exc:warnings.append('Kill feed unavailable: '+str(exc)[:180])
    folder.mkdir(parents=True,exist_ok=True);temporary=folder/'tracks.pending'
    with temporary.open('wb') as f:
        f.write(struct.pack('<4sIIIff',b'SRP1',len(ticks),len(players),len(FIELDS),float(step),float(info['tickrate'])))
        output.tofile(f);f.flush();os.fsync(f.fileno())
    os.replace(temporary,folder/'tracks.bin')
    meta={'schema':SCHEMA,'decoder_schema':DECODER_SCHEMA,'sha256':sha,'source':str(demo),'title':demo.stem,'map':map_name,'info':info,
          'map_asset':str(glb),'native_scene':str(native_scene),'asset_info':map_meta,'tracks':str(folder/'tracks.bin'),'frames':len(ticks),'fields':FIELDS,
          'players':players,'weapons':['Unknown',*weapons],'rounds':rounds,'kills':kills,'step':step,'map_in_selected_pool':setup['in_pool'],
          'parser':{'name':'demoparser2','version':parser_version},'warnings':[*warnings,*companion_warnings],
          'map_preparation_warnings':companion_warnings,'cs2_process_required':False}
    save(folder/'replay.json',meta)
    enrich_gameplay(parser,meta,folder,game,progress)
    save(job/'progress.json',{'state':'complete','percent':100,'message':'Ready','replay':str(folder/'replay.json')})
    return meta


def enrich_gameplay(parser,meta,folder,game,progress):
    if __package__:
        from .presentation import prepare_presentation,prepare_inventory
    else:
        from presentation import prepare_presentation,prepare_inventory
    if __package__:
        from .stock_assets import ensure_stock,canonical
        from .gameplay import prepare_gameplay
        from .grenades import prepare_grenades,WEAPON_KINDS
    else:
        from stock_assets import ensure_stock,canonical
        from gameplay import prepare_gameplay
        from grenades import prepare_grenades,WEAPON_KINDS
    stock=ensure_stock(game,meta['weapons'],progress)
    if __package__:
        from .character_materials import prepare_character_materials
    else:
        from character_materials import prepare_character_materials
    meta['character_materials']=prepare_character_materials(game,stock)
    if __package__:
        from .postprocess import prepare_postprocess
    else:
        from postprocess import prepare_postprocess
    meta['postprocess']=prepare_postprocess(game,meta['map'])
    stock=dict(stock)
    if __package__:
        from .gait import prepare_gait
        from .network_presentation import prepare_network
    else:
        from gait import prepare_gait
        from network_presentation import prepare_network
    stock['gait_strides']=prepare_gait(stock,progress)
    stock['aliases']={value:canonical(value) for value in meta['weapons']}
    meta['stock']=stock
    meta['gameplay']=prepare_gameplay(parser,meta,folder,progress)
    # Presentation travel depends on the decoded gameplay state, including on
    # the first preparation when meta has no gameplay entry yet.
    meta['presentation']=prepare_presentation(parser,meta,folder,progress)
    meta['network_presentation']=prepare_network(meta,folder,progress)
    if __package__:
        from .ragdoll_presentation import prepare_ragdolls
    else:
        from ragdoll_presentation import prepare_ragdolls
    meta['death_presentation']=prepare_ragdolls(meta,folder,progress)
    meta['inventory']=prepare_inventory(parser,meta,folder,progress)
    if __package__:
        from .shot_events import prepare_shots
    else:
        from shot_events import prepare_shots
    meta['shots']=prepare_shots(parser,meta,folder,progress)
    if __package__:
        from .hud_data import prepare_hud
    else:
        from hud_data import prepare_hud
    meta['hud']=prepare_hud(parser,meta,folder,progress)
    if __package__:
        from .replay_audio import prepare as prepare_audio
    else:
        from replay_audio import prepare as prepare_audio
    try:
        meta['replay_audio']=prepare_audio(parser,meta,folder,game,progress)
    except (OSError, ValueError, RuntimeError) as exc:
        meta.pop('replay_audio',None)
        meta.setdefault('warnings',[]).append('Additional replay audio unavailable: '+str(exc))
    meta['grenades']=prepare_grenades(parser,meta,folder,game,stock,progress)
    if __package__:
        from .smoke_fill import prepare_smoke
    else:
        from smoke_fill import prepare_smoke
    meta['smoke_presentation']=prepare_smoke(meta,folder)
    # The same prepared grenade meshes serve flight, held and player-eye views.
    stock['weapons']=dict(stock['weapons'])
    for weapon,kind in WEAPON_KINDS.items():
        stock['weapons'][weapon]={'scene':meta['grenades']['models'][kind], 'class':'knife', 'clip':weapon, 'utility':True}
    if __package__:
        from .actor_assets import ensure_actors
    else:
        from actor_assets import ensure_actors
    meta['actor_assets']=ensure_actors(game,stock,progress)
    if __package__:
        from .inspect_assets import prepare_inspects
    else:
        from inspect_assets import prepare_inspects
    meta['actor_assets']=prepare_inspects(game,meta['actor_assets'],stock,meta['weapons'],progress)
    if __package__:
        from .utility_animations import prepare_utility_animations
    else:
        from utility_animations import prepare_utility_animations
    meta['actor_assets']=prepare_utility_animations(game,meta['actor_assets'],progress)
    if __package__:
        from .weapon_graph import prepare_weapon_graph
    else:
        from weapon_graph import prepare_weapon_graph
    meta['actor_assets']=prepare_weapon_graph(game,meta['actor_assets'],meta['weapons'],progress)
    for gap in meta['actor_assets'].get('weapon_graph_gaps',[]):
        if gap not in meta.setdefault('warnings',[]):meta['warnings'].append(gap)
    if __package__:
        from .particle_assets import ensure_particles
    else:
        from particle_assets import ensure_particles
    meta['particle_assets']=ensure_particles(game,progress)
    meta['warnings']=[w for w in meta.get('warnings',[]) if 'players are simplified 3D figures' not in w]
    meta['warnings']=[w for w in meta['warnings'] if 'first-person arms, exact blending' not in w]
    note='Authored stock arms, weapon and death animation reconstruction with sampled spatial audio; exact Source 2 animation blending, physics ragdolls and full acoustic simulation remain approximate.'
    if note not in meta['warnings']:meta['warnings'].append(note)
    save(Path(folder)/'replay.json',meta)
    if __package__:
        from .native_pack import replay_mount
    else:
        from native_pack import replay_mount
    mount=replay_mount(meta)
    if mount:save(Path(folder)/'replay.pack.json',mount)
    if __package__:
        from .prepared_cache import write_receipt
    else:
        from prepared_cache import write_receipt
    write_receipt(meta,folder)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--demo',type=Path,required=True)
    parser.add_argument('--game',type=Path,default=DEFAULT_GAME);parser.add_argument('--job',type=Path,required=True)
    parser.add_argument('--hz',type=int,choices=[8,16,32,64],default=64);args=parser.parse_args()
    deps=ROOT/'app/extractor/.deps';sys.path.insert(0,str(deps))
    args.job.mkdir(parents=True,exist_ok=True)
    log=(args.job/'worker.log').open('a',encoding='utf-8')
    sys.stdout=log;sys.stderr=log
    sys.path.insert(0,str(ROOT/'app/extractor'))
    from job_lock import exclusive
    try:
        with exclusive(CACHE/'preparation.lock'):
            prepare(args.demo,args.game,args.job,args.hz)
    except BaseException as exc:
        if hasattr(exc,'map_setup'):
            save(args.job/'progress.json',{'state':'permission_required','percent':0,'message':str(exc),'map_setup':exc.map_setup});return 2
        save(args.job/'progress.json',{'state':'error','percent':0,'message':str(exc)});return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
