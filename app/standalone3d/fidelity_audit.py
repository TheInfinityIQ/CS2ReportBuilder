"""Read-only source-to-viewer coverage inventory; never imports or rebuilds maps."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

if __package__:
    from .backend import CACHE,read,save
    from .stock_assets import gltf_info
else:
    from backend import CACHE,read,save
    from stock_assets import gltf_info

VERSION=4
REVIEW_FEATURES={
    'first_person_hands':{'status':'implemented_native_checked','owner':'authored stock rigs, poses and weapon anchors'},
    'death_bodies':{'status':'implemented_approximate_death_animation','owner':'recorded death/respawn lifecycle; not Source physics ragdolls'},
    'muzzle_flash_and_impacts':{'status':'implemented_recorded_events_only','owner':'tick-driven muzzle flash; impacts unavailable when not networked'},
    'firing_animation':{'status':'implemented_native_checked','owner':'manual stance/recoil layering with retained root-axis conversion'},
    'backward_locomotion':{'status':'implemented_native_checked','owner':'eight-direction lower body retained during upper-body reload'},
    'smoke_rendering':{'status':'partial','owner':'voxel reconstruction and volumetric density'},
    'fire_rendering':{'status':'partial','owner':'patch-driven particle/material renderer'},
    'baked_lighting':{'status':'missing','adapter_status':'implemented_requires_matching_companion','owner':'The glTF export lacks baked lighting. Source 8.2 adapter availability alone is not evidence that this map has a validated, revision-bound companion and UV witness.'},
    'geometry_completeness':{'status':'anubis_export_roundtrip_checked','owner':'3,654,355 triangles retained; historical source-map equivalence unverified'},
    'flash_review_visibility':{'status':'implemented_native_checked','owner':'review-only bounded haze'},
}


def inspect_material(material):
    source=material.get('extras',{}).get('vmat',{})
    shader=source.get('ShaderName','unknown')
    flags=source.get('IntParams',{});textures=source.get('TextureParams',{})
    losses=[]
    if 'water' in shader:losses.append('water_shader')
    if flags.get('F_LAYERS',0) or any('Layer2Color' in k for k in textures) or '2way_blend' in shader:losses.append('layered_material')
    if 'static_overlay' in shader:losses.append('decal_blending')
    if 'glass' in shader:losses.append('glass_shader')
    if 'effects' in shader:
        losses.append('partial_atmospheric_adapter' if material.get('name') in {'anubis_dust_001','lightshaft_001'} else 'unsupported_effect_shader')
    if 'lightmapped' in shader:losses.append('baked_lighting')
    if any(flags.get(k,0) for k in ['F_WORLDSPACE_UVS','F_TRIPLANAR','F_WORLD_ALIGNED_TEXTURE']):losses.append('source_uv_projection')
    if shader=='unknown':losses.append('missing_source_shader_provenance')
    if not losses and shader not in {'generic.vfx','csgo_vertexlitgeneric.vfx','csgo_foliage.vfx','csgo_complex.vfx'}:
        losses.append('unmapped_source_shader')
    return {'name':material.get('name',''),'source_shader':shader,'export_alpha':material.get('alphaMode','OPAQUE'),
            'source_textures':sorted(textures),'losses':losses,
            'status':'requires_adapter_or_review' if losses else 'standard_pbr_approximation'}


def audit_map(glb):
    glb=Path(glb);data=gltf_info(glb)
    materials=[inspect_material(m) for m in data.get('materials',[])]
    return {'schema':VERSION,'source_glb':str(glb),'source_json_sha256':hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest(),
            'fidelity_ready':False,'functional_pass_is_fidelity_pass':False,
            'shader_counts':dict(Counter(m['source_shader'] for m in materials)),
            'loss_counts':dict(Counter(loss for m in materials for loss in m['losses'])),
            'materials':materials,'review_features':REVIEW_FEATURES}


def ensure_audit(glb):
    glb=Path(glb);stamp=glb.stat();key=[VERSION,stamp.st_size,stamp.st_mtime_ns]
    target=glb.parent/'fidelity.json';cached=read(target,{})
    if cached.get('input_stamp')==key:return cached
    result=audit_map(glb);result['input_stamp']=key;save(target,result)
    return result


def main():
    if __package__:
        from .map_setup import SUPPORTED_MAPS
    else:
        from map_setup import SUPPORTED_MAPS
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=CACHE/'visual-audit/system-coverage.json');args=parser.parse_args()
    maps=[]
    for path in (CACHE/'maps').glob('*/manifest.json'):
        meta=read(path,{})
        if meta.get('map') in SUPPORTED_MAPS and not meta.get('geometry_only',True) and (path.parent/'world.glb').is_file():
            report=ensure_audit(path.parent/'world.glb')
            maps.append({'map':meta['map'],'report':str(path.parent/'fidelity.json'),'loss_counts':report['loss_counts']})
    save(args.output,{'schema':VERSION,'fidelity_ready':False,'maps':maps,'review_features':REVIEW_FEATURES})
    print(json.dumps({'maps':len(maps),'fidelity_ready':False,'output':str(args.output),'summary':maps},indent=2))


if __name__=='__main__':main()
