// Recovered from the installed csgo_lightmappedgeneric Vulkan program (v72).
// The bounded shader probe records the selected variant and original bytecode.
float source_modulate_blend(float src_weight,float src_mask,float src_width) {
    return smoothstep(max(0.0,src_mask-src_width),min(1.0,src_mask+max(.0001,src_width)),src_weight);
}
float source_layer_border(float src_weight,float src_mask,float src_softness,float src_offset,float src_strength) {
    float edge=source_modulate_blend(clamp(src_weight-src_offset,0.0,1.0),src_mask,src_softness);
    return (1.0-abs(edge*2.0-1.0))*src_strength;
}
vec3 source_detail_color(vec3 src_base,vec3 src_detail,vec3 src_tint,float src_amount) {
    return src_base*mix(vec3(1.0),src_detail*src_tint*2.0,src_amount);
}
