shader_type canvas_item;
// Review-only cue: retain the unobscured scene rather than simulating blindness.
void fragment() {
    float halo=1.0-smoothstep(.10,.72,length((UV-.5)*vec2(1.0,.8)));
    COLOR.rgb=vec3(.98,.98,1.0);
    COLOR.a*=.55+.45*halo;
}
