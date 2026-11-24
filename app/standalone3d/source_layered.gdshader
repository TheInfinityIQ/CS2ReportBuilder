shader_type spatial;
#include "res://source_bounce.gdshaderinc"
#include "res://source_reflection.gdshaderinc"
#include "res://source_direct.gdshaderinc"
// Source layer/modulation adapted from ValveResourceFormat
// Renderer/Shaders/csgo/csgo_lightmappedgeneric.frag.slang and common/utils.slang.
// MIT, copyright ValveResourceFormat Contributors; see third_party/VRF_LICENSE.txt.
uniform sampler2D color1 : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D color2 : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal1 : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal2 : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D modulation : filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec4 tint : source_color = vec4(1.0);
uniform vec4 tint1 : source_color = vec4(1.0);
uniform vec4 tint2 : source_color = vec4(1.0);
uniform vec4 border_tint : source_color = vec4(1.0);
uniform int fancy=0;
uniform float softness=.1;
uniform float border_strength=.0;
uniform float border_softness=.5;
uniform float border_offset=.0;
uniform float metalness=0.0;
uniform bool has_normals=false;
uniform vec2 scale1=vec2(1.0);
uniform vec2 scale2=vec2(1.0);
uniform vec2 offset1=vec2(0.0);
uniform vec2 offset2=vec2(0.0);
uniform vec2 normal_scale1=vec2(1.0);
uniform vec2 normal_scale2=vec2(1.0);
uniform vec2 normal_offset1=vec2(0.0);
uniform vec2 normal_offset2=vec2(0.0);
uniform vec2 center1=vec2(.5);
uniform vec2 center2=vec2(.5);
uniform float rotation1=0.0;
uniform float rotation2=0.0;
uniform vec2 normal_center1=vec2(.5);
uniform vec2 normal_center2=vec2(.5);
uniform float normal_rotation1=0.0;
uniform float normal_rotation2=0.0;
uniform vec2 modulation_scale=vec2(1.0);
uniform vec2 modulation_offset=vec2(0.0);
uniform vec2 modulation_center=vec2(.5);
uniform float modulation_rotation=0.0;
uniform bool texture_transforms=false;
uniform bool specular_enabled=false;
#include "res://source_layer_math.gdshaderinc"
uniform sampler2D detail1 : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D material_ao1 : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D material_ao2 : filter_linear_mipmap_anisotropic, repeat_enable;
uniform bool has_detail=false;
uniform bool has_material_ao=false;
uniform vec2 detail_scale=vec2(1.0);
uniform vec4 detail_tint_blend=vec4(1.0,1.0,1.0,0.0);
varying vec4 blend_values;
varying vec3 surface_world;
void vertex() { blend_values=COLOR;surface_world=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz; }
// Source's secondary coordinate transform has an asymmetric centre term
// in its V row. Preserve it rather than substituting a generic UV rotation.
vec2 source_uv(vec2 uv,vec2 scale,vec2 offset,vec2 center,float degrees) {
    float angle=radians(degrees);
    float c=cos(angle);float s=sin(angle);
    vec2 p=uv-center;
    return vec2(c*scale.x*p.x-s*scale.y*p.y,
        s*scale.x*(uv.x+center.x)+c*scale.y*p.y)+center+offset;
}
void fragment() {
    vec2 uv1=texture_transforms?source_uv(UV,scale1,offset1,center1,rotation1):UV;
    vec2 uv2=texture_transforms?source_uv(uv1,scale2,offset2,center2,rotation2):uv1;
    vec4 a=texture(color1,uv1);
    vec4 b=texture(color2,uv2);
    a.rgb=review_linear_color(a.rgb)*review_linear_color(tint1.rgb);
    b.rgb=review_linear_color(b.rgb)*review_linear_color(tint2.rgb);
    vec2 blend_uv=texture_transforms?source_uv(uv1,modulation_scale,modulation_offset,modulation_center,modulation_rotation):uv1;
    vec4 m=texture(modulation,blend_uv);
    float mask=(fancy==3)?m.a:m.g;
    float width=(fancy==1)?m.r:softness;
    float factor=(fancy>0)?source_modulate_blend(blend_values.r,mask,width):blend_values.r;
    if(fancy>1) {
        float edge=source_layer_border(blend_values.r,mask,border_softness,border_offset,border_strength);
        a.rgb*=mix(vec3(1.0),review_linear_color(border_tint.rgb),edge);
    }
    vec3 base_color=mix(a.rgb,b.rgb,factor);
    if(has_detail)base_color=source_detail_color(base_color,review_linear_color(texture(detail1,UV*detail_scale).rgb),detail_tint_blend.rgb,detail_tint_blend.a);
    ALBEDO=review_shader_color(base_color*review_linear_color(tint.rgb));
    vec3 shading_normal=NORMAL;
    vec3 tangent_normal=vec3(0.0,0.0,1.0);
    if(has_normals) {
        // Source2Viewer PNG export has already expanded HemiOct to RGB
        // and moved roughness from B into alpha (TextureCodec.HemiOctRB).
        vec2 nuv1=texture_transforms?source_uv(uv1,normal_scale1,normal_offset1,normal_center1,normal_rotation1):uv1;
        vec2 nuv2=texture_transforms?source_uv(uv1,normal_scale2,normal_offset2,normal_center2,normal_rotation2):uv1;
        vec4 n1=texture(normal1,nuv1);
        vec4 n2=texture(normal2,nuv2);
        vec3 detail_normal=normalize(mix(n1.rgb*2.0-1.0,n2.rgb*2.0-1.0,factor));
        tangent_normal=detail_normal;
        NORMAL_MAP=detail_normal*.5+.5;
        shading_normal=normalize(TANGENT*detail_normal.x+BINORMAL*detail_normal.y+NORMAL*detail_normal.z);
        ROUGHNESS=clamp(mix(n1.a,n2.a,factor),.05,1.0);
    } else { ROUGHNESS=.85; }
    ROUGHNESS=max(ROUGHNESS,source_geometric_roughness(NORMAL));
    METALLIC=metalness;
    SPECULAR=specular_enabled?.5:0.0;
    vec3 geometric_world=normalize((INV_VIEW_MATRIX*vec4(NORMAL,0.0)).xyz);
    vec4 bounce=use_source_lightmap?source_lightmap(UV2,tangent_normal,geometric_world,surface_world.zxy/.0254):source_bounce(surface_world,normalize((INV_VIEW_MATRIX*vec4(shading_normal,0.0)).xyz));
    if(has_material_ao)bounce.rgb*=mix(texture(material_ao1,uv1).r,texture(material_ao2,uv2).r,factor);
    AO=1.0-bounce.a;AO_LIGHT_AFFECT=0.0;
    vec3 emitted=review_linear_color(ALBEDO)*(1.0-METALLIC)*bounce.rgb;
    source_specular_visibility=source_baked_specular_occlusion(UV2);
    if(specular_enabled){
        vec4 reflected=source_reflection(surface_world,normalize((INV_VIEW_MATRIX*vec4(shading_normal,0.0)).xyz),normalize((INV_VIEW_MATRIX*vec4(VIEW,0.0)).xyz),ROUGHNESS,bounce.rgb);
        emitted+=reflected.rgb*reflection_brdf(review_linear_color(ALBEDO),METALLIC,ROUGHNESS,max(0.0,dot(shading_normal,VIEW)))*source_specular_visibility;
        AO=1.0-max(bounce.a,reflected.a);
    }
    EMISSION=review_shader_color(emitted);
    source_sun_visibility=source_sun_shadow(surface_world,UV2);
}
void light(){
    vec3 diffuse;vec3 specular;
    source_direct_brdf(NORMAL,LIGHT,VIEW,ALBEDO,METALLIC,ROUGHNESS,specular_enabled,diffuse,specular);
    float visibility=LIGHT_IS_DIRECTIONAL?source_sun_visibility:1.0;
    DIFFUSE_LIGHT+=diffuse*LIGHT_COLOR*ATTENUATION*visibility;
    SPECULAR_LIGHT+=specular*LIGHT_COLOR*ATTENUATION*visibility*SPECULAR_AMOUNT*source_specular_visibility;
}
