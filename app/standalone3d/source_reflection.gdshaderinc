// Original, prefiltered Source cubemaps. Vulkan uses a real cubemap array for
// cross-face filtering; Compatibility retains a 2D-array fallback. The GPU
// witnesses require exact adjacent-mip interpolation, made explicit below.
// Face order: +X,-X,+Y,-Y,+Z,-Z. Box projection stays in Source probe space.
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
uniform sampler2DArray reflection_atlas : filter_linear_mipmap,repeat_disable;
#else
uniform samplerCubeArray reflection_atlas : filter_linear_mipmap,repeat_disable;
#endif
uniform int reflection_count=0;
uniform mat4 reflection_transforms[4];
uniform vec3 reflection_extents[4];
uniform vec3 reflection_centers[4];
uniform vec3 reflection_fades[4];
uniform int reflection_indices[4];
uniform float reflection_max_lod=0.0;
uniform float reflection_resolution=256.0;
uniform vec4 reflection_normalization_sh[4];

vec3 reflection_lookup(vec3 direction,int cube,float lod) {
#if CURRENT_RENDERER != RENDERER_COMPATIBILITY
    float level=clamp(lod,0.0,reflection_max_lod);float low=floor(level);float high=min(low+1.0,reflection_max_lod);
    return mix(textureLod(reflection_atlas,vec4(direction,float(cube)),low).rgb,
        textureLod(reflection_atlas,vec4(direction,float(cube)),high).rgb,fract(level));
#else
    vec3 axis=abs(direction);vec2 uv;float face;float major;
    if(axis.x>=axis.y && axis.x>=axis.z) {
        major=axis.x;
        if(direction.x>=0.0){face=0.0;uv=vec2(-direction.z,-direction.y);}
        else {face=1.0;uv=vec2(direction.z,-direction.y);}
    } else if(axis.y>=axis.z) {
        major=axis.y;
        if(direction.y>=0.0){face=2.0;uv=vec2(direction.x,direction.z);}
        else {face=3.0;uv=vec2(direction.x,-direction.z);}
    } else {
        major=axis.z;
        if(direction.z>=0.0){face=4.0;uv=vec2(direction.x,-direction.y);}
        else {face=5.0;uv=vec2(-direction.x,-direction.y);}
    }
    uv=uv/max(major,.00001)*.5+.5;
    float edge=.5*exp2(lod)/reflection_resolution;
    uv=clamp(uv,vec2(edge),vec2(1.0-edge));
    float level=clamp(lod,0.0,reflection_max_lod);float low=floor(level);float high=min(low+1.0,reflection_max_lod);
    return mix(textureLod(reflection_atlas,vec3(uv,float(cube*6)+face),low).rgb,
        textureLod(reflection_atlas,vec3(uv,float(cube*6)+face),high).rgb,fract(level));
#endif
}

float source_env_normalization(vec4 coefficients,vec3 normal,float roughness,vec3 irradiance) {
    float baked_luma=dot(vec4(normal,1.0),coefficients);
    if(baked_luma<=0.0){return 1.0;}
    return min(dot(irradiance,vec3(.2125,.7154,.0721))/baked_luma,max(1.0,roughness*2.0+1.0));
}

vec4 source_reflection(vec3 world_position,vec3 normal,vec3 to_camera,float roughness,vec3 irradiance) {
    if(source_bounce_strength<=0.0){return vec4(0.0);}
    vec3 position=probe_override?probe_position:world_position.zxy/.0254;
    vec3 n=normalize((probe_override?probe_normal_basis*normal:normal).zxy);
    vec3 v=normalize((probe_override?probe_normal_basis*to_camera:to_camera).zxy);
    float r=clamp(roughness,0.0,1.0);
    float r2=r*r;float smoothness=1.0-r2;
    float dominant=smoothness*(sqrt(smoothness)+r2);
    vec3 ray=normalize(mix(n,reflect(-v,n),dominant));
    vec3 result=vec3(0.0);float coverage=0.0;vec4 normalization=vec4(0.0);
    for(int i=0;i<4;i++) {
        if(i>=reflection_count || coverage>.995){break;}
        vec3 local=(reflection_transforms[i]*vec4(position,1.0)).xyz;
        if(any(lessThan(local,vec3(0.0))) || any(greaterThan(local,vec3(1.0)))){continue;}
        vec3 feather=min(local,1.0-local)/max(reflection_fades[i],vec3(.00001));
        float weight=smoothstep(0.0,1.0,min(feather.x,min(feather.y,feather.z)))*(1.0-coverage);
        vec3 local_ray=mat3(reflection_transforms[i])*ray;
        vec3 safe_ray=mix(vec3(.000001),local_ray,step(vec3(.000001),abs(local_ray)));
        vec3 exit_times=(step(vec3(0.0),safe_ray)-local)/safe_ray;
        float distance_to_box=min(exit_times.x,min(exit_times.y,exit_times.z));
        vec3 projected=(local+local_ray*max(0.0,distance_to_box)-reflection_centers[i])*reflection_extents[i];
        result+=reflection_lookup(normalize(projected),reflection_indices[i],sqrt(r)*reflection_max_lod)*weight;
        normalization+=reflection_normalization_sh[i]*weight;
        coverage+=weight;
    }
    float scale=source_env_normalization(normalization/max(coverage,.0001),n,r,irradiance);
    return vec4(result*source_bounce_strength*scale,coverage);
}

vec4 source_reflection(vec3 world_position,vec3 normal,vec3 to_camera,float roughness) {
    return source_reflection(world_position,normal,to_camera,roughness,vec3(1.0));
}

vec3 reflection_brdf(vec3 albedo,float metalness,float roughness,float ndotv) {
    vec3 f0=mix(vec3(.04),albedo,metalness);
    return (f0+(1.0-f0)*pow(1.0-clamp(ndotv,0.0,1.0),5.0))*(1.0-.3*roughness);
}
