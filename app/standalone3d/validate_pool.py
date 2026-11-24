"""Owned embedded rendering matrix. Synthetic fixtures never enter the demo library."""
import argparse
import copy
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
import tempfile

if __package__:
    from .backend import CACHE,ROOT,DEFAULT_GAME,read,save
    from .map_setup import SUPPORTED_MAPS,require_setup
    from .material_assets import ensure_materials,family
    from .effect_assets import ensure_effects
    from .stock_assets import gltf_info
else:
    from backend import CACHE,ROOT,DEFAULT_GAME,read,save
    from map_setup import SUPPORTED_MAPS,require_setup
    from material_assets import ensure_materials,family
    from effect_assets import ensure_effects
    from stock_assets import gltf_info

def fixtures():
    baseline=next(p for p in (CACHE/'replays').glob('*/replay.json') if read(p,{}).get('map')=='de_anubis')
    original=read(baseline,{})
    stock=read(CACHE/'visual-audit/full-stock.json',{})
    actors=read(CACHE/'visual-audit/full-actors.json',{})
    if len(stock.get('weapons',{}))!=42:raise ValueError('Prepare the full stock set before running the matrix.')
    root=CACHE/'validation/pool';root.mkdir(parents=True,exist_ok=True)
    result=[]
    for name in sorted(SUPPORTED_MAPS):
        detail=require_setup(DEFAULT_GAME,name)
        folder=Path(detail['folder']);glb=folder/'world.glb'
        ensure_effects(glb,DEFAULT_GAME,lambda *a:None)
        ensure_materials(glb,DEFAULT_GAME,lambda *a:None)
        source=gltf_info(glb);expected={'layered':0,'decal':0,'water':0}
        for node in source['nodes']:
            if 'mesh' not in node:continue
            for primitive in source['meshes'][node['mesh']]['primitives']:
                kind=family(source['materials'][primitive['material']].get('extras',{}).get('vmat',{}))
                if kind:expected[kind]+=1
        target=root/name;target.mkdir(exist_ok=True)
        frames=129;players=2
        tracks=target/'tracks.bin';states=target/'gameplay.bin'
        # 1 Hz synthetic samples, expressly not recorded demo positions.
        with tracks.open('wb') as stream:
            stream.write(struct.pack('<4sIIIff',b'SRP1',frames,players,11,64.,64.))
            for frame in range(frames):
                for player in range(players):stream.write(struct.pack('<11f',player*80.,0,0,0,0,100,3-player,1,0,1,1))
        with states.open('wb') as stream:
            stream.write(struct.pack('<4sIII',b'GSA1',frames,players,8));stream.write(bytes(frames*players*8*4))
        data=copy.deepcopy(original)
        for key in ['grenades','grenade_data','shots','hud']:data.pop(key,None)
        data.update(title='Rendering validation · '+name,map=name,map_asset=str(glb),native_scene=detail['native_scene'],
                    asset_info=read(folder/'manifest.json',{}),tracks=str(tracks),frames=frames,step=64,
                    players=[{'id':'validation-ct','name':'CT stock model'},{'id':'validation-t','name':'T stock model'}],
                    weapons=['Unknown','knife'],rounds=[{'number':1,'tick':0}],kills=[],stock=stock,actor_assets=actors,
                    gameplay={'states':str(states),'events':[]},validation_fixture={'type':'synthetic_map_weapon_rendering','expected_materials':expected},
                    hud={'events':[{'tick':0,'kind':'round_freeze_end','round':1,'ct_score':0,'t_score':0,'ct_name':'Validation CT','t_name':'Validation T'}],'kills':[]})
        data['info']={'ticks':8192,'tickrate':64}
        path=target/'fixture.json';save(path,data);result.append(path)
        print('Fixture ready:',name,flush=True)
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-only',action='store_true');parser.add_argument('--map');args=parser.parse_args()
    paths=fixtures()
    if args.prepare_only:return
    reports=[]
    for path in paths:
        if args.map and path.parent.name!=args.map:continue
        started=time.monotonic()
        run_folder=Path(tempfile.mkdtemp(prefix='run-',dir=path.parent))
        process=subprocess.run([sys.executable,str(ROOT/'app/desktop/embedded_smoke.py'),'--replay',str(path),
                                '--timeout','240','--max-ready-seconds','30','--output-dir',str(run_folder)],
                               capture_output=True,text=True,timeout=260)
        report=read(run_folder/'result.json',{})
        report['ok']=bool(report.get('ok') and process.returncode==0)
        if not (run_folder/'result.json').is_file():
            report['error']='This renderer run exited without a validation report.'
        report['validation_type']='synthetic_map_weapon_rendering';report['map']=path.parent.name
        report['process_returncode']=process.returncode
        save(path.parent/'result.json',report)
        reports.append(report)
        print(path.parent.name,report.get('ok'),report.get('ready_seconds'),'seconds; errors:',report.get('renderer_errors',[]),flush=True)
        if process.returncode and not report.get('playback'):print(process.stderr[-1000:],flush=True)
        coverage=[read(CACHE/'validation/pool'/name/'result.json',{}) for name in sorted(SUPPORTED_MAPS)]
        coverage=[item for item in coverage if item]
        save(CACHE/'validation/pool/results.json',{'maps':coverage,'ok':len(coverage)==len(SUPPORTED_MAPS) and all(r.get('ok') for r in coverage)})
    return 0 if reports and all(r.get('ok') for r in reports) else 1

if __name__=='__main__':raise SystemExit(main())
