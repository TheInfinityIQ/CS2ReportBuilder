extends RefCounted

# Original static masks plus live actor shadows. Other map revisions/backends
# keep the existing geometry-shadow path until their own image qualification.
const ANUBIS_REVISION="72f45768ff0154af40b4e37904b6decfaa466b37b314f8735491dbe70eb27fea"
var changed_nodes:Array=[]
var changed_suns:Array=[]

static func qualified(data:Dictionary) -> bool:
	return data.get("map","")=="de_anubis" and data.get("asset_info",{}).get("fingerprint","")==ANUBIS_REVISION

func restore() -> void:
	for item in changed_nodes:
		var node:Node=item[0].get_ref()
		if node!=null:node.layers=item[1]
	for item in changed_suns:
		var sun:Node=item[0].get_ref()
		if sun!=null:sun.shadow_caster_mask=item[1]
	changed_nodes.clear();changed_suns.clear()

func configure(viewer:Node,enabled:bool) -> Dictionary:
	restore()
	if not enabled:return {"enabled":false,"reason":"Map revision has not been qualified"}
	if not viewer.source_direct.state.available:return {"enabled":false,"reason":"Native shadow data unavailable"}
	if viewer.map_suns.is_empty():return {"enabled":false,"reason":"Authored sun unavailable"}
	if (viewer.camera.cull_mask&(1<<19))==0:return {"enabled":false,"reason":"Camera excludes the static world layer"}
	for sun in viewer.map_suns:
		if (sun.light_cull_mask&(1<<19))==0:return {"enabled":false,"reason":"Sun excludes the static world layer"}
	var stack:Array=[viewer.map_scene];var targets:Array=[];var unsupported:Array=[]
	while not stack.is_empty():
		var node:Node=stack.pop_back();stack.append_array(node.get_children())
		if not node is MeshInstance3D or node.mesh==null or node.skin!=null:continue
		if node.layers!=1:return {"enabled":false,"reason":"Map uses reserved render layers"}
		targets.append(node)
		if not node.is_visible_in_tree() or node.cast_shadow==GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY:continue
		for surface in range(node.mesh.get_surface_count()):
			var material:Material=node.get_active_material(surface)
			if material is StandardMaterial3D and material.shading_mode==BaseMaterial3D.SHADING_MODE_UNSHADED:continue
			if material is ShaderMaterial:
				if "unshaded" in material.shader.code:continue
				if material.get_shader_parameter("source_direct_enabled")==true and (material.get_shader_parameter("use_source_lightmap")==true or int(material.get_shader_parameter("probe_count"))>0):continue
			if unsupported.size()<8:unsupported.append(str(node.name))
	if not unsupported.is_empty():return {"enabled":false,"reason":"Unqualified static lighting receivers","examples":unsupported}
	for node in targets:
		changed_nodes.append([weakref(node),node.layers]);node.layers=1<<19
	for sun in viewer.map_suns:
		changed_suns.append([weakref(sun),sun.shadow_caster_mask]);sun.shadow_caster_mask=0x7ffff&sun.shadow_caster_mask
	return {"enabled":true,"static_meshes":targets.size(),"scope":"Qualified native static masks plus live actor shadows"}
