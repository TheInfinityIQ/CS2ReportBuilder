extends SceneTree
func _initialize() -> void:
	var pool=preload("res://static_material_pool.gd");var group:=Node3D.new();root.add_child(group)
	var shader:=Shader.new();shader.code="shader_type spatial;uniform float gain=1.0;void fragment(){ALBEDO=vec3(gain);}"
	var originals:Array=[];var meshes:Array=[]
	for value in [1.0,1.0,.5]:
		var material:=ShaderMaterial.new();material.shader=shader;material.resource_name="same";material.set_shader_parameter("gain",value)
		var node:=MeshInstance3D.new();node.mesh=QuadMesh.new();node.mesh.material=material;group.add_child(node);meshes.append(node);originals.append(material)
	var stats:Dictionary=pool.apply(group,true);var failures:Array=[]
	if stats.identical_materials_reused!=1 or meshes[0].get_active_material(0)!=meshes[1].get_active_material(0):failures.append("Equal immutable states were not shared")
	if meshes[0].get_active_material(0)==meshes[2].get_active_material(0):failures.append("Different uniform values were shared")
	var animated:=Shader.new();animated.code="shader_type spatial;uniform float demo_time;void fragment(){ALBEDO=vec3(demo_time);}"
	for material in originals:material.shader=animated
	for index in range(meshes.size()):meshes[index].set_surface_override_material(0,originals[index])
	stats=pool.apply(group,true)
	if stats.eligible_materials!=0:failures.append("Animated material was pooled")
	group.free();print(JSON.stringify({"ok":failures.is_empty(),"failures":failures}));quit(0 if failures.is_empty() else 1)
