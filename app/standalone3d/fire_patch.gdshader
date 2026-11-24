shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never;
#include "res://review_depth.gdshaderinc"
uniform float demo_time = 0.0;
uniform float life_opacity = 1.0;
uniform sampler2D flames : source_color, filter_linear_mipmap, repeat_disable;
uniform sampler2DArray flame_layers : source_color, filter_linear_mipmap, repeat_disable;
uniform bool use_layers=false;
uniform sampler2D depth_map : hint_depth_texture, filter_nearest, repeat_disable;
uniform float feather_distance=.06;
uniform int frame_count=1;
uniform bool source_frames=false;
uniform vec2 sequence_ranges[8];
uniform int sequence_count=0;
varying float seed;
float noise(vec2 p) {
    vec2 cell=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
    vec4 h=fract(sin(vec4(dot(cell,vec2(127.1,311.7)),dot(cell+vec2(1,0),vec2(127.1,311.7)),dot(cell+vec2(0,1),vec2(127.1,311.7)),dot(cell+vec2(1,1),vec2(127.1,311.7))))*43758.5453);
    return mix(mix(h.x,h.y,f.x),mix(h.z,h.w,f.x),f.y);
}
void vertex() {
    seed = INSTANCE_CUSTOM.r*17.0;
    // Face the viewer while retaining each recorded patch's world location.
    vec3 up=vec3(0,1,0);
    vec3 toward=normalize(vec3(CAMERA_POSITION_WORLD.x-MODEL_MATRIX[3].x,0.0,CAMERA_POSITION_WORLD.z-MODEL_MATRIX[3].z)+vec3(.00001,0,.00001));
    MODELVIEW_MATRIX = VIEW_MATRIX * mat4(vec4(cross(up,toward),0),vec4(up,0),vec4(toward,0),MODEL_MATRIX[3]);
}
void fragment() {
    if(source_frames){
        vec2 sequence=vec2(0.0,float(frame_count));
        if(sequence_count>0){sequence=sequence_ranges[int(mod(floor(seed*7.1),float(sequence_count)))];}
        float phase=mod(demo_time*30.0+seed*3.0,max(1.0,sequence.y));
        vec2 grid=vec2(8.0,ceil(float(frame_count)/8.0));
        float first=sequence.x+floor(phase),second=sequence.x+mod(floor(phase)+1.0,max(1.0,sequence.y));
        vec2 uv=clamp(UV,vec2(.008),vec2(.992));
        vec4 a;vec4 b;
        if(use_layers){
            a=texture(flame_layers,vec3(UV,first));
            b=texture(flame_layers,vec3(UV,second));
        }else{
            a=texture(flames,(vec2(mod(first,8.0),floor(first/8.0))+uv)/grid);
            b=texture(flames,(vec2(mod(second,8.0),floor(second/8.0))+uv)/grid);
        }
        vec4 flame=mix(a,b,fract(phase));
        ALBEDO=flame.rgb;
        EMISSION=flame.rgb*.65;
        ALPHA=flame.a*.85*life_opacity;
    } else {
    float height = 1.0-UV.y;
    float turbulent=noise(vec2(UV.x*6.0+seed,height*5.0-demo_time*3.8));
    turbulent=.7*turbulent+.3*noise(vec2(UV.x*13.0+seed,height*11.0-demo_time*6.0));
    float envelope=(1.0-height)*(1.0-abs(UV.x-.5)*1.9);
    float flame=smoothstep(.22,.52,envelope+turbulent*.5-height*.25);
    ALBEDO = mix(vec3(.85,.07,.008),vec3(1.0,.64,.12),clamp((1.0-height)*turbulent*1.5,0.0,1.0));
    EMISSION = ALBEDO*.35;
    ALPHA = flame*smoothstep(0.0,.08,height)*(1.0-smoothstep(.75,1.0,height))*.72*life_opacity;
    }
    // Soft intersections only where an opaque surface actually exists.
    // Sky depth is zero with reversed Z, and must never be unprojected at infinity.
    float scene_depth=texture(depth_map,SCREEN_UV).r;
    if(scene_depth>0.0000001 && feather_distance>0.0){
        vec3 scene=review_view_position(SCREEN_UV,scene_depth,INV_PROJECTION_MATRIX).xyz;
        ALPHA*=clamp((-scene.z+VERTEX.z)/feather_distance,0.0,1.0);
    }
}
