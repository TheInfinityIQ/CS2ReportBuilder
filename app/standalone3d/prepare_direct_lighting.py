"""Explicit shared sun-shadow/local-light preparation for prepared map revisions."""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile

if __package__:
    from .prepare_bounce import CACHE, HERE, SUPPORTED_MAPS, asset_identity, read, save, _run
else:
    from prepare_bounce import CACHE, HERE, SUPPORTED_MAPS, asset_identity, read, save, _run

NAMES = {'direct_light_shadows', 'env_light_probe_volume_atlas_dlshd'}
FORMATS = {'ATI2N': 16, 'ATI1N': 8, 'BC7': 16, 'DXT5': 16, 'DXT1': 8}


def validate_direct(folder, fingerprint):
    folder = Path(folder)
    data = read(folder/'direct.json', {})
    if data.get('schema') != 1 or data.get('source_fingerprint') != fingerprint:
        raise ValueError('Direct lighting companion revision mismatch.')
    if set(data.get('textures', {})) != NAMES or data.get('sun_channel') not in range(-1, 4):
        raise ValueError('Unsupported direct lighting dependencies.')
    for name, info in data['textures'].items():
        width, height, depth = (int(info[key]) for key in ('width', 'height', 'depth'))
        if not (4 <= width <= 8192 and 4 <= height <= 8192 and 1 <= depth <= 2048) or info['format'] not in FORMATS:
            raise ValueError('Unsupported shadow atlas layout.')
        expected = ((width+3)//4)*((height+3)//4)*depth*FORMATS[info['format']]
        path = folder/(name+'.blocks')
        if expected > 96*1024**2 or expected != info['bytes'] or not path.is_file() or path.stat().st_size != expected:
            raise ValueError('Shadow atlas length mismatch.')
        if name == 'direct_light_shadows' and depth != 1:
            raise ValueError('Unsupported static shadow array.')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != info['sha256']:
            raise ValueError('Shadow atlas integrity failure.')
    return data


def prepare_map(game, name):
    if name not in SUPPORTED_MAPS:
        raise ValueError('Map outside the selected review pool.')
    source, fingerprint, _ = asset_identity(game, name)
    maps = CACHE/'maps'/f'{name}_{fingerprint[:20]}'
    if not (maps/'world.glb').is_file():
        raise ValueError('Prepare this installed map revision in Toolbox first.')
    folder = CACHE/'lighting'/maps.name
    if (folder/'direct.json').is_file():
        try:
            data = validate_direct(folder, fingerprint)
            print(name, 'verified existing shadow cache', flush=True)
            return data
        except ValueError:
            pass
    staging_root = CACHE/'lighting/jobs'
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=name+'-direct-', dir=staging_root) as temporary:
        staging = Path(temporary)
        _run([CACHE/'tools/dotnet-10/dotnet.exe', CACHE/'tools/lighting-bridge/LightingBridge.dll',
              source, name, staging, fingerprint, maps/'world.glb', 'direct'],
             staging, 'reader.log', limit=192*1024**2, timeout=90)
        data = validate_direct(staging, fingerprint)
        data['bridge_source_sha256'] = hashlib.sha256((HERE/'lighting_bridge/Program.cs').read_bytes()).hexdigest()
        save(staging/'direct.json', data)
        folder.mkdir(parents=True, exist_ok=True)
        for name_ in sorted(NAMES):
            os.replace(staging/(name_+'.blocks'), folder/(name_+'.blocks'))
        os.replace(staging/'direct.json', folder/'direct.json')
    print(name, len(data['lights']), 'local lights and sun masks prepared', flush=True)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--map', choices=sorted(SUPPORTED_MAPS))
    choice.add_argument('--pool', action='store_true')
    parser.add_argument('--game', type=Path, default=Path('C:/Program Files (x86)/Steam/steamapps/common/Counter-Strike Global Offensive/game'))
    args = parser.parse_args()
    for name in sorted(SUPPORTED_MAPS) if args.pool else [args.map]:
        prepare_map(args.game, name)


if __name__ == '__main__':
    main()
