extends RefCounted
# Independent GPU check: a known linear radiance, quarter-exposure intermediate,
# authored rational curve, then a neutral color LUT. No game/map content changes.
static func run(viewer:Node) -> Dictionary:
	var result:Dictionary={"ok":true,"failures":[]}
	var viewport:=SubViewport.new();viewport.size=Vector2i(32,32);viewport.own_world_3d=true
	viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS;viewer.add_child(viewport)
	var scene:=Node3D.new();viewport.add_child(scene)
	var environment:=WorldEnvironment.new();environment.environment=Environment.new();scene.add_child(environment)
	environment.environment.background_mode=Environment.BG_COLOR
	environment.environment.tonemap_mode=Environment.TONE_MAPPER_LINEAR;environment.environment.tonemap_exposure=.25
	var camera:=Camera3D.new();camera.position.z=2;camera.current=true;scene.add_child(camera)
	var material:=ShaderMaterial.new();var shader:=Shader.new()
	shader.code="shader_type spatial;render_mode unshaded;\n#include \"res://source_bounce.gdshaderinc\"\nvoid fragment(){ALBEDO=review_shader_color(vec3(.18));}"
	material.shader=shader
	var mesh:=MeshInstance3D.new();mesh.mesh=QuadMesh.new();mesh.material_override=material;scene.add_child(mesh)
	for settle in range(3):await viewer.get_tree().process_frame
	await RenderingServer.frame_post_draw
	var raw:Color=viewport.get_texture().get_image().get_pixel(16,16)
	result["raw_quarter_gray"]=raw.r
	if absf(raw.r-.2347950794)>.015:result.failures.append("Raw quarter-exposure color space changed")
	var post=preload("res://source_post.gd").new()
	post.configure({"profiles":[{"master":true,"resource":"gpu-fixture","min_exposure":1,"max_exposure":1,"exposure_enabled":false,
		"tone":{"m_flShoulderStrength":.15,"m_flLinearStrength":.5,"m_flLinearAngle":.1,"m_flToeStrength":.2,"m_flToeNum":.02,"m_flToeDenom":.3,"m_flWhitePoint":4}}]},environment.environment)
	post.attach(viewport)
	for settle in range(3):await viewer.get_tree().process_frame
	await RenderingServer.frame_post_draw
	var mapped:Color=viewport.get_texture().get_image().get_pixel(16,16);result["mapped_gray"]=mapped.r
	if absf(mapped.r-.5299251156)>.018:result.failures.append("Authored tone curve does not match known gray reference")
	var layers:Array[Image]=[]
	for z in range(8):
		var layer:=Image.create(8,8,false,Image.FORMAT_RGBA8)
		for y in range(8):
			for x in range(8):layer.set_pixel(x,y,Color(float(x)/7,float(y)/7,float(z)/7))
		layers.append(layer)
	var lut:=ImageTexture3D.new();lut.create(Image.FORMAT_RGBA8,8,8,8,false,layers)
	post.material.set_shader_parameter("grading",lut);post.material.set_shader_parameter("dimension",8.0);post.material.set_shader_parameter("has_grading",true)
	for settle in range(3):await viewer.get_tree().process_frame
	await RenderingServer.frame_post_draw
	var neutral:Color=viewport.get_texture().get_image().get_pixel(16,16);result["neutral_lut_gray"]=neutral.r
	if maxf(absf(mapped.r-neutral.r),maxf(absf(mapped.g-neutral.g),absf(mapped.b-neutral.b)))>.012:result.failures.append("Neutral color grading changes the tone curve output")
	post.material.set_shader_parameter("has_grading",false)
	for field in {"shoulder":0.0,"linear_strength":.001,"linear_angle":.001,"toe":1.0,"toe_num":1.0,"toe_denom":1.0,"white_point":1.5}:
		post.material.set_shader_parameter(field,{"shoulder":0.0,"linear_strength":.001,"linear_angle":.001,"toe":1.0,"toe_num":1.0,"toe_denom":1.0,"white_point":1.5}[field])
	for settle in range(3):await viewer.get_tree().process_frame
	await RenderingServer.frame_post_draw
	var negative:Color=viewport.get_texture().get_image().get_pixel(16,16);result["negative_curve_gray"]=negative.r
	# Independent ratio for Mirage/Nuke's signed near-linear authoring curve.
	var ratio:float=(.504/(1.0+.001*.504))/(1.5/(1.0+.001*1.5))
	var expected:float=Color(ratio,ratio,ratio).linear_to_srgb().r
	if absf(negative.r-expected)>.02:result.failures.append("Signed white-point normalization turns stock maps black")
	# A bright object entering the view must not flash the entire gray surface.
	post.configure({"profiles":[{"master":true,"resource":"exposure-fixture","min_exposure":.7,"max_exposure":1.8,"exposure_enabled":true,"tone":{"m_flExposureBias":0}}]},environment.environment)
	var rectangle:ColorRect=post.attach(viewport);var exposure_samples:Array=[]
	for background in [Color.BLACK,Color(4,4,4),Color.BLACK]:
		environment.environment.background_color=background
		for settle in range(3):await viewer.get_tree().process_frame
		await RenderingServer.frame_post_draw
		exposure_samples.append(viewport.get_texture().get_image().get_pixel(16,16).r)
	result["exposure_samples"]=exposure_samples
	if exposure_samples.max()-exposure_samples.min()>.012:result.failures.append("Changing the background pumps the exposure of unchanged geometry")
	if post.state.get("exposure_mode","")!="fixed":result.failures.append("Unfiltered screen-average exposure re-enabled")
	# Confirm actual GPU edge coverage, not just an anti-aliasing setting.
	rectangle.visible=false;environment.environment.background_color=Color.BLACK
	for settle in range(3):await viewer.get_tree().process_frame
	await RenderingServer.frame_post_draw
	var before_overlay:Color=viewport.get_texture().get_image().get_pixel(16,16)
	var overlay:=MeshInstance3D.new();overlay.mesh=QuadMesh.new();overlay.position.z=.01;scene.add_child(overlay)
	var modulate:=ShaderMaterial.new();modulate.shader=preload("res://source_overlay.gdshader")
	var additive:=ShaderMaterial.new();additive.shader=preload("res://source_overlay_add.gdshader");modulate.next_pass=additive
	var gray:=Image.create(4,4,false,Image.FORMAT_RGBA8);gray.fill(Color(.5,.5,.5,1))
	var gray_texture:ImageTexture=ImageTexture.create_from_image(gray)
	modulate.set_shader_parameter("color_texture",gray_texture);additive.set_shader_parameter("color_texture",gray_texture);overlay.material_override=modulate
	var modulations:Array=[]
	for opacity in [1.0,0.0]:
		modulate.set_shader_parameter("opacity",opacity)
		additive.set_shader_parameter("opacity",opacity)
		for settle in range(3):await viewer.get_tree().process_frame
		await RenderingServer.frame_post_draw
		var actual:Color=viewport.get_texture().get_image().get_pixel(16,16);modulations.append(actual.r)
		if absf(actual.r-before_overlay.r)>.012:result.failures.append("Neutral/transparent modulation overlay darkens exposed geometry")
	result["neutral_overlay"]={"base":before_overlay.r,"overlays":modulations}
	var nonneutral:Array=[]
	for value in [.25,.75]:
		gray.fill(Color(value,value,value,1));gray_texture.update(gray)
		modulate.set_shader_parameter("opacity",1.0);additive.set_shader_parameter("opacity",1.0)
		for settle in range(3):await viewer.get_tree().process_frame
		await RenderingServer.frame_post_draw
		var actual:Color=viewport.get_texture().get_image().get_pixel(16,16)
		var linear:float=.18*.25*(value*2.0);var target:float=Color(linear,linear,linear).linear_to_srgb().r
		nonneutral.append({"texture":value,"actual":actual.r,"expected":target})
		if absf(actual.r-target)>.018:result.failures.append("Dark/bright modulation is clipped or uses the wrong color space")
	result["nonneutral_overlays"]=nonneutral
	overlay.free();environment.environment.tonemap_exposure=1.0
	shader.code="shader_type spatial;render_mode unshaded;void fragment(){ALBEDO=vec3(1.0);}"
	mesh.rotation.z=.3;mesh.scale=Vector3.ONE*1.7
	var coverage:Array=[]
	for mode in [Viewport.MSAA_DISABLED,Viewport.MSAA_4X]:
		viewport.msaa_3d=mode
		for settle in range(3):await viewer.get_tree().process_frame
		await RenderingServer.frame_post_draw
		var image:Image=viewport.get_texture().get_image();var edges:int=0
		for y in range(32):
			for x in range(32):
				var value:float=image.get_pixel(x,y).r
				if value>.02 and value<.98:edges+=1
		coverage.append(edges)
	result["msaa_edge_pixels"]=coverage
	if coverage[1]<=coverage[0]+4:result.failures.append("4x MSAA did not produce anti-aliased geometry edges")
	viewport.msaa_3d=Viewport.MSAA_DISABLED;environment.environment.tonemap_exposure=.25;rectangle.visible=true
	var filtered:Array=[]
	for enabled in [false,true]:
		post.material.set_shader_parameter("anti_alias",enabled)
		for settle in range(3):await viewer.get_tree().process_frame
		await RenderingServer.frame_post_draw
		var image:Image=viewport.get_texture().get_image();var peak:float=image.get_pixel(16,16).r;var edges:int=0
		for y in range(32):
			for x in range(32):
				var value:float=image.get_pixel(x,y).r
				if value>.02 and value<peak-.02:edges+=1
		filtered.append(edges)
	result["fxaa_edge_pixels"]=filtered
	if filtered[1]<=filtered[0]+4:result.failures.append("Post edge filtering did not smooth shader/transparency edges")
	viewport.free();result.ok=result.failures.is_empty();return result
