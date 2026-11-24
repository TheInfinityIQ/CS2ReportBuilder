extends RefCounted

# Executed on the actual embedded GPU: cube face order/orientation, authored mip
# selection, box projection and independent static/dynamic sun-shadow channels.
static func run(viewer:Node) -> Dictionary:
	var result:Dictionary={"ok":true,"failures":[],"samples":[]}
	var viewport:=SubViewport.new();viewport.size=Vector2i(32,32);viewport.own_world_3d=true
	viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS;viewer.add_child(viewport)
	var scene:=Node3D.new();viewport.add_child(scene)
	var camera:=Camera3D.new();camera.position.z=2;camera.current=true;scene.add_child(camera)
	var environment:=WorldEnvironment.new();environment.environment=Environment.new();environment.environment.background_mode=Environment.BG_COLOR;scene.add_child(environment)
	var slices:Array[Image]=[]
	for face in range(6):
		var base:=Image.create(8,8,false,Image.FORMAT_RGBAF)
		for y in range(8):
			for x in range(8):base.set_pixel(x,y,Color(.1+.3*x/7.0,.1+.3*y/7.0,.1+.1*face))
		var raw:=base.get_data()
		for size in [4,2,1]:
			var mip:=Image.create(size,size,false,Image.FORMAT_RGBAF);mip.fill(Color(.2,.3,.4));raw.append_array(mip.get_data())
		slices.append(Image.create_from_data(8,8,true,Image.FORMAT_RGBAF,raw))
	var texture:=Texture2DArray.new();texture.create_from_images(slices)
	var material:=ShaderMaterial.new();var shader:=Shader.new()
	shader.code="shader_type spatial;render_mode unshaded;\n#include \"res://source_bounce.gdshaderinc\"\n#include \"res://source_reflection.gdshaderinc\"\n#include \"res://source_direct.gdshaderinc\"\nuniform vec3 ray=vec3(1,0,0);uniform float mip=0.0;uniform float test_roughness=0.0;uniform int test=0;void fragment(){vec3 value=reflection_lookup(ray,0,mip);if(test==1){value=vec3(source_sun_shadow(vec3(.0127),UV));}if(test==2){value=source_reflection(vec3(.0127),ray.yzx,ray.yzx,test_roughness).rgb;}if(test==3){value=vec3(source_baked_specular_occlusion(UV));}if(test==4){value=vec3(source_env_normalization(vec4(0,0,0,2),ray,test_roughness,vec3(mip))*.5);}if(test==5){value=vec3(source_env_normalization(vec4(0),ray,test_roughness,vec3(0)));}if(test==6){value=vec3(test_roughness,sqrt(test_roughness),reflection_max_lod)*.5;}if(test==7){value=reflection_lookup(ray,0,sqrt(test_roughness));}if(test==8){value=vec3(source_geometric_roughness(vec3(UV,0)));}if(test==9){value=vec3(source_lightmap_direction(vec3(1,.5,.3),mip).z);}if(test==10){vec3 diffuse;vec3 specular;source_direct_brdf(vec3(0,0,1),normalize(ray),vec3(0,0,1),vec3(.5),0.0,.5,true,diffuse,specular);value=vec3(diffuse.x*PI*.2,specular.x*PI*4.0,specular.y*PI*4.0);}ALBEDO=review_shader_color(value);}"
	material.shader=shader
	var reflection_texture:TextureLayered=texture
	if RenderingServer.get_current_rendering_method()!="gl_compatibility":
		reflection_texture=CubemapArray.new();reflection_texture.create_from_images(slices)
	material.set_shader_parameter("reflection_atlas",reflection_texture);material.set_shader_parameter("reflection_resolution",8.0);material.set_shader_parameter("reflection_max_lod",1.0)
	var probe=preload("res://source_bounce.gd").new();probe.atlas=texture;probe.dimensions=Vector3(1,1,2)
	probe.bind(material,[{"transform":Transform3D.IDENTITY,"size":Vector3(1,1,2),"offset":Vector3.ZERO,"fade":Vector3.ZERO}])
	material.set_shader_parameter("reflection_count",1)
	material.set_shader_parameter("reflection_transforms",[Projection(Transform3D.IDENTITY)])
	material.set_shader_parameter("reflection_extents",PackedVector3Array([Vector3.ONE]))
	material.set_shader_parameter("reflection_centers",PackedVector3Array([Vector3.ONE*.5]))
	material.set_shader_parameter("reflection_fades",PackedVector3Array([Vector3.ZERO]))
	material.set_shader_parameter("reflection_indices",PackedInt32Array([0]))
	var mesh:=MeshInstance3D.new();mesh.mesh=QuadMesh.new();mesh.material_override=material;scene.add_child(mesh)
	# Face-center and off-center samples detect both ordering and UV sign errors.
	var rays:Array[Vector3]=[Vector3(1,0,0),Vector3(-1,0,0),Vector3(0,1,0),Vector3(0,-1,0),Vector3(0,0,1),Vector3(0,0,-1),Vector3(1,.25,.5),Vector3(-1,.25,.5),Vector3(.25,1,.5),Vector3(.25,-1,.5),Vector3(.25,.5,1),Vector3(.25,.5,-1)]
	var face_uv:Array[Vector2]=[Vector2(.5,.5),Vector2(.5,.5),Vector2(.5,.5),Vector2(.5,.5),Vector2(.5,.5),Vector2(.5,.5),Vector2(.25,.375),Vector2(.75,.375),Vector2(.625,.75),Vector2(.625,.25),Vector2(.625,.25),Vector2(.375,.25)]
	for index in range(rays.size()):
		material.set_shader_parameter("ray",rays[index]);material.set_shader_parameter("test",0)
		var uv:Vector2=(face_uv[index]*8.0-Vector2(.5,.5))/7.0
		var expected:=Color(.1+.3*uv.x,.1+.3*uv.y,.1+.1*(index%6))
		await sample(viewer,viewport,result,"reflection-face-"+str(index),expected)
	material.set_shader_parameter("mip",1.0)
	await sample(viewer,viewport,result,"roughness-authored-mip",Color(.2,.3,.4))
	material.set_shader_parameter("mip",0.0);material.set_shader_parameter("test",2);material.set_shader_parameter("ray",Vector3.RIGHT)
	await sample(viewer,viewport,result,"box-projected-reflection",Color(.25,.25,.1))
	material.set_shader_parameter("test_roughness",.25)
	await sample(viewer,viewport,result,"source-roughness-sqrt-mip",Color(.225,.275,.25))
	material.set_shader_parameter("test",6)
	await sample(viewer,viewport,result,"roughness-uniform-input",Color(.125,.25,.5))
	material.set_shader_parameter("test",7)
	await sample(viewer,viewport,result,"fractional-reflection-mip",Color(.225,.275,.25))
	material.set_shader_parameter("test",2)
	material.set_shader_parameter("test_roughness",1.0)
	await sample(viewer,viewport,result,"roughest-reflection-filter",Color(.2,.3,.4))
	material.set_shader_parameter("test",4);material.set_shader_parameter("mip",1.0)
	await sample(viewer,viewport,result,"reflection-irradiance-darkening",Color(.25,.25,.25))
	material.set_shader_parameter("mip",4.0);material.set_shader_parameter("test_roughness",.25)
	await sample(viewer,viewport,result,"reflection-brightening-limit",Color(.75,.75,.75))
	material.set_shader_parameter("test",5)
	await sample(viewer,viewport,result,"missing-normalization-no-change",Color.WHITE)
	material.set_shader_parameter("test",8)
	var uv_derivative:float=2.0*camera.position.z*tan(deg_to_rad(camera.fov)*.5)/(viewport.size.y*float(mesh.mesh.size.x))
	var geometric:float=pow(uv_derivative*uv_derivative,1.0/3.0)
	await sample(viewer,viewport,result,"geometric-specular-antialiasing",Color(geometric,geometric,geometric))
	material.set_shader_parameter("test",9);material.set_shader_parameter("mip",0.0)
	var horizon:float=.0872*1.8/sqrt(1.0-.0872*.0872+pow(.0872*1.8,2))
	await sample(viewer,viewport,result,"flat-baked-horizon-direction",Color(horizon,horizon,horizon))
	material.set_shader_parameter("mip",1.0)
	await sample(viewer,viewport,result,"curved-baked-horizon-direction",Color(.0872,.0872,.0872))
	material.set_shader_parameter("test",10);material.set_shader_parameter("ray",Vector3.BACK)
	await sample(viewer,viewport,result,"source-direct-brdf-head-on",Color(.2,.64/(PI*PI)*PI,.64/(PI*PI)*PI))
	material.set_shader_parameter("ray",Vector3(sqrt(.75),0,.5))
	var nh:float=sqrt(.75);var distribution:float=.0625/(PI*pow(1.0-nh*nh+pow(nh*.25,2),2))
	var fresnel:float=.04+.96*pow(1.0-nh,5)
	var native_specular:float=distribution/(4.0*(.5*(1.0-.28125)+.28125))*fresnel*.5*4.0
	await sample(viewer,viewport,result,"source-direct-brdf-oblique",Color(.1,native_specular,native_specular))
	var mask:=Image.create(4,4,false,Image.FORMAT_RGBAF);mask.fill(Color(.75,.25,0,1))
	material.set_shader_parameter("source_baked_shadows",ImageTexture.create_from_image(mask))
	var shadow_slices:Array[Image]=[mask,mask];var shadow_array:=Texture2DArray.new();shadow_array.create_from_images(shadow_slices)
	material.set_shader_parameter("source_probe_shadows",shadow_array);material.set_shader_parameter("source_direct_enabled",true)
	material.set_shader_parameter("test",1)
	for static_mask in [true,false]:
		material.set_shader_parameter("use_source_lightmap",static_mask)
		for channel in range(2):
			material.set_shader_parameter("source_sun_channels",Vector4(1,0,0,0) if channel==0 else Vector4(0,1,0,0))
			var expected:float=.25 if channel==0 else .75
			await sample(viewer,viewport,result,"sun-mask-"+str(static_mask)+"-"+str(channel),Color(expected,expected,expected))
	material.set_shader_parameter("test",3)
	for alpha in [0.0,.25,1.0]:
		var direction:=Image.create(4,4,false,Image.FORMAT_RGBAF);direction.fill(Color(.5,.5,.8,alpha))
		material.set_shader_parameter("baked_direction",ImageTexture.create_from_image(direction))
		material.set_shader_parameter("use_source_lightmap",true)
		await sample(viewer,viewport,result,"baked-specular-occlusion-"+str(alpha),Color(alpha,alpha,alpha))
	material.set_shader_parameter("use_source_lightmap",false)
	await sample(viewer,viewport,result,"unbaked-specular-occlusion",Color.WHITE)
	viewport.free();result.ok=result.failures.is_empty();return result

static func sample(viewer:Node,viewport:SubViewport,result:Dictionary,label:String,linear:Color) -> void:
	await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
	var measured:=viewport.get_texture().get_image().get_pixel(16,16);var expected:=linear.linear_to_srgb()
	var error:float=maxf(absf(measured.r-expected.r),maxf(absf(measured.g-expected.g),absf(measured.b-expected.b)))
	result.samples.append({"case":label,"max_error":error})
	if error>.025:result.failures.append(label+": GPU colour mismatch "+str(measured)+" expected "+str(expected))
