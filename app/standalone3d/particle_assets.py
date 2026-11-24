"""Small, revision-bound stock particle imagery shared by every replay."""
from pathlib import Path
import re
if __package__:
    from .backend import CACHE,CONVERTER,HERE,read,save,digest
    from .stock_assets import _run
    from .launcher import find_godot,runtime_version
else:
    from backend import CACHE,CONVERTER,HERE,read,save,digest
    from stock_assets import _run
    from launcher import find_godot,runtime_version

def ensure_particles(game,progress):
    game=Path(game);godot=find_godot()
    identity=[4,digest(game/'csgo/pak01_dir.vpk'),runtime_version(godot)]
    folder=CACHE/'particles'/identity[1][:20];folder.mkdir(parents=True,exist_ok=True)
    receipt=folder/'manifest.json';cached=read(receipt,{})
    if cached.get('identity')==identity and all(Path(p).is_file() for p in cached.get('textures',{}).values()):
        cached['fire_bank']=prepare_retained_fire(cached,progress);return cached
    definitions={'fire':'materials/particle/fire_small_sim/fire_small_sim_b.vtex',
                 'muzzle':'materials/effects/muzzleflash1_color_tga_b013e2bc.vtex'}
    jobs=[];textures={};counts={}
    for kind,asset in definitions.items():
        local=folder/Path(asset).with_suffix('.png');sequence=local.with_suffix('.mks')
        if not local.is_file() and not sequence.is_file():
            progress('particles',34,'Preparing shared stock flame and muzzle imagery once…')
            _run([CONVERTER,'-i',game/'csgo/pak01_dir.vpk','-f',asset+'_c','-d','-o',folder],folder,'export.log',limit=96*1024**2,timeout=60)
        if kind=='fire':
            # Source2Viewer expands the source spritesheet using its authored
            # sequence metadata; retain every authored variation and its range.
            frames=[];ranges=[];active=False;start=0
            for line in sequence.read_text(encoding='utf-8-sig').splitlines():
                if line.startswith('sequence '):
                    if active:ranges.append([start,len(frames)-start])
                    active=True;start=len(frames)
                match=re.match(r'frame (\S+) ',line)
                if active and match:frames.append(str(sequence.parent/match.group(1)))
            if active:ranges.append([start,len(frames)-start])
            counts['fire_sequences']=ranges[:8]
            if len(frames)<2:raise ValueError('Stock flame sequence was not exported completely.')
        else:frames=[str(local)]
        target=folder/(kind+'-v4.res');textures[kind]=str(target);counts[kind]=len(frames)
        jobs.append({'frames':frames,'target':str(target)})
    path=folder/'prepare.json';save(path,jobs)
    _run([godot,'--headless','--path',HERE,'--log-file',folder/'godot.log','--script',HERE/'prepare_particles.gd','--',path],folder,'prepare.log',limit=128*1024**2,timeout=90)
    if not all(Path(p).is_file() for p in textures.values()):raise ValueError('Stock particle imagery preparation failed.')
    result={'identity':identity,'textures':textures,'frames':counts,'source':definitions}
    result['fire_bank']=prepare_retained_fire(result,progress)
    save(receipt,result);return result


def prepare_retained_fire(cached,progress=lambda *args:None):
    """Refilter retained pixels, with no game read or particle revision change."""
    folder=Path(cached['textures']['fire']).parent
    sequence=folder/Path(cached['source']['fire']).with_suffix('.mks')
    frames=[(sequence.parent/m.group(1)).resolve() for line in sequence.read_text(encoding='utf-8-sig').splitlines()
            if (m:=re.match(r'frame (\S+) ',line))]
    if len(frames)!=cached['frames']['fire'] or not 2<=len(frames)<=512 or not all(p.is_file() and p.is_relative_to(folder.resolve()) for p in frames):
        raise ValueError('Retained flame sequence is incomplete or outside its revision folder.')
    target=folder/'fire-layers-v1';receipt=target.with_suffix('.receipt.json')
    identity=[1,digest(HERE/'prepare_particles.gd'),[[p.name,digest(p)] for p in frames]]
    old=read(receipt,{})
    info=read(Path(str(target)+'.json'),{});blocks=Path(str(target)+'.blocks')
    if old.get('identity')==identity and info.get('layers')==len(frames) and blocks.is_file() and digest(blocks)==info.get('sha256'):return str(target)+'.json'
    progress('particles',90,'Preparing independently filtered stock flame frames once…')
    job=folder/'prepare-fire-layers.json';save(job,[{'frames':[str(p) for p in frames],'target':str(target),'layer_bank':True}])
    _run([find_godot(),'--headless','--path',HERE,'--log-file',folder/'fire-layers-godot.log','--script',HERE/'prepare_particles.gd','--',job],folder,'fire-layers.log',limit=32*1024**2,timeout=90,incremental=True)
    info=read(Path(str(target)+'.json'),{});blocks=Path(str(target)+'.blocks')
    if info.get('layers')!=len(frames) or not blocks.is_file() or digest(blocks)!=info.get('sha256'):raise ValueError('Stock flame bank failed its integrity check.')
    save(receipt,{'identity':identity,'retained_source':cached['identity']});return str(target)+'.json'
