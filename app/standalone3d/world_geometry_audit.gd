extends RefCounted

static func inventory(root:Node) -> Dictionary:
	var stack:Array=[root];var groups:Dictionary={};var meshes:Dictionary={};var eligible:int=0;var visible:int=0
	var checked:int=0;var inflated:int=0;var examples:Array=[]
	while not stack.is_empty():
		var node:Node=stack.pop_back();stack.append_array(node.get_children())
		if not node is MeshInstance3D or not node.mesh is ArrayMesh:continue
		if not node.is_visible_in_tree() or node.cast_shadow==GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY:continue
		visible+=1;meshes[node.mesh.get_rid()]=true
		if node.mesh.get_surface_count()!=1 or node.skin!=null:continue
		var material:Material=node.get_active_material(0)
		if material==null:continue
		if material is StandardMaterial3D and material.transparency!=BaseMaterial3D.TRANSPARENCY_DISABLED:continue
		if material is ShaderMaterial and (material.shader==null or material.shader.code.contains("ALPHA")):continue
		eligible+=1
		if checked<128:
			var arrays:Array=node.mesh.surface_get_arrays(0);var positions:PackedVector3Array=arrays[Mesh.ARRAY_VERTEX];var indices:PackedInt32Array=arrays[Mesh.ARRAY_INDEX]
			if not positions.is_empty() and not indices.is_empty():
				var actual:=AABB(positions[indices[0]],Vector3.ZERO)
				for index in indices:actual=actual.expand(positions[index])
				var original:AABB=node.mesh.get_aabb();checked+=1
				if original.size.length()>actual.size.length()*1.1:
					inflated+=1
					if examples.size()<3:examples.append({"name":str(node.name),"vertices":positions.size(),"indices":indices.size(),"old":str(original),"actual":str(actual)})
		var key:String=str(node.mesh.get_rid())+":"+str(material.get_rid())+":"+str(node.cast_shadow)
		if not groups.has(key):groups[key]=0
		groups[key]+=1
	var savings:int=0;var batches:int=0;var largest:int=0
	for count in groups.values():
		if count>1:savings+=count-1;batches+=1;largest=maxi(largest,count)
	return {"visible_meshes":visible,"unique_mesh_resources":meshes.size(),"eligible_single_surface_opaque":eligible,"repeated_groups":batches,"maximum_group":largest,"potential_saved_draws":savings,"bounds_sampled":checked,"inflated_runtime_bounds":inflated,"bounds_examples":examples}
