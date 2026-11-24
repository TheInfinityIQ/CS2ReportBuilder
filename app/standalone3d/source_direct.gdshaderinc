uniform bool source_direct_enabled=false;
uniform sampler2D source_baked_shadows : filter_linear,repeat_disable;
uniform sampler2DArray source_probe_shadows : filter_linear,repeat_disable;
uniform vec4 source_sun_channels=vec4(0.0);
varying float source_sun_visibility;
varying float source_specular_visibility;

// Source geometric roughness suppresses subpixel specular sparkle, without a
// screen-space blur or any changes to the material's authored texture pixels.
float source_geometric_roughness(vec3 normal) {
    vec3 dx=dFdx(normal);vec3 dy=dFdy(normal);
    return pow(clamp(max(dot(dx,dx),dot(dy,dy)),0.0,1.0),1.0/3.0);
}

float source_sun_shadow(vec3 world_position,vec2 lightmap_uv) {
    if(!source_direct_enabled){return 1.0;}
    if(use_source_lightmap){return clamp(1.0-dot(texture(source_baked_shadows,lightmap_uv),source_sun_channels),0.0,1.0);}
#ifdef SOURCE_LIGHTMAP_ONLY
    return 1.0;
#else
    vec3 position=probe_override?probe_position:world_position.zxy/.0254;
    vec4 shadows=vec4(0.0);float coverage=0.0;
    for(int i=0;i<8;i++) {
        if(i>=probe_count || coverage>.995){break;}
        vec3 local=(probe_transforms[i]*vec4(position,1.0)).xyz;
        if(any(lessThan(local,vec3(0.0))) || any(greaterThan(local,vec3(1.0)))){continue;}
        vec3 feather=min(local,1.0-local)/max(probe_fades[i],vec3(.00001));
        float weight=smoothstep(0.0,1.0,min(feather.x,min(feather.y,feather.z)))*(1.0-coverage);
        vec3 coord=(clamp(local*probe_sizes[i],vec3(.5),probe_sizes[i]-.5)+probe_offsets[i])/probe_dimensions;
        float slice=coord.z*probe_dimensions.z-.5;
        vec4 value=mix(textureLod(source_probe_shadows,vec3(coord.xy,floor(slice)),0.0),textureLod(source_probe_shadows,vec3(coord.xy,floor(slice)+1.0),0.0),fract(slice));
        shadows+=value*weight;coverage+=weight;
    }
    return clamp(1.0-dot(shadows,source_sun_channels),0.0,1.0);
#endif
}

// Source Lambert diffuse and GGX/Schlick-Smith specular. Godot multiplies its
// nonphysical light energy by PI, so each output compensates that light-color
// convention; the GGX distribution already contains its own physical 1/PI.
// Adapted from VRF common/pbr.slang, MIT (third_party/VRF_LICENSE.txt).
void source_direct_brdf(vec3 n,vec3 l,vec3 v,vec3 albedo,float metal,float rough,bool specular_allowed,out vec3 diffuse,out vec3 specular) {
    float nl=clamp(dot(n,l),0.0,1.0);float nv=clamp(dot(n,v),0.0,1.0);
    vec3 h=normalize(l+v);float nh=clamp(dot(n,h),0.0,1.0);float vh=clamp(dot(l,h),0.0,1.0);
    diffuse=vec3(nl/PI);specular=vec3(0.0);
    if(specular_allowed && nl>0.0){
        float a=max(.0001,rough*rough);
        float k=min(a/max(.00000001,1.0-nh*nh+(nh*a)*(nh*a)),453.5);
        float distribution=k*k/PI;
        float vis_rough=(rough+1.0)*(rough+1.0)/8.0;
        float visibility=1.0/(4.0*max(.0001,(nl*(1.0-vis_rough)+vis_rough)*(nv*(1.0-vis_rough)+vis_rough)));
        vec3 f0=mix(vec3(.04),albedo,metal);
        vec3 fresnel=f0+(1.0-f0)*pow(1.0-vh,5.0);
        specular=fresnel*distribution*visibility*nl/PI;
    }
}
