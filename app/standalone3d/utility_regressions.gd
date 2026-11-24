extends RefCounted

static func image(viewer:Node,viewport:SubViewport) -> Image:
	for settle in range(3):await viewer.get_tree().process_frame
	await RenderingServer.frame_post_draw
	return viewport.get_texture().get_image()

static func run(viewer:Node) -> Dictionary:
	var result:Dictionary={"ok":true,"failures":[],"samples":[]}
	var viewport:=SubViewport.new();viewport.size=Vector2i(96,96);viewport.own_world_3d=true;viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS;viewer.add_child(viewport)
	var camera:=Camera3D.new();camera.position.z=4;camera.current=true;viewport.add_child(camera)
	var env:=WorldEnvironment.new();env.environment=Environment.new();env.environment.background_mode=Environment.BG_COLOR;env.environment.background_color=Color(.01,.01,.01);env.environment.tonemap_mode=Environment.TONE_MAPPER_LINEAR;viewport.add_child(env)
	var mesh:=MeshInstance3D.new();mesh.mesh=BoxMesh.new();mesh.mesh.size=Vector3(2,2,2);viewport.add_child(mesh)
	var slices:Array[Image]=[]
	for z in range(32):
		var layer:=Image.create(32,32,false,Image.FORMAT_R8);layer.fill(Color.BLACK)
		if z>7 and z<24:layer.fill_rect(Rect2i(8,8,16,16),Color.WHITE)
		slices.append(layer)
	var volume:=ImageTexture3D.new();volume.create(Image.FORMAT_R8,32,32,32,false,slices)
	var smoke:=ShaderMaterial.new();smoke.shader=preload("res://smoke_volume.gdshader");smoke.set_shader_parameter("occupancy",volume);smoke.set_shader_parameter("box_min",Vector3(-1,-1,-1));smoke.set_shader_parameter("box_size",Vector3(2,2,2));smoke.set_shader_parameter("smoke_color",Vector3(.54,.54,.54));mesh.material_override=smoke
	var optimized:Image=await image(viewer,viewport)
	var baseline:=Shader.new();baseline.code=FileAccess.get_file_as_string("res://smoke_volume.gdshader").replace("if(occupied<=.12 || expansion<=0.0){continue;}","")
	smoke.shader=baseline
	var original:Image=await image(viewer,viewport);var max_error:float=0
	for y in range(96):
		for x in range(96):
			var a:Color=optimized.get_pixel(x,y);var b:Color=original.get_pixel(x,y)
			max_error=maxf(max_error,maxf(absf(a.r-b.r),maxf(absf(a.g-b.g),absf(a.b-b.b))))
	result.samples.append({"case":"smoke-empty-space-preserves-pixels","max_error":max_error})
	if max_error>.004:result.failures.append("Skipping empty smoke cells changed rendered pixels")
	if optimized.get_pixel(48,48).r<.2:result.failures.append("Smoke disappeared against sky depth")
	mesh.mesh=QuadMesh.new();mesh.mesh.size=Vector2(2,2)
	var fire:=ShaderMaterial.new();fire.shader=preload("res://fire_patch.gdshader");fire.set_shader_parameter("source_frames",true);fire.set_shader_parameter("use_layers",true);fire.set_shader_parameter("frame_count",2)
	var layers:Array[Image]=[]
	for color in [Color(.5,0,0,1),Color(0,0,1,1)]:
		var layer:=Image.create(32,32,false,Image.FORMAT_RGBA8);layer.fill(color);layer.generate_mipmaps();layers.append(layer)
	var array:=Texture2DArray.new();array.create_from_images(layers);fire.set_shader_parameter("flame_layers",array);mesh.material_override=fire
	var first:Image=await image(viewer,viewport);var pixel:Color=first.get_pixel(48,48)
	result.samples.append({"case":"independent-flame-layers","pixel":str(pixel)})
	if pixel.r<.3 or pixel.b>.08:result.failures.append("Fire mixed adjacent sprite layers")
	var wall:=MeshInstance3D.new();wall.mesh=QuadMesh.new();wall.position.z=-.03
	var black:=StandardMaterial3D.new();black.shading_mode=BaseMaterial3D.SHADING_MODE_UNSHADED;black.albedo_color=Color.BLACK;wall.material_override=black;viewport.add_child(wall)
	var feathered:Image=await image(viewer,viewport);fire.set_shader_parameter("feather_distance",0.0)
	var hard:Image=await image(viewer,viewport)
	var soft_pixel:float=feathered.get_pixel(48,48).r;var hard_pixel:float=hard.get_pixel(48,48).r
	result.samples.append({"case":"fire-geometry-feather","soft":soft_pixel,"hard":hard_pixel})
	if soft_pixel<.1 or soft_pixel>=hard_pixel-.02:result.failures.append("Fire depth feather failed")
	viewport.free();result.ok=result.failures.is_empty();return result
