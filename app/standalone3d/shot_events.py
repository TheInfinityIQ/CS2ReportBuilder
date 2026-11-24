"""Recorded impact points only; no hits inferred from a player's aim angle."""
import math
from pathlib import Path
if __package__:
    from .backend import read,save
else:
    from backend import read,save

def finite(value):
    try:
        number=float(value)
        return number if math.isfinite(number) else None
    except (TypeError,ValueError,OverflowError):return None

def prepare_shots(parser,meta,folder,progress):
    path=Path(folder)/'shot_recording.json'
    identity={'schema':2,'source':meta['sha256'],'parser':meta['parser']}
    cached=read(path,{})
    if cached.get('identity')==identity:return cached
    slots={str(player['id']):i for i,player in enumerate(meta['players'])}
    progress('shots',86,'Preparing this demo’s recorded bullet impacts once…')
    impacts=[]
    tables=list(parser.parse_events(['bullet_impact','player_hurt'],player=['X','Y','Z']))
    for kind,table in tables:
        if kind!='bullet_impact':continue
        for row in table.to_dict('records'):
            player=slots.get(str(row.get('user_steamid','')))
            if player is None:continue
            time=finite(row.get('tick'));point=[finite(row.get(axis)) for axis in ['x','y','z']]
            if time is None or not 0<=time<=meta['info']['ticks'] or not all(v is not None and abs(v)<131072 for v in point):continue
            tick=int(time)
            impacts.append({'tick':tick,'player':player,'position':point})
    impacts.sort(key=lambda item:(item['tick'],item['player']))
    damage=[]
    for kind,table in tables:
        if kind!='player_hurt':continue
        for row in table.to_dict('records'):
            victim=slots.get(str(row.get('user_steamid','')))
            time=finite(row.get('tick'))
            if victim is None or time is None or not 0<=time<=meta['info']['ticks']:continue
            point=[finite(row.get('user_'+axis)) for axis in ['X','Y','Z']]
            if not all(v is not None and abs(v)<131072 for v in point):continue
            group=row.get('hitgroup',0)
            if isinstance(group,str):group={'head':1,'chest':2,'stomach':3,'left_arm':4,'right_arm':5,'left_leg':6,'right_leg':7}.get(group.lower(),0)
            amount=finite(row.get('dmg_health'));group=finite(group)
            if amount is None or amount<=0:continue
            damage.append({'tick':int(time),'victim':victim,'attacker':slots.get(str(row.get('attacker_steamid','')),-1),
                           'position':point,'hitgroup':int(group or 0),'amount':int(amount)})
    damage.sort(key=lambda item:item['tick'])
    result={'identity':identity,'impacts':impacts,'damage':damage,'geometry':'recorded_bullet_impact_events',
            'presentation_note':'Blood and shell motion are cosmetic; hurt events do not identify an exact surface impact.'}
    save(path,result);return result
