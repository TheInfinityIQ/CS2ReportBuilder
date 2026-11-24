extends SceneTree

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var bank: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var result: Dictionary = {"dependencies": {}, "players": {}, "weapons": {}}
	for team in bank["players"]:
		var path := str(bank["players"][team])
		result["dependencies"][path] = Array(ResourceLoader.get_dependencies(path))
		var packed := load(path) as PackedScene
		var scene := packed.instantiate()
		var info := {"clips": [], "bones": [], "skeletons": [], "reload_tracks": []}
		_inspect(scene, info)
		result["players"][team] = info
		scene.free()
	for key in bank["weapons"]:
		var path := str(bank["weapons"][key]["scene"])
		result["dependencies"][path] = Array(ResourceLoader.get_dependencies(path))
		if key in ["glock", "ak47"]:
			var scene := (load(path) as PackedScene).instantiate()
			var info := {"clips": [], "bones": [], "skeletons": [], "reload_tracks": []}
			_inspect(scene, info)
			result["weapons"][key] = info
			scene.free()
	var output := FileAccess.open(args[1], FileAccess.WRITE)
	output.store_string(JSON.stringify(result))
	output.close()
	quit()

func _inspect(node: Node, info: Dictionary) -> void:
	if node is AnimationPlayer:
		info["clips"].append_array(Array(node.get_animation_list()))
		for clip in node.get_animation_list():
			if str(clip).ends_with("reload_glock"):
				var animation: Animation = node.get_animation(clip)
				for track in range(animation.get_track_count()): info["reload_tracks"].append(str(animation.track_get_path(track)))
				var samples: Array = []
				for track in range(animation.get_track_count()):
					if "glock18" not in str(animation.track_get_path(track)): continue
					var keys: Array = []
					for key in range(0, animation.track_get_key_count(track), maxi(1, animation.track_get_key_count(track) / 4)):
						keys.append([animation.track_get_key_time(track, key), str(animation.track_get_key_value(track, key))])
					samples.append({"path": str(animation.track_get_path(track)), "keys": keys})
				info["weapon_key_samples"] = samples
	if node is Skeleton3D:
		var all_bones: Array = []
		for bone in range(node.get_bone_count()):
			var name: String = node.get_bone_name(bone)
			all_bones.append(name)
			if "hand" in name.to_lower() or "weapon" in name.to_lower(): info["bones"].append(name)
		info["skeletons"].append({"name": str(node.name), "parent": str(node.get_parent().name), "bones": all_bones})
	for child in node.get_children(): _inspect(child, info)
