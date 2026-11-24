shader_type spatial;
render_mode unshaded,blend_mix,cull_disabled,depth_draw_never;
#include "res://review_depth.gdshaderinc"
// Source effect-sheet opacity contract, after VRF csgo_effects.frag.slang
// (MIT; third_party/VRF_LICENSE.txt). Source world distances are bound in metres.
uniform sampler2D color_map : source_color,filter_linear_mipmap,repeat_enable,hint_default_white;
uniform sampler2D mask1 : filter_linear_mipmap,repeat_enable,hint_default_white;
uniform sampler2D mask2 : filter_linear_mipmap,repeat_enable,hint_default_white;
uniform sampler2D mask3 : filter_linear_mipmap,repeat_enable,hint_default_white;
uniform sampler2D scene_depth : hint_depth_texture,filter_nearest,repeat_disable;
uniform vec4 tint : source_color=vec4(1.0);
uniform vec2 scale1=vec2(1.0);
uniform vec2 scale2=vec2(1.0);
uniform vec2 scale3=vec2(1.0);
uniform vec2 pan1=vec2(0.0);
uniform vec2 pan2=vec2(0.0);
uniform vec2 pan3=vec2(0.0);
uniform vec2 scroll=vec2(0.0);
uniform float demo_time=0.0;
uniform float color_boost=1.0;
uniform float opacity_scale=1.0;
uniform float fade_distance=1.0;
uniform float fade_falloff=1.0;
uniform float fade_min=0.0;
uniform float fade_max=1.0;
uniform float feather_distance=1.0;
uniform float feather_falloff=1.0;
uniform float fresnel_exponent=.001;
uniform float fresnel_falloff=1.0;
uniform float fresnel_min=0.0;
uniform float fresnel_max=1.0;
uniform bool feather_enabled=false;
uniform bool flip_backface=true;
varying vec3 surface_world;
varying vec4 vertex_tint;
void vertex(){surface_world=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz;vertex_tint=COLOR;}
void fragment(){
    vec2 uv=UV+scroll*demo_time;
    vec4 color=texture(color_map,uv)*tint;
    float masks=texture(mask1,uv*scale1+pan1*demo_time).r*texture(mask2,uv*scale2+pan2*demo_time).r*texture(mask3,uv*scale3+pan3*demo_time).r;
    // Godot already flips NORMAL for cull_disabled. Undo that only when the
    // authored Source flag explicitly keeps back-face normals unchanged.
    vec3 normal=(!FRONT_FACING && !flip_backface)?-NORMAL:NORMAL;
    float facing=clamp(pow(clamp(dot(normalize(VIEW),normalize(normal)),.0001,1.0),fresnel_exponent)*fresnel_falloff,0.0,1.0);
    float fresnel=mix(fresnel_min,fresnel_max,facing);
    float distance_to_eye=distance(surface_world,CAMERA_POSITION_WORLD);
    float fade=pow(max(0.0,mix(fade_min,fade_max,clamp(distance_to_eye/max(.00001,fade_distance),0.0,1.0))),fade_falloff);
    float feather=1.0;
    if(feather_enabled){
        float depth=texture(scene_depth,SCREEN_UV).r;
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
        bool background=depth>=.999999;
#else
        bool background=depth<=.000001;
#endif
        if(!background){
            vec3 behind=review_view_position(SCREEN_UV,depth,INV_PROJECTION_MATRIX).xyz;
            feather=pow(clamp(distance(behind,VERTEX)/max(.00001,feather_distance),.0001,1.0),feather_falloff);
        }
    }
    ALBEDO=color.rgb*vertex_tint.rgb*color_boost;
    ALPHA=clamp(color.a*vertex_tint.a*opacity_scale*masks*fresnel*fade*feather,0.0,1.0);
}
