extends SceneTree
var result:Dictionary={"meshes":0,"triangles":0,"arch_meshes":0,"arch_triangles":0,"negative_scale":0,"mixed_tools":[]}
func _initialize() -> void:
	_run.call_deferred()
func _run() -> void:
	var args:=OS.get_cmdline_user_args()
	var metadata:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var scene=load(metadata.native_scene).instantiate();root.add_child(scene)
	_walk(scene)
	var output:=FileAccess.open(args[1],FileAccess.WRITE);output.store_string(JSON.stringify(result,"\t"));output.close()
	scene.free();quit()
func _walk(node:Node) -> void:
	if node is MeshInstance3D and node.mesh!=null:
		result.meshes+=1
		var triangles:=0;var tools:=0;var visible:=0
		for index in range(node.mesh.get_surface_count()):
			var arrays:Array=node.mesh.surface_get_arrays(index)
			triangles+=(arrays[Mesh.ARRAY_INDEX].size() if arrays[Mesh.ARRAY_INDEX]!=null else arrays[Mesh.ARRAY_VERTEX].size())/3
			var material:Material=node.get_active_material(index)
			if material!=null and material.resource_name.to_lower().begins_with("tools"):tools+=1
			else:visible+=1
		result.triangles+=triangles
		if tools>0 and visible>0:result.mixed_tools.append(str(node.name))
		if node.global_basis.determinant()<0:result.negative_scale+=1
		if "arch" in str(node.name).to_lower() or "bridge" in str(node.name).to_lower():
			result.arch_meshes+=1;result.arch_triangles+=triangles
	for child in node.get_children():_walk(child)
