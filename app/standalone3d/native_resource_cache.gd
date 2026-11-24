extends RefCounted

var folder:String
var items:Dictionary={}
var hits:int=0
var fallbacks:int=0

func configure(cache:String) -> void:
	folder=cache.path_join("native-resources");items.clear();hits=0;fallbacks=0
	var file:=FileAccess.open(folder.path_join("active.json"),FileAccess.READ)
	if file==null or file.get_length()>1024*1024:return
	var parsed:Variant=JSON.parse_string(file.get_as_text())
	if parsed is Dictionary and int(parsed.get("schema",0))==4 and parsed.get("items") is Dictionary:items=parsed.items

func resolve(original:String) -> String:
	var value:Variant=items.get(original.replace("\\","/"),{})
	if not value is Dictionary:return original
	var entry:Dictionary=value
	if int(entry.get("schema",0))!=4:return original
	var name:String=str(entry.get("path",""));var stem:String=name.trim_suffix(".scn")
	if stem.length()!=64 or not stem.is_valid_hex_number(false) or name!=stem+".scn":return original
	var source:=FileAccess.open(original,FileAccess.READ)
	if source==null or source.get_length()!=int(entry.get("source_bytes",0)) or FileAccess.get_modified_time(original)!=int(entry.get("source_modified",0)):return original
	var path:String=folder.path_join(name);var file:=FileAccess.open(path,FileAccess.READ)
	if file==null or file.get_length()!=int(entry.get("bytes",0)) or FileAccess.get_modified_time(path)!=int(entry.get("modified",0)) or file.get_buffer(4).get_string_from_ascii()!="RSRC":return original
	hits+=1;return path

func load_scene(original:String) -> PackedScene:
	var path:String=resolve(original)
	var scene:=ResourceLoader.load(path,"PackedScene") as PackedScene
	if scene==null and path!=original:fallbacks+=1;scene=ResourceLoader.load(original,"PackedScene") as PackedScene
	return scene
