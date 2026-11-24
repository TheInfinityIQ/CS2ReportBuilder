// Godot's inverse projection handles reversed Z; only the NDC range differs.
vec4 review_view_position(vec2 uv,float depth,mat4 inverse_projection) {
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
    vec3 ndc=vec3(uv,depth)*2.0-1.0;
#else
    vec3 ndc=vec3(uv*2.0-1.0,depth);
#endif
    vec4 p=inverse_projection*vec4(ndc,1.0);
    return p/p.w;
}
