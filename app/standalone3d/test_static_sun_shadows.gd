extends SceneTree
class Viewer extends Node:
	var source_direct:Node
	var map_scene:Node3D
	var camera:Camera3D
	var map_suns:Array=[]
class Direct extends Node:
	var state:Dictionary={"available":true}
func _initialize() -> void:
	var adapter=preload("res://static_sun_shadows.gd").new();var failures:Array=[]
	if not adapter.qualified({"map":"de_anubis","asset_info":{"fingerprint":adapter.ANUBIS_REVISION}}) or adapter.qualified({"map":"de_nuke","asset_info":{"fingerprint":adapter.ANUBIS_REVISION}}) or adapter.qualified({"map":"de_anubis","asset_info":{"fingerprint":"new"}}):failures.append("Revision qualification is not exact")
	var viewer:=Viewer.new();root.add_child(viewer);viewer.source_direct=Direct.new();viewer.add_child(viewer.source_direct)
	viewer.map_scene=Node3D.new();viewer.add_child(viewer.map_scene);viewer.camera=Camera3D.new();viewer.add_child(viewer.camera)
	var sun:=DirectionalLight3D.new();viewer.add_child(sun);viewer.map_suns.append(sun);var original_mask:int=sun.shadow_caster_mask
	var node:=MeshInstance3D.new();node.mesh=BoxMesh.new();viewer.map_scene.add_child(node)
	var shader:=Shader.new();shader.code="shader_type spatial;uniform bool source_direct_enabled;uniform bool use_source_lightmap;void fragment(){ALBEDO=vec3(1);}"
	var material:=ShaderMaterial.new();material.shader=shader;material.set_shader_parameter("source_direct_enabled",true);material.set_shader_parameter("use_source_lightmap",true);node.material_override=material
	var result:Dictionary=adapter.configure(viewer,true)
	if not result.enabled or node.layers!=1<<19 or (sun.shadow_caster_mask&(1<<19))!=0 or (sun.shadow_caster_mask&1)==0:failures.append("Static and dynamic shadow layers are not separated")
	result=adapter.configure(viewer,true)
	if not result.enabled:failures.append("Reopening the same map did not restore/requalify its layers")
	adapter.configure(viewer,false)
	if node.layers!=1 or sun.shadow_caster_mask!=original_mask:failures.append("Disabling did not restore original render states")
	node.material_override=StandardMaterial3D.new();result=adapter.configure(viewer,true)
	if result.enabled or node.layers!=1:failures.append("Unqualified lighting receiver lost geometry shadows")
	viewer.free();print(JSON.stringify({"ok":failures.is_empty(),"failures":failures}));quit(0 if failures.is_empty() else 1)
