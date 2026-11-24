shader_type sky;
render_mode disable_fog;
uniform sampler2DArray sky_faces : filter_linear,repeat_disable;
uniform float intensity=1.0;
uniform vec3 tint=vec3(1.0);
uniform mat3 source_rotation=mat3(1.0);
uniform float resolution=512.0;
void sky() {
	// Original Source cube face order, as in the existing reflection sampler.
    vec3 direction=normalize(source_rotation*EYEDIR.zxy);
	vec3 axis=abs(direction);vec2 uv;float face;float major;
	if(axis.x>=axis.y && axis.x>=axis.z) {
		major=axis.x;
		if(direction.x>=0.0){face=0.0;uv=vec2(-direction.z,-direction.y);}
		else{face=1.0;uv=vec2(direction.z,-direction.y);}
	}else if(axis.y>=axis.z){
		major=axis.y;
		if(direction.y>=0.0){face=2.0;uv=vec2(direction.x,direction.z);}
		else{face=3.0;uv=vec2(direction.x,-direction.z);}
	}else{
		major=axis.z;
		if(direction.z>=0.0){face=4.0;uv=vec2(direction.x,-direction.y);}
		else{face=5.0;uv=vec2(-direction.x,-direction.y);}
	}
	uv=clamp(uv/max(major,.00001)*.5+.5,vec2(.5/resolution),vec2(1.0-.5/resolution));
	vec3 radiance=texture(sky_faces,vec3(uv,face)).rgb*intensity*tint;
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
    // GLES3 sky.glsl linearizes custom COLOR before applying exposure. The
    // original BC6H sample is already linear, just like our probe irradiance.
    COLOR=mix(radiance*12.92,1.055*pow(max(radiance,vec3(0.0)),vec3(1.0/2.4))-.055,step(vec3(.0031308),radiance));
#else
    COLOR=radiance;
#endif
}
