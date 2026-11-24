extends SceneTree

class TestViewer extends Node:
	var map_scene:Node3D
	var source_direct:Dictionary={"natives":[]}

var failures:Array=[]
func check(condition:bool,message:String) -> void:
	if not condition:failures.append(message)

func mesh(name:String,material:Material,shadows:int) -> MeshInstance3D:
	var shape:=BoxMesh.new();var geometry:=ArrayMesh.new()
	geometry.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,shape.surface_get_arrays(0))
	geometry.surface_set_material(0,material)
	var instance:=MeshInstance3D.new();instance.name=name;instance.mesh=geometry;instance.cast_shadow=shadows
	return instance

func _initialize() -> void:run.call_deferred()
func run() -> void:
	var args:PackedStringArray=OS.get_cmdline_user_args()
	if args.is_empty():quit(2);return
	var directory:String=args[0];DirAccess.make_dir_recursive_absolute(directory)
	var viewer:=TestViewer.new();root.add_child(viewer)
	viewer.map_scene=Node3D.new();viewer.add_child(viewer.map_scene)
	var wall:=StandardMaterial3D.new();wall.resource_name="wall"
	var effect:=StandardMaterial3D.new();effect.resource_name="steam_001"
	var glass:=ShaderMaterial.new();glass.resource_name="glass";glass.shader=Shader.new();glass.shader.code="shader_type spatial;void fragment(){ALBEDO=vec3(1.0);ALPHA=0.5;}"
	var solid:=mesh("Solid",wall,GeometryInstance3D.SHADOW_CASTING_SETTING_ON)
	var no_shadow:=mesh("NoShadow",wall,GeometryInstance3D.SHADOW_CASTING_SETTING_OFF)
	var ambient:=mesh("Effect",effect,GeometryInstance3D.SHADOW_CASTING_SETTING_OFF)
	var overlay:=mesh("Overlay",glass,GeometryInstance3D.SHADOW_CASTING_SETTING_OFF)
	for node in [solid,no_shadow,ambient,overlay]:viewer.map_scene.add_child(node)
	var light:=OmniLight3D.new();viewer.add_child(light);viewer.source_direct.natives.append(light)
	var nodes:=PackedByteArray();nodes.resize(12);nodes.encode_u32(0,1);nodes.encode_u32(4,0);nodes.encode_u32(8,1)
	var regions:=PackedByteArray();regions.resize(8);regions.encode_u32(0,1);regions.encode_u32(4,0)
	var masks:=PackedByteArray();masks.resize(8);masks.fill(255)
	var rows:=PackedByteArray();rows.resize(4096);rows.fill(0)
	var pvs:=PackedByteArray();pvs.resize(512*4098);pvs.fill(0)
	var manifest:Dictionary={"schema":2,"algorithm":2,"clusters":4096,"row_bytes":1,"nodes":1,"regions":1,"masks":1,"min":[0,0,0],"max":[16,16,16],"objects":["Solid","NoShadow","Effect","Overlay","!light:0"],"opaque_materials":["wall","glass"],"probes":[{"point":[8,8,8],"pvs":Marshalls.raw_to_base64(pvs.slice(512,1024))},{"point":[32,32,32],"pvs":null}]}
	var payload:Dictionary={"manifest":manifest,"nodes.bin":nodes,"regions.bin":regions,"masks.bin":masks,"object-visibility.bin":rows,"pvs.bin":pvs}
	var helper=preload("res://world_visibility.gd").new()
	check(helper.configure(viewer,payload),"Valid native point probes should enable culling")
	var displaced_material:=ShaderMaterial.new();displaced_material.resource_name="wall";displaced_material.shader=Shader.new()
	displaced_material.shader.code="shader_type spatial;void vertex(){VERTEX += vec3(0.0,0.2,0.0);}void fragment(){ALBEDO=vec3(1.0);}"
	var displaced:=mesh("Displaced",displaced_material,GeometryInstance3D.SHADOW_CASTING_SETTING_OFF)
	check(not helper.opaque_static(displaced),"Vertex-displaced geometry must retain full drawing regardless of shader whitespace");displaced.free()
	helper.update(Vector3.ONE*.2032)
	check(solid.visible and solid.cast_shadow==GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY,"Hidden geometry must retain its shadow casting")
	check(not no_shadow.visible,"Hidden non-caster should stop drawing")
	check(ambient.visible and overlay.visible,"Opaque-imported effects and transparent shaders must remain visible")
	check(not light.visible,"Unseen bounded light should stop drawing")
	check(helper.state.hidden_meshes==2 and helper.state.hidden_lights==1,"Packed visibility changes must count eligible objects")
	var updates:int=helper.state.updates;helper.update(Vector3.ONE*.2033)
	check(helper.state.updates==updates,"Unchanged cells must not resubmit scene mutations")
	helper.update(Vector3.ONE*10000)
	check(solid.cast_shadow==GeometryInstance3D.SHADOW_CASTING_SETTING_ON and no_shadow.visible and light.visible,"Unknown camera regions must restore full rendering")
	helper.update(Vector3.ONE*.2032)
	check(not helper.configure(viewer,{}),"Missing cache must disable optimization")
	check(no_shadow.visible and solid.cast_shadow==GeometryInstance3D.SHADOW_CASTING_SETTING_ON,"Replacing a cache must restore the previous scene")
	manifest["files"]={}
	for name in ["nodes.bin","regions.bin","masks.bin","object-visibility.bin","pvs.bin"]:
		var bytes:PackedByteArray=payload[name];var file:=FileAccess.open(directory.path_join(name),FileAccess.WRITE);file.store_buffer(bytes);file.close()
		manifest.files[name]=FileAccess.get_sha256(directory.path_join(name))
	var header:=FileAccess.open(directory.path_join("manifest.json"),FileAccess.WRITE);header.store_string(JSON.stringify(manifest));header.close()
	check(not helper.read_cache(directory.path_join("manifest.json")).is_empty(),"A complete hashed cache should load")
	var corrupt:=FileAccess.open(directory.path_join("masks.bin"),FileAccess.WRITE);corrupt.store_8(0);corrupt.close()
	check(helper.read_cache(directory.path_join("manifest.json")).is_empty(),"Corrupt visibility must fail open to full drawing")
	if args.size()>1:
		var fixture:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[1]))
		check(not helper.read_for_map(fixture.map_asset,fixture.native_scene,fixture.asset_info.fingerprint).is_empty(),"Published real-map companion should load through the production selector")
		check(helper.read_for_map(fixture.map_asset,fixture.native_scene,fixture.asset_info.fingerprint+"updated").is_empty(),"Updated installed map revisions must disable the previous companion")
	var result:=FileAccess.open(directory.path_join("result.json"),FileAccess.WRITE);result.store_string(JSON.stringify({"ok":failures.is_empty(),"failures":failures}));result.close()
	print(JSON.stringify({"ok":failures.is_empty(),"failures":failures}));viewer.free();quit(0 if failures.is_empty() else 1)
