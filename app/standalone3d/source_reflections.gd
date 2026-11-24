extends RefCounted
var map_root:Node3D
var static_queries:Dictionary={}

var atlas:TextureLayered
var spatial=preload("res://source_bounce.gd").new()
var entries:Array=[]
var max_lod:float=0
var resolution:float=256
var materials:Dictionary={}
var actor_bindings:Dictionary={}
var actor_updates:int=0
var supported_shaders:Dictionary={}
var normalizations:Array=[]
var state:Dictionary={"available":false,"cubes":0,"surfaces":0,"failures":[]}

static func read_cache(asset:String,fingerprint:String) -> Dictionary:
	var folder:=asset.get_base_dir()
	var path:=folder.get_base_dir().get_base_dir().path_join("lighting").path_join(folder.get_file()).path_join("reflections.json")
	if not FileAccess.file_exists(path):return {}
	var meta:Variant=JSON.parse_string(FileAccess.get_file_as_string(path))
	if not meta is Dictionary or meta.get("schema",0)!=1 or meta.get("source_fingerprint","")!=fingerprint:return {"error":"Reflection cache revision mismatch"}
	var w:int=meta.width;var h:int=meta.height;var count:int=meta.cubes
	if w<4 or w>512 or w!=h or count<1 or count*6>2048 or meta.levels.is_empty() or meta.levels.size()>10:return {"error":"Unsupported reflection atlas dimensions"}
	var file:=FileAccess.open(path.get_base_dir().path_join("radiance.blocks"),FileAccess.READ)
	if file==null or file.get_length()!=int(meta.bytes) or file.get_length()>192*1024*1024:return {"error":"Reflection data length mismatch"}
	var bytes:=file.get_buffer(file.get_length());var hash:=HashingContext.new();hash.start(HashingContext.HASH_SHA256);hash.update(bytes)
	if hash.finish().hex_encode()!=meta.sha256:return {"error":"Reflection texture integrity failure"}
	var slices:Array[Image]=[]
	for layer in range(count*6):
		var data:=PackedByteArray();var last:=PackedByteArray();var next_size:int=w
		for index in range(meta.levels.size()):
			var level:Dictionary=meta.levels[index]
			var size:int=maxi(1,w>>index)
			var stride:int=((size+3)/4)*((size+3)/4)*16
			if int(level.level)!=index or int(level.width)!=size or int(level.height)!=size or int(level.bytes)!=stride*count*6 or int(level.offset)+int(level.bytes)>bytes.size():return {"error":"Reflection mip layout mismatch"}
			var start:int=int(level.offset)+stride*layer
			last=bytes.slice(start,start+stride);data.append_array(last);next_size=maxi(1,size/2)
		# Image requires a complete chain. Source stops at 4x4; padding levels
		# are never sampled: explicit LOD is clamped to the final authored mip.
		var source_last_size:int=maxi(1,w>>(meta.levels.size()-1))
		if source_last_size>1:
			while next_size>=1:
				data.append_array(last.slice(0,16))
				if next_size==1:break
				next_size=maxi(1,next_size/2)
		slices.append(Image.create_from_data(w,h,true,Image.FORMAT_BPTC_RGBFU,data))
	var texture:TextureLayered=Texture2DArray.new() if RenderingServer.get_current_rendering_method()=="gl_compatibility" else CubemapArray.new()
	var error:Error=texture.create_from_images(slices)
	if error!=OK:return {"error":"Could not upload reflection atlas: "+str(error)}
	meta["texture"]=texture
	var companion:=FileAccess.open(path.get_base_dir().path_join("normalization.json"),FileAccess.READ)
	if companion!=null and companion.get_length()<=64*1024:
		var data:Variant=JSON.parse_string(companion.get_as_text());var valid:bool=data is Dictionary
		if valid:valid=data.get("schema",0)==1 and data.get("source_fingerprint","")==fingerprint and data.get("atlas_sha256","")==meta.sha256 and data.get("coefficients") is Array
		if valid:
			valid=data.coefficients.size()==count
			for entry in data.coefficients:
				if not entry is Array or entry.size()!=4:valid=false;break
				for value in entry:
					if typeof(value) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(value)) or absf(float(value))>1e6:valid=false;break
		if valid:meta["normalization"]=data.coefficients
	return meta

func configure(data:Dictionary) -> void:
	if data.is_empty():return
	if data.has("error"):state.failures.append(data.error);return
	atlas=data.texture;resolution=float(data.width);max_lod=float(data.levels.size()-1)
	normalizations=data.get("normalization",[]);state["normalization_available"]=not normalizations.is_empty()
	var volumes:Array=[]
	for entry in data.volumes:
		if entry.disabled or entry.get("cube_texture")==null or str(entry.cube_texture).is_empty() or entry.cube_index<0 or entry.cube_index>=data.cubes:continue
		entries.append(entry)
		var volume:Dictionary=entry.duplicate();volume["size"]=[1,1,1];volume["offset"]=[0,0,0];volumes.append(volume)
	# This helper supplies volume selection only, not an irradiance atlas.
	spatial.configure({"texture":null,"width":1,"height":1,"depth":6,"volumes":volumes})
	state.available=not entries.is_empty();state.cubes=int(data.cubes)

func bind(material:ShaderMaterial,chosen:Array) -> void:
	material.set_shader_parameter("reflection_count",mini(4,chosen.size()))
	if chosen.is_empty():return
	var transforms:Array[Transform3D]=[];var extents:=PackedVector3Array();var centers:=PackedVector3Array();var fades:=PackedVector3Array();var indices:=PackedInt32Array();var coefficients:=PackedVector4Array()
	for index in range(4):
		var volume:Dictionary=chosen[mini(index,chosen.size()-1)];var entry:Dictionary=entries[volume.index]
		transforms.append(volume.transform);extents.append(spatial.vector(entry.extent));centers.append(spatial.vector(entry.cube_center));fades.append(volume.fade);indices.append(int(entry.cube_index))
		var values:Array=normalizations[int(entry.cube_index)] if int(entry.cube_index)<normalizations.size() else [0,0,0,0]
		coefficients.append(Vector4(values[0],values[1],values[2],values[3]))
	material.set_shader_parameter("reflection_atlas",atlas);material.set_shader_parameter("reflection_max_lod",max_lod);material.set_shader_parameter("reflection_resolution",resolution)
	material.set_shader_parameter("reflection_transforms",transforms);material.set_shader_parameter("reflection_extents",extents);material.set_shader_parameter("reflection_centers",centers);material.set_shader_parameter("reflection_fades",fades);material.set_shader_parameter("reflection_indices",indices)
	material.set_shader_parameter("reflection_normalization_sh",coefficients)

func apply_mesh(mesh:MeshInstance3D) -> void:
	if atlas==null or mesh.mesh==null:return
	var token:String=str(map_root.get_path_to(mesh)) if map_root!=null else "";var chosen:Array=[]
	spatial.static_queries=static_queries
	chosen=spatial.static_candidates(mesh.global_transform*mesh.get_aabb(),token,4)
	if not token.is_empty():static_queries[token]=chosen.map(func(v:Dictionary):return v.index)
	if chosen.is_empty():return
	for surface in range(mesh.mesh.get_surface_count()):
		var original:Material=mesh.get_active_material(surface)
		if not original is ShaderMaterial or not supports(original.shader):continue
		var key:=str(original.get_instance_id())+":"+str(chosen.map(func(v:Dictionary):return v.index))
		if not materials.has(key):
			materials[key]=original.duplicate();bind(materials[key],chosen)
		mesh.set_surface_override_material(surface,materials[key]);state.surfaces+=1

func collect(node:Node,output:Array) -> void:
	if node is MeshInstance3D and node.mesh!=null:
		for surface in range(node.mesh.get_surface_count()):
			var material:Material=node.get_active_material(surface)
			if material is ShaderMaterial and supports(material.shader):output.append(material)
	for child in node.get_children():collect(child,output)

func supports(shader:Shader) -> bool:
	if shader==null:return false
	var id:int=shader.get_instance_id()
	if not supported_shaders.has(id):
		supported_shaders[id]=shader.get_shader_uniform_list().any(func(item:Dictionary):return item.name=="reflection_count")
	return supported_shaders[id]

func update_actor(root:Node3D,position:Vector3) -> void:
	if atlas==null or root==null:return
	actor_updates+=1
	if actor_updates%64==0:
		for old in actor_bindings.keys():
			if actor_bindings[old].root.get_ref()==null:actor_bindings.erase(old)
	var id:int=root.get_instance_id()
	if not actor_bindings.has(id):
		var bound:Array=[];collect(root,bound);actor_bindings[id]={"root":weakref(root),"materials":bound,"key":""}
	var entry:Dictionary=actor_bindings[id]
	var chosen:Array=spatial.candidates(AABB(position-Vector3.ONE*.01,Vector3.ONE*.02)).slice(0,4)
	var key:=str(chosen.map(func(v:Dictionary):return v.index))
	if key==entry.key:return
	for material in entry.materials:bind(material,chosen)
	entry.key=key
