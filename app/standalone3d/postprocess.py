"""Revision-bound, small authored post-processing profiles, separate from maps."""
from pathlib import Path
if __package__:
    from .backend import CACHE,asset_identity,digest,read,save
    from .stock_assets import _run
else:
    from backend import CACHE,asset_identity,digest,read,save
    from stock_assets import _run

def prepare_postprocess(game,map_name):
    source,fingerprint,_=asset_identity(game,map_name)
    folder=CACHE/'postprocess'/f'{map_name}_{fingerprint[:20]}'
    identity=[1,fingerprint,digest(Path(game)/'csgo/pak01_dir.vpk')]
    receipt=folder/'manifest.json';cached=read(receipt,{})
    if cached.get('identity')==identity and all(Path(p['lut']).is_file() for p in cached.get('profiles',[]) if p.get('lut_dimension',0)>0):return cached
    folder.mkdir(parents=True,exist_ok=True)
    _run([CACHE/'tools/dotnet-10/dotnet.exe',CACHE/'tools/lighting-bridge/LightingBridge.dll',source,map_name,folder,fingerprint,'unused','environment',Path(game)/'csgo/pak01_dir.vpk'],folder,'reader.log',limit=16*1024**2,timeout=35)
    profiles=read(folder/'postprocessing.json',[])
    for profile in profiles:
        path=folder/profile['lut'];dimension=int(profile.get('lut_dimension',0))
        if dimension and (not 1<=dimension<=64 or not path.is_file() or path.stat().st_size!=dimension**3*4):raise ValueError('Authored color grading table has an unsupported layout.')
        profile['lut']=str(path.resolve())
    result={'identity':identity,'profiles':profiles};save(receipt,result);return result
