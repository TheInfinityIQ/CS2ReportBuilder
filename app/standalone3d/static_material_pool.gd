extends RefCounted

# Pool only immutable world materials after all native lighting bindings. Exact
# shader/uniform/texture/state equality is required; geometry is never merged.
static func canonical(value:Variant) -> Variant:
	if value is Texture:return ["texture",value.get_rid().get_id()]
	if value is Object:return ["object",value.get_instance_id()]
	return value

static func apply(root:Node,enabled:bool) -> Dictionary:
	var stack:Array=[root];var seen:Dictionary={};var layouts:Dictionary={};var buckets:Dictionary={}
	var reused:int=0;var eligible:int=0;var started:int=Time.get_ticks_usec()
	while not stack.is_empty():
		var node:Node=stack.pop_back();stack.append_array(node.get_children())
		if not node is MeshInstance3D or node.mesh==null or node.material_override!=null:continue
		for surface in range(node.mesh.get_surface_count()):
			var material:Material=node.get_active_material(surface)
			if not material is ShaderMaterial or material.shader==null or material.next_pass!=null:continue
			var id:int=material.get_instance_id()
			if seen.has(id):
				if enabled and seen[id]!=material:node.set_surface_override_material(surface,seen[id])
				continue
			var shader_id:int=material.shader.get_instance_id()
			if not layouts.has(shader_id):
				var names:Array=[]
				for entry in material.shader.get_shader_uniform_list():names.append(str(entry.name))
				names.sort();layouts[shader_id]=names
			var names:Array=layouts[shader_id]
			if "demo_time" in names or "TIME" in material.shader.code:continue
			eligible+=1
			var payload:Array=[shader_id,material.render_priority,material.resource_name]
			for name in names:payload.append(canonical(material.get_shader_parameter(name)))
			var bytes:PackedByteArray=var_to_bytes(payload);var key:int=hash(bytes)
			var existing:ShaderMaterial=null
			for candidate in buckets.get(key,[]):
				if candidate.bytes==bytes:existing=candidate.material;break
			if existing!=null:
				reused+=1;seen[id]=existing
				if enabled:node.set_surface_override_material(surface,existing)
			else:
				if not buckets.has(key):buckets[key]=[]
				buckets[key].append({"bytes":bytes,"material":material});seen[id]=material
	return {"enabled":enabled,"eligible_materials":eligible,"identical_materials_reused":reused,"milliseconds":(Time.get_ticks_usec()-started)/1000.0}
