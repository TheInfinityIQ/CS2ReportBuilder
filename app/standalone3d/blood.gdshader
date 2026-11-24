shader_type spatial;
render_mode unshaded,cull_disabled,depth_draw_never;
uniform float fade=1.0;
void vertex(){MODELVIEW_MATRIX=VIEW_MATRIX*mat4(INV_VIEW_MATRIX[0],INV_VIEW_MATRIX[1],INV_VIEW_MATRIX[2],MODEL_MATRIX[3]);}
void fragment(){
    vec2 p=UV*2.0-1.0;
    float pattern=sin(p.x*27.0+p.y*13.0)*sin(p.y*31.0-p.x*9.0);
    float alpha=(1.0-smoothstep(.1,1.0,length(p)))*smoothstep(-.3,.4,pattern)*fade;
    ALBEDO=vec3(.31,.018,.012);ALPHA=alpha*.8;
}
