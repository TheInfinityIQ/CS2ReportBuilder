shader_type spatial;
#include "res://source_bounce.gdshaderinc"
#include "res://source_reflection.gdshaderinc"
render_mode unshaded, cull_disabled, depth_draw_never;
#include "res://review_depth.gdshaderinc"
uniform sampler2D waves : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D scene_color : hint_screen_texture, filter_linear, repeat_disable;
uniform sampler2D scene_depth : hint_depth_texture, filter_nearest, repeat_disable;
uniform vec4 fog_color : source_color = vec4(.3,.4,.3,1.0);
uniform vec4 decay_color : source_color = vec4(.4,.7,.7,1.0);
uniform float demo_time=0.0;
uniform float wave_speed=.8;
uniform float wave_scale=.4;
uniform float depth_scale=2.5;
uniform vec4 reflection_color : source_color = vec4(.48,.60,.68,1.0);
varying vec3 world_vertex;
void vertex() { world_vertex=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz; }
void fragment() {
    vec2 uv=world_vertex.xz/max(.1,wave_scale);
    vec2 movement=vec2(demo_time*.027,-demo_time*.019)*wave_speed;
    vec4 a=texture(waves,uv+movement);
    vec4 b=texture(waves,uv*.73-movement*.8);
    vec2 slope=((a.rg+b.rg)-1.0)*.20;
    vec3 normal=normalize(vec3(slope.x,slope.y,1.0));
    float depth=texture(scene_depth,SCREEN_UV).r;
    vec4 scene=review_view_position(SCREEN_UV,depth,INV_PROJECTION_MATRIX);
    float thickness=max(0.0,length(scene.xyz/scene.w)-distance(world_vertex,CAMERA_POSITION_WORLD));
    float transmission=exp(-thickness/max(.1,depth_scale));
    vec2 refracted_uv=clamp(SCREEN_UV+slope*.014,vec2(.001),vec2(.999));
    vec3 displaced=review_view_position(refracted_uv,texture(scene_depth,refracted_uv).r,INV_PROJECTION_MATRIX).xyz;
    // Do not refract a foreground player/ledge across the water boundary.
    if(-displaced.z < -VERTEX.z) { refracted_uv=SCREEN_UV; }
    vec3 refracted=texture(scene_color,refracted_uv).rgb;
    vec3 surface_normal=normalize(TANGENT*normal.x+BINORMAL*normal.y+NORMAL*normal.z);
    float fresnel=.02+.98*pow(1.0-clamp(dot(surface_normal,normalize(VIEW)),0.0,1.0),5.0);
    // The scene colour is already lit: applying diffuse lighting to it again
    // made the canal look like opaque paint. Reflection is an explicit sky
    // approximation until revision-bound source probes are supported.
    vec3 transmitted=mix(review_linear_color(fog_color.rgb),review_linear_color(refracted)*mix(vec3(1.0),review_linear_color(decay_color.rgb),.3),transmission);
    vec4 reflection=source_reflection(world_vertex,normalize((INV_VIEW_MATRIX*vec4(surface_normal,0.0)).xyz),normalize((INV_VIEW_MATRIX*vec4(VIEW,0.0)).xyz),.12);
    vec3 reflected=mix(review_linear_color(reflection_color.rgb),reflection.rgb/max(.0001,reflection.a),reflection.a);
    ALBEDO=review_shader_color(mix(transmitted,reflected,fresnel*.8));
    ALPHA=.98;
}
