"""Shared authored pin/hold/throw clips, using the existing stock pose reader."""
import hashlib
from pathlib import Path
if __package__:
    from .backend import CACHE,read,HERE
    from .stock_assets import _run
else:
    from backend import CACHE,read,HERE
    from stock_assets import _run

SUFFIX={'smokegrenade':'smoke','hegrenade':'hegrenade','flashbang':'flashbang',
        'molotov':'molotov','incgrenade':'incendiary','decoy':'flashbang'}

def prepare_utility_animations(game,actors,progress=lambda *args:None):
    folder=Path(actors['models']['ct']).parents[2];catalog=set(read(folder/'catalog.json',[]))
    result={**actors,'viewmodels':{k:dict(v) for k,v in actors['viewmodels'].items()},'utility_world':{}}
    def decode(resource):
        if resource not in catalog:raise ValueError('Required stock utility animation is missing: '+resource)
        target=folder/'poses'/hashlib.sha256(resource.encode()).hexdigest()[:20];path=target/'clip.json'
        if not path.is_file():
            target.mkdir(parents=True,exist_ok=True);progress('actors',90,'Preparing shared grenade hold and throw animations…')
            _run([CACHE/'tools/dotnet-10/dotnet.exe',CACHE/'tools/resource-bridge/ResourceBridge.dll',
                  Path(game)/'csgo/pak01_dir.vpk',resource,target,folder/'compiled'],target,'reader.log',limit=64*1024**2,timeout=45)
        if not path.is_file():raise ValueError('Utility pose could not be prepared: '+resource)
        return str(path)
    for weapon,suffix in SUFFIX.items():
        if weapon not in result['viewmodels']:continue
        for action in ['pullpin','throw_overhand','throw_underhand','throwcharge_high','throwcharge_mid','throwcharge_low']:
            candidates=[p for p in catalog if p.startswith('animation/anims/viewmodel/grenade/') and Path(p).stem==action+'_'+suffix and '+' not in p]
            if not candidates:raise ValueError('Stock utility action unavailable: '+weapon+' '+action)
            result['viewmodels'][weapon][action]=decode(min(candidates,key=lambda p:(len(p),p)))
        clips={}
        for action in ['idle','idle_crouch','pullpin','pullpin_crouch','throw_overhand','throw_underhand']:
            resource='animation/anims/world/grenade/_default_grenade/'+action+'_grenade.vnmclip_c'
            specific='animation/anims/world/grenade/grenade_molotov/'+action+'_molotov.vnmclip_c'
            if weapon=='molotov' and specific in catalog:resource=specific
            clips[action]=decode(resource)
        result['utility_world'][weapon]=clips
    return result
