extends RefCounted

var textures:Dictionary={}
var lights:Array=[]
var sun_channel:int=-1
var root:Node3D
var natives:Array[Light3D]=[]
var base_energies:Array[float]=[]
var supported:Dictionary={}
var actor_bindings:Dictionary={}
var actor_updates:int=0
var state:Dictionary={"available":false,"surfaces":0,"local_lights":0,"unsupported_lights":0,"failures":[]}

static func image_format(name:String) -> int:
	return {"ATI2N":Image.FORMAT_RGTC_RG,"ATI1N":Image.FORMAT_RGTC_R,"BC7":Image.FORMAT_BPTC_RGBA,"DXT5":Image.FORMAT_DXT5,"DXT1":Image.FORMAT_DXT1}.get(name,-1)

static func read_cache(asset:String,fingerprint:String) -> Dictionary:
	var folder:=asset.get_base_dir();var path:=folder.get_base_dir().get_base_dir().path_join("lighting").path_join(folder.get_file()).path_join("direct.json")
	if not FileAccess.file_exists(path):return {}
	var data:Variant=JSON.parse_string(FileAccess.get_file_as_string(path))
	if not data is Dictionary or data.get("schema",0)!=1 or data.get("source_fingerprint","")!=fingerprint:return {"error":"Direct lighting cache revision mismatch"}
	data["loaded"]={}
	for name in data.textures:
		var info:Dictionary=data.textures[name];var format:int=image_format(info.format)
		if name not in ["direct_light_shadows","env_light_probe_volume_atlas_dlshd"] or format<0:return {"error":"Unsupported direct shadow dependency"}
		var w:int=info.width;var h:int=info.height;var d:int=info.depth
		if w<4 or h<4 or d<1 or w>8192 or h>8192 or d>2048:return {"error":"Shadow atlas dimensions exceed bounds"}
		var stride:int=((w+3)/4)*((h+3)/4)*(8 if info.format in ["ATI1N","DXT1"] else 16)
		var file:=FileAccess.open(path.get_base_dir().path_join(name+".blocks"),FileAccess.READ)
		if file==null or file.get_length()!=stride*d or file.get_length()!=int(info.bytes) or file.get_length()>96*1024*1024:return {"error":"Direct shadow data length mismatch"}
		var bytes:=file.get_buffer(file.get_length());var hash:=HashingContext.new();hash.start(HashingContext.HASH_SHA256);hash.update(bytes)
		if hash.finish().hex_encode()!=info.sha256:return {"error":"Direct shadow integrity failure"}
		if name=="direct_light_shadows":
			if d!=1:return {"error":"Unsupported shadow lightmap array"}
			data.loaded[name]=ImageTexture.create_from_image(Image.create_from_data(w,h,false,format,bytes))
		else:
			var slices:Array[Image]=[]
			for index in range(d):slices.append(Image.create_from_data(w,h,false,format,bytes.slice(index*stride,(index+1)*stride)))
			var texture:=Texture2DArray.new()
			if texture.create_from_images(slices)!=OK:return {"error":"Could not upload probe shadow atlas"}
			data.loaded[name]=texture
	return data

func configure(data:Dictionary,parent:Node) -> void:
	if data.is_empty():return
	if data.has("error"):state.failures.append(data.error);return
	textures=data.loaded;lights=data.lights;sun_channel=int(data.sun_channel)
	state.available=textures.has("direct_light_shadows") and textures.has("env_light_probe_volume_atlas_dlshd") and sun_channel>=0 and sun_channel<4
	root=Node3D.new();root.name="AuthoredLocalLights";parent.add_child(root)
	for definition in lights:
		if natives.size()>=256:state.unsupported_lights+=1;continue
		var light:Light3D
		if definition.kind=="light_omni2":
			var point:=OmniLight3D.new();point.omni_range=clampf(float(definition.range)*.0254,1,60);point.omni_attenuation=2.0;light=point
		elif definition.kind in ["light_barn","light_spot"]:
			var spot:=SpotLight3D.new();spot.spot_range=clampf(float(definition.range)*.0254,1,60)
			spot.spot_angle=45;spot.spot_angle_attenuation=1;spot.spot_attenuation=2;light=spot
			# Barn-door/cookie projection is retained as a known approximation.
			state.unsupported_lights+=1
		else:state.unsupported_lights+=1;continue
		var p:Array=definition.origin;light.position=Vector3(p[1],p[2],p[0])*.0254
		var a:Array=definition.angles;var yaw:float=deg_to_rad(float(a[1]));var pitch:float=deg_to_rad(float(a[0]))
		var forward:=Vector3(sin(yaw)*cos(pitch),-sin(pitch),cos(yaw)*cos(pitch))
		var up:=Vector3.UP if absf(forward.dot(Vector3.UP))<.99 else Vector3.RIGHT
		light.basis=Basis.looking_at(forward,up)
		var c:Array=definition.color;light.light_color=Color(c[0],c[1],c[2])
		var energy:float=clampf(float(definition.lumens)/1000.0*.65,0,20)
		light.light_energy=energy;light.shadow_enabled=int(definition.shadow)>0
		light.shadow_bias=.1;light.shadow_normal_bias=1.0
		light.distance_fade_enabled=true;light.distance_fade_begin=28;light.distance_fade_length=12;light.distance_fade_shadow=22
		root.add_child(light);natives.append(light);base_energies.append(energy)
	state.local_lights=natives.size()

func set_brightness(value:float) -> void:
	for index in range(natives.size()):natives[index].light_energy=base_energies[index]*value

func bind(material:ShaderMaterial) -> void:
	if not state.available:return
	var id:int=material.shader.get_instance_id()
	if not supported.has(id):supported[id]=material.shader.get_shader_uniform_list().any(func(item:Dictionary):return item.name=="source_direct_enabled")
	if not supported[id]:return
	var channels:=Vector4.ZERO;channels[sun_channel]=1
	material.set_shader_parameter("source_direct_enabled",true);material.set_shader_parameter("source_sun_channels",channels)
	material.set_shader_parameter("source_baked_shadows",textures.direct_light_shadows)
	material.set_shader_parameter("source_probe_shadows",textures.env_light_probe_volume_atlas_dlshd)
	state.surfaces+=1

func apply_mesh(mesh:MeshInstance3D) -> void:
	if not state.available or mesh.mesh==null:return
	for surface in range(mesh.mesh.get_surface_count()):
		var material:Material=mesh.get_active_material(surface)
		if material is ShaderMaterial:bind(material)

func collect(node:Node) -> void:
	if node is MeshInstance3D:apply_mesh(node)
	for child in node.get_children():collect(child)

func update_actor(node:Node3D) -> void:
	if not state.available or node==null:return
	actor_updates+=1
	if actor_updates%64==0:
		for old in actor_bindings.keys():
			if actor_bindings[old].get_ref()==null:actor_bindings.erase(old)
	var id:int=node.get_instance_id()
	if actor_bindings.has(id):return
	collect(node);actor_bindings[id]=weakref(node)
