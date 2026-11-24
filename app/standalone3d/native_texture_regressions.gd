extends RefCounted

# Bounded one-asset qualification, not an automatic stock/cache rebuild.
# Source weapon mip chains may end at 4x4; preserve that exact chain on RD
# instead of padding/decoding/recompressing it for Image's full-chain contract.
static func run(viewer:Node,folder:String) -> Dictionary:
	var rd:RenderingDevice=RenderingServer.get_rendering_device()
	if rd==null:return {"ok":false,"failures":["Native texture probe requires RenderingDevice"]}
	var meta:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(folder.path_join("resource.json")))
	if meta.get("format","")!="BC7" or int(meta.get("depth",0))!=1 or int(meta.get("bytes",0))>64*1024*1024:return {"ok":false,"failures":["Unqualified native texture format"]}
	var bytes:=FileAccess.get_file_as_bytes(folder.path_join("texture.blocks"));var hash:=HashingContext.new();hash.start(HashingContext.HASH_SHA256);hash.update(bytes)
	if bytes.size()!=int(meta.bytes) or hash.finish().hex_encode()!=meta.sha256:return {"ok":false,"failures":["Native texture byte integrity mismatch"]}
	var original:Texture2D;var model:Node=viewer.stock_scenes["weapon:glock"].instantiate();var stack:Array=[model]
	while not stack.is_empty():
		var node:Node=stack.pop_back();stack.append_array(node.get_children())
		if not node is MeshInstance3D or node.mesh==null:continue
		for surface in range(node.mesh.get_surface_count()):
			var mat:Material=node.get_active_material(surface)
			if mat is StandardMaterial3D and mat.albedo_texture!=null and mat.albedo_texture.resource_name==str(meta.resource).get_file().get_basename():original=mat.albedo_texture
	model.free()
	if original==null:return {"ok":false,"failures":["Original stock color texture unavailable"]}
	var format:=RDTextureFormat.new();format.width=int(meta.width);format.height=int(meta.height);format.depth=1;format.array_layers=1;format.mipmaps=meta.levels.size();format.texture_type=RenderingDevice.TEXTURE_TYPE_2D
	format.format=RenderingDevice.DATA_FORMAT_BC7_UNORM_BLOCK;format.usage_bits=RenderingDevice.TEXTURE_USAGE_SAMPLING_BIT
	format.add_shareable_format(RenderingDevice.DATA_FORMAT_BC7_UNORM_BLOCK);format.add_shareable_format(RenderingDevice.DATA_FORMAT_BC7_SRGB_BLOCK)
	var texture_rid:RID=rd.texture_create(format,RDTextureView.new(),[bytes])
	if not texture_rid.is_valid():return {"ok":false,"failures":["Native BC7 texture upload failed"]}
	var native:=Texture2DRD.new();native.texture_rd_rid=texture_rid
	var viewport:=SubViewport.new();viewport.size=Vector2i(96,96);viewport.own_world_3d=true;viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS;viewer.add_child(viewport)
	var camera:=Camera3D.new();camera.projection=Camera3D.PROJECTION_ORTHOGONAL;camera.size=2;camera.position.z=2;camera.current=true;viewport.add_child(camera)
	var env:=WorldEnvironment.new();env.environment=Environment.new();env.environment.background_mode=Environment.BG_COLOR;env.environment.background_color=Color.BLACK;env.environment.tonemap_mode=Environment.TONE_MAPPER_LINEAR;viewport.add_child(env)
	var mesh:=MeshInstance3D.new();mesh.mesh=QuadMesh.new();mesh.mesh.size=Vector2(2,2);viewport.add_child(mesh)
	var shader:=Shader.new();shader.code="shader_type spatial;render_mode unshaded;uniform sampler2D sampled:source_color,filter_nearest,repeat_disable;uniform float level=0.0;void fragment(){ALBEDO=textureLod(sampled,UV,level).rgb;}"
	var material:=ShaderMaterial.new();material.shader=shader;mesh.material_override=material
	var images:Array[Image]=[]
	for texture in [original,native]:
		material.set_shader_parameter("sampled",texture)
		for frame in range(3):await viewer.get_tree().process_frame
		await RenderingServer.frame_post_draw
		images.append(viewport.get_texture().get_image())
	var maximum:float=0;var changed:int=0
	for y in range(96):
		for x in range(96):
			var a:Color=images[0].get_pixel(x,y);var b:Color=images[1].get_pixel(x,y)
			var error:float=maxf(absf(a.r-b.r),maxf(absf(a.g-b.g),absf(a.b-b.b)));maximum=maxf(maximum,error)
			if error>.008:changed+=1
	material.set_shader_parameter("sampled",null);viewport.free();native.texture_rd_rid=RID();rd.free_rid(texture_rid)
	var ok:bool=maximum<=2.0/255.0
	return {"ok":ok,"maximum_channel_error":maximum,"pixels_over_tolerance":changed,"source_bytes":bytes.size(),"source_mip_levels":meta.levels.size(),"scope":"One original BC7 stock color, retained native mip count; production materials unchanged","failures":[] if ok else ["Native GPU color differs from the cached stock texture"]}
