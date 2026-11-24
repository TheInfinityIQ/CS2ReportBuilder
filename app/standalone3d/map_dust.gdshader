shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never;
#include "res://review_depth.gdshaderinc"
uniform vec4 tint : source_color = vec4(1.0);
uniform sampler2D mask1 : filter_linear_mipmap, repeat_enable;
uniform sampler2D mask2 : filter_linear_mipmap, repeat_enable;
uniform sampler2D mask3 : filter_linear_mipmap, repeat_enable;
uniform vec2 scale1=vec2(1.0);
uniform vec2 scale2=vec2(1.0);
uniform vec2 scale3=vec2(1.0);
uniform vec2 pan1=vec2(0.0);
uniform vec2 pan2=vec2(0.0);
uniform vec2 pan3=vec2(0.0);
uniform float demo_time=0.0;
uniform sampler2D scene_depth : hint_depth_texture, filter_nearest, repeat_disable;
varying vec3 world_vertex;
void vertex() { world_vertex=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz; }
void fragment() {
    float density=texture(mask1,UV*scale1+pan1*demo_time).r
        *texture(mask2,UV*scale2+pan2*demo_time).r
        *texture(mask3,UV*scale3+pan3*demo_time).r;
    float depth=texture(scene_depth,SCREEN_UV).r;
    vec4 scene=review_view_position(SCREEN_UV,depth,INV_PROJECTION_MATRIX);
    float feather=clamp((length(scene.xyz/scene.w)-distance(world_vertex,CAMERA_POSITION_WORLD))/4.1,0.0,1.0);
    ALBEDO=tint.rgb;
    ALPHA=clamp(density*feather*.22,0.0,.22);
}
