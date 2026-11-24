// Authored Source ambient-cube probe evaluation. Sampling layout follows
// ValveResourceFormat lighting_lpv.slang (MIT; third_party/VRF_LICENSE.txt).
#ifndef SOURCE_LIGHTMAP_ONLY
uniform sampler2DArray probe_atlas : filter_linear, repeat_disable;
uniform int probe_count=0;
uniform mat4 probe_transforms[8];
uniform vec3 probe_sizes[8];
uniform vec3 probe_offsets[8];
uniform vec3 probe_fades[8];
uniform vec3 probe_dimensions=vec3(1.0);
#endif
uniform bool probe_override=false;
uniform vec3 probe_position=vec3(0.0);
uniform mat3 probe_normal_basis=mat3(1.0);
uniform bool use_source_lightmap=false;
uniform sampler2D baked_irradiance : filter_linear,repeat_disable;
uniform sampler2D baked_direction : filter_linear,repeat_disable;
global uniform float source_bounce_strength;

// Compatibility converts user ALBEDO/EMISSION from sRGB after fragment().
// Source HDR irradiance is already linear: do the light multiplication in
// linear space and encode only the result handed back to that renderer.
vec3 review_linear_color(vec3 color) {
    if(!OUTPUT_IS_SRGB){return color;}
    return mix(color/12.92,pow(max((color+.055)/1.055,vec3(0.0)),vec3(2.4)),step(vec3(.04045),color));
}
vec3 review_shader_color(vec3 linear_color) {
    if(!OUTPUT_IS_SRGB){return linear_color;}
    return mix(linear_color*12.92,1.055*pow(max(linear_color,vec3(0.0)),vec3(1.0/2.4))-.055,step(vec3(.0031308),linear_color));
}

vec3 source_lightmap_direction(vec3 encoded,float curvature) {
    const float min_z=.0872;
    float max_xy=sqrt(1.0-min_z*min_z);
    vec2 xy=encoded.xy*2.0-1.0;
    xy*=max_xy/max(max_xy,length(xy));
    float z=sqrt(max(0.0,1.0-dot(xy,xy)));
    float flatness=(1.0-smoothstep(.01,.1,curvature))*.8;
    float z_scale=mix(1.0,mix(.1,2.0,clamp((1.0-z)*1.5,0.0,1.0)),flatness);
    return normalize(vec3(xy,z*z_scale));
}

vec4 source_lightmap(vec2 uv,vec3 tangent_normal,vec3 geometric_normal,vec3 source_position) {
    if(source_bounce_strength<=0.0){return vec4(0.0);}
    vec3 irradiance=texture(baked_irradiance,uv).rgb;
    vec3 direction=texture(baked_direction,uv).rgb;
    float curvature=length(fwidth(geometric_normal))/max(.000001,length(fwidth(source_position)));
    vec3 incoming=source_lightmap_direction(direction,curvature);
    vec3 isotropic=irradiance*clamp(direction.z,0.0,1.0);
    vec3 diffuse=max(0.0,dot(incoming,tangent_normal))*(irradiance-isotropic)/max(.05,incoming.z)+isotropic;
    return vec4(max(vec3(0.0),diffuse)*source_bounce_strength,1.0);
}

// The directional lightmap alpha carries authored specular occlusion, separate
// from its RGB directionality. Do not light reflective recesses as open sky.
float source_baked_specular_occlusion(vec2 uv) {
    return use_source_lightmap?clamp(texture(baked_direction,uv).a,0.0,1.0):1.0;
}

#ifndef SOURCE_LIGHTMAP_ONLY
vec3 probe_sample(vec3 coord) {
    float layer=coord.z*probe_dimensions.z*6.0-.5;
    float low=floor(layer);
    return mix(textureLod(probe_atlas,vec3(coord.xy,low),0.0).rgb,
        textureLod(probe_atlas,vec3(coord.xy,low+1.0),0.0).rgb,fract(layer));
}

vec4 source_bounce(vec3 world_position,vec3 world_normal) {
    if(source_bounce_strength<=0.0){return vec4(0.0);}
    vec3 position=probe_override?probe_position:world_position.zxy/.0254;
    vec3 normal=normalize((probe_override?probe_normal_basis*world_normal:world_normal).zxy);
    vec3 radiance=vec3(0.0);float coverage=0.0;
    vec3 axis_weights=normal*normal;
    for(int i=0;i<8;i++) {
        if(i>=probe_count || coverage>.995) { break; }
        vec3 local=(probe_transforms[i]*vec4(position,1.0)).xyz;
        if(any(lessThan(local,vec3(0.0))) || any(greaterThan(local,vec3(1.0)))) { continue; }
        vec3 feather=min(local,1.0-local)/max(probe_fades[i],vec3(.00001));
        float weight=smoothstep(0.0,1.0,min(feather.x,min(feather.y,feather.z)))*(1.0-coverage);
        // Half-texel inset prevents filtering into neighbouring atlas volumes.
        vec3 coord=clamp(local*probe_sizes[i],vec3(.5),probe_sizes[i]-.5)+probe_offsets[i];
        coord/=probe_dimensions;
        vec3 value=vec3(0.0);
        for(int axis=0;axis<3;axis++) {
            float face=float(axis)+(normal[axis]<0.0?3.0:0.0);
            value+=probe_sample(vec3(coord.xy,(coord.z+face)/6.0))*axis_weights[axis];
        }
        radiance+=value*weight;coverage+=weight;
    }
    return vec4(radiance*source_bounce_strength,coverage);
}
#else
vec4 source_bounce(vec3 world_position,vec3 world_normal){return vec4(0.0);}
#endif
