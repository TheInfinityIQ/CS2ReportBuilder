shader_type canvas_item;
render_mode unshaded;
// Authored Source 2 rational tone curve + gamma-domain color LUT.
// Reference: VRF post_processing.frag.slang (MIT; third_party/VRF_LICENSE.txt).
uniform sampler2D scene : hint_screen_texture,filter_linear,repeat_disable;
uniform sampler3D grading : filter_linear,repeat_disable;
uniform bool has_grading=false;
uniform float dimension=32.0;
uniform float exposure=1.0;
uniform bool anti_alias=true;
uniform float bias=1.0;
uniform float shoulder=.15;
uniform float linear_strength=.5;
uniform float linear_angle=.1;
uniform float toe=.2;
uniform float toe_num=.02;
uniform float toe_denom=.3;
uniform float white_point=4.0;
vec3 decode(vec3 x){return mix(x/12.92,pow((x+.055)/1.055,vec3(2.4)),step(vec3(.04045),x));}
vec3 encode(vec3 x){return mix(x*12.92,1.055*pow(max(x,vec3(0.0)),vec3(1.0/2.4))-.055,step(vec3(.0031308),x));}
vec3 curve(vec3 x){return (x*(shoulder*x+linear_strength*linear_angle)+toe_num*toe)/(x*(shoulder*x+linear_strength)+toe_denom*toe)-toe_num/toe_denom;}
vec3 antialias(vec2 uv){
    vec3 center=texture(scene,uv).rgb;
    if(!anti_alias){return center;}
    vec2 pixel=1.0/vec2(textureSize(scene,0));
    vec3 nw=texture(scene,uv+vec2(-1.0,-1.0)*pixel).rgb;
    vec3 ne=texture(scene,uv+vec2(1.0,-1.0)*pixel).rgb;
    vec3 sw=texture(scene,uv+vec2(-1.0,1.0)*pixel).rgb;
    vec3 se=texture(scene,uv+vec2(1.0,1.0)*pixel).rgb;
    vec3 weights=vec3(.299,.587,.114);
    float c=dot(center,weights),a=dot(nw,weights),b=dot(ne,weights),d=dot(sw,weights),e=dot(se,weights);
    float lo=min(c,min(min(a,b),min(d,e))),hi=max(c,max(max(a,b),max(d,e)));
    if(hi-lo<max(.0312,hi*.125)){return center;}
    vec2 direction=vec2(-((a+b)-(d+e)),(a+d)-(b+e));
    float reduce=max((a+b+d+e)*.03125,.0078125);
    direction=clamp(direction/(min(abs(direction.x),abs(direction.y))+reduce),vec2(-8.0),vec2(8.0))*pixel;
    vec3 first=.5*(texture(scene,uv+direction*(-1.0/6.0)).rgb+texture(scene,uv+direction*(1.0/6.0)).rgb);
    vec3 second=first*.5+.25*(texture(scene,uv-direction*.5).rgb+texture(scene,uv+direction*.5).rgb);
    float value=dot(second,weights);return value<lo || value>hi?first:second;
}
void fragment(){
    // The 3D environment uses a linear quarter-exposure intermediate. Keeping
    // that range below SDR clipping preserves a fourfold radiance range
    // for this curve without touching game/video/monitor settings.
    vec3 radiance=decode(antialias(SCREEN_UV))*4.0;
    float scale=exposure;
    // Several stock maps author negative-valued near-linear rational curves.
    // Their white normalization is negative as well; replacing it with a
    // positive epsilon destroys the ratio and turns the whole map black.
    vec3 white=curve(vec3(white_point));
    vec3 normalization=mix(vec3(.000001),white,step(vec3(.000001),abs(white)));
    vec3 color=curve(min(radiance*scale*bias*2.8,vec3(white_point)))/normalization;
    color=encode(max(color,vec3(0.0)));
    if(has_grading){color=texture(grading,clamp(color,vec3(0.0),vec3(1.0))*((dimension-1.0)/dimension)+vec3(.5/dimension)).rgb;}
    COLOR=vec4(color,1.0);
}
