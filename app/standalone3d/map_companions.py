"""Small companions of the one map already authorized by Toolbox map setup."""
if __package__:
    from .backend import CACHE,HERE,read,save,digest
    from .collision_assets import prepare_collision
    from .sky_assets import prepare_sky
    from .environment_assets import prepare_environment
else:
    from backend import CACHE,HERE,read,save,digest
    from collision_assets import prepare_collision
    from sky_assets import prepare_sky
    from environment_assets import prepare_environment

def ensure_companions(game,scene,meta,progress):
    # A failed unsupported format retains the original viewer fallback, with a
    # visible preparation warning. Never retry it on every demo opening.
    folder=CACHE/'companions'/scene.parent.name;receipt=folder/'status.json'
    revision=[digest(HERE/name) for name in ['collision_assets.py','prepare_collision.gd','sky_assets.py','environment_assets.py','resource_bridge/NativeResourceBridge.cs']]
    previous=read(receipt,{})
    if (previous.get('schema')==1 and previous.get('fingerprint')==meta['fingerprint']
            and previous.get('scene')==str(scene) and previous.get('revision')==revision):
        warnings=previous.get('warnings',[])
        if warnings:return warnings
    warnings=[]
    for label,prepare in [('camera collision',lambda:prepare_collision(game,scene)),
                          ('original sky',lambda:prepare_sky(game,meta['map'])),
                          ('authored sunlight',lambda:prepare_environment(game,scene))]:
        progress('map_details',27,'Preparing this map’s '+label+'…')
        try:prepare()
        except (ValueError,OSError,TimeoutError) as exc:
            warnings.append('Map '+label+' uses the viewer fallback: '+str(exc)[:240])
    save(receipt,{'schema':1,'fingerprint':meta['fingerprint'],'scene':str(scene),'revision':revision,'warnings':warnings})
    return warnings
