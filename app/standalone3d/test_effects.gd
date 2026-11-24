extends SceneTree
var failures:Array=[]
func check(value:bool,message:String) -> void:
	if not value:failures.append(message)
func _initialize() -> void:run.call_deferred()
func run() -> void:
	var effects=preload("res://source_effects.gd").new()
	var definition:Dictionary={"IntParams":{"F_ADDITIVE_BLEND":1,"F_DEPTH_FEATHER":1,"F_DO_NOT_CAST_SHADOWS":1,"F_RENDER_BACKFACES":1},"FloatParams":{"g_flFeatherDistance":20,"g_flOpacityScale":.75},"TextureParams":{"g_tMask1":"old/revision.vtex"}}
	effects.configure({"steam":definition},{})
	var original:=StandardMaterial3D.new();original.resource_name="steam"
	var mesh:=MeshInstance3D.new();mesh.mesh=QuadMesh.new();mesh.material_override=original
	# Surface overrides cannot supersede a whole-instance material override.
	mesh.material_override=null;mesh.mesh.material=original
	effects.apply_mesh(mesh);var material:Material=mesh.get_active_material(0)
	check(material is ShaderMaterial,"Source effects remained opaque PBR materials")
	check(material.shader.code.contains("blend_add"),"Authored additive blending ignored")
	check(is_equal_approx(material.get_shader_parameter("feather_distance"),.508),"Depth feather distance did not convert Source units")
	check(is_equal_approx(material.get_shader_parameter("opacity_scale"),.75),"Authored opacity ignored")
	check(mesh.cast_shadow==GeometryInstance3D.SHADOW_CASTING_SETTING_OFF,"Atmosphere sheet cast opaque shadows")
	check(effects.state.missing_masks==["old/revision.vtex"],"Unavailable historical mask silently replaced")
	effects.update_tick(12.5);check(material.get_shader_parameter("demo_time")==12.5,"Effect masks do not follow the demo clock")
	var other:=MeshInstance3D.new();other.mesh=mesh.mesh;effects.apply_mesh(other)
	check(other.get_active_material(0)==material,"Identical effect materials were duplicated per mesh")
	mesh.free();other.free()
	var args:=OS.get_cmdline_user_args()
	if args.size()==1:
		var fixture:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[0]))
		var data:Dictionary=effects.read_cache(fixture.map_asset,fixture.asset_info.fingerprint)
		check(data.has("steam_001") and data.steam_001.IntParams.F_ADDITIVE_BLEND==1,"Retained map steam definition was not recovered")
		check(effects.read_cache(fixture.map_asset,fixture.asset_info.fingerprint)==data,"Material metadata changed across cached reads")
	print(JSON.stringify({"ok":failures.is_empty(),"failures":failures}));quit(0 if failures.is_empty() else 1)
