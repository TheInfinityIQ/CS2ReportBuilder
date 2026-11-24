extends RefCounted
var fallback:Sky
var material:ShaderMaterial
var base_intensity:float=1
var state:Dictionary={"available":false}

static func read_cache(asset:String,fingerprint:String) -> Dictionary:
	var folder:String=asset.get_base_dir();var base:String=folder.get_base_dir().get_base_dir().path_join("sky").path_join(folder.get_file())
	var header:=FileAccess.open(base.path_join("sky.json"),FileAccess.READ)
	if header==null or header.get_length()>64*1024:return {}
	var data:Variant=JSON.parse_string(header.get_as_text())
	if not data is Dictionary or data.get("schema",0)!=1 or data.get("source_fingerprint","")!=fingerprint or data.get("format","")!="BC6H":return {}
	var width:int=data.get("width",0);var height:int=data.get("height",0)
	if width<4 or width>1024 or width!=height or not data.get("sky") is Dictionary:return {}
	var file:=FileAccess.open(base.path_join("texture.blocks"),FileAccess.READ)
	if file==null or file.get_length()!=int(data.get("bytes",0)) or file.get_length()>8*1024*1024:return {}
	var bytes:PackedByteArray=file.get_buffer(file.get_length());var hash:=HashingContext.new();hash.start(HashingContext.HASH_SHA256);hash.update(bytes)
	if hash.finish().hex_encode()!=data.get("sha256",""):return {}
	var stride:int=((width+3)/4)*((height+3)/4)*16
	if bytes.size()<stride*6:return {}
	var slices:Array[Image]=[]
	for face in range(6):slices.append(Image.create_from_data(width,height,false,Image.FORMAT_BPTC_RGBFU,bytes.slice(face*stride,(face+1)*stride)))
	var texture:=Texture2DArray.new()
	if texture.create_from_images(slices)!=OK:return {}
	data["texture"]=texture;return data

func configure(data:Dictionary,environment:Environment) -> void:
	if fallback==null:fallback=environment.sky
	environment.sky=fallback;state={"available":false};material=null
	if data.is_empty():return
	material=ShaderMaterial.new();material.shader=preload("res://source_sky.gdshader")
	material.set_shader_parameter("sky_faces",data.texture);material.set_shader_parameter("resolution",float(data.width))
	base_intensity=float(data.sky.get("brightness",1));set_brightness(1)
	var tint:Array=data.sky.get("tint",[1,1,1]);material.set_shader_parameter("tint",Vector3(tint[0],tint[1],tint[2]))
	material.set_shader_parameter("source_rotation",source_rotation(data.sky.get("angles",[0,0,0])))
	var sky:=Sky.new();sky.sky_material=material;sky.radiance_size=Sky.RADIANCE_SIZE_128;environment.sky=sky
	state={"available":true,"resource":data.resource,"material":data.material,"brightness":data.sky.brightness}

func set_brightness(value:float) -> void:
	if material!=null:material.set_shader_parameter("intensity",base_intensity*value)

static func source_rotation(angles:Array) -> Basis:
	# These angles rotate Source XYZ (Z-up), before the Godot YZX conversion.
	return (Basis(Vector3.BACK,deg_to_rad(float(angles[1])))*Basis(Vector3.UP,deg_to_rad(float(angles[0])))*Basis(Vector3.RIGHT,deg_to_rad(float(angles[2])))).inverse()
