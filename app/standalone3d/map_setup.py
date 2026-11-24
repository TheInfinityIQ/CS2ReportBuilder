"""Map preparation is explicit, version-bound, and separate from demo decoding."""
import hashlib
from pathlib import Path
import re
import json
import sys
import time

if __package__:
    from . import backend, launcher
    from .native_cache import valid_container
else:
    import backend, launcher
    from native_cache import valid_container

# User's chosen review pool, not a claim about Valve's current competitive list.
SUPPORTED_MAPS = ('de_ancient','de_anubis','de_dust2','de_mirage','de_inferno','de_cache','de_nuke')
MAP_CACHE_LIMIT = 8_000_000_000


class MapSetupRequired(ValueError):
    def __init__(self, details):
        self.map_setup = details
        outside = ' is outside your selected map pool and' if not details['in_pool'] else ''
        message=details['label']+outside+' needs map preparation. Your permission is required before importing assets.'
        if not details.get('installed',True):message=details['label']+' is not installed. Install its map assets through Steam, then reopen the demo.'
        super().__init__(message)


def inspect(game, map_name):
    if not re.fullmatch(r'[a-z0-9_]{1,64}',map_name):raise ValueError('The recording has an unsupported map name.')
    if not (Path(game)/'csgo/maps'/f'{map_name}.vpk').is_file():
        return {'map':map_name,'label':map_name.removeprefix('de_').replace('_',' ').title(),
                'in_pool':map_name in SUPPORTED_MAPS,'installed':False,'ready':False,'cache_limit':MAP_CACHE_LIMIT}
    # asset_identity validates the map identifier and installed VPK boundary.
    source,key,evidence = backend.asset_identity(game,map_name)
    version = launcher.runtime_version(launcher.find_godot())
    key = backend.asset_key(evidence, True)
    folder = backend.CACHE/'maps'/f'{map_name}_{key[:20]}'
    manifest = backend.read(folder/'manifest.json',{})
    parts_layout=manifest.get('native_texture_parts',False) or map_name in ('de_cache','de_inferno')
    identity = {'source':key,'godot':version,'adapter':2,'textures':'s3tc_parts' if parts_layout else 's3tc'}
    native_key = hashlib.sha256(repr(sorted(identity.items())).encode()).hexdigest()[:20]
    scene = folder/f'world_{native_key}.scn'
    ready = (manifest.get('fingerprint') == key and not manifest.get('geometry_only',True)
             and (folder/'world.glb').is_file() and scene.is_file()
             and backend.read(scene.with_suffix('.json'),{}) == identity and valid_container(scene))
    if ready and parts_layout:
        parts=backend.read(scene.with_suffix('.parts.json'),{})
        ready=bool(parts.get('files')) and all((folder/p).is_file() and (folder/p).stat().st_size==size for p,size in parts.get('files',{}).items())
    return {'map':map_name,'label':map_name.removeprefix('de_').replace('_',' ').title(),
            'in_pool':map_name in SUPPORTED_MAPS, 'installed':True, 'fingerprint':backend.asset_stamp(evidence),
            'runtime':version,'ready':ready,'cache_limit':MAP_CACHE_LIMIT,'folder':str(folder),
            'native_scene':str(scene)}


def approved(details):
    if not details.get('installed',True):return False
    settings = backend.read(backend.CACHE/'settings.json',{})
    grant = settings.get('map_setup_grants',{}).get(details['map'],{})
    return (not grant.get('prepared',False) and grant.get('fingerprint') == details['fingerprint'] and grant.get('runtime') == details['runtime']
            and settings.get('texture_grants',{}).get(details['map']) == details['fingerprint'])


def require_setup(game,map_name):
    details = inspect(game,map_name)
    if not details['ready'] and not approved(details): raise MapSetupRequired(details)
    if details['ready']:mark_prepared(details)
    return details


def mark_prepared(details):
    def update(settings):
        grant=settings.get('map_setup_grants',{}).get(details['map'])
        if grant and not grant.get('prepared',False) and grant.get('fingerprint')==details['fingerprint']:
            grant['prepared']=True
    _edit_settings(update)


def _edit_settings(update):
    # Approvals may arrive while another approved map finishes. Do not lose
    # either revision grant through competing read/modify/write operations.
    sys.path.insert(0,str(backend.ROOT/'app/extractor'))
    from job_lock import exclusive
    deadline=time.monotonic()+3
    while True:
        guard=exclusive(backend.CACHE/'map-settings.lock')
        try:guard.__enter__();break
        except RuntimeError:
            if time.monotonic()>deadline:raise
            time.sleep(.05)
    try:
        settings=backend.read(backend.CACHE/'settings.json',{})
        previous=json.dumps(settings,sort_keys=True)
        update(settings)
        if json.dumps(settings,sort_keys=True)!=previous:backend.save(backend.CACHE/'settings.json',settings)
    finally:guard.__exit__(None,None,None)


def approve(game,request):
    """Called only after a concrete user approval; stale requests never grant new assets."""
    current = inspect(game,request['map'])
    if not current.get('installed',True):raise ValueError('This map is not installed. Install its assets through Steam and reopen the demo.')
    if current['fingerprint'] != request.get('fingerprint') or current['runtime'] != request.get('runtime'):
        raise ValueError('The installed map or renderer changed. Reopen this demo to review the updated setup request.')
    def update(settings):
        settings.setdefault('texture_grants',{})[current['map']] = current['fingerprint']
        settings.setdefault('map_setup_grants',{})[current['map']] = {
            'fingerprint':current['fingerprint'],'runtime':current['runtime'],'cache_limit':MAP_CACHE_LIMIT}
    _edit_settings(update)
    return current


def configured_game():
    settings = backend.read(backend.ROOT/'data/.desktop/settings.json',{})
    return Path(settings.get('cs2_game_directory') or backend.DEFAULT_GAME)
