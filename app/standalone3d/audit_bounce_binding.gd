extends SceneTree
func _initialize() -> void:
	var args:=OS.get_cmdline_user_args()
	var meta:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var probes:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[1]))
	var scene:=load(str(meta.native_scene)) as PackedScene
	var state:=scene.get_state();var samples:Array=[];var matched:int=0;var uv2_count:int=0;var eligible:int=0
	for node in range(state.get_node_count()):
		for prop in range(state.get_node_property_count(node)):
			if state.get_node_property_name(node,prop)!=&"mesh":continue
			var mesh:Mesh=state.get_node_property_value(node,prop)
			var key:String=mesh.resource_name.trim_prefix("world_vwrld_c_")
			if not probes.lightmap_eligibility.has(key):key=str(state.get_node_name(node)).replace("_meshset_",".meshset_")
			if probes.lightmap_eligibility.has(key):matched+=1
			for surface in range(mesh.get_surface_count()):
				var uv=mesh.surface_get_arrays(surface)[Mesh.ARRAY_TEX_UV2]
				if uv!=null and not uv.is_empty():uv2_count+=1
			var flags:Array=probes.lightmap_eligibility.get(key,[])
			if "mesh_overlay0_nz" in key:print(JSON.stringify({"witness_mesh":key,"native_uv":str(mesh.surface_get_arrays(0)[Mesh.ARRAY_TEX_UV2].slice(0,4))}))
			if true in flags:eligible+=1
			if samples.size()<8 and not probes.lightmap_eligibility.has(key):samples.append({"mesh":mesh.resource_name,"node":str(state.get_node_name(node)),"key":key,"flags":flags,"uv2":mesh.surface_get_arrays(0)[Mesh.ARRAY_TEX_UV2]!=null})
	print(JSON.stringify({"matched":matched,"uv2":uv2_count,"eligible":eligible,"samples":samples}))
	quit()
