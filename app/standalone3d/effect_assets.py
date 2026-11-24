"""Recover source effect masks during an approved, revision-matched map setup."""
from pathlib import Path

if __package__:
    from .backend import CONVERTER,read,save,digest
    from .stock_assets import gltf_info,_run
else:
    from backend import CONVERTER,read,save,digest
    from stock_assets import gltf_info,_run


def ensure_effects(glb,game,progress):
    glb=Path(glb);game=Path(game);receipt=glb.parent/'effects.json'
    package=game/'csgo/pak01_dir.vpk';package_hash=digest(package)
    sources=read(glb.parent/'manifest.json',{}).get('source_files',{})
    expected=next((value for path,value in sources.items() if str(Path(path)).casefold()==str(package).casefold()),None)
    if expected!=package_hash:
        raise ValueError('This map was prepared from a different game revision. Approve setup for the installed revision before importing effect masks.')
    stamp=glb.stat();identity=[2,stamp.st_size,stamp.st_mtime_ns,package_hash]
    cached=read(receipt,{})
    if cached.get('identity')==identity and all(Path(p).is_file() for d in cached.get('materials',{}).values() for p in d['masks']):
        return cached
    definitions={}
    for material in gltf_info(glb).get('materials',[]):
        source=material.get('extras',{}).get('vmat',{})
        name=material.get('name','')
        # Match the authored shader contract, including steam and future map
        # material names. Name allowlists left valid sheets opaque/unprepared.
        if source.get('ShaderName')!='csgo_effects.vfx':continue
        if name in definitions:continue
        textures=source.get('TextureParams',{});vectors=source.get('VectorParams',{})
        masks=[];scales=[];speeds=[]
        directory=glb.parent/'effects';directory.mkdir(exist_ok=True)
        for i in range(1,4):
            texture=textures.get(f'g_tMask{i}')
            if not texture:continue
            asset=Path(texture)
            if asset.is_absolute() or '..' in asset.parts or not texture.startswith('materials/') or asset.suffix!='.vtex':
                raise ValueError('Unsupported atmospheric mask path in prepared map.')
            png=directory/asset.with_suffix('.png')
            if not png.is_file():
                progress('effects',27,'Preparing atmospheric effect masks once…')
                _run([CONVERTER,'-i',Path(game)/'csgo/pak01_dir.vpk','-f',texture+'_c','-d','-o',directory],directory,'export.log',limit=32*1024**2,timeout=45)
            if not png.is_file():raise ValueError('Atmospheric mask export is incomplete: '+texture)
            masks.append(str(png));scales.append(vectors.get(f'g_vMask{i}Scale',[1,1])[:2]);speeds.append(vectors.get(f'g_vMask{i}PanSpeed',[0,0])[:2])
        if masks:definitions[name]={'masks':masks,'scales':scales,'speeds':speeds,'source_shader':source['ShaderName']}
    if digest(package)!=package_hash or glb.stat().st_size!=stamp.st_size or glb.stat().st_mtime_ns!=stamp.st_mtime_ns:
        raise ValueError('Map assets changed while effect masks were being prepared. Retry setup for the current revision.')
    result={'schema':2,'identity':identity,'materials':definitions}
    save(receipt,result)
    return result
