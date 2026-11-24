"""Prepare a small shared camera/shot collision companion for one cached map."""
from pathlib import Path
if __package__:
    from .backend import CACHE,HERE,CONVERTER,digest,read,save
    from .fingerprints import fingerprint as file_fingerprint
    from .launcher import find_godot
    from .stock_assets import _run
else:
    from backend import CACHE,HERE,CONVERTER,digest,read,save
    from fingerprints import fingerprint as file_fingerprint
    from launcher import find_godot
    from stock_assets import _run

def identity(path):
    path=Path(path);stat=path.stat()
    return {'path':str(path),'bytes':stat.st_size,'modified':stat.st_mtime_ns//1_000_000_000}

def prepare_collision(game,scene):
    scene=Path(scene).resolve();meta=read(scene.parent/'manifest.json',{})
    if not scene.is_relative_to((CACHE/'maps').resolve()):raise ValueError('Select an existing prepared map.')
    # This derivative reads ONLY the map archive. A shared-pak/Steam update must
    # not make us re-import or mix newer assets into a retained older map cache.
    source=Path(game).resolve()/'csgo/maps'/f'{meta["map"]}.vpk'
    archive_sha=file_fingerprint(source)
    if meta.get('source_files',{}).get(str(source))!=archive_sha:
        raise ValueError('The map archive changed. Use Toolbox map setup first.')
    fingerprint=meta['fingerprint']
    folder=CACHE/'collision'/scene.parent.name;folder.mkdir(parents=True,exist_ok=True)
    target=folder/'world.scn';job=folder/'job.json'
    existing=read(folder/'manifest.json',{})
    if (existing.get('source_type')=='compiled_physics' and existing.get('archive_sha256')==archive_sha
            and existing.get('scene')==identity(scene) and existing.get('source_fingerprint')==fingerprint
            and target.is_file() and existing.get('collision')==identity(target)
            and existing.get('sha256')==digest(target)):
        return existing
    physics=folder/'native_physics.glb'
    _run([CONVERTER,'-i',source,'-f',f'maps/{meta["map"]}/world_physics.vmdl_c','-d','--gltf_export_format','glb','-o',folder/'native.glb'],folder,'source-physics.log',limit=128*1024**2,timeout=40)
    if not physics.is_file():raise ValueError('The map has no supported compiled collision geometry.')
    save(job,{'scene':str(scene),'geometry':[],'physics':str(physics),'output':str(target)})
    _run([find_godot(),'--headless','--path',HERE,'--script',HERE/'prepare_collision.gd',
          '--log-file',folder/'godot.log','--',job],folder,'prepare.log',limit=32*1024**2,timeout=80,incremental=True)
    info=read(Path(str(target)+'.json'),{})
    save(folder/'manifest.json',{'schema':1,'source_fingerprint':fingerprint,'scene':identity(scene),
        'geometry':[],'collision':identity(target),'source_type':info['source_type'],'archive_sha256':archive_sha,
        'sha256':digest(target),'meshes':info['meshes'],'triangles':info['triangles'],
        'mesh_paths':info['mesh_paths'],'triangle_ends':info['triangle_ends']})
    return read(folder/'manifest.json',{})
