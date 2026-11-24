shader_type spatial;
render_mode unshaded,blend_add,depth_draw_never,cull_disabled;
#include "res://source_overlay.gdshaderinc"
// A normalized color buffer clamps multiplicative factors above one. Preserve
// bright caustics in an additive companion pass instead of flattening them to
// white multipliers. Both passes share the same authored timing and opacity.
void fragment(){
    vec3 factor=max(overlay_modulation(UV),vec3(1.0));
    vec3 background=texture(opaque_scene,SCREEN_UV).rgb;
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
    vec3 target=overlay_encode(overlay_decode(background)*factor);
    ALBEDO=overlay_exposed_output(max(vec3(0.0),target-background));
#else
    ALBEDO=background*(factor-1.0);
#endif
    ALPHA=1.0;
}
