// Source modulate-x2 overlays; VRF reference (MIT, third_party/VRF_LICENSE.txt).
uniform sampler2D color_texture : source_color,filter_linear_mipmap,repeat_enable;
uniform float demo_time=0.0;
uniform vec2 animation_grid=vec2(1.0);
uniform float frame_count=1.0;
uniform float frame_seconds=.05;
uniform float opacity=1.0;
global uniform float review_modulation_exposure;
uniform sampler2D opaque_scene : hint_screen_texture,filter_linear,repeat_disable;
varying float vertex_opacity;
void vertex(){vertex_opacity=COLOR.a;}

vec3 overlay_modulation(vec2 surface_uv){
    float frame=mod(floor(demo_time/max(.001,frame_seconds)),frame_count);
    vec2 cell=vec2(mod(frame,animation_grid.x),floor(frame/animation_grid.x));
    vec2 uv=(cell+clamp(surface_uv,vec2(.001),vec2(.999)))/animation_grid;
    vec4 sample_color=texture(color_texture,uv);
    vec3 encoded=sample_color.rgb;
    if(!OUTPUT_IS_SRGB){
        encoded=mix(encoded*12.92,1.055*pow(max(encoded,vec3(0.0)),vec3(1.0/2.4))-.055,step(vec3(.0031308),encoded));
    }
    return mix(vec3(1.0),encoded*2.0,clamp(vertex_opacity*opacity*sample_color.a,0.0,1.0));
}
vec3 overlay_decode(vec3 value){return mix(value/12.92,pow(max((value+.055)/1.055,vec3(0.0)),vec3(2.4)),step(vec3(.04045),value));}
vec3 overlay_encode(vec3 value){return mix(value*12.92,1.055*pow(max(value,vec3(0.0)),vec3(1.0/2.4))-.055,step(vec3(.0031308),value));}
vec3 overlay_exposed_output(vec3 encoded){return overlay_encode(overlay_decode(encoded)*review_modulation_exposure);}
