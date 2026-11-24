shader_type spatial;
render_mode unshaded,blend_mul,depth_draw_never,cull_disabled;
#include "res://source_overlay.gdshaderinc"
void fragment(){
    vec3 factor=min(overlay_modulation(UV),vec3(1.0));
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
    // LDR blending operates on encoded exposed pixels. Derive the multiplier
    // from linear-light modulation rather than darkening gamma values twice.
    vec3 background=texture(opaque_scene,SCREEN_UV).rgb;
    vec3 target=overlay_encode(overlay_decode(background)*factor);
    vec3 ratio=mix(vec3(1.0),target/max(background,vec3(.00001)),step(vec3(.00001),background));
    ALBEDO=overlay_exposed_output(ratio);
#elif CURRENT_RENDERER == RENDERER_MOBILE
    // Mobile stores HDR radiance divided by two in its UNORM target. A
    // multiplicative factor must remain neutral after that normalization.
    ALBEDO=factor*2.0;
#else
    ALBEDO=factor;
#endif
    ALPHA=1.0;
}
