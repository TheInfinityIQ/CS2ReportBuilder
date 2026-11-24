extends RefCounted

const Surface=preload("res://source_effects.gdshader")
var definitions:Dictionary={}
var materials:Dictionary={}
var shaders:Dictionary={}
var animated:Array[ShaderMaterial]=[]
var state:Dictionary={"surfaces":0,"materials":0,"missing_masks":[]}

static func read_cache(asset:String,fingerprint:String) -> Dictionary:
	# Only the retained GLB's bounded JSON header is read. There is no game
	# archive lookup or texture import when opening an older prepared revision.
	var file:=FileAccess.open(asset,FileAccess.READ)
	if file==null:return {}
	var size:int=file.get_length();var modified:int=FileAccess.get_modified_time(asset)
	var receipt:String=asset.get_base_dir().path_join("source-effects.json")
	var header:=FileAccess.open(receipt,FileAccess.READ)
	if header!=null and header.get_length()<512*1024:
		var old:Variant=JSON.parse_string(header.get_as_text())
		if old is Dictionary and old.get("schema",0)==1 and old.get("fingerprint","")==fingerprint and int(old.get("bytes",0))==size and int(old.get("modified",0))==modified and old.get("materials") is Dictionary:return old.materials
	if file.get_buffer(4).get_string_from_ascii()!="glTF" or file.get_32()!=2:return {}
	file.get_32();var length:int=file.get_32()
	if length<2 or length>32*1024*1024 or file.get_32()!=0x4e4f534a or file.get_position()+length>size:return {}
	var data:Variant=JSON.parse_string(file.get_buffer(length).get_string_from_utf8())
	if not data is Dictionary or not data.get("materials") is Array or data.materials.size()>10000:return {}
	var output:Dictionary={}
	for material in data.materials:
		var source:Dictionary=material.get("extras",{}).get("vmat",{})
		if source.get("ShaderName","")!="csgo_effects.vfx":continue
		output[str(material.get("name",""))]=source
	if FileAccess.get_modified_time(asset)!=modified or file.get_length()!=size:return {}
	var writer:=FileAccess.open(receipt+".tmp",FileAccess.WRITE)
	if writer!=null:
		writer.store_string(JSON.stringify({"schema":1,"fingerprint":fingerprint,"bytes":size,"modified":modified,"materials":output}));writer.close()
		DirAccess.rename_absolute(receipt+".tmp",receipt)
	return output

func configure(data:Dictionary,masks:Dictionary) -> void:
	definitions=data;materials.clear();shaders.clear();animated.clear()
	state={"surfaces":0,"materials":data.size(),"missing_masks":[]}
	# Reuse already prepared masks by virtual source path. Missing masks are
	# explicit fallbacks; never substitute assets from a newer game revision.
	var prepared:Dictionary={}
	for name in masks:
		if not data.has(name):continue
		var paths:Dictionary=data[name].get("TextureParams",{})
		for i in range(3):
			if i<masks[name].get("textures",[]).size():prepared[str(paths.get("g_tMask"+str(i+1),""))]=masks[name].textures[i]
	for name in definitions:
		var definition:Dictionary=definitions[name];var loaded:Array=[]
		for i in range(1,4):
			var path:String=str(definition.get("TextureParams",{}).get("g_tMask"+str(i),""))
			loaded.append(prepared.get(path))
			if not path.is_empty() and not prepared.has(path) and not state.missing_masks.has(path):state.missing_masks.append(path)
		definition["loaded_masks"]=loaded

func apply_mesh(node:MeshInstance3D) -> void:
	if node.mesh==null:return
	for surface in range(node.mesh.get_surface_count()):
		var original:Material=node.get_active_material(surface)
		if not original is StandardMaterial3D or not definitions.has(original.resource_name):continue
		var definition:Dictionary=definitions[original.resource_name];var flags:Dictionary=definition.get("IntParams",{})
		var key:int=original.get_instance_id()
		if not materials.has(key):materials[key]=make_material(original,definition)
		node.set_surface_override_material(surface,materials[key]);state.surfaces+=1
		if int(flags.get("F_DO_NOT_CAST_SHADOWS",0))==1:node.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF

func make_material(original:StandardMaterial3D,definition:Dictionary) -> ShaderMaterial:
	var flags:Dictionary=definition.get("IntParams",{});var floats:Dictionary=definition.get("FloatParams",{});var vectors:Dictionary=definition.get("VectorParams",{})
	var additive:bool=int(flags.get("F_ADDITIVE_BLEND",0))==1;var backfaces:bool=int(flags.get("F_RENDER_BACKFACES",0))==1
	var key:String=str(additive)+":"+str(backfaces)
	if not shaders.has(key):
		var shader:=Shader.new();var code:String=Surface.code
		if additive:code=code.replace("blend_mix","blend_add")
		if not backfaces:code=code.replace("cull_disabled","cull_back")
		shader.code=code;shaders[key]=shader
	var material:=ShaderMaterial.new();material.shader=shaders[key];material.resource_name=original.resource_name
	material.set_shader_parameter("color_map",original.albedo_texture);material.set_shader_parameter("tint",original.albedo_color)
	material.set_shader_parameter("feather_enabled",int(flags.get("F_DEPTH_FEATHER",0))==1)
	material.set_shader_parameter("flip_backface",int(flags.get("F_DONT_FLIP_BACKFACE_NORMALS",0))==0)
	var fields:Dictionary={"color_boost":["g_flColorBoost",1.0],"fade_distance":["g_flFadeDistance",1.0],"fade_falloff":["g_flFadeFalloff",1.0],"fade_max":["g_flFadeMax",1.0],"fade_min":["g_flFadeMin",0.0],"feather_distance":["g_flFeatherDistance",1.0],"feather_falloff":["g_flFeatherFalloff",1.0],"fresnel_exponent":["g_flFresnelExponent",.001],"fresnel_falloff":["g_flFresnelFalloff",1.0],"fresnel_max":["g_flFresnelMax",1.0],"fresnel_min":["g_flFresnelMin",0.0],"opacity_scale":["g_flOpacityScale",1.0]}
	for uniform_name in fields:
		var field:Array=fields[uniform_name];var value:float=float(floats.get(field[0],field[1]))
		if uniform_name in ["fade_distance","feather_distance"]:value*=.0254
		material.set_shader_parameter(uniform_name,value)
	for i in range(1,4):
		var masks:Array=definition.get("loaded_masks",[])
		if masks.size()>=i and masks[i-1]!=null:material.set_shader_parameter("mask"+str(i),masks[i-1])
		var scale:Array=vectors.get("g_vMask"+str(i)+"Scale",[1,1]);var pan:Array=vectors.get("g_vMask"+str(i)+"PanSpeed",[0,0])
		material.set_shader_parameter("scale"+str(i),Vector2(scale[0],scale[1]));material.set_shader_parameter("pan"+str(i),Vector2(pan[0],pan[1]))
	var scroll:Array=vectors.get("g_vTexCoordScrollSpeed",[0,0]);material.set_shader_parameter("scroll",Vector2(scroll[0],scroll[1]))
	animated.append(material);return material

func update_tick(seconds:float) -> void:
	for material in animated:material.set_shader_parameter("demo_time",seconds)
