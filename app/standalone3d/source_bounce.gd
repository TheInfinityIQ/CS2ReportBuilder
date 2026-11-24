extends RefCounted

const INCH=.0254
var atlas:Texture2DArray
var dimensions:=Vector3.ONE
var volumes:Array=[]
var shaders:Dictionary={}
static var shared_shaders:Dictionary={}
var materials:Dictionary={}
var actor_bindings:Dictionary={}
var lightmaps:Dictionary={}
var eligibility:Dictionary={}
var actor_updates:int=0
var white_texture:Texture2D
var volume_grid:Dictionary={}
var global_volumes:Array=[]
var state:Dictionary={"available":false,"surfaces":0,"dynamic_surfaces":0,"candidate_truncations":0,"failures":[]}
var map_root:Node3D
var static_queries:Dictionary={}
var volumes_by_id:Dictionary={}

static func read_cache(asset:String,fingerprint:String) -> Dictionary:
	var folder:=asset.get_base_dir()
	var path:=folder.get_base_dir().get_base_dir().path_join("lighting").path_join(folder.get_file()).path_join("probes.json")
	if not FileAccess.file_exists(path):return {}
	var meta:Variant=JSON.parse_string(FileAccess.get_file_as_string(path))
	if not meta is Dictionary or int(meta.get("schema",0))!=1 or meta.get("source_fingerprint","")!=fingerprint:
		return {"error":"Authored probe cache revision mismatch"}
	var w:int=meta.width;var h:int=meta.height;var d:int=meta.depth
	if w<4 or h<4 or d<6 or d%6!=0 or maxi(w,maxi(h,d))>2048:return {"error":"Probe atlas dimensions exceed bounds"}
	var expected:int=((w+3)/4)*((h+3)/4)*16*d
	if expected>192*1024*1024:return {"error":"Probe atlas exceeds the bounded cache size"}
	var file:=FileAccess.open(path.get_base_dir().path_join("atlas.bc6h"),FileAccess.READ)
	if file==null or file.get_length()!=expected:return {"error":"Probe atlas length mismatch"}
	var bytes:=file.get_buffer(expected)
	var hash:=HashingContext.new();hash.start(HashingContext.HASH_SHA256);hash.update(bytes)
	if hash.finish().hex_encode()!=meta.atlas_sha256:return {"error":"Probe atlas integrity check failed"}
	var slices:Array[Image]=[];var stride:int=expected/d
	for z in range(d):slices.append(Image.create_from_data(w,h,false,Image.FORMAT_BPTC_RGBFU,bytes.slice(z*stride,(z+1)*stride)))
	# Compatibility supports compressed 2D arrays, not compressed 3D textures.
	# Keep BC6H HDR data on the GPU and interpolate the two depth slices in shader.
	var texture:=Texture2DArray.new()
	var error:=texture.create_from_images(slices)
	if error!=OK:return {"error":"The renderer cannot upload the source HDR probe atlas: "+str(error)}
	meta["texture"]=texture
	meta["loaded_lightmaps"]={}
	if int(meta.get("lightmap_version",0))==8 and int(meta.get("lightmap_game_version",0))==2:
		for name in meta.get("lightmaps",{}):
			var item:Dictionary=meta.lightmaps[name]
			if int(item.width)<4 or int(item.height)<4 or int(item.width)>8192 or int(item.height)>8192:return {"error":"Static lightmap dimensions exceed bounds"}
			var format:int=Image.FORMAT_BPTC_RGBFU if item.format=="BC6H" else Image.FORMAT_DXT1
			if item.format not in ["BC6H","DXT1"]:return {"error":"Unsupported source lightmap format"}
			var lightmap_size:int=((int(item.width)+3)/4)*((int(item.height)+3)/4)*(16 if item.format=="BC6H" else 8)
			var lightmap_file:=FileAccess.open(path.get_base_dir().path_join(name+".blocks"),FileAccess.READ)
			if lightmap_file==null or lightmap_file.get_length()!=lightmap_size or lightmap_size!=int(item.bytes):return {"error":"Static lightmap length mismatch"}
			var raw:=lightmap_file.get_buffer(lightmap_size)
			var digest:=HashingContext.new();digest.start(HashingContext.HASH_SHA256);digest.update(raw)
			if raw.size()!=int(item.bytes) or digest.finish().hex_encode()!=item.sha256:return {"error":"Static lightmap integrity check failed"}
			var image:=Image.create_from_data(int(item.width),int(item.height),false,format,raw)
			meta.loaded_lightmaps[name]=ImageTexture.create_from_image(image)
	return meta

func configure(data:Dictionary) -> void:
	if data.is_empty():return
	if data.has("error"):state.failures.append(data.error);return
	var white:=Image.create(1,1,false,Image.FORMAT_RGBA8);white.fill(Color.WHITE)
	white_texture=ImageTexture.create_from_image(white)
	atlas=data.texture;dimensions=Vector3(data.width,data.height,float(data.depth)/6)
	lightmaps=data.get("loaded_lightmaps",{})
	eligibility=data.get("lightmap_eligibility",{})
	state["lightmapped_surfaces"]=0
	for entry in data.volumes:
		if entry.disabled:continue
		var m:Array=entry.world_to_local
		var transform:=Transform3D(Basis(Vector3(m[0],m[4],m[8]),Vector3(m[1],m[5],m[9]),Vector3(m[2],m[6],m[10])),Vector3(m[3],m[7],m[11]))
		var size:=vector(entry.size);var offset:=vector(entry.offset)
		if size.min_axis_index()<0 or minf(size.x,minf(size.y,size.z))<1 or offset.x<0 or offset.y<0 or offset.z<0 or (offset+size).x>dimensions.x or (offset+size).y>dimensions.y or (offset+size).z>dimensions.z:
			state.failures.append("Invalid probe volume bounds");continue
		var extent:Vector3=vector(entry.maxs)-vector(entry.mins)
		var source_bounds:AABB=transform.affine_inverse()*AABB(Vector3.ZERO,Vector3.ONE)
		var bounds:=AABB(Vector3(source_bounds.position.y,source_bounds.position.z,source_bounds.position.x)*INCH,Vector3(source_bounds.size.y,source_bounds.size.z,source_bounds.size.x)*INCH)
		volumes.append({"bounds":bounds,"transform":transform,"size":size,"offset":offset,"fade":vector(entry.fade)/extent,"priority":entry.priority,"volume":absf(extent.x*extent.y*extent.z),"index":volumes.size()})
	volumes.sort_custom(func(a:Dictionary,b:Dictionary):return a.priority>b.priority if a.priority!=b.priority else a.volume<b.volume)
	build_grid()
	state.available=not volumes.is_empty();state["volumes"]=volumes.size()

func build_grid() -> void:
	volume_grid.clear();global_volumes.clear();volumes_by_id.clear()
	for index in range(volumes.size()):
		# IDs refer to source records, whereas the array is sorted by priority.
		# Persisted selections must retain source IDs across that sort.
		volumes_by_id[int(volumes[index].index)]=volumes[index]
		var box:AABB=volumes[index].bounds.grow(.001)
		var low:=Vector3i((box.position/16).floor());var high:=Vector3i((box.end/16).floor())
		var count:Vector3i=high-low+Vector3i.ONE
		if count.x*count.y*count.z>4096:global_volumes.append(index);continue
		for z in range(low.z,high.z+1):
			for y in range(low.y,high.y+1):
				for x in range(low.x,high.x+1):
					var key:=Vector3i(x,y,z)
					if not volume_grid.has(key):volume_grid[key]=[]
					volume_grid[key].append(index)

func candidate_indices(bounds:AABB) -> Array:
	if volume_grid.is_empty():return range(volumes.size())
	var box:=bounds.grow(.001);var low:=Vector3i((box.position/16).floor());var high:=Vector3i((box.end/16).floor())
	var count:Vector3i=high-low+Vector3i.ONE
	if count.x*count.y*count.z>512:return range(volumes.size())
	var ids:Dictionary={}
	for index in global_volumes:ids[index]=true
	for z in range(low.z,high.z+1):
		for y in range(low.y,high.y+1):
			for x in range(low.x,high.x+1):
				for index in volume_grid.get(Vector3i(x,y,z),[]):ids[index]=true
	var result:Array=ids.keys();result.sort();return result

static func vector(values:Array) -> Vector3:return Vector3(values[0],values[1],values[2])
static func source(point:Vector3) -> Vector3:return Vector3(point.z,point.x,point.y)/INCH

func candidates(bounds:AABB) -> Array:
	var output:Array=[]
	for index in candidate_indices(bounds):
		var volume:Dictionary=volumes[index]
		if not volume.bounds.grow(.001).intersects(bounds.grow(.001)):continue
		var local:=AABB(volume.transform*source(bounds.get_endpoint(0)),Vector3.ZERO)
		for corner in range(1,8):local=local.expand(volume.transform*source(bounds.get_endpoint(corner)))
		if local.end.x<0 or local.end.y<0 or local.end.z<0 or local.position.x>1 or local.position.y>1 or local.position.z>1:continue
		output.append(volume)
	if output.size()>8:state.candidate_truncations+=1
	return output.slice(0,8)

func static_candidates(bounds:AABB,token:String,maximum:int=8) -> Array:
	if not token.is_empty() and static_queries.has(token):
		var cached:Variant=static_queries[token];var output:Array=[];var valid:bool=cached is Array
		if valid:
			for index in cached:
				if typeof(index) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(index)) or float(index)!=floor(float(index)) or not volumes_by_id.has(int(index)):valid=false;break
				output.append(volumes_by_id[int(index)])
		if valid and output.size()<=maximum:return output
	var chosen:Array=candidates(bounds).slice(0,maximum)
	if not token.is_empty():static_queries[token]=chosen.map(func(v:Dictionary):return v.index)
	return chosen

func bind(material:ShaderMaterial,chosen:Array,has_lightmap:bool=false) -> void:
	material.set_shader_parameter("use_source_lightmap",has_lightmap)
	if has_lightmap:
		material.set_shader_parameter("baked_irradiance",lightmaps.irradiance)
		material.set_shader_parameter("baked_direction",lightmaps.directional_irradiance)
		material.set_shader_parameter("probe_count",0)
		return
	material.set_shader_parameter("probe_count",chosen.size())
	if chosen.is_empty():return
	var transforms:Array[Transform3D]=[];var sizes:=PackedVector3Array();var offsets:=PackedVector3Array();var fades:=PackedVector3Array()
	for i in range(8):
		var volume:Dictionary=chosen[mini(i,chosen.size()-1)]
		transforms.append(volume.transform);sizes.append(volume.size);offsets.append(volume.offset);fades.append(volume.fade)
	material.set_shader_parameter("probe_atlas",atlas);material.set_shader_parameter("probe_dimensions",dimensions)
	material.set_shader_parameter("probe_transforms",transforms);material.set_shader_parameter("probe_sizes",sizes)
	material.set_shader_parameter("probe_offsets",offsets);material.set_shader_parameter("probe_fades",fades)

func shader_for(original:StandardMaterial3D,has_lightmap:bool=false) -> Shader:
	var mode:int=original.transparency
	var key:=str(mode)+":"+str(original.cull_mode)+("/baked" if has_lightmap else "/probe")
	if shaders.has(key):return shaders[key]
	if shared_shaders.has(key):shaders[key]=shared_shaders[key];return shaders[key]
	var code:=FileAccess.get_file_as_string("res://source_probe_surface.gdshader")
	if has_lightmap:code=code.replace("shader_type spatial;","shader_type spatial;\n#define SOURCE_LIGHTMAP_ONLY")
	if original.cull_mode==BaseMaterial3D.CULL_DISABLED:code=code.replace("render_mode cull_back;","render_mode cull_disabled;")
	elif original.cull_mode==BaseMaterial3D.CULL_FRONT:code=code.replace("render_mode cull_back;","render_mode cull_front;")
	if mode==BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR:code=code.replace("// OPACITY","ALPHA=base.a;ALPHA_SCISSOR_THRESHOLD=alpha_cutoff;")
	elif mode==BaseMaterial3D.TRANSPARENCY_ALPHA_HASH:code=code.replace("// OPACITY","ALPHA=base.a;ALPHA_HASH_SCALE=1.0;")
	elif mode==BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS:
		code=code.replace("render_mode ","render_mode depth_prepass_alpha,")
		code=code.replace("// OPACITY","ALPHA=base.a;")
	elif mode!=BaseMaterial3D.TRANSPARENCY_DISABLED:code=code.replace("// OPACITY","ALPHA=base.a;")
	var shader:=Shader.new();shader.code=code;shaders[key]=shader
	shared_shaders[key]=shader
	return shader

func make_material(original:StandardMaterial3D,chosen:Array,has_lightmap:bool=false) -> ShaderMaterial:
	var material:=ShaderMaterial.new();material.shader=shader_for(original,has_lightmap);material.resource_name=original.resource_name
	material.set_shader_parameter("reflection_count",0)
	material.set_shader_parameter("base_color",original.albedo_texture if original.albedo_texture!=null else white_texture)
	material.set_shader_parameter("base_tint",original.albedo_color)
	material.set_shader_parameter("uv_scale",original.uv1_scale);material.set_shader_parameter("uv_offset",original.uv1_offset)
	material.set_shader_parameter("roughness",original.roughness);material.set_shader_parameter("metalness",original.metallic)
	material.set_shader_parameter("use_vertex_color",original.vertex_color_use_as_albedo)
	material.set_shader_parameter("alpha_cutoff",original.alpha_scissor_threshold)
	material.set_shader_parameter("has_normal",original.normal_enabled and original.normal_texture!=null)
	material.set_shader_parameter("normal_texture",original.normal_texture);material.set_shader_parameter("normal_strength",original.normal_scale)
	material.set_shader_parameter("has_roughness",original.roughness_texture!=null)
	material.set_shader_parameter("has_metalness",original.metallic_texture!=null)
	material.set_shader_parameter("orm_texture",original.roughness_texture)
	material.set_shader_parameter("metal_texture",original.metallic_texture)
	for pair in [["rough_channel",original.roughness_texture_channel],["metal_channel",original.metallic_texture_channel],["ao_channel",original.ao_texture_channel]]:
		var channel:=Vector4.ZERO
		if int(pair[1])<4:channel[int(pair[1])]=1
		else:channel=Vector4(.333333,.333333,.333333,0)
		material.set_shader_parameter(pair[0],channel)
	material.set_shader_parameter("has_ao",original.ao_enabled and original.ao_texture!=null)
	material.set_shader_parameter("ao_texture",original.ao_texture)
	material.set_shader_parameter("has_emission",original.emission_enabled)
	material.set_shader_parameter("glow_texture",original.emission_texture if original.emission_texture!=null else white_texture)
	material.set_shader_parameter("glow_tint",original.emission*original.emission_energy_multiplier)
	bind(material,chosen,has_lightmap)
	return material

func apply_mesh(mesh:MeshInstance3D) -> void:
	if atlas==null or mesh.mesh==null:return
	var key_name:String=mesh.mesh.resource_name.trim_prefix("world_vwrld_c_")
	if not eligibility.has(key_name):key_name=str(mesh.name).replace("_meshset_",".meshset_")
	var flags:Array=eligibility.get(key_name,[])
	var all_baked:bool=flags.size()==mesh.mesh.get_surface_count() and not flags.is_empty() and flags.all(func(flag:bool):return flag) and lightmaps.has("irradiance")
	var token:String=str(map_root.get_path_to(mesh)) if map_root!=null else ""
	var chosen:Array=[]
	if not all_baked:
		chosen=static_candidates(mesh.global_transform*mesh.get_aabb(),token)
	if not token.is_empty():static_queries[token]=chosen.map(func(v:Dictionary):return v.index)
	if chosen.is_empty() and lightmaps.is_empty():return
	for surface in range(mesh.mesh.get_surface_count()):
		var has_uv2:bool=mesh.mesh is ArrayMesh and (mesh.mesh.surface_get_format(surface)&Mesh.ARRAY_FORMAT_TEX_UV2)!=0
		var has_lightmap:bool=surface<flags.size() and flags[surface] and lightmaps.has("irradiance") and lightmaps.has("directional_irradiance") and has_uv2
		if has_lightmap:state.lightmapped_surfaces+=1
		var original:Material=mesh.get_active_material(surface)
		var key:=str(original.get_instance_id())+":"+str([] if has_lightmap else chosen.map(func(v:Dictionary):return v.index))+":"+str(has_lightmap) if original!=null else ""
		if original is ShaderMaterial and original.shader==preload("res://source_layered.gdshader"):
			if not materials.has(key):
				materials[key]=original.duplicate()
				if has_lightmap:
					if not shared_shaders.has("layered/baked"):
						var shader:=Shader.new();shader.code=FileAccess.get_file_as_string("res://source_layered.gdshader").replace("shader_type spatial;","shader_type spatial;\n#define SOURCE_LIGHTMAP_ONLY")
						shared_shaders["layered/baked"]=shader
					materials[key].shader=shared_shaders["layered/baked"]
				bind(materials[key],chosen,has_lightmap)
			mesh.set_surface_override_material(surface,materials[key]);state.surfaces+=1
		elif original is StandardMaterial3D and original.shading_mode!=BaseMaterial3D.SHADING_MODE_UNSHADED and original.next_pass==null:
			if not materials.has(key):materials[key]=make_material(original,chosen,has_lightmap)
			mesh.set_surface_override_material(surface,materials[key]);state.surfaces+=1

func _actor_materials(node:Node,output:Array) -> void:
	if node is MeshInstance3D and node.mesh!=null:
		for surface in range(node.mesh.get_surface_count()):
			var original:Material=node.get_active_material(surface)
			if original is StandardMaterial3D and original.shading_mode!=BaseMaterial3D.SHADING_MODE_UNSHADED:
				var material:=make_material(original,[])
				node.set_surface_override_material(surface,material);output.append(material)
				state.dynamic_surfaces+=1
	for child in node.get_children():_actor_materials(child,output)

func update_actor(root:Node3D,position:Vector3,view_override:bool=false,normal_basis:Basis=Basis.IDENTITY) -> void:
	if atlas==null or root==null:return
	actor_updates+=1
	if actor_updates%64==0:
		for old in actor_bindings.keys():
			if actor_bindings[old].root.get_ref()==null:actor_bindings.erase(old)
	var id:int=root.get_instance_id()
	if not actor_bindings.has(id):
		var bound:Array=[];_actor_materials(root,bound)
		actor_bindings[id]={"root":weakref(root),"materials":bound,"key":"","override":null,"position":Vector3.INF,"basis":Basis.IDENTITY}
	var entry:Dictionary=actor_bindings[id]
	var chosen:=candidates(AABB(position-Vector3.ONE*.01,Vector3.ONE*.02))
	var key:=str(chosen.map(func(v:Dictionary):return v.index))
	for material in entry.materials:
		if entry.key!=key:bind(material,chosen)
		if entry.override!=view_override:material.set_shader_parameter("probe_override",view_override)
		if view_override:
			if entry.position!=position:material.set_shader_parameter("probe_position",source(position))
			if entry.basis!=normal_basis or entry.override!=view_override:material.set_shader_parameter("probe_normal_basis",normal_basis)
	entry.key=key
	entry.override=view_override;entry.position=position;entry.basis=normal_basis
