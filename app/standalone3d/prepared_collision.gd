extends RefCounted
static func matches(info:Dictionary,path:String) -> bool:
	var file:=FileAccess.open(path,FileAccess.READ)
	return file!=null and file.get_length()==int(info.get("bytes",0)) and FileAccess.get_modified_time(path)==int(info.get("modified",0))
static func read_metadata(asset:String,scene:String,fingerprint:String) -> Dictionary:
	var folder:String=asset.get_base_dir();var base:String=folder.get_base_dir().get_base_dir().path_join("collision").path_join(folder.get_file())
	var file:=FileAccess.open(base.path_join("manifest.json"),FileAccess.READ)
	if file==null or file.get_length()>2*1024*1024:return {}
	var data:Variant=JSON.parse_string(file.get_as_text())
	if not data is Dictionary or data.get("schema",0)!=1 or data.get("source_fingerprint","")!=fingerprint:return {}
	if not data.get("mesh_paths") is Array or not data.get("triangle_ends") is Array or data.mesh_paths.size()!=int(data.get("meshes",0)) or data.mesh_paths.size()!=data.triangle_ends.size():return {}
	var previous:int=0
	for end in data.triangle_ends:
		if typeof(end) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(end)) or float(end)!=floor(float(end)) or int(end)<=previous:return {}
		previous=int(end)
	if previous!=int(data.get("triangles",0)):return {}
	if not matches(data.get("scene",{}),scene):return {}
	for geometry in data.get("geometry",[]):
		if not matches(geometry,str(geometry.get("path",""))):return {}
	var path:String=base.path_join("world.scn")
	if not matches(data.get("collision",{}),path) or FileAccess.get_sha256(path)!=data.get("sha256",""):return {}
	data["path"]=path;return data

static func mesh_for_face(data:Dictionary,index:int) -> String:
	var ends:Array=data.get("triangle_ends",[]);var low:int=0;var high:int=ends.size()
	if index<0 or ends.is_empty() or index>=int(ends[-1]):return ""
	while low<high:
		var middle:int=(low+high)/2
		if int(ends[middle])<=index:low=middle+1
		else:high=middle
	return str(data.mesh_paths[low])
