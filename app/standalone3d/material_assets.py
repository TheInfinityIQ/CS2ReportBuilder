"""Source material families and lost vertex attributes over existing map caches.

No map geometry re-export: only selected missing texture dependencies and compact
blend attributes are prepared. Originals remain read-only.
"""
import hashlib
import copy
import os
from pathlib import Path
import struct

if __package__:
    from .backend import CACHE,CONVERTER,HERE,read,save,digest
    from .stock_assets import gltf_info,_run
    from .launcher import find_godot,runtime_version
else:
    from backend import CACHE,CONVERTER,HERE,read,save,digest
    from stock_assets import gltf_info,_run
    from launcher import find_godot,runtime_version

VERSION=4
DETAIL_SCHEMA=1
LIMIT=256*1024**2


def family(source):
    shader=source.get('ShaderName','');flags=source.get('IntParams',{})
    if 'water' in shader:return 'water'
    if 'static_overlay' in shader:return 'decal'
    if flags.get('F_LAYERS',0) and source.get('TextureParams',{}).get('g_tLayer2Color'):return 'layered'
    return None


class Accessors:
    def __init__(self,path,data):
        self.path=Path(path);self.data=data
        with self.path.open('rb') as stream:
            stream.seek(12);length,kind=struct.unpack('<II',stream.read(8))
            stream.seek(20+length);_,kind=struct.unpack('<II',stream.read(8))
            if kind!=0x004e4942:raise ValueError('Map has no embedded binary attributes.')
            self.base=stream.tell()

    def floats(self,index,components):
        a=self.data['accessors'][index];v=self.data['bufferViews'][a['bufferView']]
        if a['componentType']!=5126 or a.get('sparse') or a['type']!=f'VEC{components}':
            raise ValueError('Unsupported Source blend attribute encoding.')
        width=4*components;stride=v.get('byteStride',width)
        with self.path.open('rb') as stream:
            stream.seek(self.base+v.get('byteOffset',0)+a.get('byteOffset',0))
            raw=stream.read((a['count']-1)*stride+width)
        if len(raw)!=(a['count']-1)*stride+width:raise ValueError('Truncated map attributes.')
        return [struct.unpack_from('<'+'f'*components,raw,i*stride) for i in range(a['count'])]


def ensure_materials(glb,game,progress):
    glb=Path(glb);game=Path(game);stamp=glb.stat()
    godot=find_godot();version=runtime_version(godot)
    identity=[VERSION,stamp.st_size,stamp.st_mtime_ns,version]
    receipt=glb.parent/'source-materials.json';cached=read(receipt,{})
    reusable=cached.get('identity')==identity and Path(cached.get('geometry','')).is_file() and all(Path(p).is_file() for d in cached['materials'].values() for p in d['native_textures'].values())
    if reusable and cached.get('detail_schema')==DETAIL_SCHEMA:return cached
    shared=CACHE/'material_textures'/digest(game/'csgo/pak01_dir.vpk')[:20];shared.mkdir(parents=True,exist_ok=True)

    def texture(asset,semantic):
        path=Path(asset)
        if path.is_absolute() or '..' in path.parts or not asset.startswith(('materials/','models/')) or path.suffix!='.vtex':raise ValueError('Unsafe Source texture dependency.')
        local=glb.parent/(path.stem+'.png')
        if local.is_file() and semantic in {'g_tColor','g_tLayer2Color'}:return str(local)
        # Workshop map models may carry textures under models/, inside the
        # map VPK rather than the base game archive. Keep those revision-bound.
        custom=asset.startswith('models/')
        map_info=read(glb.parent/'manifest.json',{}) if custom else {}
        bucket=CACHE/'material_textures'/str(map_info.get('fingerprint',glb.parent.name))[:20] if custom else shared
        bucket.mkdir(parents=True,exist_ok=True)
        archive=game/'csgo/maps'/(str(map_info.get('map',''))+'.vpk') if custom else game/'csgo/pak01_dir.vpk'
        out=bucket/path.with_suffix('.png')
        if not out.is_file():
            progress('materials',27,'Preparing missing source material textures once…')
            _run([CONVERTER,'-i',archive,'-f',asset+'_c','-d','--game',game/'csgo/gameinfo.gi','-o',bucket],bucket,'export.log',limit=LIMIT,timeout=45,incremental=True)
        if not out.is_file():raise ValueError('Source texture dependency was not exported: '+asset)
        return str(out)

    # Extend only this requested map's material dependencies. Existing geometry,
    # lightmaps, models and other prepared map revisions are never rebuilt here.
    if reusable:
        result=copy.deepcopy(cached)
        _add_material_details(result['materials'],texture)
        _prepare_gpu_textures(result['materials'],shared,godot,version,progress)
        result['detail_schema']=DETAIL_SCHEMA
        save(receipt,result)
        return result

    data=gltf_info(glb);reader=Accessors(glb,data)
    materials={};indices={}
    for index,material in enumerate(data.get('materials',[])):
        source=material.get('extras',{}).get('vmat',{});kind=family(source)
        if not kind:continue
        name=material.get('name','');indices[index]=name
        if name in materials:continue
        wanted={'g_tColor','g_tLayer2Color','g_tLayer1NormalRoughness','g_tLayer2NormalRoughness','g_tBlendModulation','g_tWavesNormalHeight'}
        textures={k:texture(p,k) for k,p in source.get('TextureParams',{}).items() if k in wanted}
        materials[name]={'family':kind,'textures':textures,'source':source}
    _add_material_details(materials,texture)

    # Generic importers discard custom attributes, and can then merge vertices
    # whose only difference was a Source blend weight. Preserve weights before
    # that optimization by importing the affected geometry with COLOR_0 carrying
    # the original blend values. No position/index data is fabricated or copied.
    geometry_dir=CACHE/'material_geometry'/glb.parent.name;geometry_dir.mkdir(parents=True,exist_ok=True)
    bank=geometry_dir/('layers_'+hashlib.sha256(repr(identity).encode()).hexdigest()[:16]+'.scn')
    if not bank.is_file():
        selected=[];mesh_map={};zero_count=0;accessors=copy.deepcopy(data['accessors'])
        for original_index,mesh in enumerate(data.get('meshes',[])):
            if not any(indices.get(p.get('material')) and materials[indices[p['material']]]['family']=='layered' for p in mesh['primitives']):continue
            mesh=copy.deepcopy(mesh)
            for primitive in mesh['primitives']:
                attributes=primitive['attributes']
                material_name=indices.get(primitive.get('material'))
                if material_name and materials[material_name]['family']=='layered':
                    if '_TEXCOORD_4' in attributes:attributes['COLOR_0']=attributes['_TEXCOORD_4']
                    else:
                        # Absent source vertex input defaults to zero blend,
                        # not Godot's default white vertex color (layer 2).
                        count=data['accessors'][attributes['POSITION']]['count'];zero_count=max(zero_count,count)
                        attributes['COLOR_0']=len(accessors)
                        accessors.append({'bufferView':len(data['bufferViews']),'componentType':5126,'count':count,'type':'VEC4'})
                primitive['attributes']={k:v for k,v in attributes.items() if not k.startswith('_')}
            mesh_map[original_index]=len(selected);selected.append(mesh)
        views=copy.deepcopy(data['bufferViews'])
        for view in views:
            if view.get('buffer',0)!=0:raise ValueError('Unsupported multi-buffer Source map.')
            view['byteOffset']=view.get('byteOffset',0)+reader.base
        buffers=[{'uri':os.path.relpath(glb,geometry_dir).replace('\\','/'),'byteLength':glb.stat().st_size}]
        if zero_count:
            (geometry_dir/'zero-blends.bin').write_bytes(bytes(zero_count*16))
            views.append({'buffer':1,'byteLength':zero_count*16});buffers.append({'uri':'zero-blends.bin','byteLength':zero_count*16})
        nodes=copy.deepcopy(data['nodes'])
        for node in nodes:
            node.pop('extensions',None)
            if 'mesh' in node:
                if node['mesh'] in mesh_map:node['mesh']=mesh_map[node['mesh']]
                else:node.pop('mesh');node.pop('skin',None)
        interchange={'asset':{'version':'2.0'},'buffers':buffers,
            'bufferViews':views,'accessors':accessors,'meshes':selected,
            'materials':[{'name':m.get('name','')} for m in data['materials']],
            'nodes':nodes,'scenes':data['scenes'],'scene':data.get('scene',0)}
        path=geometry_dir/'layers.gltf';save(path,interchange)
        progress('materials',28,'Preserving source blend attributes in shared map geometry once…')
        _run([godot,'--headless','--path',HERE,'--log-file',geometry_dir/'geometry-godot.log','--script',HERE/'prepare_scene.gd','--',path,bank],geometry_dir,'prepare.log',limit=128*1024**2,timeout=180)
        if not bank.is_file():raise ValueError('Source blend geometry preparation failed.')
    # GPU-native texture dependencies are shared by path, including source
    # images already present in another map; no per-demo texture copies.
    _prepare_gpu_textures(materials,shared,godot,version,progress)
    result={'identity':identity,'schema':VERSION,'detail_schema':DETAIL_SCHEMA,'materials':materials,'geometry':str(bank),'weight_encoding':'vertex_color'}
    save(receipt,result)
    return result


def _add_material_details(materials,texture):
    for definition in materials.values():
        if definition['family']!='layered':continue
        source=definition['source'];flags=source.get('IntParams',{})
        wanted={'g_tLayer1AmbientOcclusion','g_tLayer2AmbientOcclusion'}
        if flags.get('F_DETAILTEXTURE')==1 and not flags.get('F_ADDBUMPMAPS',0):wanted.add('g_tLayer1Detail')
        for semantic in wanted:
            asset=source.get('TextureParams',{}).get(semantic)
            if asset:definition['textures'][semantic]=texture(asset,semantic)
        definition['detail_gap']=''
        if flags.get('F_DETAILTEXTURE',0)>1 or flags.get('F_ADDBUMPMAPS',0):
            definition['detail_gap']='Two-layer detail/bump composition is not yet reconstructed.'


def _prepare_gpu_textures(materials,shared,godot,version,progress):
    native=shared/'native';native.mkdir(exist_ok=True);jobs=[]
    for definition in materials.values():
        definition['native_textures']={}
        for semantic,value in definition['textures'].items():
            if semantic=='g_tColor':continue
            png=Path(value);info=png.stat()
            key=hashlib.sha256(repr((str(png),info.st_size,info.st_mtime_ns,version)).encode()).hexdigest()[:24]
            target=native/(key+'.res');definition['native_textures'][semantic]=str(target)
            if not target.is_file() and not any(j['target']==str(target) for j in jobs):jobs.append({'source':str(png),'target':str(target)})
    if jobs:
        job_path=shared/'texture-job.json';save(job_path,jobs)
        progress('materials',28,'Preparing shared GPU material textures once…')
        _run([godot,'--headless','--path',HERE,'--log-file',shared/'texture-godot.log','--script',HERE/'prepare_material_textures.gd','--',job_path],shared,'texture-prepare.log',limit=LIMIT*2,timeout=180,incremental=True)
        if not all(Path(j['target']).is_file() for j in jobs):raise ValueError('Native material textures were not prepared completely.')
