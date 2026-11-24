"""Explicit, bounded lighting preparation for existing approved map exports.

Never called automatically by playback. Reuses the installed offline reader,
map revision fingerprints, and supervised background process handling.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import struct

if __package__:
    from .backend import CACHE, HERE, asset_identity, read, save
    from .stock_assets import _run
    from .map_setup import SUPPORTED_MAPS
    from .stock_assets import gltf_info
    from .material_assets import Accessors
else:
    from backend import CACHE, HERE, asset_identity, read, save
    from stock_assets import _run
    from map_setup import SUPPORTED_MAPS
    from stock_assets import gltf_info
    from material_assets import Accessors


def verify_uv_witness(folder, glb, data):
    witness = read(Path(folder)/'uv-witness.json', {})
    if not isinstance(witness, dict) or not witness.get('samples'):
        raise ValueError('Source lightmap UV witness is missing.')
    document = gltf_info(glb)
    mesh = next((mesh for mesh in document['meshes'] if mesh.get('name')==witness['mesh']), None)
    if mesh is None or len(mesh['primitives'])!=1:
        raise ValueError('The source lightmap witness does not match the exported mesh.')
    attributes = mesh['primitives'][0]['attributes']
    if 'TEXCOORD_1' not in attributes:
        raise ValueError('The exporter lost lightmap coordinates.')
    sample = next((s for s in witness['samples'] if s.get('index')==3 and s['format']=='R16G16_UNORM'), None)
    if sample is None:
        raise ValueError('Unsupported source lightmap witness encoding; needs review.')
    raw = bytes.fromhex(sample['bytes'])
    expected = [tuple(value/65535*scale for value, scale in zip(struct.unpack_from('<2H', raw, i*sample['stride']+sample['offset']), data['uv_scale'])) for i in range(4)]
    actual = Accessors(glb, document).floats(attributes['TEXCOORD_1'], 2)[:4]
    error = max(abs(a-b) for one,two in zip(actual,expected) for a,b in zip(one,two))
    if error>2e-6:
        raise ValueError('Exported lightmap UV scale differs from the source; preparation stopped.')
    return {'mesh':witness['mesh'], 'samples':4, 'max_error':error, 'export_scale_already_applied':True}


def validate_companion(folder, fingerprint):
    folder = Path(folder)
    data = read(folder/'probes.json', {})
    if data.get('schema') != 1 or data.get('source_fingerprint') != fingerprint:
        raise ValueError('Lighting companion does not match the installed map revision.')
    w, h, d = [int(data[k]) for k in ('width', 'height', 'depth')]
    expected = ((w+3)//4)*((h+3)//4)*16*d
    if min(w,h,d) <= 0 or max(w,h,d) > 2048 or d % 6 or expected > 192*1024**2:
        raise ValueError('Unsupported probe atlas dimensions.')
    entries = [('atlas.bc6h', expected, data['atlas_sha256'])]
    for name, texture in data.get('lightmaps', {}).items():
        if name not in {'irradiance', 'directional_irradiance'}:
            raise ValueError('Unexpected lightmap dependency.')
        entries.append((name+'.blocks', int(texture['bytes']), texture['sha256']))
    for name, size, digest in entries:
        path = folder/name
        if not path.is_file() or size > 192*1024**2 or path.stat().st_size != size:
            raise ValueError('Lighting texture length mismatch: '+name)
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != digest:
            raise ValueError('Lighting texture integrity failure: '+name)
    if data.get('lightmap_version') != 8 or data.get('lightmap_game_version') != 2:
        raise ValueError('This adapter requires Source lightmap version 8.2.')
    if not data.get('lightmap_eligibility'):
        raise ValueError('Source lightmap draw-call provenance is missing.')
    return data


def prepare_map(game, name):
    if name not in SUPPORTED_MAPS:
        raise ValueError('Map is outside the approved seven-map pool.')
    source, fingerprint, _ = asset_identity(game, name)
    map_folder = CACHE/'maps'/f'{name}_{fingerprint[:20]}'
    if not (map_folder/'world.glb').is_file():
        raise ValueError('Prepare this installed map revision in Toolbox first.')
    folder = CACHE/'lighting'/map_folder.name
    bridge_hash = hashlib.sha256((HERE/'lighting_bridge/Program.cs').read_bytes()).hexdigest()
    if (folder/'probes.json').is_file():
        try:
            result = validate_companion(folder, fingerprint)
            # Optional reflection/direct-light readers share this executable.
            # Their source edits do not change the validated 8.2 GI contract.
            if result.get('adapter_version',1) != 1 or not result.get('uv_witness', {}).get('export_scale_already_applied'):
                raise ValueError('The lighting companion needs this adapter revision.')
            print(name, 'verified existing lighting', flush=True)
            return result
        except ValueError:
            pass
    if shutil.disk_usage(CACHE).free < 2*1024**3:
        raise ValueError('Lighting preparation needs 2 GB of free temporary space.')
    bridge = CACHE/'tools/lighting-bridge/LightingBridge.dll'
    runtime = CACHE/'tools/dotnet-10/dotnet.exe'
    if not bridge.is_file() or not runtime.is_file():
        raise ValueError('Build the pinned lighting bridge using the existing offline SDK first.')
    staging_root = CACHE/'lighting/jobs';staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=name+'-', dir=staging_root) as temporary:
        staging = Path(temporary)
        _run([runtime, bridge, source, name, staging, fingerprint, map_folder/'world.glb'],
             staging, 'reader.log', limit=320*1024**2, timeout=120)
        result = validate_companion(staging, fingerprint)
        result['uv_witness'] = verify_uv_witness(staging, map_folder/'world.glb', result)
        result['bridge_source_sha256'] = bridge_hash
        result['adapter_version'] = 1
        save(staging/'probes.json', result)
        folder.mkdir(parents=True, exist_ok=True)
        # Commit the receipt last. Old installed revisions live in other folders.
        for path in staging.iterdir():
            if path.name != 'probes.json':os.replace(path, folder/path.name)
        os.replace(staging/'probes.json', folder/'probes.json')
    print(name, len(result['volumes']), 'authored probe volumes prepared', flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--map', choices=sorted(SUPPORTED_MAPS))
    choice.add_argument('--pool', action='store_true', help='Explicit bulk operation; obtain approval first.')
    parser.add_argument('--game', type=Path, default=Path('C:/Program Files (x86)/Steam/steamapps/common/Counter-Strike Global Offensive/game'))
    args = parser.parse_args()
    for name in sorted(SUPPORTED_MAPS) if args.pool else [args.map]:
        prepare_map(args.game, name)


if __name__ == '__main__':main()
