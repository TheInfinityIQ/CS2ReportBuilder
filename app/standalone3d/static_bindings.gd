extends RefCounted
const SCRIPTS=["res://source_bounce.gd","res://source_reflections.gd"]
static func revision() -> Array:
	var output:Array=[]
	for path in SCRIPTS:output.append(FileAccess.get_sha256(path))
	return output
static func folder(asset:String) -> String:
	var base:String=asset.get_base_dir();return base.get_base_dir().get_base_dir().path_join("bindings").path_join(base.get_file())
static func dependency_hashes(asset:String) -> Array:
	var base:String=asset.get_base_dir();var light:String=base.get_base_dir().get_base_dir().path_join("lighting").path_join(base.get_file())
	var hashes:Array=[]
	for name in ["probes.json","reflections.json"]:hashes.append(FileAccess.get_sha256(light.path_join(name)))
	return hashes
static func read_cache(asset:String,scene:String,fingerprint:String) -> Dictionary:
	var file:=FileAccess.open(folder(asset).path_join("queries.json"),FileAccess.READ)
	if file==null or file.get_length()>4*1024*1024:return {}
	var data:Variant=JSON.parse_string(file.get_as_text())
	if not data is Dictionary or data.get("schema",0)!=1 or data.get("fingerprint","")!=fingerprint or data.get("revision",[])!=revision() or data.get("dependencies",[])!=dependency_hashes(asset):return {}
	var original:=FileAccess.open(scene,FileAccess.READ)
	if original==null or original.get_length()!=int(data.get("scene_bytes",0)) or FileAccess.get_modified_time(scene)!=int(data.get("scene_modified",0)):return {}
	for key in ["bounce","reflections"]:
		if not data.get(key) is Dictionary or data[key].size()>50000:return {}
	return data
static func save_cache(viewer:Node,data:Dictionary) -> bool:
	var asset:String=data.map_asset
	var scene := str(data.get("native_scene",""))
	# Older replay metadata can load the GLB directly without a native scene.
	if scene.is_empty():return false
	var file:=FileAccess.open(scene,FileAccess.READ)
	if file==null:return false
	var output:Dictionary={"schema":1,"fingerprint":data.asset_info.fingerprint,"revision":revision(),"dependencies":dependency_hashes(asset),"scene_bytes":file.get_length(),"scene_modified":FileAccess.get_modified_time(scene),"bounce":viewer.source_bounce.static_queries,"reflections":viewer.source_reflections.static_queries}
	var text:String=JSON.stringify(output)
	if text.to_utf8_buffer().size()>4*1024*1024:return false
	var directory:String=folder(asset)
	if DirAccess.make_dir_recursive_absolute(directory)!=OK:return false
	var temporary:String=directory.path_join("queries.json.tmp")
	var writer:=FileAccess.open(temporary,FileAccess.WRITE)
	if writer==null:return false
	writer.store_string(text);writer.flush();var error:int=writer.get_error();writer.close()
	if error!=OK:DirAccess.remove_absolute(temporary);return false
	return DirAccess.rename_absolute(temporary,directory.path_join("queries.json"))==OK
