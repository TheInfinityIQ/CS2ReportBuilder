"""Preserve source lightmap UVs when glTF has more than two UV sets.

References the existing GLB buffer; exports no textures or original game assets.
"""
import argparse
import copy
import hashlib
import os
from pathlib import Path

if __package__:
    from .prepare_bounce import CACHE,HERE,SUPPORTED_MAPS,asset_identity,read,save,_run,gltf_info,Accessors
    from .launcher import find_godot,runtime_version
else:
    from prepare_bounce import CACHE,HERE,SUPPORTED_MAPS,asset_identity,read,save,_run,gltf_info,Accessors
    from launcher import find_godot,runtime_version

def remap_primitive(primitive, channel):
    """Keep the source lightmap channel even when detail UVs precede it."""
    attrs=primitive['attributes']
    if channel not in {'TEXCOORD_1','TEXCOORD_2','TEXCOORD_3'}:
        raise ValueError('Unsupported lightmap UV channel')
    if channel!='TEXCOORD_1' and channel not in attrs:
        raise ValueError('Source lightmap UV contract is missing its channel')
    if channel in attrs:attrs['TEXCOORD_1']=attrs[channel]
    primitive['attributes']={k:v for k,v in attrs.items() if not k.startswith('_') and k not in {'TEXCOORD_2','TEXCOORD_3'}}


def prepare_map(game,name):
    if name not in SUPPORTED_MAPS:raise ValueError('Map outside selected pool')
    source,fingerprint,_=asset_identity(game,name);maps=CACHE/'maps'/f'{name}_{fingerprint[:20]}'
    glb=maps/'world.glb';metadata=CACHE/'lighting'/maps.name;receipt=read(metadata/'probes.json',{})
    if receipt.get('source_fingerprint')!=fingerprint:raise ValueError('Prepare the authored lighting companion first.')
    godot=find_godot();key=hashlib.sha256((fingerprint+runtime_version(godot)+'-uv2-adapter-2').encode()).hexdigest()[:20]
    folder=CACHE/'lightmap_uv'/key;folder.mkdir(parents=True,exist_ok=True)
    bank=folder/'geometry.scn'
    if not bank.is_file():
        _run([CACHE/'tools/dotnet-10/dotnet.exe',CACHE/'tools/lighting-bridge/LightingBridge.dll',source,name,folder,fingerprint,glb,'uv_channels'],folder,'reader.log',limit=8*1024**2,timeout=90)
        channels=read(folder/'uv-channels.json',{}).get('channels',{})
        if not channels:
            print(name,'no extra UV sets',flush=True);return
        data=gltf_info(glb);reader=Accessors(glb,data);selected=[];mapping={};zero_count=0;accessors=copy.deepcopy(data['accessors'])
        definitions=read(maps/'source-materials.json',{}).get('materials',{})
        for index,original in enumerate(data['meshes']):
            if original.get('name') not in channels:continue
            mesh=copy.deepcopy(original)
            for ordinal,primitive in enumerate(mesh['primitives']):
                attrs=primitive['attributes'];channel=channels[mesh['name']][ordinal]
                material=data['materials'][primitive['material']].get('name','') if 'material' in primitive else ''
                if definitions.get(material,{}).get('family')=='layered':
                    if '_TEXCOORD_4' in attrs:attrs['COLOR_0']=attrs['_TEXCOORD_4']
                    else:
                        count=data['accessors'][attrs['POSITION']]['count'];zero_count=max(zero_count,count)
                        attrs['COLOR_0']=len(accessors);accessors.append({'bufferView':len(data['bufferViews']),'componentType':5126,'count':count,'type':'VEC4'})
                remap_primitive(primitive,channel)
            mapping[index]=len(selected);selected.append(mesh)
        views=copy.deepcopy(data['bufferViews'])
        for view in views:
            if view.get('buffer',0)!=0:raise ValueError('Unsupported multi-buffer map')
            view['byteOffset']=view.get('byteOffset',0)+reader.base
        buffers=[{'uri':os.path.relpath(glb,folder).replace('\\','/'),'byteLength':glb.stat().st_size}]
        if zero_count:
            (folder/'zero-blends.bin').write_bytes(bytes(zero_count*16))
            views.append({'buffer':1,'byteLength':zero_count*16});buffers.append({'uri':'zero-blends.bin','byteLength':zero_count*16})
        nodes=copy.deepcopy(data['nodes'])
        for node in nodes:
            node.pop('extensions',None)
            if 'mesh' in node:
                if node['mesh'] in mapping:node['mesh']=mapping[node['mesh']]
                else:node.pop('mesh');node.pop('skin',None)
        interchange={'asset':{'version':'2.0'},'buffers':buffers,
                     'bufferViews':views,'accessors':accessors,'meshes':selected,'materials':[{'name':m.get('name','')} for m in data['materials']],
                     'nodes':nodes,'scenes':data['scenes'],'scene':data.get('scene',0)}
        save(folder/'geometry.gltf',interchange)
        _run([godot,'--headless','--path',HERE,'--log-file',folder/'godot.log','--script',HERE/'prepare_scene.gd','--',folder/'geometry.gltf',bank],folder,'prepare.log',limit=128*1024**2,timeout=120)
    receipt['uv_geometry']=str(bank);receipt['uv_geometry_source_fingerprint']=fingerprint
    save(metadata/'probes.json',receipt)
    print(name,'source lightmap UV bank prepared',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--map',choices=sorted(SUPPORTED_MAPS));choice.add_argument('--pool',action='store_true')
    parser.add_argument('--game',type=Path,default=Path('C:/Program Files (x86)/Steam/steamapps/common/Counter-Strike Global Offensive/game'))
    args=parser.parse_args()
    for name in sorted(SUPPORTED_MAPS) if args.pool else [args.map]:prepare_map(args.game,name)


if __name__=='__main__':main()
