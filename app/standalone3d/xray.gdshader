shader_type spatial;
render_mode unshaded,cull_front,depth_draw_never,depth_test_disabled;
uniform vec4 outline_color:source_color=vec4(.3,.7,1.,.75);
void vertex(){VERTEX+=NORMAL*.012;}
void fragment(){ALBEDO=outline_color.rgb;ALPHA=outline_color.a;}
