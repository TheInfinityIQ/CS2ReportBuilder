"""Small lighting metadata for one retained map revision; no texture re-export."""
import math
from pathlib import Path
if __package__:
    from .backend import CACHE,read,save,digest
    from .fingerprints import fingerprint,stamp
    from .visibility_assets import build_bridge
    from .stock_assets import _run
else:
    from backend import CACHE,read,save,digest
    from fingerprints import fingerprint,stamp
    from visibility_assets import build_bridge
    from stock_assets import _run


def normalization(coefficients,count):
    # VRF SceneEnvMap.CalculateNormalizationSH, MIT (third_party/VRF_LICENSE.txt).
    if not 1<=count<=320 or len(coefficients)!=count*27 or not all(math.isfinite(float(x)) and abs(float(x))<=1e6 for x in coefficients):
        raise ValueError('Invalid cubemap radiance coefficients.')
    output=[]
    for cube in range(count):
        at=cube*27
        luma=[sum(float(coefficients[at+channel*9+band])*weight for channel,weight in enumerate((.2125,.7154,.0721))) for band in range(4)]
        output.append([luma[3]*.325735,luma[1]*.325735,luma[2]*.325735,luma[0]*.282095])
    return output


def prepare_environment(game,scene):
    scene=Path(scene).resolve()
    if not scene.is_relative_to((CACHE/'maps').resolve()):raise ValueError('Select an existing prepared map.')
    meta=read(scene.parent/'manifest.json',{});name=meta['map']
    archives=[Path(path) for path in meta.get('source_files',{}) if Path(path).suffix.lower()=='.vpk' and Path(path).name!='pak01_dir.vpk']
    if len(archives)!=1:raise ValueError('Prepared map archive is ambiguous.')
    source=archives[0]
    if meta.get('source_files',{}).get(str(source))!=fingerprint(source):
        raise ValueError('The map archive changed. Use Toolbox map setup first.')
    source_stamp=stamp(source)
    folder=CACHE/'environment'/scene.parent.name;folder.mkdir(parents=True,exist_ok=True)
    runtime,bridge,revision=build_bridge();receipt=folder/'environment.json'
    reflection=CACHE/'lighting'/scene.parent.name/'reflections.json';old=read(reflection,{})
    companion=read(reflection.parent/'normalization.json',{})
    norm_ready=not old or (companion.get('source_fingerprint')==meta['fingerprint'] and companion.get('atlas_sha256')==old.get('sha256'))
    previous=read(receipt,{})
    authoring=folder/'dynamic-authoring.json'
    acoustic=folder/'soundscapes.json'
    if previous.get('source_fingerprint')==meta['fingerprint'] and previous.get('reader')==revision and norm_ready and authoring.is_file() and acoustic.is_file():return previous
    _run([runtime,bridge,'--native-resource',source,f'maps/{name}/entities/default_ents.vents_c',folder],folder,'entities.log',limit=4*1024**2,timeout=30)
    entities=read(folder/'resource.json',{});suns=[]
    for entry in entities.get('suns',[]):
        values=entry['properties'];energy=float(values.get('brightness','1'))*float(values.get('brightnessscale','1'))
        if not math.isfinite(energy) or not 0<=energy<=128:raise ValueError('Unsupported authored sunlight range.')
        if values.get('enabled','1')=='0' or values.get('directlight','1')=='0':continue
        suns.append({'angles':entry['angles'],'color':entry['color'],'energy':energy,
                     'shadows':int(values.get('castshadows','1'))>0,'specular':values.get('renderspecular','1')!='0'})
    if len(suns)>1:raise ValueError('Multiple authored suns need explicit selection.')
    result={'schema':1,'source_fingerprint':meta['fingerprint'],'reader':revision,'suns':suns}
    # The original texture is read only for its small coefficient table. Its
    # mip payload is neither exported nor copied into a second reflection bank.
    pending_normalization=None
    if old.get('source_fingerprint')==meta['fingerprint']:
        _run([runtime,bridge,'--texture-metadata',source,f'maps/{name}/cubemaps/env_cubemap_array.vtex_c',folder],folder,'coefficients.log',limit=512*1024,timeout=30)
        texture=read(folder/'resource.json',{})
        if texture.get('radiance_coefficients'):
            coefficients=normalization(texture['radiance_coefficients'],int(old['cubes']))
            pending_normalization={'schema':1,'source_fingerprint':meta['fingerprint'],
                 'atlas_sha256':old['sha256'],'coefficients':coefficients}
    if stamp(source)!=source_stamp:raise ValueError('The map archive changed during lighting preparation.')
    save(authoring,{'schema':1,'map_revision':meta['fingerprint'],'objects':entities.get('objects',[])})
    save(acoustic,{'schema':1,'map_revision':meta['fingerprint'],'zones':entities.get('soundscapes',[])})
    if pending_normalization:save(reflection.parent/'normalization.json',pending_normalization)
    save(receipt,result);return result
