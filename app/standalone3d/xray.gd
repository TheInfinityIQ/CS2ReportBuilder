extends RefCounted
var roots:Dictionary={}
var updates:int=0

func attach(node:Node,material:ShaderMaterial) -> void:
	if node is MeshInstance3D and node.mesh!=null:
		for surface in range(node.mesh.get_surface_count()):
			var base:Material=node.get_active_material(surface)
			if base==null:continue
			if not base is ShaderMaterial:
				base=base.duplicate();node.set_surface_override_material(surface,base)
			base.next_pass=material
	for child in node.get_children():attach(child,material)

func update(root:Node3D,team:int,enabled:bool) -> void:
	if root==null:return
	updates+=1
	if updates%64==0:
		for id in roots.keys():
			if roots[id].root.get_ref()==null:roots.erase(id)
	var id:int=root.get_instance_id()
	if not enabled and not roots.has(id):return
	if not roots.has(id):
		var material:=ShaderMaterial.new();material.shader=preload("res://xray.gdshader");material.render_priority=12
		attach(root,material);roots[id]={"root":weakref(root),"material":material,"enabled":true}
	if roots[id].enabled!=enabled:
		attach(root,roots[id].material if enabled else null);roots[id].enabled=enabled
	var color:=Color("ffb36b") if team==2 else Color("69c7ff")
	color.a=.75 if enabled else 0
	roots[id].material.set_shader_parameter("outline_color",color)
