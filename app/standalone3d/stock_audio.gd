extends Node3D

var streams: Dictionary = {}
var events: Array = []
var cursor := 0
var voices: Array[AudioStreamPlayer3D] = []
var enabled := true
var played_count := 0
var ambience: AudioStreamPlayer
var listener: Camera3D
var surface_pattern := RegEx.create_from_string("(?:^|[/._-])(metal|wood|dirt|gravel|grass|glass|tile)(?:$|[/._-])")
var zones: Array = []
var ambient_key := ""

func configure(bank: Dictionary, timeline: Array, camera:Camera3D=null, soundscapes:Array=[]) -> void:
	streams = bank
	events = timeline
	listener = camera
	zones = soundscapes
	if streams.has("ambience") or not zones.is_empty():
		ambience = AudioStreamPlayer.new()
		ambience.volume_db = -30
		ambience.finished.connect(func():if enabled and ambience.stream != null:ambience.play())
		add_child(ambience)
	for index in range(32):
		var voice := AudioStreamPlayer3D.new()
		voice.volume_db = -14
		voice.unit_size = 5
		voice.max_distance = 120
		add_child(voice)
		voices.append(voice)

func reset(tick: float) -> void:
	for voice in voices: voice.stop()
	if ambience != null and ambience.playing:ambience.stop()
	var low := 0
	var high := events.size()
	while low < high:
		var middle := (low + high) / 2
		if float(events[middle]["tick"]) <= tick: low = middle + 1
		else: high = middle
	cursor = low

func footstep_key(position: Vector3) -> String:
	if not is_inside_tree():
		return "step"
	var ray := PhysicsRayQueryParameters3D.create(position+Vector3.UP*0.25,position-Vector3.UP*0.45,1)
	var hit := get_world_3d().direct_space_state.intersect_ray(ray)
	if hit.is_empty():
		return "step"
	var collider: Node = hit.collider
	var mesh := collider.get_parent() as MeshInstance3D
	if mesh == null:
		mesh = collider.get_node_or_null("Visual") as MeshInstance3D
	if mesh == null or mesh.mesh == null:
		return "step"
	var key := ""
	for index in range(mesh.mesh.get_surface_count()):
		var material := mesh.mesh.surface_get_material(index)
		if material == null:
			material = mesh.get_active_material(index)
		if material == null:
			return "step"
		var name := (material.resource_name if not material.resource_name.is_empty() else material.resource_path).to_lower()
		var matched := surface_pattern.search(name)
		if matched == null:
			return "step"
		var surface := "step:"+matched.get_string(1)
		if not key.is_empty() and key != surface:
			return "step"
		key = surface
	return key if streams.has(key) else "step"

func update_ambience() -> void:
	if ambience == null:
		return
	if not enabled:
		ambience.stop()
		return
	var selected := "ambience"
	if listener != null:
		var closest := INF
		for zone in zones:
			var p: Array = zone.origin
			var distance := listener.global_position.distance_squared_to(Vector3(p[1],p[2],p[0])*0.0254)
			if distance < closest and distance <= pow(float(zone.radius)*0.0254,2) and streams.has(zone.sound):
				closest = distance
				selected = str(zone.sound)
	if ambient_key != selected:
		ambience.stop()
		ambient_key = selected
		ambience.stream = streams.get(selected)
	if ambience.stream != null and not ambience.playing:
		ambience.play()

func emit_until(tick: float) -> void:
	update_ambience()
	while cursor < events.size() and float(events[cursor]["tick"]) <= tick:
		var event: Dictionary = events[cursor]
		cursor += 1
		if not enabled: continue
		var point: Array = event["position"]
		var position := Vector3(point[1], point[2], point[0]) * 0.0254
		var key := ""
		match str(event["kind"]):
			"grenade", "cue": key = str(event.get("sound", ""))
			"weapon_fire": key = "fire:" + str(event["weapon"])
			"weapon_reload": key = "reload:" + str(event["weapon"])
			"player_footstep": key = footstep_key(position)
		if event["kind"] == "weapon_fire" and not event.get("silenced", false) and streams.has("fire_unsilenced:" + str(event["weapon"])):
			key = "fire_unsilenced:" + str(event["weapon"])
		if not streams.has(key): continue
		var voice: AudioStreamPlayer3D = null
		for candidate in voices:
			if not candidate.playing:
				voice = candidate
				break
		if voice == null: voice = voices[played_count % voices.size()]
		voice.stop()
		voice.stream = streams[key]
		voice.position = position
		voice.volume_db = -14
		if listener != null and listener.is_inside_tree():
			var source := voice.global_position + Vector3.UP * 0.15
			if listener.global_position.distance_squared_to(source) > 1.0:
				var query := PhysicsRayQueryParameters3D.create(listener.global_position,source,1)
				if not get_world_3d().direct_space_state.intersect_ray(query).is_empty():
					voice.volume_db -= 9
		voice.play()
		played_count += 1
