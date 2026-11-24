extends RefCounted
var definitions:Dictionary={}
var roots:Dictionary={}
var state:Dictionary={"bound":0,"cloth":0,"skin":0}

func configure(data:Dictionary) -> void:
	for group in data.values():
		for material in group:definitions[str(material.resource).get_file().get_basename()]=material

func apply(root:Node) -> void:
	if root==null:return
	var id:int=root.get_instance_id()
	if roots.has(id) and roots[id].get_ref()!=null:return
	bind(root);roots[id]=weakref(root)
	if roots.size()>64:
		for old in roots.keys():
			if roots[old].get_ref()==null:roots.erase(old)

func bind(node:Node) -> void:
	if node is MeshInstance3D and node.mesh!=null:
		for i in range(node.mesh.get_surface_count()):
			var material:Material=node.get_active_material(i)
			if not material is ShaderMaterial:continue
			var name:String=material.resource_name.get_file().get_basename()
			if not definitions.has(name):continue
			var definition:Dictionary=definitions[name]
			if definition.shader!="csgo_character.vfx":continue
			var cloth:bool=definition.ints.get("F_CLOTH_SHADING",0)==1
			var skin:bool=definition.ints.get("F_SUBSURFACE_SCATTERING",0)==1
			material.set_shader_parameter("roughness_floor",.6 if cloth else (.38 if skin else .04))
			material.set_shader_parameter("cloth_sheen",float(definition.floats.get("g_flSheenScale",.0)) if cloth else 0.0)
			material.set_shader_parameter("metalness",float(definition.floats.get("g_flMetalness",0.0)))
			state.bound+=1;state.cloth+=int(cloth);state.skin+=int(skin)
	for child in node.get_children():bind(child)
