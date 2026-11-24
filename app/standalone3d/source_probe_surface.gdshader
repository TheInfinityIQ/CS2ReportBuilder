shader_type spatial;
render_mode cull_back;
uniform float roughness_floor=.04;
uniform float cloth_sheen=0.0;
#include "res://source_bounce.gdshaderinc"
#include "res://source_reflection.gdshaderinc"
#include "res://source_direct.gdshaderinc"
uniform sampler2D base_color : source_color,filter_linear_mipmap_anisotropic,repeat_enable;
uniform sampler2D normal_texture : hint_normal,filter_linear_mipmap_anisotropic,repeat_enable;
uniform sampler2D orm_texture : filter_linear_mipmap_anisotropic,repeat_enable;
uniform sampler2D metal_texture : filter_linear_mipmap_anisotropic,repeat_enable;
uniform sampler2D ao_texture : filter_linear_mipmap_anisotropic,repeat_enable;
uniform sampler2D glow_texture : source_color,filter_linear_mipmap_anisotropic,repeat_enable;
uniform vec4 base_tint : source_color=vec4(1.0);
uniform vec4 glow_tint : source_color=vec4(0.0);
uniform vec3 uv_scale=vec3(1.0);
uniform vec3 uv_offset=vec3(0.0);
uniform vec4 rough_channel=vec4(0,1,0,0);
uniform vec4 metal_channel=vec4(0,0,1,0);
uniform vec4 ao_channel=vec4(1,0,0,0);
uniform float roughness=.9;
uniform float metalness=0.0;
uniform float normal_strength=1.0;
uniform float alpha_cutoff=.5;
uniform bool use_vertex_color=false;
uniform bool has_normal=false;
uniform bool has_roughness=false;
uniform bool has_metalness=false;
uniform bool has_ao=false;
uniform bool has_emission=false;
varying vec3 surface_world;
varying vec4 vertex_tint;
void vertex(){surface_world=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz;vertex_tint=COLOR;}
void fragment(){
    vec2 uv=UV*uv_scale.xy+uv_offset.xy;
    vec4 base=texture(base_color,uv)*base_tint;
    if(use_vertex_color){base*=vertex_tint;}
    ALBEDO=base.rgb;
    ROUGHNESS=clamp(roughness*(has_roughness?dot(texture(orm_texture,uv),rough_channel):1.0),roughness_floor,1.0);
    ROUGHNESS=max(ROUGHNESS,source_geometric_roughness(NORMAL));
    METALLIC=metalness*(has_metalness?dot(texture(metal_texture,uv),metal_channel):1.0);
    vec3 shading_normal=NORMAL;
    vec3 tangent_normal=vec3(0.0,0.0,1.0);
    if(has_normal){
        vec3 normal=texture(normal_texture,uv).rgb*2.0-1.0;
        normal.xy*=normal_strength;normal=normalize(normal);
        tangent_normal=normal;
        NORMAL_MAP=normal*.5+.5;
        shading_normal=normalize(TANGENT*normal.x+BINORMAL*normal.y+NORMAL*normal.z);
    }
    vec3 geometric_world=normalize((INV_VIEW_MATRIX*vec4(NORMAL,0.0)).xyz);
    vec4 bounce=use_source_lightmap?source_lightmap(UV2,tangent_normal,geometric_world,surface_world.zxy/.0254):source_bounce(surface_world,normalize((INV_VIEW_MATRIX*vec4(shading_normal,0.0)).xyz));
    float cavity=has_ao?dot(texture(ao_texture,uv),ao_channel):1.0;
    AO=cavity*(1.0-bounce.a);AO_LIGHT_AFFECT=0.0;
    vec3 emitted=review_linear_color(ALBEDO)*(1.0-METALLIC)*bounce.rgb*cavity;
    source_specular_visibility=min(cavity,source_baked_specular_occlusion(UV2));
    vec3 world_normal=normalize((INV_VIEW_MATRIX*vec4(shading_normal,0.0)).xyz);
    vec3 world_view=normalize((INV_VIEW_MATRIX*vec4(VIEW,0.0)).xyz);
    vec4 reflected=source_reflection(surface_world,world_normal,world_view,ROUGHNESS,bounce.rgb);
    emitted+=reflected.rgb*reflection_brdf(review_linear_color(ALBEDO),METALLIC,ROUGHNESS,max(0.0,dot(shading_normal,VIEW)))*source_specular_visibility;
    AO=cavity*(1.0-max(bounce.a,reflected.a));
    if(has_emission){emitted+=review_linear_color(texture(glow_texture,uv).rgb)*review_linear_color(glow_tint.rgb);}
    EMISSION=review_shader_color(emitted);
    source_sun_visibility=source_sun_shadow(surface_world,UV2);
    // OPACITY
}
void light(){
    vec3 diffuse;vec3 specular;
    source_direct_brdf(NORMAL,LIGHT,VIEW,ALBEDO,METALLIC,ROUGHNESS,true,diffuse,specular);
    float visibility=LIGHT_IS_DIRECTIONAL?source_sun_visibility:1.0;
    DIFFUSE_LIGHT+=diffuse*LIGHT_COLOR*ATTENUATION*visibility;
    SPECULAR_LIGHT+=specular*LIGHT_COLOR*ATTENUATION*visibility*SPECULAR_AMOUNT*source_specular_visibility;
    SPECULAR_LIGHT+=ALBEDO*cloth_sheen*.08*pow(1.0-max(0.0,dot(NORMAL,VIEW)),5.0)*max(0.0,dot(NORMAL,LIGHT))*LIGHT_COLOR*ATTENUATION*visibility;
}
