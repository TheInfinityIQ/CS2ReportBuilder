extends SceneTree
func _initialize() -> void:run.call_deferred()
func run() -> void:
	var failures:Array=[];var group:=Node3D.new();root.add_child(group)
	var viewport:=SubViewport.new()
	if not viewport.get_property_list().any(func(item:Dictionary):return item.name=="mesh_lod_threshold"):failures.append("Installed Godot lacks the preparation LOD control")
	else:viewport.mesh_lod_threshold=0.0
	viewport.free()
	var environment:=Environment.new();environment.sky=Sky.new();environment.sky.radiance_size=Sky.RADIANCE_SIZE_128
	environment.sky.sky_material=ProceduralSkyMaterial.new()
	var warm:Environment=preload("res://utility_preparation.gd").preparation_environment(environment)
	warm.sky.radiance_size=Sky.RADIANCE_SIZE_64
	if environment.sky.radiance_size!=Sky.RADIANCE_SIZE_128:failures.append("Preparation changed the main sky radiance state")
	if warm.sky.sky_material!=environment.sky.sky_material:failures.append("Preparation duplicated authored sky assets")
	var shader:=Shader.new();shader.code="shader_type spatial;void fragment(){ALBEDO=vec3(1);}";var material:=ShaderMaterial.new();material.shader=shader
	var originals:Array=[]
	for count in [2,5]:
		var arrays:Array=[];arrays.resize(Mesh.ARRAY_MAX);var points:=PackedVector3Array()
		for triangle in range(count):points.append_array([Vector3(triangle,0,0),Vector3(triangle+1,0,0),Vector3(triangle,1,0)])
		arrays[Mesh.ARRAY_VERTEX]=points
		var mesh:=ArrayMesh.new();mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays);mesh.surface_set_material(0,material)
		var node:=MeshInstance3D.new();node.mesh=mesh;group.add_child(node);originals.append(node)
	var seeds:Array=preload("res://utility_preparation.gd").world_pipeline_seeds(group)
	if seeds.size()!=1 or seeds[0]!=originals[0]:failures.append("Warmup did not choose the smallest existing mesh for a shader/vertex format")
	if originals[0].mesh==null or originals[1].mesh==null or not originals[0].visible or originals[0].transform!=Transform3D.IDENTITY:failures.append("Warmup selection changed original map nodes")
	group.free();print(JSON.stringify({"ok":failures.is_empty(),"failures":failures}));quit(0 if failures.is_empty() else 1)
