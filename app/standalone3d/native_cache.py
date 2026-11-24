"""One native map resource per installed revision and exact Godot runtime."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import struct
import sys
import time


def valid_container(path):
    """Godot's RSCC raw-length field wraps above 4 GiB; reject its bad table."""
    try:
        with Path(path).open('rb') as stream:
            if stream.read(4)!=b'RSCC':return False
            mode,block,total=struct.unpack('<III',stream.read(12))
            if not 1<=block<=1024**2:return False
            count=total//block+1
            table=stream.read(count*4)
            if len(table)!=count*4:return False
            size=16+len(table)+sum(v[0] for v in struct.iter_unpack('<I',table))+4
            return size==Path(path).stat().st_size
    except (OSError,ValueError,struct.error):return False


def valid_parts(scene,read):
    parts=read(scene.with_suffix('.parts.json'),{}).get('files',{})
    return bool(parts) and all((scene.parent/p).is_file() and (scene.parent/p).stat().st_size==size for p,size in parts.items())


def ensure_scene(glb, map_meta, progress, cache_limit=3_000_000_000):
    # Imported lazily: launcher also imports backend at startup.
    if __package__:
        from .backend import HERE, ROOT, read, save
        from .launcher import find_godot, runtime_version
    else:
        from backend import HERE, ROOT, read, save
        from launcher import find_godot, runtime_version
    sys.path.insert(0, str(ROOT/'app/desktop'))
    from jobs import WindowsProcessGroup, hidden_options
    glb=Path(glb);runtime=find_godot();version=runtime_version(runtime)
    parts=map_meta.get('native_texture_parts',False) or map_meta.get('map') in ('de_cache','de_inferno')
    identity={'source':map_meta['fingerprint'],'godot':version,'adapter':2,'textures':'s3tc_parts' if parts else 's3tc'}
    key=hashlib.sha256(repr(sorted(identity.items())).encode()).hexdigest()[:20]
    scene=glb.parent/f'world_{key}.scn';receipt=scene.with_suffix('.json')
    if read(receipt,{})==identity and scene.is_file() and valid_container(scene) and (not parts or valid_parts(scene,read)):return scene
    if shutil.disk_usage(glb.parent).free<3*1024**3:
        raise ValueError('Native map preparation needs 3 GB of free temporary cache space.')
    progress('native_map',25,'Preparing this map once for fast opening in Godot…')
    source=glb
    for previous in glb.parent.glob('world_*.json'):
        old=read(previous,{})
        if old.get('textures')=='s3tc_parts':continue
        if old.get('source')==identity['source'] and old.get('godot')==version and previous.with_suffix('.scn').is_file():
            source=previous.with_suffix('.scn');break
    args=[str(runtime),'--headless','--path',str(HERE),'--log-file',str(glb.parent/'native-godot.log'),'--script',str(HERE/'prepare_scene.gd'),
          '--',str(source),str(scene),'gpu']
    if parts:args.append('parts')
    with (glb.parent/'native-prepare.log').open('wb') as log:
        process=subprocess.Popen(args,cwd=glb.parent,stdout=log,stderr=subprocess.STDOUT,**hidden_options())
        group=WindowsProcessGroup(process)
        try:
            if not group.handle:raise RuntimeError('Could not supervise map preparation.')
            started=time.monotonic();last_report=started
            while process.poll() is None:
                if time.monotonic()-started>(600 if parts else 240):raise TimeoutError('One-map native preparation exceeded its bounded time limit.')
                written=sum(p.stat().st_size for p in glb.parent.rglob('*') if p.is_file())
                if written>cache_limit:
                    raise ValueError(f'Native map preparation reached its approved {cache_limit/1e9:g} GB cache limit.')
                if time.monotonic()-last_report>3:
                    progress('native_map',25,f"Preparing {map_meta.get('map','map')} for the viewer - {int(time.monotonic()-started)} seconds - {written//(1024**2)} MB cached")
                    last_report=time.monotonic()
                time.sleep(.5)
            if process.returncode or not scene.is_file():
                raise ValueError('Native map preparation failed. See '+str(glb.parent/'native-prepare.log'))
            if not valid_container(scene):
                if parts:raise ValueError('The prepared native map failed its compressed-container integrity check.')
                # Retry only this newly generated oversized cache, preserving
                # source exports and every previously working map revision.
                scene.unlink();map_meta['native_texture_parts']=True
                save(glb.parent/'manifest.json',map_meta)
                return ensure_scene(glb,map_meta,progress,cache_limit)
            if parts:
                directory=scene.with_name(scene.stem+'_textures')
                files={str(p.relative_to(scene.parent)):p.stat().st_size for p in directory.glob('*.res')}
                if not files:raise ValueError('The prepared map has no native texture parts.')
                save(scene.with_suffix('.parts.json'),{'files':files})
            save(receipt,identity)
        finally:
            if process.poll() is None:group.terminate();process.wait(timeout=10)
            group.close()
            # A cancelled/failed conversion must not strand a large partial file.
            scene.with_name(scene.stem+'.pending.scn').unlink(missing_ok=True)
    return scene
