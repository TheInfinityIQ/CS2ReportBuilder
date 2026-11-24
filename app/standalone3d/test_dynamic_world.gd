extends SceneTree

func _initialize() -> void:
	run.call_deferred()

func prop(parent: Node3D, label: String, position: Vector3) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = label
	parent.add_child(body)
	body.position = position
	var visual := MeshInstance3D.new()
	visual.name = "Visual"
	visual.mesh = BoxMesh.new()
	body.add_child(visual)
	var collider := CollisionShape3D.new()
	collider.name = "Collision"
	collider.shape = BoxShape3D.new()
	body.add_child(collider)
	return body

func run() -> void:
	var world := Node3D.new()
	root.add_child(world)
	var window := prop(world, "Window", Vector3.ZERO)
	var door := prop(world, "Door", Vector3(0,0,2.54))
	var dynamic := preload("res://dynamic_world.gd").new()
	var data := {"asset_info":{"fingerprint":"fixture"},"dynamic_bindings":{
		"schema":1,"map_revision":"fixture","objects":[
			{"node":"Window","kind":"CBreakable","origin":[0,0,0]},
			{"node":"Door","kind":"CPropDoorRotating","origin":[100,0,0],"angles":[0,0,0]}
		]},"recorded_world":[
			{"tick":1,"handle":"8","kind":"CBreakable","origin":[0,0,0],"life":0},
			{"tick":1,"handle":"9","kind":"CPropDoorRotating","origin":[100,0,0],"angles":[0,0,0],"life":0},
			{"tick":5,"handle":"9","kind":"CPropDoorRotating","origin":[100,0,0],"angles":[0,90,0],"life":0},
			{"tick":6,"handle":"8","kind":"CBreakable","origin":[0,0,0],"life":2},
			{"tick":12,"handle":"10","kind":"CBreakable","origin":[0,0,0],"life":0}
		]}
	var ok := dynamic.configure(world, false, data) == 2
	dynamic.at_tick(7)
	ok = ok and window.collision_layer == 0 and not window.get_node("Visual").visible
	ok = ok and door.basis.z.is_equal_approx(Vector3.RIGHT) and door.collision_layer == 1
	dynamic.at_tick(12)
	ok = ok and window.collision_layer == 1 and window.get_node("Visual").visible
	dynamic.at_tick(2)
	ok = ok and door.basis.is_equal_approx(Basis.IDENTITY)
	ok = ok and window.collision_layer == 1 and window.get_node("Visual").visible
	dynamic.at_tick(7)
	ok = ok and dynamic.configure(world, true, data) == 0 and window.collision_layer == 1
	data.asset_info.fingerprint = "other"
	ok = ok and dynamic.configure(world, false, data) == 0
	world.free()
	var args := OS.get_cmdline_user_args()
	if args.size() >= 3:
		ok = verify_recording(args[0],args[1],args[2],args[3] if args.size()>=4 else "") and ok
	print(JSON.stringify({"ok":ok}))
	quit(0 if ok else 1)

func verify_recording(scene_path: String, authoring_path: String, recording_path: String, audio_path:String) -> bool:
	var scene := (load(scene_path) as PackedScene).instantiate() as Node3D
	root.add_child(scene)
	var authoring: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(authoring_path))
	var recording: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(recording_path))
	var adapter := preload("res://dynamic_world.gd").new()
	var bindings: Dictionary = adapter.install(scene,authoring)
	var count: int = adapter.configure(scene,false,{"asset_info":{"fingerprint": authoring.map_revision},
		"dynamic_bindings": bindings, "recorded_world": recording.worldRows})
	var moved := 0
	var restored := 0
	var breakables := 0
	var removed := 0
	for entry in adapter.objects:
		if entry.kind == "CBreakable":
			breakables += 1
			for index in range(1,entry.states.size()):
				var current: Dictionary = entry.states[index]
				var previous: Dictionary = entry.states[index-1]
				if not current.get("removed",false) or previous.get("removed",false) or current.tick <= previous.tick:
					continue
				adapter.at_tick(current.tick)
				var disabled: bool = not entry.mesh.visible and entry.body.collision_layer == 0
				adapter.at_tick(previous.tick)
				if disabled and entry.mesh.visible and entry.body.collision_layer == entry.layer:
					removed += 1
					break
			continue
		var opened: Array = entry.states.filter(func(state: Dictionary) -> bool:
			return state.door == "DOOR_STATE_OPEN")
		if opened.is_empty():
			continue
		adapter.at_tick(opened[0].tick)
		if not entry.body.global_basis.is_equal_approx(entry.transform.basis):
			moved += 1
		adapter.at_tick(0)
		if entry.body.global_transform.is_equal_approx(entry.transform):
			restored += 1
	var glass_cues: Array = adapter.audio_events()
	var glass_played := audio_path.is_empty()
	if not audio_path.is_empty() and not glass_cues.is_empty():
		var audio_data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(audio_path))
		var viewer := preload("res://main.gd").new()
		var bank: Dictionary = viewer._read_sound_bank(audio_data.sounds)
		viewer.free()
		var audio := preload("res://stock_audio.gd").new()
		root.add_child(audio)
		glass_cues.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:return a.tick < b.tick)
		audio.configure(bank,glass_cues)
		audio.reset(float(glass_cues[0].tick)-1)
		audio.emit_until(glass_cues[0].tick)
		glass_played = audio.played_count>0
		audio.free()
	print(JSON.stringify({"authored":authoring.objects.size(),"bound":count,"real_open":moved,
		"rewound":restored,"breakable_meshes":breakables,"real_removals_rewound":removed,"glass_cues":glass_cues.size(),"glass_played":glass_played}))
	adapter.restore()
	scene.free()
	return count == authoring.objects.size() and moved > 0 and restored == moved and breakables == 2 and removed == breakables and glass_cues.size() >= 2 and glass_played
