extends RefCounted

static func run(viewer:Node) -> Dictionary:
	var result:Dictionary={"ok":true,"failures":[],"samples":[]}
	var viewport:=SubViewport.new();viewport.size=Vector2i(32,32);viewport.own_world_3d=true;viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS;viewer.add_child(viewport)
	var world:=Node3D.new();viewport.add_child(world)
	var camera:=Camera3D.new();camera.position.z=2;camera.current=true;world.add_child(camera)
	var environment:=WorldEnvironment.new();environment.environment=Environment.new();environment.environment.background_mode=Environment.BG_COLOR;environment.environment.background_color=Color.BLACK;environment.environment.tonemap_mode=Environment.TONE_MAPPER_LINEAR;world.add_child(environment)
	var effects=preload("res://source_effects.gd").new();var original:=StandardMaterial3D.new()
	var quad:=QuadMesh.new();var arrays:Array=quad.get_mesh_arrays();var colors:=PackedColorArray()
	for i in range(arrays[Mesh.ARRAY_VERTEX].size()):colors.append(Color.WHITE)
	arrays[Mesh.ARRAY_COLOR]=colors
	var geometry:=ArrayMesh.new();geometry.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
	var mesh:=MeshInstance3D.new();mesh.mesh=geometry;world.add_child(mesh)
	for additive in [false,true]:
		for opacity in [0.0,.25,1.0]:
			var definition:Dictionary={"IntParams":{"F_ADDITIVE_BLEND":1 if additive else 0,"F_RENDER_BACKFACES":1},"FloatParams":{"g_flOpacityScale":opacity,"g_flFresnelExponent":0}}
			mesh.material_override=effects.make_material(original,definition)
			await sample(viewer,viewport,result,("add" if additive else "mix")+"-"+str(opacity),opacity)
	var material:ShaderMaterial=mesh.material_override
	material.set_shader_parameter("fade_distance",4.0)
	await sample(viewer,viewport,result,"source-distance-fade",.5)
	material.set_shader_parameter("fade_distance",1.0);material.set_shader_parameter("feather_enabled",true);material.set_shader_parameter("feather_distance",.5)
	var wall:=MeshInstance3D.new();wall.mesh=QuadMesh.new();wall.position.z=-.25
	var black:=StandardMaterial3D.new();black.shading_mode=BaseMaterial3D.SHADING_MODE_UNSHADED;black.albedo_color=Color.BLACK;wall.material_override=black;world.add_child(wall)
	await sample(viewer,viewport,result,"source-depth-feather",.5)
	wall.free();material.set_shader_parameter("feather_enabled",false)
	camera.projection=Camera3D.PROJECTION_ORTHOGONAL;mesh.rotation.y=PI/3
	material.set_shader_parameter("fresnel_exponent",2.0)
	await sample(viewer,viewport,result,"source-fresnel-opacity",.25)
	mesh.rotation.y=PI*2/3
	await sample(viewer,viewport,result,"source-backface-opacity",.25)
	material.set_shader_parameter("flip_backface",false)
	await sample(viewer,viewport,result,"source-unflipped-backface-opacity",0.0)
	material.set_shader_parameter("flip_backface",true)
	mesh.material_override=effects.make_material(original,{"IntParams":{"F_ADDITIVE_BLEND":1},"FloatParams":{"g_flFresnelExponent":0}})
	await sample(viewer,viewport,result,"authored-backface-culling",0.0)
	mesh.material_override=material
	camera.projection=Camera3D.PROJECTION_PERSPECTIVE;mesh.rotation.y=0;material.set_shader_parameter("fresnel_exponent",0.0)
	var half_mask:=Image.create(4,4,false,Image.FORMAT_R8);half_mask.fill(Color(.5,.5,.5))
	var mask:=ImageTexture.create_from_image(half_mask)
	for i in range(1,4):material.set_shader_parameter("mask"+str(i),mask)
	await sample(viewer,viewport,result,"three-source-mask-product",.125)
	colors.fill(Color(1,1,1,0));arrays[Mesh.ARRAY_COLOR]=colors
	var transparent:=ArrayMesh.new();transparent.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays);mesh.mesh=transparent
	await sample(viewer,viewport,result,"authored-zero-vertex-alpha",0.0)
	viewport.free();result.ok=result.failures.is_empty();return result

static func sample(viewer:Node,viewport:SubViewport,result:Dictionary,label:String,linear:float) -> void:
	for settle in range(3):await viewer.get_tree().process_frame
	await RenderingServer.frame_post_draw
	var measured:Color=viewport.get_texture().get_image().get_pixel(16,16);var expected:Color=Color(linear,linear,linear).linear_to_srgb()
	var error:float=maxf(absf(measured.r-expected.r),maxf(absf(measured.g-expected.g),absf(measured.b-expected.b)))
	result.samples.append({"case":label,"measured":measured.r,"expected":expected.r,"max_error":error})
	if error>.025:result.failures.append(label+": effect output differs from authored opacity "+str(measured)+" expected "+str(expected))
