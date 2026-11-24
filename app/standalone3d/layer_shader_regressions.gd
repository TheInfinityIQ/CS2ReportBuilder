extends RefCounted

# Numeric expectations calculated from the recovered native shader expression,
# not from the translated include. Read back real GPU output in the owned app.
static func run(viewer:Node) -> Dictionary:
	var failures:Array=[];var samples:Array=[]
	var viewport:=SubViewport.new();viewport.size=Vector2i(16,16);viewport.own_world_3d=true
	viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS;viewer.add_child(viewport)
	var environment:=WorldEnvironment.new();environment.environment=Environment.new()
	environment.environment.background_mode=Environment.BG_COLOR;environment.environment.background_color=Color.BLACK
	environment.environment.tonemap_mode=Environment.TONE_MAPPER_LINEAR;viewport.add_child(environment)
	var camera:=Camera3D.new();camera.position.z=2;camera.current=true;viewport.add_child(camera)
	var shader:=Shader.new()
	shader.code="shader_type spatial;render_mode unshaded;\n#include \"res://source_bounce.gdshaderinc\"\n#include \"res://source_layer_math.gdshaderinc\"\nuniform vec4 border=vec4(.35,.5,.2,.1);uniform int test=0;uniform vec3 detail=vec3(.5);uniform vec3 tint=vec3(1.0);uniform float amount=.2;void fragment(){vec3 result=vec3(source_layer_border(border.x,border.y,border.z,border.w,1.0));if(test==1)result=source_detail_color(vec3(.4),detail,tint,amount);ALBEDO=review_shader_color(result);}"
	var material:=ShaderMaterial.new();material.shader=shader
	var quad:=MeshInstance3D.new();quad.mesh=QuadMesh.new();quad.material_override=material;viewport.add_child(quad)
	var cases:Array=[
		{"name":"positive-border-offset","test":0,"border":Vector4(.35,.5,.2,.1),"expected":0.0},
		{"name":"negative-border-offset","test":0,"border":Vector4(.35,.5,.2,-.1),"expected":.6328125},
		{"name":"border-centre","test":0,"border":Vector4(.6,.5,.2,.1),"expected":1.0},
		{"name":"neutral-detail","test":1,"detail":Vector3.ONE*.5,"tint":Vector3.ONE,"amount":.2,"expected":.4},
		{"name":"dim-detail","test":1,"detail":Vector3.ONE*.25,"tint":Vector3.ONE,"amount":.2,"expected":.36},
		{"name":"bright-detail","test":1,"detail":Vector3.ONE*.75,"tint":Vector3.ONE,"amount":.2,"expected":.44},
		{"name":"disabled-detail","test":1,"detail":Vector3.ZERO,"tint":Vector3.ONE,"amount":0.0,"expected":.4},
		{"name":"detail-tint","test":1,"detail":Vector3.ONE*.25,"tint":Vector3.ONE*2,"amount":.2,"expected":.4}]
	for item in cases:
		material.set_shader_parameter("test",item.test)
		for key in ["border","detail","tint","amount"]:
			if item.has(key):material.set_shader_parameter(key,item[key])
		for settle in range(3):await viewer.get_tree().process_frame
		await RenderingServer.frame_post_draw
		var color:Color=viewport.get_texture().get_image().get_pixel(8,8)
		var expected:Color=Color(item.expected,item.expected,item.expected).linear_to_srgb()
		var error:float=maxf(absf(color.r-expected.r),maxf(absf(color.g-expected.g),absf(color.b-expected.b)))
		samples.append({"case":item.name,"rgb":str(color),"linear_expected":item.expected,"expected":str(expected),"error":error})
		if error>.012:failures.append(str(item.name)+": GPU differs from native expression")
	viewport.free()
	return {"ok":failures.is_empty(),"failures":failures,"samples":samples}
