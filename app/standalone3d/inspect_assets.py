"""Small, shared authored inspect clips; never reconvert an actor bank."""
import hashlib
from pathlib import Path
if __package__:
    from .backend import CACHE,read
    from .stock_assets import _run,canonical
    from .actor_assets import VM_ALIASES
else:
    from backend import CACHE,read
    from stock_assets import _run,canonical
    from actor_assets import VM_ALIASES


def choose(catalog,suffix,kind):
    paths=[p for p in catalog if p.startswith('animation/anims/viewmodel/') and '+' not in p]
    exact=[p for p in paths if Path(p).stem=='lookat01_'+suffix]
    if exact:return min(exact,key=lambda p:(len(p),p))
    # Only the default knife is eligible; never substitute a cosmetic knife.
    fallback=f'animation/anims/viewmodel/{kind}/_default_{kind}/lookat01_{kind}.vnmclip_c'
    return fallback if kind=='knife' and fallback in paths else None


def prepare_inspects(game,actors,stock,requested,progress):
    folder=Path(actors['models']['ct']).parents[2]
    catalog=read(folder/'catalog.json',[])
    result={**actors,'viewmodels':{key:dict(value) for key,value in actors['viewmodels'].items()}}
    result['inspect_unavailable']=[]
    for weapon in sorted({canonical(name) for name in requested}):
        definition=stock['weapons'].get(weapon,{})
        if not definition or definition.get('utility'):continue
        kind='pistol' if definition['class']=='pistol' else ('knife' if weapon=='knife' else 'rifle')
        resource=choose(catalog,VM_ALIASES.get(definition['clip'],definition['clip']),kind)
        if not resource:
            result['inspect_unavailable'].append(weapon);continue
        target=folder/'poses'/hashlib.sha256(resource.encode()).hexdigest()[:20]
        output=target/'clip.json'
        if not output.is_file():
            target.mkdir(parents=True,exist_ok=True)
            progress('actors',89,'Preparing shared stock inspect animations…')
            _run([CACHE/'tools/dotnet-10/dotnet.exe',CACHE/'tools/resource-bridge/ResourceBridge.dll',
                  Path(game)/'csgo/pak01_dir.vpk',resource,target,folder/'compiled'],folder,'inspect-reader.log',limit=256*1024**2,timeout=45)
        if not output.is_file():raise ValueError('Stock inspect pose could not be decoded: '+weapon)
        result['viewmodels'][weapon]['inspect']=str(output)
    return result
