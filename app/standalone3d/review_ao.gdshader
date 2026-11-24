shader_type spatial;
render_mode unshaded,blend_mul,depth_draw_never,depth_test_disabled,cull_disabled,fog_disabled;
#include "res://review_depth.gdshaderinc"
uniform sampler2D scene_depth : hint_depth_texture,filter_nearest,repeat_disable;
uniform float radius=.55;
uniform float strength=.6;
void vertex(){POSITION=vec4(VERTEX.xy,1.0,1.0);}
void fragment(){
    float depth=texture(scene_depth,SCREEN_UV).r;
    vec3 p=review_view_position(SCREEN_UV,depth,INV_PROJECTION_MATRIX).xyz;
    vec3 normal=normalize(cross(dFdx(p),dFdy(p)));
    normal*=sign(dot(normal,-p));
    float occlusion=0.0;
    vec2 projection_scale=vec2(PROJECTION_MATRIX[0][0],PROJECTION_MATRIX[1][1]);
    vec2 screen_radius=projection_scale*radius/max(.1,-p.z)*.5;
    for(int i=0;i<12;i++){
        float angle=float(i)*2.3999632;
        float distance_fraction=sqrt((float(i)+.5)/12.0);
        vec2 uv=clamp(SCREEN_UV+vec2(cos(angle),sin(angle))*screen_radius*distance_fraction,vec2(.001),vec2(.999));
        vec3 neighbour=review_view_position(uv,texture(scene_depth,uv).r,INV_PROJECTION_MATRIX).xyz;
        vec3 delta=neighbour-p;
        float distance_to_point=length(delta);
        float horizon=max(0.0,dot(normal,delta/max(.0001,distance_to_point))-.08);
        occlusion+=horizon*(1.0-smoothstep(radius*.3,radius,distance_to_point));
    }
    float near_fade=smoothstep(.08,.25,-p.z)*(1.0-smoothstep(60.0,90.0,-p.z));
    ALBEDO=vec3(clamp(1.0-occlusion/12.0*strength*3.0*near_fade,.5,1.0));
    ALPHA=1.0;
}
