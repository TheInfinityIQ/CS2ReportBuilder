shader_type canvas_item;
uniform float damage=0.0;
void fragment(){
    float edge=smoothstep(.15,.7,length((UV-.5)*vec2(1.0,.85)));
    COLOR=vec4(.48,.012,.006,damage*edge*.22);
}
