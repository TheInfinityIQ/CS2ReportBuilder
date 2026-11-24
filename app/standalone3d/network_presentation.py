"""Viewer-only weapon states using the already-installed network entity reader."""
import hashlib
import os
import shutil
from pathlib import Path
if __package__:
    from .backend import CACHE,HERE,read,save
    from .stock_assets import _run
else:
    from backend import CACHE,HERE,read,save
    from stock_assets import _run

def prepare_network(meta,folder,progress=lambda *args:None):
    project=HERE/'network_presentation'
    # Source identity forces a bounded rebuild when this reader changes, while
    # unrelated viewer edits never trigger another demo read.
    identity=[3,meta['sha256'],hashlib.sha256((project/'Program.cs').read_bytes()).hexdigest()]
    output=Path(folder)/'network-presentation.json';old=read(output,{})
    if old.get('identity')==identity:return str(output)
    dotnet=shutil.which('dotnet')
    if not dotnet:raise ValueError('The installed .NET runtime for demo reading could not be found.')
    env={**os.environ,'DOTNET_CLI_HOME':str(CACHE/'tools/dotnet-home'),'DOTNET_SKIP_FIRST_TIME_EXPERIENCE':'1','DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_GENERATE_ASPNET_CERTIFICATE':'false'}
    build=project/'bin/Release/net9.0/NetworkPresentation.dll'
    if not build.is_file() or build.stat().st_mtime<(project/'Program.cs').stat().st_mtime:
        _run([dotnet,'build',project/'NetworkPresentation.csproj','-c','Release','--no-restore','--nologo'],Path(folder),'network-build.log',limit=32*1024**2,timeout=90,incremental=True,env=env)
    progress('presentation',88,'Preparing recorded weapon animation and ammunition state…')
    temporary=output.with_suffix('.pending.json')
    _run([dotnet,build,meta['source'],temporary,meta['sha256']],Path(folder),'network-reader.log',limit=64*1024**2,timeout=180,incremental=True,env=env)
    result=read(temporary,{})
    if result.get('source')!=meta['sha256'] or not result.get('players'):raise ValueError('Recorded weapon state failed its identity check.')
    # Keep the rendering companion small. These are firing rays, not recorded
    # impacts: spread seed and cone remain available without inventing hits.
    result['shots']=[{'tick':shot['tick'],'shooter':shot['shooter'],
        'origin':[shot['data'].get('origin',{}).get(axis,0) for axis in ('x','y','z')],
        'angles':[shot['data'].get('angles',{}).get(axis,0) for axis in ('x','y')],
        'seed':shot['data'].get('seed',0),'spread':shot['data'].get('spread',0),
        'inaccuracy':shot['data'].get('inaccuracy',0)} for shot in result.get('shots',[])]
    result['identity']=identity;save(output,result);temporary.unlink(missing_ok=True)
    return str(output)
