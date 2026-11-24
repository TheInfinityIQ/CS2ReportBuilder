"""Explicit shared reflection-cubemap preparation for already prepared maps."""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile

if __package__:
    from .prepare_bounce import CACHE, HERE, SUPPORTED_MAPS, asset_identity, read, save, _run
else:
    from prepare_bounce import CACHE, HERE, SUPPORTED_MAPS, asset_identity, read, save, _run


def validate_reflections(folder, fingerprint):
    folder=Path(folder);data=read(folder/'reflections.json', {})
    if data.get('schema')!=1 or data.get('source_fingerprint')!=fingerprint:
        raise ValueError('Reflection companion revision mismatch.')
    width=int(data['width']);cubes=int(data['cubes']);offset=0
    if width<4 or width>512 or width!=data['height'] or width&(width-1) or not 0<cubes*6<=2048 or not data['levels']:
        raise ValueError('Unsupported reflection dimensions.')
    for index,level in enumerate(data['levels']):
        size=max(1,width>>index);count=((size+3)//4)**2*16*cubes*6
        if level['level']!=index or level['width']!=size or level['height']!=size or level['bytes']!=count or level['offset']!=offset:
            raise ValueError('Reflection mip layout mismatch.')
        offset+=count
    path=folder/'radiance.blocks'
    if offset>192*1024**2 or offset!=data['bytes'] or not path.is_file() or path.stat().st_size!=offset:
        raise ValueError('Reflection data length mismatch.')
    with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
    if actual!=data['sha256']:raise ValueError('Reflection data integrity failure.')
    return data


def prepare_map(game,name):
    if name not in SUPPORTED_MAPS:raise ValueError('Map is outside the selected review pool.')
    source,fingerprint,_=asset_identity(game,name)
    map_folder=CACHE/'maps'/f'{name}_{fingerprint[:20]}'
    if not (map_folder/'world.glb').is_file():raise ValueError('Prepare this installed map revision in Toolbox first.')
    folder=CACHE/'lighting'/map_folder.name
    if (folder/'reflections.json').is_file():
        try:
            data=validate_reflections(folder,fingerprint)
            print(name,'verified existing reflection cache',flush=True);return data
        except ValueError:pass
    staging_root=CACHE/'lighting/jobs';staging_root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=name+'-reflections-',dir=staging_root) as temporary:
        staging=Path(temporary)
        _run([CACHE/'tools/dotnet-10/dotnet.exe',CACHE/'tools/lighting-bridge/LightingBridge.dll',source,name,staging,fingerprint,map_folder/'world.glb','reflections'],
             staging,'reader.log',limit=192*1024**2,timeout=90)
        data=validate_reflections(staging,fingerprint)
        data['bridge_source_sha256']=hashlib.sha256((HERE/'lighting_bridge/Program.cs').read_bytes()).hexdigest()
        save(staging/'reflections.json',data);folder.mkdir(parents=True,exist_ok=True)
        os.replace(staging/'radiance.blocks',folder/'radiance.blocks')
        os.replace(staging/'reflections.json',folder/'reflections.json')
    print(name,data['cubes'],'reflection cubes prepared',flush=True)
    return data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--map',choices=sorted(SUPPORTED_MAPS));choice.add_argument('--pool',action='store_true')
    parser.add_argument('--game',type=Path,default=Path('C:/Program Files (x86)/Steam/steamapps/common/Counter-Strike Global Offensive/game'))
    args=parser.parse_args()
    for name in sorted(SUPPORTED_MAPS) if args.pool else [args.map]:prepare_map(args.game,name)


if __name__=='__main__':main()
