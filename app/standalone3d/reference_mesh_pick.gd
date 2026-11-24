extends RefCounted

# Diagnostic only: pick rendered triangles, including geometry absent from
# collision. A bounded query identifies visual defects without game control.
static func pick(root:Node,camera:Camera3D,pixel:Vector2) -> Dictionary:
	var origin:Vector3=camera.project_ray_origin(pixel);var direction:Vector3=camera.project_ray_normal(pixel)
	var stack:Array=[root];var best:float=INF;var result:Dictionary={};var triangles:int=0;var started:int=Time.get_ticks_msec()
	while not stack.is_empty():
		if Time.get_ticks_msec()-started>8000:return {"error":"Rendered geometry query exceeded its bound","triangles":triangles}
		var node:Node=stack.pop_back();stack.append_array(node.get_children())
		if not node is MeshInstance3D or node.mesh==null or not node.is_visible_in_tree() or node.cast_shadow==GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY:continue
		var inverse:Transform3D=node.global_transform.affine_inverse();var local_origin:Vector3=inverse*origin;var local_direction:Vector3=inverse.basis*direction
		if node.get_aabb().intersects_ray(local_origin,local_direction)==null:continue
		for surface in range(node.mesh.get_surface_count()):
			if node.mesh.surface_get_primitive_type(surface)!=Mesh.PRIMITIVE_TRIANGLES:continue
			var arrays:Array=node.mesh.surface_get_arrays(surface);var vertices:PackedVector3Array=arrays[Mesh.ARRAY_VERTEX];var indices:PackedInt32Array=arrays[Mesh.ARRAY_INDEX]
			var count:int=indices.size() if not indices.is_empty() else vertices.size()
			for i in range(0,count-2,3):
				triangles+=1
				if triangles%1024==0 and Time.get_ticks_msec()-started>8000:return {"error":"Rendered geometry query exceeded its bound","triangles":triangles}
				var a:Vector3=vertices[indices[i] if not indices.is_empty() else i];var b:Vector3=vertices[indices[i+1] if not indices.is_empty() else i+1];var c:Vector3=vertices[indices[i+2] if not indices.is_empty() else i+2]
				var hit:Variant=Geometry3D.ray_intersects_triangle(local_origin,local_direction,a,b,c)
				if hit==null:continue
				var point:Vector3=node.global_transform*hit;var distance:float=point.distance_to(origin)
				if distance>=best:continue
				best=distance;var material:Material=node.get_active_material(surface)
				result={"node":str(root.get_path_to(node)),"surface":surface,"triangle":i/3,"material":material.resource_name if material!=null else "","position":str(point),"distance":distance,"shader":material.shader.resource_path if material is ShaderMaterial else "standard"}
	result["triangles"]=triangles;result["origin"]=str(origin);result["direction"]=str(direction);result["milliseconds"]=Time.get_ticks_msec()-started
	return result
