extends RefCounted

const INCH := 0.0254
var objects: Array[Dictionary] = []

static func point(value: Array) -> Vector3:
	return Vector3(value[1], value[2], value[0]) * INCH

static func read_authoring(asset: String, revision: String) -> Dictionary:
	var folder := asset.get_base_dir()
	var file_path := folder.get_base_dir().get_base_dir().path_join("environment").path_join(folder.get_file()).path_join("dynamic-authoring.json")
	var file := FileAccess.open(file_path, FileAccess.READ)
	if file == null or file.get_length() > 128*1024:
		return {}
	var data: Variant = JSON.parse_string(file.get_as_text())
	if not data is Dictionary or revision.is_empty() or data.get("schema") != 1 or data.get("map_revision") != revision:
		return {}
	return data

static func install(world: Node3D, authoring: Dictionary) -> Dictionary:
	if authoring.is_empty():
		return {}
	var candidates: Array[MeshInstance3D] = []
	var stack: Array[Node] = [world]
	while not stack.is_empty():
		var node: Node = stack.pop_back()
		stack.append_array(node.get_children())
		if node is MeshInstance3D and node.mesh != null and node.visible:
			candidates.append(node)
	var result: Array = []
	for object in authoring.get("objects", []):
		var asset := str(object.get("model","")).get_file().get_basename()
		var anchor := point(object.origin)
		if asset.is_empty():
			continue
		var matching := candidates.filter(func(mesh: MeshInstance3D) -> bool:
			var name := str(mesh.name)
			return (name.begins_with(asset+".") or name.begins_with(asset+"_")) and mesh.global_position.distance_to(anchor) <= 0.05)
		if matching.size() != 1:
			continue
		var visual: MeshInstance3D = matching[0]
		var faces := visual.mesh.get_faces()
		if faces.is_empty() or faces.size() > 180000:
			continue
		candidates.erase(visual)
		var body := StaticBody3D.new()
		body.name = "ReplayObject_%d" % result.size()
		visual.get_parent().add_child(body)
		body.global_transform = Transform3D(Basis.IDENTITY, anchor)
		visual.reparent(body, true)
		visual.name = "Visual"
		var collision := CollisionShape3D.new()
		collision.name = "Collision"
		var shape := ConcavePolygonShape3D.new()
		shape.set_faces(visual.transform*faces)
		collision.shape = shape
		body.add_child(collision)
		result.append({"node":str(world.get_path_to(body)),"kind":object.kind,"origin":object.origin,"angles":object.angles})
	return {"schema":1,"map_revision":authoring.map_revision,"objects":result}

func restore() -> void:
	for entry in objects:
		if is_instance_valid(entry.body):
			apply_state(entry, {})
	objects.clear()

func configure(world: Node3D, packed_collision: bool, replay: Dictionary) -> int:
	restore()
	# A packed whole-map collision mesh cannot release an individual object.
	if packed_collision or world == null:
		return 0
	var revision := str(replay.get("asset_info", {}).get("fingerprint", ""))
	var manifest: Dictionary = replay.get("dynamic_bindings", {})
	if revision.is_empty() or manifest.get("schema") != 1 or manifest.get("map_revision") != revision:
		return 0
	var records: Array = replay.get("recorded_world", [])
	var claimed: Dictionary = {}
	for binding in manifest.get("objects", []):
		var path := NodePath(str(binding.get("node", "")))
		if path.is_absolute() or path.get_subname_count() != 0 or claimed.has(path):
			continue
		var body := world.get_node_or_null(path) as StaticBody3D
		if body == null or not world.is_ancestor_of(body) or body.collision_layer == 0:
			continue
		var origin: Array = binding.get("origin", [])
		var kind := str(binding.get("kind", ""))
		var angles: Array = binding.get("angles", [])
		if origin.size() != 3 or kind not in ["CPropDoorRotating", "CBreakable", "CBreakableProp"]:
			continue
		if kind == "CPropDoorRotating" and angles.size() != 3:
			continue
		var anchor := point(origin)
		if body.global_position.distance_to(anchor) > 0.05:
			continue
		# Only a separately exported visual/collider pair may be changed.
		var mesh := body.get_node_or_null("Visual") as MeshInstance3D
		var shape := body.get_node_or_null("Collision") as CollisionShape3D
		if mesh == null or shape == null or shape.shape == null or shape.disabled:
			continue
		var handles: Dictionary = {}
		var samples: Array = []
		var valid := true
		for record in records:
			if record.get("kind") != kind:
				continue
			var handle := str(record.handle)
			if not handles.has(handle):
				handles[handle] = point(record.origin).distance_to(anchor) <= 0.05
			if not handles[handle]:
				continue
			if (not samples.is_empty() and int(samples[-1].tick) > int(record.tick)
					or kind == "CPropDoorRotating" and (absf(float(record.angles[0])-float(angles[0])) > 0.05
					or absf(float(record.angles[2])-float(angles[2])) > 0.05)):
				valid = false
				break
			if not samples.is_empty() and int(samples[-1].tick) == int(record.tick):
				if str(samples[-1].handle) != handle and not samples[-1].get("removed",false):
					valid = false
					break
				samples[-1] = record
				continue
			samples.append(record)
		if not valid or samples.is_empty():
			continue
		claimed[path] = true
		objects.append({"body":body,"mesh":mesh,"layer":body.collision_layer,
			"mask":body.collision_mask,"transform":body.global_transform,"visible":mesh.visible,
			"kind":kind,"states":samples,"origin":origin,"angles":angles,"last_index":-2})
	return objects.size()

func apply_state(entry: Dictionary, state: Dictionary) -> void:
	var body: StaticBody3D = entry.body
	var transform: Transform3D = entry.transform
	var broken: bool = not state.is_empty() and entry.kind != "CPropDoorRotating" and (int(state.life) != 0 or state.get("removed",false))
	if not state.is_empty() and entry.kind == "CPropDoorRotating":
		transform.origin += point(state.origin) - point(entry.origin)
		var angle := deg_to_rad(float(state.angles[1])-float(entry.angles[1]))
		transform.basis = Basis(Vector3.UP, angle) * transform.basis
	body.global_transform = transform
	entry.mesh.visible = entry.visible and not broken
	body.collision_layer = 0 if broken else entry.layer
	body.collision_mask = 0 if broken else entry.mask

func at_tick(tick: float) -> void:
	for entry in objects:
		var states: Array = entry.states
		var low := 0
		var high := states.size()
		while low < high:
			var middle := (low + high) / 2
			if float(states[middle].tick) <= tick:low = middle+1
			else:high = middle
		var index := low-1
		if index != entry.last_index:
			entry.last_index = index
			apply_state(entry, states[index] if index >= 0 else {})

func audio_events() -> Array:
	var events: Array = []
	for entry in objects:
		if entry.kind == "CPropDoorRotating":
			continue
		var mesh: MeshInstance3D = entry.mesh
		if mesh.mesh.get_surface_count() != 1:
			continue
		var material := mesh.mesh.surface_get_material(0)
		if material == null or "glass" not in material.resource_name.to_lower():
			continue
		var missing := false
		for state in entry.states:
			var removed: bool = state.get("removed",false) or int(state.life) != 0
			if removed and not missing:
				events.append({"kind":"cue","tick":state.tick,"sound":"glass_break","position":state.origin})
			missing = removed
	return events
