"""Recorded death inputs, decoded with the Toolbox's existing DemoFile runtime."""
import hashlib
import math
import os
from pathlib import Path
import shutil
if __package__:
    from .backend import CACHE,HERE,read,save
    from .stock_assets import _run
else:
    from backend import CACHE,HERE,read,save
    from stock_assets import _run


def join_deaths(meta,recording):
    """Join stable player IDs and death ticks, never entity handles or nicknames."""
    if recording.get('source')!=meta['sha256']:raise ValueError('Death recording belongs to another demo.')
    players={p['id']:i for i,p in enumerate(meta['players'])};events={}
    for event in meta['gameplay']['events']:
        if event['kind']=='player_death':events.setdefault(event['player'],[]).append(event['tick'])
    selected={}
    for row in recording.get('rows',[]):
        state=row['state'];player=players.get(state.get('player'))
        if state.get('kind')!='player' or player is None or not state.get('enabled'):continue
        # Network death properties can arrive one or two ticks after the event.
        # Match only the same player and a bounded interval, including respawns.
        candidates=[tick for tick in events.get(player,[]) if 0<=row['tick']-tick<=4]
        if not candidates:continue
        key=str(player)+':'+str(max(candidates))
        if key in selected:continue
        fields={k:state[k] for k in ['serverOrigin','eyeAngles','force','damagePosition','bone','headshot','weapon','clientSide']}
        if any(len(fields[k])!=3 or not all(math.isfinite(float(n)) for n in fields[k]) for k in ['serverOrigin','eyeAngles','force','damagePosition']):continue
        # Zero/default origin is common on uninitialized/deleted entities.
        if not any(abs(v)>.001 for v in fields['serverOrigin']):continue
        selected[key]={**fields,'recorded_tick':row['tick'],'transform_count':len(state.get('transforms',[]))}
    return selected


def prepare_ragdolls(meta,folder,progress=lambda *args:None):
    project=HERE/'ragdoll_reader';output=Path(folder)/'death-presentation.json'
    identity=[1,meta['sha256'],hashlib.sha256((project/'Program.cs').read_bytes()).hexdigest()]
    if read(output,{}).get('identity')==identity:return str(output)
    dotnet=shutil.which('dotnet')
    if not dotnet:raise ValueError('The existing demo-reading runtime could not be found.')
    env={**os.environ,'DOTNET_CLI_HOME':str(CACHE/'tools/dotnet-home'),'DOTNET_SKIP_FIRST_TIME_EXPERIENCE':'1','DOTNET_CLI_TELEMETRY_OPTOUT':'1'}
    build=project/'bin/Release/net9.0/RagdollReader.dll'
    if not build.is_file() or build.stat().st_mtime<(project/'Program.cs').stat().st_mtime:
        packages=CACHE/'tools/offline-packages';packages.mkdir(parents=True,exist_ok=True)
        _run([dotnet,'restore',project/'RagdollReader.csproj','--source',packages,'--nologo'],Path(folder),'death-build.log',limit=32*1024**2,timeout=90,incremental=True,env=env)
        _run([dotnet,'build',project/'RagdollReader.csproj','-c','Release','--no-restore','--nologo'],Path(folder),'death-build.log',limit=32*1024**2,timeout=90,incremental=True,env=env)
    progress('presentation',89,'Preparing recorded death and smoke presentation inputs once…')
    temporary=output.with_suffix('.pending.json')
    _run([dotnet,build,meta['source'],temporary,meta['sha256']],Path(folder),'death-reader.log',limit=32*1024**2,timeout=180,incremental=True,env=env)
    recording=read(temporary,{})
    smokes=[{'tick':row['tick'],**row['state']} for row in recording.get('rows',[]) if row['state'].get('kind')=='smoke']
    result={'identity':identity,'deaths':join_deaths(meta,recording),'smokes':smokes,'max_recorded_transforms':recording.get('maxTransforms',0),
            'world':recording.get('worldRows',[]) if not recording.get('worldTruncated') else [],
            'world_truncated':recording.get('worldTruncated',False),
            'scope':'Recorded death inputs; client-simulated ragdoll bone motion is not supplied by these inputs.'}
    save(output,result);temporary.unlink(missing_ok=True);return str(output)
