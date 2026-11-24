"""Viewer-only smoke reconstruction from recorded seeds and collision blocks.

Format reference: PureSkill CSDS smoke_voxel spec (20-unit world cells; linear
4x4x4 mask bits). Four neighbour-fill steps are a visual approximation, not the
native GPU fluid simulation. Existing analysis/decoded sidecars stay unchanged.
"""
import base64
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'extractor'))
from smoke_voxels_v8 import SmokeDecoder,demorton,runs
if __package__:
    from .backend import read,save
else:
    from backend import read,save


def fill(seeds,masks,steps=4):
    import numpy as np
    allowed=np.zeros((32,32,32),dtype=bool);blocked=allowed.copy()
    for block,mask in masks.items():
        x,y,z=(v*4 for v in demorton(block,3));allowed[z:z+4,y:y+4,x:x+4]=True
        for bit in range(64):
            if mask&(1<<bit):blocked[z+(bit>>4),y+((bit>>2)&3),x+(bit&3)]=True
    free=allowed&~blocked;occupied=np.zeros_like(free)
    for x,y,z in seeds:
        if 0<=x<32 and 0<=y<32 and 0<=z<32 and not blocked[z,y,x]:occupied[z,y,x]=True
    for _ in range(steps):
        neighbours=np.zeros_like(free)
        neighbours[1:,:,:]|=occupied[:-1,:,:];neighbours[:-1,:,:]|=occupied[1:,:,:]
        neighbours[:,1:,:]|=occupied[:,:-1,:];neighbours[:,:-1,:]|=occupied[:,1:,:]
        neighbours[:,:,1:]|=occupied[:,:,:-1];neighbours[:,:,:-1]|=occupied[:,:,1:]
        occupied|=neighbours&free
    return bytearray(occupied.astype('uint8').tobytes())


def prepare_smoke(meta,folder):
    folder=Path(folder).resolve();source=folder/'grenade_entities/smoke_frames.jsonl.gz';target=folder/'smoke-presentation.json'
    if not source.is_file():return ''
    identity=[1,meta['sha256'],source.stat().st_size,'collision-fill-20-linear-4']
    if read(target,{}).get('identity')==identity:return str(target)
    recording=read(Path(meta['grenades']['recording']),{})
    effects=[e for e in recording.get('effects',[]) if e['kind']=='smoke']
    decoders={};frames={};signatures={}
    with gzip.open(source,'rt',encoding='utf-8-sig') as stream:
        for line in stream:
            row=json.loads(line);identifier=row['id'];tick=row['tick']
            if row['action']!='upsert':decoders.pop(identifier,None);continue
            state=row['state'];decoder=decoders.setdefault(identifier,SmokeDecoder())
            decoder.ingest(base64.b64decode(state['voxelBase64']),state['declaredBytes'])
            if not decoder.ready:continue
            matches=[e for e in effects if e['entity']==state['entityIndex'] and e['start']<=tick<e['end']]
            if not matches:continue
            effect=min(matches,key=lambda e:tick-e['start']);signature=(tuple(decoder.seeds),tuple(sorted(decoder.masks.items())),decoder.fading)
            if signatures.get(effect['id'])==signature:continue
            signatures[effect['id']]=signature
            occupied=fill(decoder.seeds,decoder.masks)
            origin=[(math.floor(float(state[a])/20)-16)*20 for a in ['x','y','z']]
            frames.setdefault(effect['id'],[]).append({'tick':tick,'position':[state[a] for a in ['x','y','z']],
                'origin':origin,'cell':20,'grid':32,'occupied':runs(occupied),'fading':decoder.fading})
    save(target,{'identity':identity,'effects':frames,'method':'seed fill through received free cells, four steps; approximate fluid rendering'})
    return str(target)
