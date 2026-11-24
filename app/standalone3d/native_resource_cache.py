"""Lossless fast-read copies of existing stock scenes; explicit preparation only.

Godot reloads and saves its own scene without container compression, preserving
full texture pixels, geometry, poses and materials. Installed game files and the
original Toolbox scenes remain untouched. Binary offsets are left to Godot.
"""
from pathlib import Path
import shutil
import struct

if __package__:
    from .backend import CACHE, HERE, digest, read, save
    from .fingerprints import fingerprint, stamp
    from .stock_assets import _run
    from .launcher import find_godot
else:
    from backend import CACHE, HERE, digest, read, save
    from fingerprints import fingerprint, stamp
    from stock_assets import _run
    from launcher import find_godot


def sources(meta):
    bank = meta.get('stock', {})
    paths = set(bank.get('players', {}).values())
    paths.update(entry['scene'] for entry in meta.get('actor_assets', {}).get('arms', {}).values())
    for name in meta.get('weapons', []):
        key = bank.get('aliases', {}).get(name, name)
        if key in bank.get('weapons', {}):paths.add(bank['weapons'][key]['scene'])
    paths.update(meta.get('grenades', {}).get('models', {}).values())
    return sorted(Path(path).resolve() for path in paths)


def layout(stream):
    if stream.read(4) != b'RSCC':raise ValueError('Expected an existing compressed Godot scene.')
    header = stream.read(12)
    if len(header) != 12:raise ValueError('Truncated resource header.')
    mode, block, total = struct.unpack('<III', header)
    if mode != 2 or not 1 <= block <= 1024**2 or not 1 <= total <= 1024**3:
        raise ValueError('Unsupported compressed stock resource layout.')
    count = total//block+1;table = stream.read(count*4)
    if len(table) != count*4:raise ValueError('Truncated resource block table.')
    sizes = struct.unpack('<'+'I'*count, table)
    if any(size > block*2+1024 for size in sizes):raise ValueError('Invalid compressed block size.')
    return block, total, sizes


def estimate(meta):
    paths = sources(meta);total = 0
    for path in paths:
        with path.open('rb') as stream:total += layout(stream)[1]+4
    return {'scenes': len(paths), 'bytes': total,
            'original_bytes': sum(path.stat().st_size for path in paths),
            'folder': str(CACHE/'native-resources')}


def repack(source, target):
    source, target = Path(source), Path(target)
    before = stamp(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as stream:total = layout(stream)[1]
    if shutil.disk_usage(target.parent).free < total+64*1024**2:raise ValueError('Not enough private cache space for the selected stock scene.')
    _run([find_godot(), '--headless', '--path', HERE, '--script', HERE/'prepare_scene.gd',
          '--log-file', target.with_suffix('.godot.log'), '--', source, target, 'uncompressed'],
          target.parent, target.stem+'.process.log', limit=int(total*1.35)+32*1024**2, timeout=50, incremental=True)
    if before != stamp(source):raise ValueError('The original scene changed during preparation.')
    with target.open('rb') as stream:
        if stream.read(4) != b'RSRC':raise ValueError('Prepared resource format mismatch.')
    return {'bytes': target.stat().st_size, 'disk_bytes': target.stat().st_size,'sha256': digest(target)}


def prepare_one(source):
    source = Path(source).resolve()
    if not any(source.is_relative_to((CACHE/group).resolve()) for group in ('stock', 'actors', 'utility_models')):
        raise ValueError('Only existing Toolbox stock/arm scenes can use this cache.')
    identity = fingerprint(source)
    folder = CACHE/'native-resources';target = folder/(identity+'.scn')
    receipt = read(target.with_suffix('.json'), {})
    if receipt.get('schema') == 4 and receipt.get('source_stamp') == stamp(source) and target.is_file() and target.stat().st_size == receipt.get('bytes') and target.stat().st_mtime_ns//1_000_000_000 == receipt.get('modified'):
        return receipt
    result = repack(source, target)
    result.update(schema=4, source=str(source), source_stamp=stamp(source),
                  source_bytes=source.stat().st_size, source_modified=source.stat().st_mtime_ns//1_000_000_000,
                  path=target.name, modified=target.stat().st_mtime_ns//1_000_000_000)
    save(target.with_suffix('.json'), result)
    return result


def prepare_selected(meta):
    """Call only after explicit approval for the estimated whole-bank scope."""
    scope = estimate(meta)
    if shutil.disk_usage(CACHE).free < scope['bytes']+128*1024**2:
        raise ValueError('Not enough private cache space for this stock bank.')
    previous = read(CACHE/'native-resources/active.json', {})
    items = previous.get('items', {}) if previous.get('schema') in (2,3,4) else {}
    items.update({str(path).replace('\\', '/'): prepare_one(path) for path in sources(meta)})
    save(CACHE/'native-resources/active.json', {'schema': 4, 'items': items})
    scope['bytes']=sum(item['bytes'] for item in items.values())
    scope['disk_bytes']=scope['bytes']
    return scope
