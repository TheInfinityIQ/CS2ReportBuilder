shader_type spatial;
render_mode unshaded, cull_front, depth_draw_never, depth_test_disabled;
#include "res://review_depth.gdshaderinc"

uniform sampler3D occupancy : filter_linear, repeat_disable;
uniform sampler2D depth_map : hint_depth_texture, filter_nearest, repeat_disable;
uniform vec3 box_min;
uniform vec3 box_size = vec3(9.7536);
uniform float opacity = 1.0;
uniform float demo_time = 0.0;
uniform float bloom = 1.0;
uniform vec3 smoke_color=vec3(.54);
uniform sampler3D detail_noise : filter_linear,repeat_enable;
uniform bool has_detail=false;
uniform vec4 blast_a=vec4(0.0);
uniform vec4 blast_b=vec4(0.0);
uniform vec4 bullet_start[4];
uniform vec4 bullet_end[4];
varying vec3 world_vertex;

void vertex() { world_vertex = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz; }

void fragment() {
    vec3 origin = CAMERA_POSITION_WORLD;
    vec3 ray = normalize(world_vertex - origin);
    vec3 safe_ray = sign(ray + vec3(0.0000001)) * max(abs(ray), vec3(0.00001));
    vec3 t0 = (box_min - origin) / safe_ray;
    vec3 t1 = (box_min + box_size - origin) / safe_ray;
    vec3 lo = min(t0,t1), hi = max(t0,t1);
    float begin = max(max(lo.x,lo.y),max(lo.z,0.0));
    float end = min(min(hi.x,hi.y),hi.z);
    float depth = texture(depth_map, SCREEN_UV).r;
    // Sky has no finite opaque intersection (reversed-Z clear value is zero).
    // Unprojecting it produces infinity/NaN on some GPUs and destroys the cloud.
    if(depth>0.0000001){
        vec4 scene=review_view_position(SCREEN_UV,depth,INV_PROJECTION_MATRIX);
        end = min(end,length(scene.xyz));
    }
    if (end <= begin) { discard; }
    float step_size = (end - begin) / 64.0;
    float transmission = 1.0;
    vec3 scattering=vec3(0.0);
    for (int i=0;i<64;i++) {
        vec3 p = origin + ray * (begin + (float(i)+0.5)*step_size);
        vec3 uvw = (p-box_min)/box_size;
        // Demo/source XYZ -> Godot YZX. The texture retains source order.
        vec3 drift = vec3(sin(p.y*3.7+demo_time*.3),sin(p.z*2.9-demo_time*.2),sin(p.x*3.1))*0.012;
		vec3 q=(uvw+drift).zxy;
        // The viewer companion already reconstructs occupied free cells.
        // Do not dilate that filled volume again: a cell is 20 Source units,
        // and the former max-of-neighbours added an opaque half-metre shell.
        float occupied=texture(occupancy,q).r;
		// A deterministic expansion front, bounded by the recorded occupancy.
		// This is visual reconstruction, not a change to evidence/voxel data.
		float radius = mix(.12,5.2,bloom);
		float expansion = 1.0-smoothstep(radius-.30,radius+.30,length(p-(box_min+box_size*.5)));
        // Exactly zero contribution: skip detail, shading and every clearing
        // segment test, retaining all 64 integration samples in occupied cells.
        if(occupied<=.12 || expansion<=0.0){continue;}
        float detail=has_detail?texture(detail_noise,p*.025+vec3(demo_time*.001,0.0,-demo_time*.0008)).r:.5;
        float fine=has_detail?texture(detail_noise,p*.10+vec3(0.0,demo_time*.002,0.0)).r:.5;
        float billow=.15+1.35*smoothstep(.20,.80,detail)+.20*fine;
        float density = smoothstep(.12,.85,occupied)*billow*opacity*expansion;
        // Recorded HE timing/position; clearing/recovery is presentation art,
        // not a claim to reconstruct Valve's unrecorded GPU fluid state.
        if(blast_a.w>0.0){density*=smoothstep(blast_a.w*.6,blast_a.w,distance(p,blast_a.xyz));}
        if(blast_b.w>0.0){density*=smoothstep(blast_b.w*.6,blast_b.w,distance(p,blast_b.xyz));}
        for(int bullet=0;bullet<4;bullet++){
            if(bullet_start[bullet].w<=0.0){continue;}
            vec3 segment=bullet_end[bullet].xyz-bullet_start[bullet].xyz;
            float projected=clamp(dot(p-bullet_start[bullet].xyz,segment)/max(dot(segment,segment),.001),0.0,1.0);
            float distance_to_ray=distance(p,bullet_start[bullet].xyz+segment*projected);
            density*=smoothstep(bullet_start[bullet].w*.45,bullet_start[bullet].w,distance_to_ray);
        }
        float overhang=texture(occupancy,q+vec3(.0,.0,.07)).r*.65+texture(occupancy,q+vec3(.0,.0,.15)).r*.35;
        float turbulence=sin(p.x*2.3+demo_time*.35)*sin(p.y*3.7-demo_time*.21)*sin(p.z*2.9+demo_time*.17);
        vec3 lit=smoke_color*mix(.30,1.15,clamp(.68-overhang*.40+turbulence*.07+uvw.y*.25+(detail-.5)*.75,0.0,1.0));
        float attenuation=exp(-density*step_size*4.5);
        scattering+=transmission*(1.0-attenuation)*lit;
        transmission*=attenuation;
        if (transmission < .008) { break; }
    }
    ALBEDO=scattering/max(.001,1.0-transmission);
    ALPHA = 1.0-transmission;
}
