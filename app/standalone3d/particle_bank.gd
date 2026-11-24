extends RefCounted

# One shared, immutable bank per retained particle revision. Every layer keeps
# its own mip chain; adjacent animation frames must never filter into each other.
static func read_bank(path:String,expected_layers:int=0,required:bool=false) -> Dictionary:
	if not FileAccess.file_exists(path):return {"error":"Prepared particle bank is missing"} if required else {}
	if expected_layers<2:return {"error":"Particle animation frame count is missing"} if required else {}
	var info:Variant=JSON.parse_string(FileAccess.get_file_as_string(path))
	if not info is Dictionary or int(info.get("schema",0))!=1:return {"error":"Invalid particle bank metadata"}
	if expected_layers>0 and int(info.get("layers",0))!=expected_layers:
		# Old 32-frame atlases share the retained source folder with the newer
		# 131-frame bank. They must keep their own frame/sequence contract.
		return {"error":"Particle animation frame count mismatch"} if required else {}
	var w:int=int(info.get("width",0));var h:int=int(info.get("height",0));var count:int=int(info.get("layers",0));var stride:int=int(info.get("stride",0))
	if w<4 or h<4 or w>1024 or h>1024 or count<2 or count>512 or int(info.get("format",-1))!=Image.FORMAT_DXT5:return {"error":"Particle bank dimensions or format exceed bounds"}
	var expected_stride:int=0;var mip_w:int=w;var mip_h:int=h
	while true:
		expected_stride+=ceili(mip_w/4.0)*ceili(mip_h/4.0)*16
		if mip_w==1 and mip_h==1:break
		mip_w=maxi(1,mip_w/2);mip_h=maxi(1,mip_h/2)
	if stride!=expected_stride:return {"error":"Particle mip chain length mismatch"}
	var file:=FileAccess.open(path.trim_suffix(".json")+".blocks",FileAccess.READ)
	if file==null or stride<16 or file.get_length()!=stride*count or file.get_length()!=int(info.get("bytes",0)) or file.get_length()>32*1024*1024:return {"error":"Particle bank length mismatch"}
	var data:=file.get_buffer(file.get_length())
	var digest:=HashingContext.new();digest.start(HashingContext.HASH_SHA256);digest.update(data)
	if digest.finish().hex_encode()!=str(info.get("sha256","")):return {"error":"Particle bank integrity check failed"}
	var images:Array[Image]=[]
	for index in range(count):
		var image:=Image.create_from_data(w,h,true,Image.FORMAT_DXT5,data.slice(index*stride,(index+1)*stride))
		if image==null or image.get_data_size()!=stride:return {"error":"Invalid particle layer"}
		images.append(image)
	var texture:=Texture2DArray.new()
	if texture.create_from_images(images)!=OK:return {"error":"Particle array upload failed"}
	return {"texture":texture,"layers":count}
