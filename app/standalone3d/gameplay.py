"""Selected-demo state/events, independent of cached position decoding."""
from pathlib import Path
import struct

if __package__:
    from .backend import read,save
    from .stock_assets import canonical
else:
    from backend import read,save
    from stock_assets import canonical

VERSION=1
FIELDS=['velocity_X','velocity_Y','velocity_Z','is_airborne','is_walking','is_in_reload','is_scoped','has_defuser']


def prepare_gameplay(parser,meta,folder,progress):
    folder=Path(folder);receipt=folder/'gameplay.json';states=folder/'gameplay.bin'
    cached=read(receipt,{})
    expected=16+meta['frames']*len(meta['players'])*len(FIELDS)*4
    valid_header=False
    if states.is_file():
        with states.open('rb') as stream:
            valid_header=stream.read(16)==struct.pack('<4sIII',b'GSA1',meta['frames'],len(meta['players']),len(FIELDS))
    if (cached.get('version')==VERSION and cached.get('source')==meta['sha256']
            and cached.get('parser')==meta['parser'] and cached.get('fields')==FIELDS
            and valid_header and states.stat().st_size==expected):
        # Alias repairs affect only event strings; retain unchanged samples.
        for event in cached.get('events',[]):event['weapon']=canonical(event.get('weapon',''))
        return cached
    import numpy as np
    import pandas as pd
    progress('gameplay',85,'Preparing recorded movement, weapon state and sound events once…')
    ticks=list(range(0,meta['info']['ticks']+1,meta['step']))
    data=parser.parse_ticks(FIELDS,ticks=ticks)
    slots={p['id']:i for i,p in enumerate(meta['players'])}
    data=data[data['steamid'].astype(str).isin(slots) & data['tick'].isin(ticks)].copy()
    output=np.zeros((meta['frames'],len(slots),len(FIELDS)),dtype='<f4')
    frames=(data['tick'].to_numpy(dtype=np.int64)//meta['step']).astype(np.intp)
    players=data['steamid'].astype(str).map(slots).to_numpy(dtype=np.intp)
    for index,field in enumerate(FIELDS):
        values=pd.to_numeric(data[field],errors='coerce').fillna(0).to_numpy(dtype=np.float32)
        output[frames,players,index]=np.nan_to_num(values,nan=0,posinf=0,neginf=0)
    events=[]
    positions=np.memmap(meta['tracks'],dtype='<f4',mode='r',offset=24,
                        shape=(meta['frames'],len(slots),11))
    # Same parser/property conventions as extractor.safe_parse_events; one pass.
    names=['weapon_fire','weapon_reload','player_footstep','item_equip','player_death']
    for kind,table in parser.parse_events(names,player=['X','Y','Z']):
        for row in table.to_dict('records'):
            identifier=str(row.get('user_steamid',''));tick=int(row['tick'])
            if identifier not in slots or not 0<=tick<=meta['info']['ticks']:continue
            point=[row.get('user_'+axis,0) for axis in ['X','Y','Z']]
            point=[float(x) if pd.notna(x) else 0.0 for x in point]
            weapon=canonical(row.get('weapon',''))
            if not weapon:
                frame=min(meta['frames']-1,tick//meta['step'])
                weapon=canonical(meta['weapons'][int(positions[frame,slots[identifier],10])])
            events.append({'kind':kind,'tick':tick,'player':slots[identifier],
                           'weapon':weapon,'position':point,
                           'silenced':bool(row.get('silenced',False))})
    events.sort(key=lambda event:(event['tick'],event['player'],event['kind']))
    pending=states.with_suffix('.pending')
    with pending.open('wb') as stream:
        stream.write(struct.pack('<4sIII',b'GSA1',meta['frames'],len(slots),len(FIELDS)))
        output.tofile(stream)
    pending.replace(states)
    result={'version':VERSION,'source':meta['sha256'],'parser':meta['parser'],
            'fields':FIELDS,'states':str(states),'events':events}
    save(receipt,result)
    return result
