"""Decode the published CS2 smoke chunk format; preserve raw input on failures.

Adapted from demolens v2.5.0, internal/parser/smokevoxel.go.
Copyright (c) 2026 Florian Gillmann. MIT license: entity_v8/DEMOLENS_LICENSE.txt.
Grid placement and enclosed-interior fill are reverse engineered, not engine parity.
"""
from __future__ import annotations
import argparse
import base64
import gzip
import json
import struct
from collections import deque
from pathlib import Path


def demorton(value, bits):
    return tuple(sum(((value >> (3*b+axis)) & 1) << b for b in range(bits)) for axis in range(3))


def fill_interior(occupied):
    """Fill enclosed space; exterior and open tunnels remain empty."""
    outside = bytearray(32768)
    todo = deque()
    def push(index):
        if not occupied[index] and not outside[index]:
            outside[index] = 1
            todo.append(index)
    for a in range(32):
        for b in range(32):
            for i in (a | b << 5, a | b << 5 | 31 << 10, a | b << 10,
                      a | 31 << 5 | b << 10, a << 5 | b << 10, 31 | a << 5 | b << 10):
                push(i)
    while todo:
        index = todo.pop()
        x,y,z = index & 31, index >> 5 & 31, index >> 10
        if x: push(index-1)
        if x < 31: push(index+1)
        if y: push(index-32)
        if y < 31: push(index+32)
        if z: push(index-1024)
        if z < 31: push(index+1024)
    return bytearray(1 if occupied[i] or not outside[i] else 0 for i in range(32768))


def runs(occupied):
    result = []
    previous = -2
    for i, on in enumerate(occupied):
        if not on: continue
        if i == previous + 1: result[-1] += 1
        else: result.extend((i,1))
        previous = i
    return result


class SmokeDecoder:
    def __init__(self):
        self.buffer = bytearray()
        self.parsed = 0
        self.seeds = []
        self.masks = {}
        self.ready = False
        self.fading = False
        self.chunks = 0

    def ingest(self, raw, size):
        if not 0 <= size <= len(raw):
            raise ValueError('Smoke declared size exceeds its captured buffer')
        if size < len(self.buffer):
            raise ValueError('Smoke stream shrank; this format is unsupported')
        if raw[:len(self.buffer)] != self.buffer:
            raise ValueError('Smoke stream rewrote consumed bytes; refusing an unverified format')
        self.buffer.extend(raw[len(self.buffer):size])
        changed = False
        while self.parsed + 4 <= len(self.buffer):
            seq,length = struct.unpack_from('<HH',self.buffer,self.parsed)
            end = self.parsed + 4 + length
            if end > len(self.buffer): break
            payload = self.buffer[self.parsed+4:end]
            self.parsed=end
            if len(payload) < 2: raise ValueError('Truncated smoke chunk')
            flag,kind=payload[:2]
            if flag and not self.fading: self.fading=True;changed=True
            if kind == 3:
                if len(payload)<3: raise ValueError('Missing smoke seed count')
                count=payload[2];offset=3
                if offset+8*count+2 > len(payload): raise ValueError('Truncated smoke keyframe')
                self.seeds=[];self.masks={}
                for _ in range(count):
                    x,y,z,density=payload[offset:offset+4]
                    if max(x,y,z)>31: raise ValueError('Smoke seed outside grid')
                    if density:self.seeds.append((x,y,z))
                    offset+=8
                self.ready=True
            elif kind == 2:
                offset=2
            elif kind == 0:
                self.chunks+=1
                continue
            else: raise ValueError(f'Unknown smoke chunk type {kind}')
            if offset+2 > len(payload): raise ValueError('Missing smoke mask count')
            count=struct.unpack_from('<H',payload,offset)[0];offset+=2
            expected=offset+10*count
            # Observed keyframes and deltas have one trailing zero byte.
            if expected != len(payload) and not (expected+1==len(payload) and payload[-1]==0):
                raise ValueError('Smoke mask length mismatch')
            for _ in range(count):
                cell,mask=struct.unpack_from('<HQ',payload,offset);offset+=10
                if cell>=512: raise ValueError('Smoke cell outside grid')
                self.masks[cell]=mask
            self.chunks+=1;changed=True
        return changed

    def occupancy(self):
        occupied=bytearray(32768)
        for x,y,z in self.seeds: occupied[x | y<<5 | z<<10]=1
        for cell,mask in self.masks.items():
            cx,cy,cz=demorton(cell,3)
            while mask:
                bit=(mask & -mask).bit_length()-1;mask &= mask-1
                x,y,z=demorton(bit,2)
                occupied[(cx*4+x) | (cy*4+y)<<5 | (cz*4+z)<<10]=1
        return fill_interior(occupied)


def decode_stream(source, destination):
    states={};last={};count=0;smokes=set();failures=[];failed=set();changes=[]
    with gzip.open(source,'rt',encoding='utf-8-sig') as inp,gzip.open(destination,'wt',encoding='utf-8') as out:
        for line in inp:
            row=json.loads(line);identity=row['id'];tick=row['tick']
            if row['action']!='upsert':
                if identity in last:
                    out.write(json.dumps({'tick':tick,'id':identity,'action':'removed'})+'\n');count+=1
                states.pop(identity,None);last.pop(identity,None)
                continue
            if identity in failed:continue
            state=row['state'];decoder=states.setdefault(identity,SmokeDecoder())
            try:
                changed=decoder.ingest(base64.b64decode(state['voxelBase64'],validate=True),state['declaredBytes'])
                if not changed or not decoder.ready:continue
                occupied=decoder.occupancy()
                signature=(bytes(occupied),decoder.fading)
                if last.get(identity)==signature:continue
                old=last.get(identity)
                last[identity]=signature;smokes.add(identity)
                frame={'tick':tick,'id':identity,'action':'upsert','state':{
                    'id':identity,'x':state['x'],'y':state['y'],'z':state['z'],
                    'cell':12,'grid':32,'fading':decoder.fading,'occupied':runs(occupied),
                    'voxelCount':sum(occupied),'chunks':decoder.chunks}}
                out.write(json.dumps(frame,separators=(',',':'))+'\n');count+=1
                if old:
                    removed=sum(1 for i,on in enumerate(old[0]) if on and not occupied[i])
                    added=sum(1 for i,on in enumerate(occupied) if on and not old[0][i])
                    changes.append({'tick':tick,'id':identity,'added':added,'removed':removed,'fading':decoder.fading})
            except (ValueError,struct.error) as exc:
                failed.add(identity);failures.append({'id':identity,'tick':tick,'error':str(exc)})
                if identity in last:
                    out.write(json.dumps({'tick':tick,'id':identity,'action':'removed'})+'\n');count+=1;last.pop(identity)
    return {'status':'decoded' if smokes and not failures else 'partial' if smokes else 'unavailable',
            'smokes':len(smokes),'frames':count,'failures':failures,'changes':changes,
            'geometry':'reverse_engineered_network_masks_with_enclosed_interior_fill',
            'engine_visual_parity_verified':False,'cell_units':12,'grid':32}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path)
    args=p.parse_args();result=decode_stream(args.folder/'smoke_frames.jsonl.gz',args.folder/'smoke_voxels.jsonl.gz')
    (args.folder/'smoke_decode_meta.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='changes'},indent=2))
