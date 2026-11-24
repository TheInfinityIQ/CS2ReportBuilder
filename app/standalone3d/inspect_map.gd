extends SceneTree

var meshes := 0
var materials := 0
var textured := 0
var lights := 0

func _initialize() -> void:
	run.call_deferred()

func inspect(node: Node) -> void:
	if node is Light3D: lights += 1
	if node is MeshInstance3D and node.mesh != null:
		meshes += 1
		for surface in range(node.mesh.get_surface_count()):
			var material: Material = node.mesh.surface_get_material(surface)
			if material != null: materials += 1
			if material is BaseMaterial3D and material.albedo_texture != null: textured += 1
	for child in node.get_children(): inspect(child)

func run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size()!=2: quit(2); return
	var start := Time.get_ticks_usec()
	var dependencies := ResourceLoader.get_dependencies(args[0])
	var missing: Array = []
	var unsafe: Array = []
	var base: String = args[0].replace("\\","/").get_base_dir()+"/"
	for dependency in dependencies:
		var path: String = str(dependency).split("::")[-1]
		if not path.is_absolute_path(): path = base.path_join(path).simplify_path()
		if not path.replace("\\","/").begins_with(base): unsafe.append(path)
		if not FileAccess.file_exists(path): missing.append(path)
	var packed := ResourceLoader.load(args[0],"PackedScene",ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	var scene: Node = packed.instantiate() if packed != null else null
	if scene != null: inspect(scene)
	var result := {"ok":scene != null and meshes>0 and textured>0 and missing.is_empty() and unsafe.is_empty(),
		"meshes":meshes,"materials":materials,"textured_surfaces":textured,"lights":lights,
		"native_texture_parts":dependencies.size(),"missing_dependencies":missing,"unsafe_dependencies":unsafe,
		"read_instantiate_ms":(Time.get_ticks_usec()-start)/1000.0}
	var file := FileAccess.open(args[1],FileAccess.WRITE)
	if file != null: file.store_string(JSON.stringify(result));file.close()
	if scene != null: scene.free()
	quit(0 if result["ok"] else 1)
