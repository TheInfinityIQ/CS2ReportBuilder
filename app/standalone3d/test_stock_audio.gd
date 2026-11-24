extends SceneTree

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	var player := preload("res://stock_audio.gd").new()
	root.add_child(player)
	var sample := AudioStreamWAV.new()
	sample.data = PackedByteArray([128,128,128,128])
	player.configure({"hurt":sample,"ambience":sample},[
		{"kind":"cue","sound":"hurt","tick":10,"position":[1,2,3]},
		{"kind":"cue","sound":"hurt","tick":20,"position":[1,2,3]}])
	player.emit_until(10)
	var ok:bool = player.played_count == 1 and player.ambience.playing
	player.reset(15)
	ok = ok and not player.ambience.playing
	player.emit_until(20)
	ok = ok and player.played_count == 2
	player.reset(15)
	player.enabled = false
	player.emit_until(20)
	ok = ok and player.played_count == 2 and not player.ambience.playing
	player.free()
	var listener := Camera3D.new()
	root.add_child(listener)
	var wall := StaticBody3D.new()
	root.add_child(wall)
	wall.position = Vector3(0,0,2.5)
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(3,3,1)
	shape.shape = box
	wall.add_child(shape)
	await physics_frame
	await physics_frame
	var spatial := preload("res://stock_audio.gd").new()
	root.add_child(spatial)
	spatial.configure({"hurt":sample},[{"kind":"cue","sound":"hurt","tick":10,"position":[200,0,0]}],listener)
	spatial.emit_until(10)
	ok = ok and spatial.voices[0].volume_db == -23
	spatial.free()
	wall.free()
	var floor_mesh := MeshInstance3D.new()
	var slab := BoxMesh.new()
	slab.size = Vector3(3,0.2,3)
	floor_mesh.mesh = slab
	var material := StandardMaterial3D.new()
	material.resource_name = "floor_metal_plate"
	floor_mesh.material_override = material
	root.add_child(floor_mesh)
	floor_mesh.position.y = -0.1
	floor_mesh.create_trimesh_collision()
	await physics_frame
	await physics_frame
	var surfaces := preload("res://stock_audio.gd").new()
	root.add_child(surfaces)
	surfaces.configure({"step":sample,"step:metal":sample,"ambience":sample,"zone:test":sample},[],listener,
		[{"sound":"zone:test","origin":[0,0,0],"radius":100}])
	ok = ok and surfaces.footstep_key(Vector3.ZERO) == "step:metal"
	ok = ok and surfaces.footstep_key(Vector3(10,0,0)) == "step"
	surfaces.emit_until(1)
	ok = ok and surfaces.ambient_key == "zone:test" and surfaces.ambience.playing
	listener.position.x = 10
	surfaces.emit_until(2)
	ok = ok and surfaces.ambient_key == "ambience" and surfaces.ambience.playing
	surfaces.free()
	floor_mesh.free()
	listener.free()
	var args := OS.get_cmdline_user_args()
	if not args.is_empty():
		var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
		if not data is Dictionary:
			quit(1)
			return
		var viewer := preload("res://main.gd").new()
		var bank: Dictionary = viewer._read_sound_bank(data.sounds)
		ok = ok and bank.size() == data.sounds.size() and data.events.size() > 0
		viewer.free()
		var recorded := preload("res://stock_audio.gd").new()
		root.add_child(recorded)
		var listener_recorded := Camera3D.new()
		root.add_child(listener_recorded)
		var declared: Array = data.get("zones",[])
		recorded.configure(bank, data.events, listener_recorded, declared)
		var witnessed: Dictionary = {}
		for event in data.events:
			if witnessed.has(event.sound):
				continue
			var tick: float = float(event.tick)
			recorded.reset(tick-1)
			recorded.emit_until(tick)
			var found := false
			for voice in recorded.voices:
				if voice.playing and voice.stream == bank.get(event.sound):
					found = true
			witnessed[event.sound] = found
			ok = ok and found
		var checked := 0
		for zone in declared:
			var p: Array = zone.origin
			listener_recorded.position = Vector3(p[1],p[2],p[0])*0.0254
			recorded.update_ambience()
			if recorded.ambient_key.begins_with("zone:") and recorded.ambience.playing:
				checked += 1
		ok = ok and checked == declared.size()
		print(JSON.stringify({"loaded":bank.size(),"cue_kinds":witnessed.size(),"zones_played":checked}))
		recorded.free()
		listener_recorded.free()
	print(JSON.stringify({"ok":ok}))
	quit(0 if ok else 1)
