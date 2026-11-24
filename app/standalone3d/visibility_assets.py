"""Small revision-bound visibility companion for an already prepared map.

No map extraction, demo decoding, game launch, or installed writes. Preparation
alone cannot enable culling: a matching owned-renderer image audit must pass.
"""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

if __package__:
    from .backend import CACHE, HERE, asset_identity, digest, read, save
    from .stock_assets import _run
    from .launcher import find_godot
else:
    from backend import CACHE, HERE, asset_identity, digest, read, save
    from stock_assets import _run
    from launcher import find_godot

ALGORITHM = 2
FILES = ('nodes.bin', 'regions.bin', 'masks.bin', 'pvs.bin', 'object-visibility.bin')
STATIC_SHADERS = {'generic.vfx', 'csgo_vertexlitgeneric.vfx', 'csgo_lightmappedgeneric.vfx',
                  'csgo_complex.vfx', 'csgo_simple_2way_blend.vfx'}


def scene_identity(scene):
    scene = Path(scene).resolve()
    stat = scene.stat()
    return {'name': scene.name, 'bytes': stat.st_size, 'modified': stat.st_mtime_ns // 1_000_000_000}


def build_bridge():
    runtime = CACHE/'tools/dotnet-10/dotnet.exe'
    project = HERE/'resource_bridge/ResourceBridge.csproj'
    identity = hashlib.sha256(b''.join(p.read_bytes() for p in sorted(project.parent.glob('*.cs')))
                             + project.read_bytes()).hexdigest()
    folder = CACHE/'tools/visibility-bridge'/identity[:20]
    bridge = folder/'ResourceBridge.dll'
    if not bridge.is_file() or read(folder/'build.json', {}).get('revision') != identity:
        folder.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, 'DOTNET_CLI_HOME': str(CACHE/'tools/dotnet-home'),
               'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1', 'DOTNET_CLI_TELEMETRY_OPTOUT': '1'}
        _run([runtime, 'build', project, '--no-restore', '-c', 'Release', '-o', folder,
              '--nologo', '-p:UseSharedCompilation=false', '-p:CopyLocalLockFileAssemblies=false'], folder, 'build.log',
             timeout=60, limit=16*1024**2, incremental=True, env=env)
        # Reuse the installed pinned reader's managed dependencies. Visibility
        # needs no image conversion/native Skia payload or extra runtime.
        for dependency in (CACHE/'tools/resource-bridge').glob('*.dll'):
            if dependency.name != 'ResourceBridge.dll':
                shutil.copyfile(dependency, folder/dependency.name)
        save(folder/'build.json', {'revision': identity})
    return runtime, bridge, identity


def light_bounds(data):
    """Match source_direct.gd's supported fixtures and clamped influence radius."""
    output = []
    for light in data.get('lights', []):
        if len(output) >= 256:
            break
        if light['kind'] not in ('light_omni2', 'light_barn', 'light_spot'):
            continue
        radius = min(60, max(1, float(light['range'])*.0254))/.0254
        output.append({'path': '!light:'+str(len(output)),
                       'min': [float(x)-radius for x in light['origin']],
                       'max': [float(x)+radius for x in light['origin']]})
    return output


def validate(folder, fingerprint, scene, *, verified=True):
    folder = Path(folder)
    data = read(folder/'manifest.json', {})
    if (data.get('schema') != 2 or data.get('algorithm') != ALGORITHM
            or data.get('source_fingerprint') != fingerprint
            or data.get('scene') != scene_identity(scene)):
        raise ValueError('Visibility map/scene revision mismatch.')
    if data.get('clusters') != 4096 or not 1 <= len(data.get('objects', [])) <= 50000:
        raise ValueError('Unsupported visibility layout.')
    expected = {'nodes.bin': data['nodes']*12, 'regions.bin': data['regions']*8,
                'masks.bin': data['masks']*8, 'pvs.bin': 512*(data['clusters']+2),
                'object-visibility.bin': data['row_bytes']*data['clusters']}
    if data['row_bytes'] != (len(data['objects'])+7)//8 or set(data.get('files', {})) != set(FILES):
        raise ValueError('Visibility object table mismatch.')
    for name, length in expected.items():
        path = folder/name
        if not 0 < length <= 32*1024**2 or path.stat().st_size != length or digest(path) != data['files'][name]:
            raise ValueError('Visibility integrity failure: '+name)
    if (digest(Path(scene).parent/'fidelity.json') != data.get('material_sha256')
            or digest(CACHE/'lighting'/Path(scene).parent.name/'direct.json') != data.get('light_sha256')):
        raise ValueError('Visibility material/lighting revision mismatch.')
    if verified and data.get('verified', {}).get('revision') != data.get('revision'):
        raise ValueError('Visibility rendering audit required.')
    return data


def prepare(game, scene):
    scene = Path(scene).resolve()
    if not scene.is_relative_to((CACHE/'maps').resolve()) or not scene.is_file():
        raise ValueError('Select an already prepared Toolbox map scene.')
    meta = read(scene.parent/'manifest.json', {})
    source, fingerprint, _ = asset_identity(game, meta['map'])
    if meta.get('fingerprint') != fingerprint:
        raise ValueError('The installed map changed; use the existing map approval workflow.')
    folder = CACHE/'visibility'/scene.parent.name
    selector = read(folder/'active.json', {})
    selected = folder/str(selector.get('manifest', 'missing'))
    if selected.is_file() and selected.resolve().is_relative_to(folder.resolve()):
        try:
            return selected, validate(selected.parent, fingerprint, scene)
        except (ValueError, KeyError, OSError):
            pass
    runtime, bridge, bridge_revision = build_bridge()
    jobs = CACHE/'visibility/jobs';jobs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=meta['map']+'-', dir=jobs) as temporary:
        staging = Path(temporary)
        _run([find_godot(), '--headless', '--path', HERE, '--script', 'res://dump_world_bounds.gd',
              '--log-file', staging/'godot.log', '--', scene, staging/'bounds.json'],
             staging, 'bounds.log', timeout=45, limit=8*1024**2)
        bounds = read(staging/'bounds.json', [])
        direct = CACHE/'lighting'/scene.parent.name/'direct.json'
        lighting = read(direct, {})
        if lighting.get('source_fingerprint') != fingerprint:
            raise ValueError('The prepared lighting revision does not match visibility.')
        bounds += light_bounds(lighting)
        save(staging/'bounds.json', bounds)
        output = staging/'output'
        _run([runtime, bridge, '--visibility', source, f'maps/{meta["map"]}/world_visibility.vvis_c',
              staging/'bounds.json', output], staging, 'visibility.log', timeout=45, limit=24*1024**2)
        data = read(output/'manifest.json', {})
        fidelity = scene.parent/'fidelity.json'
        classification = read(fidelity, {})
        if classification.get('schema') != 4:
            raise ValueError('The prepared map needs its existing material classification audit.')
        data.update(schema=2, algorithm=ALGORITHM, source_fingerprint=fingerprint,
                    scene=scene_identity(scene), light_sha256=digest(direct), bridge_revision=bridge_revision,
                    material_sha256=digest(fidelity), opaque_materials=sorted({material['name'] for material in classification['materials'] if material['source_shader'] in STATIC_SHADERS}))
        data['files'] = {name: digest(output/name) for name in FILES}
        data['revision'] = hashlib.sha256(repr(sorted((key, str(value)) for key, value in data.items())).encode()).hexdigest()
        save(output/'manifest.json', data)
        validate(output, fingerprint, scene, verified=False)
        # Keep older validated revisions; an interrupted preparation cannot
        # replace the last good companion with a partial binary set.
        folder = folder/data['revision'][:20]
        folder.mkdir(parents=True, exist_ok=True)
        for name in (*FILES, 'manifest.json'):
            os.replace(output/name, folder/name)
    return folder/'manifest.json', data


def certify(manifest, report):
    manifest = Path(manifest);report = Path(report)
    data = read(manifest, {});result = read(report, {});audit = result.get('playback', {}).get('world_render_audit', {})
    validate(manifest.parent, data['source_fingerprint'], CACHE/'maps'/manifest.parent.parent.name/data['scene']['name'], verified=False)
    samples = audit.get('samples', [])
    if (not result.get('ok') or audit.get('revision') != data.get('revision') or not audit.get('ok') or audit.get('comparison') != 'full_viewport_every_pixel'
            or len({(sample['tick'], sample['mode'], sample['player']) for sample in samples}) < 5
            or any(sample['changed_pixels'] > 6 for sample in samples)):
        raise ValueError('A matching successful five-view rendering comparison is required.')
    data['verified'] = {'revision': data['revision'], 'report_sha256': digest(report), 'views': len(samples)}
    save(manifest, data)
    # Publish only the small validated selector. Existing companions are retained.
    save(manifest.parent.parent/'active.json', {'schema': 2, 'revision': data['revision'],
                                              'manifest': manifest.parent.name+'/manifest.json'})
    return data
