"""One selected prepared map's original compressed sky; no map re-export."""
import shutil
from pathlib import Path
import tempfile
if __package__:
    from .backend import CACHE, asset_identity, read, save, digest
    from .stock_assets import _run
    from .visibility_assets import build_bridge
else:
    from backend import CACHE, asset_identity, read, save, digest
    from stock_assets import _run
    from visibility_assets import build_bridge

def prepare_sky(game, name):
    source, fingerprint, _ = asset_identity(game, name)
    maps = CACHE/'maps'/f'{name}_{fingerprint[:20]}'
    if not (maps/'world.glb').is_file():raise ValueError('Prepare the selected map in Toolbox first.')
    folder = CACHE/'sky'/maps.name;folder.mkdir(parents=True, exist_ok=True)
    existing=read(folder/'sky.json',{});blocks=folder/'texture.blocks'
    if (existing.get('source_fingerprint')==fingerprint and blocks.is_file()
            and blocks.stat().st_size==existing.get('bytes') and digest(blocks)==existing.get('sha256')):
        return existing
    runtime, bridge, _ = build_bridge()
    with tempfile.TemporaryDirectory(prefix='sky-', dir=folder) as temporary:
        job = Path(temporary)
        def resource(archive, path, label):
            out = job/label;out.mkdir()
            _run([runtime, bridge, '--native-resource', archive, path, out], out, 'reader.log', limit=8*1024**2, timeout=30)
            return out, read(out/'resource.json', {})
        _, entities = resource(source, f'maps/{name}/entities/default_ents.vents_c', 'entities')
        skies = entities.get('skies', [])
        if len(skies) != 1:raise ValueError('Select and validate the map’s active sky before preparing it.')
        sky = skies[0]
        _, material = resource(Path(game)/'csgo/pak01_dir.vpk', sky['material']+'_c', 'material')
        texture = material.get('textures', {}).get('g_tSkyTexture')
        if not texture or material.get('shader') != 'sky.vfx':raise ValueError('Unsupported authored sky material.')
        out, data = resource(Path(game)/'csgo/pak01_dir.vpk', texture+'_c', 'texture')
        if data['format'] != 'BC6H' or data['width'] != data['height'] or data['width'] > 1024:
            raise ValueError('Unsupported authored sky texture format.')
        stride = ((data['width']+3)//4)**2*16
        if data['levels'][0]['bytes'] != stride*6:raise ValueError('Expected six sky cube faces.')
        data.update(source_fingerprint=fingerprint, sky=sky, material=material['resource'])
        shutil.copyfile(out/'texture.blocks', folder/'texture.blocks')
        save(folder/'sky.json', data)
    return data
