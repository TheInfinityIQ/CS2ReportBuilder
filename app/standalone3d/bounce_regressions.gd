extends RefCounted

# GPU test of six-face ordering, normal-squared weighting, HDR colour conversion
# and interpolation between array slices. Runs inside the owned Toolbox renderer.
static func run(viewer:Node) -> Dictionary:
	var result:Dictionary={"ok":true,"failures":[],"samples":[]}
	var viewport:=SubViewport.new();viewport.size=Vector2i(32,32);viewport.own_world_3d=true
	viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS;viewer.add_child(viewport)
	var scene:=Node3D.new();viewport.add_child(scene)
	var camera:=Camera3D.new();camera.position.z=2;camera.current=true;scene.add_child(camera)
	var environment:=WorldEnvironment.new();environment.environment=Environment.new()
	environment.environment.background_mode=Environment.BG_COLOR;scene.add_child(environment)
	var face_colors:Array[Color]=[Color(.4,.1,.1),Color(.1,.4,.1),Color(.1,.1,.4),Color(.4,.4,.1),Color(.4,.1,.4),Color(.1,.4,.4)]
	var slices:Array[Image]=[]
	for color in face_colors:
		for bias in [-.04,.04]:
			var image:=Image.create(4,4,false,Image.FORMAT_RGBAF);image.fill(Color(color.r+bias,color.g+bias,color.b+bias));slices.append(image)
	var texture:=Texture2DArray.new();texture.create_from_images(slices)
	var material:=ShaderMaterial.new();var shader:=Shader.new()
	shader.code="shader_type spatial;render_mode unshaded;\n#include \"res://source_bounce.gdshaderinc\"\nuniform vec3 sample_normal=vec3(0,0,1);void fragment(){ALBEDO=review_shader_color(source_bounce(vec3(.0127),sample_normal).rgb);}"
	material.shader=shader
	var probe=preload("res://source_bounce.gd").new();probe.atlas=texture;probe.dimensions=Vector3(1,1,2)
	probe.bind(material,[{"transform":Transform3D.IDENTITY,"size":Vector3(1,1,2),"offset":Vector3.ZERO,"fade":Vector3.ZERO}])
	var mesh:=MeshInstance3D.new();mesh.mesh=QuadMesh.new();mesh.material_override=material;scene.add_child(mesh)
	var normals:Array[Vector3]=[Vector3.BACK,Vector3.RIGHT,Vector3.UP,Vector3.FORWARD,Vector3.LEFT,Vector3.DOWN,Vector3.ONE.normalized()]
	var expected:Array[Color]=face_colors.duplicate();expected.append(Color(.2,.2,.2))
	for index in range(normals.size()):
		material.set_shader_parameter("sample_normal",normals[index])
		await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
		var measured:Color=viewport.get_texture().get_image().get_pixel(16,16)
		var target:Color=expected[index].linear_to_srgb()
		var error:float=maxf(absf(measured.r-target.r),maxf(absf(measured.g-target.g),absf(measured.b-target.b)))
		result.samples.append({"axis":index,"rgb":str(measured),"expected":str(target),"max_error":error})
		if error>.025:result.failures.append("Ambient cube GPU sample "+str(index)+" does not match linear reference")
	viewport.free()
	result.ok=result.failures.is_empty()
	return result
