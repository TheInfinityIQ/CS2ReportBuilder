"""Resume the explicitly approved seven-map import; retain every existing cache."""
import argparse
from pathlib import Path
import shutil
import sys
import time

if __package__:
    from . import backend, map_setup
    from .native_cache import ensure_scene
else:
    import backend, map_setup
    from native_cache import ensure_scene


def run(job, game):
    job=Path(job);job.mkdir(parents=True,exist_ok=True)
    old=backend.read(job/'result.json',{})
    result={'state':'running','pool':list(map_setup.SUPPORTED_MAPS),'maps':{},'started':time.time(),
            'cache':str(backend.CACHE/'maps'),'per_map_limit':map_setup.MAP_CACHE_LIMIT,
            'additional_cache_limit':56_000_000_000,'minimum_free':30_000_000_000}
    initial=sum(p.stat().st_size for p in (backend.CACHE/'maps').rglob('*') if p.is_file())
    for index,name in enumerate(map_setup.SUPPORTED_MAPS):
        def progress(stage,percent,message):
            used=sum(p.stat().st_size for p in (backend.CACHE/'maps').rglob('*') if p.is_file())-initial
            if used>result['additional_cache_limit'] or shutil.disk_usage(backend.CACHE).free<result['minimum_free']:
                raise ValueError('Map preparation reached its approved storage budget or free-space reserve.')
            backend.save(job/'progress.json',{'state':'running','map':name,'completed':index,'total':7,
                'stage':stage,'percent':(index+percent/100)/7*100,'message':message})
        try:
            details=map_setup.inspect(game,name)
            # This fixed pool is authorized by the user's explicit seven-map request.
            if not details['ready']: map_setup.approve(game,details)
            progress('map',0,'Preparing '+details['label'])
            start=time.monotonic()
            glb,meta=backend.export_map(game,name,progress,map_setup.MAP_CACHE_LIMIT)
            native=ensure_scene(glb,meta,progress,map_setup.MAP_CACHE_LIMIT)
            map_setup.mark_prepared(details)
            result['maps'][name]={'state':'ready','reused':details['ready'],'scene':str(native),
                'seconds':round(time.monotonic()-start,2),'bytes':sum(p.stat().st_size for p in native.parent.rglob('*') if p.is_file())}
        except Exception as exc:
            result['maps'][name]={'state':'error','message':str(exc)}
        backend.save(job/'result.json',result)
    result['state']='complete' if all(v['state']=='ready' for v in result['maps'].values()) else 'incomplete'
    result['finished']=time.time();backend.save(job/'result.json',result)
    backend.save(job/'progress.json',{'state':result['state'],'completed':7,'total':7,'message':'Map preparation '+result['state']})
    return 0 if result['state']=='complete' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',type=Path,required=True)
    args=parser.parse_args()
    sys.path.insert(0,str(backend.ROOT/'app/extractor'))
    from job_lock import exclusive
    with exclusive(backend.CACHE/'preparation.lock'):
        raise SystemExit(run(args.job,map_setup.configured_game()))
