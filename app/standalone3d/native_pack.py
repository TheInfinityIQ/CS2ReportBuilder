"""Pack an approved map's existing native resources for shared, fast loading."""
import hashlib
import json
import shutil
from pathlib import Path
if __package__:
    from .backend import HERE,read,save
    from .launcher import find_godot,runtime_version
    from .native_cache import valid_parts
    from .stock_assets import _run
else:
    from backend import HERE,read,save
    from launcher import find_godot,runtime_version
    from native_cache import valid_parts
    from stock_assets import _run

def prepare_pack(scene,info,progress=lambda *args:None):
    scene=Path(scene).resolve()
    if not valid_parts(scene,read):raise ValueError('Prepare this map’s native texture resources first.')
    runtime=find_godot();identity=[1,info['fingerprint'],scene.name,runtime_version(runtime)]
    key=hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:20]
    previous=read(scene.with_suffix('.pack.json'),{})
    previous_pack=Path(previous.get('pack',''))
    if previous.get('identity')==identity and previous_pack.is_file() and previous_pack.stat().st_size==previous.get('bytes'):
        with previous_pack.open('rb') as stream:
            if stream.read(4)==b'GDPC':return previous
    folder=scene.parent/('pack-'+key);receipt=folder/'manifest.json';cached=read(receipt,{})
    pack=folder/'world.pck'
    if cached.get('identity')==identity and pack.is_file() and pack.stat().st_size==cached.get('bytes'):
        with pack.open('rb') as stream:
            if stream.read(4)==b'GDPC':return cached
    folder.mkdir(parents=True,exist_ok=True)
    parts=read(scene.with_suffix('.parts.json'),{})['files']
    bound=2*(scene.stat().st_size+sum(parts.values()))+64*1024**2
    if shutil.disk_usage(folder).free<bound:raise ValueError('Not enough private cache space to package this prepared map safely.')
    progress('native_map',28,'Packing this map’s prepared shared resources for fast opening…')
    _run([runtime,'--headless','--path',HERE,'--log-file',folder/'godot.log','--script',HERE/'prepare_map_pack.gd',
          '--',scene,folder/'world.scn',pack,key],folder,'prepare.log',limit=bound,timeout=180)
    with pack.open('rb') as stream:
        if stream.read(4)!=b'GDPC':raise ValueError('Prepared map package failed its container check.')
    result={'schema':1,'identity':identity,'fingerprint':info['fingerprint'],'pack':str(pack),'scene':f'res://prepared/{key}/world.scn','bytes':pack.stat().st_size}
    save(receipt,result);save(scene.with_suffix('.pack.json'),result)
    # Only discard our own intermediate. Original scene/texture resources stay
    # available for fallback; demos and installed assets are never touched.
    (folder/'world.scn').unlink(missing_ok=True)
    return result

def replay_mount(meta):
    if not meta.get('native_scene'):return None
    scene=Path(meta.get('native_scene',''))
    data=read(scene.with_suffix('.pack.json'),{})
    pack=Path(data.get('pack',''))
    if data.get('schema')!=1 or data.get('fingerprint')!=meta.get('asset_info',{}).get('fingerprint') or not pack.is_file() or pack.stat().st_size!=data.get('bytes'):return None
    if not str(data.get('scene','')).startswith('res://prepared/'):return None
    with pack.open('rb') as stream:
        if stream.read(4)!=b'GDPC':return None
    return {**data,'source_demo':meta['sha256']}
