"""Selected-demo HUD/camera state, using the existing parser and identity."""
import math
import hashlib
import json
from pathlib import Path
import struct

if __package__:
    from .backend import read,save
else:
    from backend import read,save

SCHEMA=1
PROPERTIES={
    'clip':'active_weapon_ammo','reserve':'total_ammo_left','armor':'armor_value',
    'helmet':'has_helmet','cash':'balance','fov':'fov',
    'vm_fov':'CCSPlayerPawn.m_flViewmodelFOV',
    'vm_x':'CCSPlayerPawn.m_flViewmodelOffsetX','vm_y':'CCSPlayerPawn.m_flViewmodelOffsetY',
    'vm_z':'CCSPlayerPawn.m_flViewmodelOffsetZ',
    'inspect':'Weapon.m_bInspectPending','inspect_loop':'Weapon.m_bInspectShouldLoop',
    'round_seconds':'CCSGameRulesProxy.CCSGameRules.m_iRoundTime',
}
PUNCH='CCSPlayerPawn.CCSPlayer_CameraServices.m_vecCsViewPunchAngle'


def scalar(value):
    try:return float(value) if math.isfinite(float(value)) else None
    except (TypeError,ValueError):return None


def prepare_presentation(parser,meta,folder,progress):
    folder=Path(folder).resolve();path=folder/'presentation.json';binary=folder/'view-punch.bin'
    identity=[SCHEMA,meta['sha256'],meta['parser'],meta['frames'],meta['step']]
    old=read(path,{})
    if old.get('identity')==identity and binary.is_file() and binary.stat().st_size==16+meta['frames']*len(meta['players'])*12:
        old['punch']=str(binary);old['travel']=prepare_travel(meta,folder);old['gait_phase']=prepare_gait_phase(meta,folder);save(path,old);return old
    import numpy as np
    progress('presentation',88,'Preparing recorded ammo, armor, camera and inspect state for this demo…')
    ticks=list(range(0,meta['info']['ticks']+1,meta['step']))
    table=parser.parse_ticks([*PROPERTIES.values(),PUNCH],ticks=ticks)
    table=table[table.steamid.astype(str).isin({p['id'] for p in meta['players']})].sort_values(['steamid','tick'])
    punch=np.zeros((meta['frames'],len(meta['players']),3),dtype='<f4');players={};available=[]
    available=[key for key,name in PROPERTIES.items() if name in table.columns]
    for slot,player in enumerate(meta['players']):
        rows=table[table.steamid.astype(str)==player['id']]
        states=[];previous=None
        columns=['tick',*[PROPERTIES[key] for key in available]]
        for row in rows[columns].itertuples(index=False,name=None):
            state=[scalar(value) for value in row[1:]]
            if state!=previous:states.append([int(row[0]),*state]);previous=state
        players[player['id']]=states
        if PUNCH in rows.columns:
            for tick,value in rows[['tick',PUNCH]].itertuples(index=False,name=None):
                if isinstance(value,(list,tuple)) and len(value)==3:
                    punch[int(tick)//meta['step'],slot]=[scalar(x) or 0 for x in value]
    temporary=binary.with_suffix('.tmp')
    with temporary.open('wb') as stream:
        stream.write(struct.pack('<4sIII',b'VPS1',meta['frames'],len(meta['players']),3));stream.write(punch.tobytes())
    temporary.replace(binary)
    result={'identity':identity,'fields':available,'players':players,'punch':str(binary),'punch_bytes':binary.stat().st_size}
    result['travel']=prepare_travel(meta,folder)
    result['gait_phase']=prepare_gait_phase(meta,folder)
    save(path,result);return result


def prepare_travel(meta,folder):
    """Ground travel from existing decoded state, not another demo parse."""
    import numpy as np
    path=Path(folder)/'travel.bin';shape=(meta['frames'],len(meta['players']))
    if path.is_file() and path.stat().st_size==16+shape[0]*shape[1]*4:return str(path)
    states=np.memmap(meta['gameplay']['states'],dtype='<f4',mode='r',offset=16,shape=(*shape,8))
    tracks=np.memmap(meta['tracks'],dtype='<f4',mode='r',offset=24,shape=(*shape,11))
    speed=np.sqrt(states[:,:,0]**2+states[:,:,1]**2)
    speed=np.where((tracks[:,:,7]>.5)&(tracks[:,:,9]>.5)&(states[:,:,3]<.5),speed,0)
    distance=np.cumsum(speed*(meta['step']/meta['info']['tickrate']),axis=0,dtype=np.float32)
    temporary=path.with_suffix('.tmp')
    with temporary.open('wb') as stream:stream.write(struct.pack('<4sIII',b'GDT1',*shape,1));stream.write(distance.astype('<f4').tobytes())
    temporary.replace(path);return str(path)


def prepare_gait_phase(meta,folder):
    """Integrate cadence before playback so direction changes and seeks agree."""
    import numpy as np
    stock=meta.get('stock',{});calibration=stock.get('gait_strides',{})
    if not calibration:return ''
    shape=(meta['frames'],len(meta['players']));path=Path(folder)/'gait-phase.bin'
    identity=[1,meta['sha256'],*shape,meta['step'],hashlib.sha256(json.dumps(calibration,sort_keys=True).encode()).hexdigest()]
    if read(path.with_suffix('.json'),{}).get('identity')==identity and path.is_file() and path.stat().st_size==16+shape[0]*shape[1]*4:return str(path)
    states=np.memmap(meta['gameplay']['states'],dtype='<f4',mode='r',offset=16,shape=(*shape,8))
    tracks=np.memmap(meta['tracks'],dtype='<f4',mode='r',offset=24,shape=(*shape,11))
    actions=['crouch','walk','run'];kinds=['pistol','rifle','knife'];directions=['n','nw','w','sw','s','se','e','ne']
    strides=np.empty((3,3,8),dtype=np.float64)
    for action,default in enumerate([64,90,128]):strides[action,:,:]=default
    for clip,value in calibration.items():
        parts=clip.rsplit('_',3)
        if len(parts)==4 and parts[1] in actions and parts[2] in directions and parts[3] in kinds:
            strides[actions.index(parts[1]),kinds.index(parts[3]),directions.index(parts[2])]=max(1,float(value))
    weapon_kinds=[]
    for weapon in meta['weapons']:
        key=stock.get('aliases',{}).get(weapon,weapon);kind=stock.get('weapons',{}).get(key,{}).get('class','rifle')
        weapon_kinds.append(kinds.index(kind) if kind in kinds else 1)
    kind=np.asarray(weapon_kinds)[tracks[:,:,10].astype(np.int32)]
    speed=np.hypot(states[:,:,0],states[:,:,1])
    angle=(np.arctan2(states[:,:,1],states[:,:,0])-np.deg2rad(tracks[:,:,3]))/(math.pi/4)
    direction=np.where(angle>=0,np.floor(angle+.5),np.ceil(angle-.5)).astype(np.int32)%8
    action=np.where(tracks[:,:,8]>.5,0,np.where((states[:,:,4]>.5)|(speed<130),1,2))
    active=(speed>10)&(tracks[:,:,7]>.5)&(tracks[:,:,9]>.5)&(states[:,:,3]<.5)
    cycles=np.cumsum(np.where(active,speed/strides[action,kind,direction],0)*(meta['step']/meta['info']['tickrate']),axis=0,dtype=np.float64)
    temporary=path.with_suffix('.tmp')
    with temporary.open('wb') as stream:stream.write(struct.pack('<4sIII',b'GPH1',*shape,1));stream.write(cycles.astype('<f4').tobytes())
    temporary.replace(path);save(path.with_suffix('.json'),{'identity':identity});return str(path)


def prepare_inventory(parser,meta,folder,progress):
    """A sparse selected-demo loadout stream, including duplicate utility counts."""
    if __package__:
        from .stock_assets import canonical
    else:
        from stock_assets import canonical
    path=Path(folder).resolve()/'inventory.json'
    identity=[1,meta['sha256'],meta['parser'],meta['step']]
    if read(path,{}).get('identity')==identity:return str(path)
    progress('presentation',89,'Preparing recorded player loadouts…')
    table=parser.parse_ticks(['inventory'],ticks=list(range(0,meta['info']['ticks']+1,meta['step'])))
    output={}
    for player in meta['players']:
        rows=table[table.steamid.astype(str)==player['id']].sort_values('tick');previous=None;events=[]
        for tick,items in rows[['tick','inventory']].itertuples(index=False,name=None):
            if hasattr(items,'tolist'):items=items.tolist()
            if not isinstance(items,(list,tuple)):continue
            inventory=sorted(canonical(item) for item in items if isinstance(item,str) and item)
            if inventory!=previous:events.append([int(tick),inventory]);previous=inventory
        output[player['id']]=events
    save(path,{'identity':identity,'players':output});return str(path)
