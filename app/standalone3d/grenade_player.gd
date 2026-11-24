extends Node3D

const UNIT := 0.0254
const SmokeShader := preload("res://smoke_volume.gdshader")
const FireShader := preload("res://fire_patch.gdshader")
var recording: Dictionary = {}
var scenes: Dictionary = {}
var streams: Dictionary = {}
var projectiles: Dictionary = {}
var effects: Dictionary = {}
var active_projectiles: Array = []
var active_effects: Array = []
var throw_cursor := 0
var effect_cursor := 0
var last_tick := -1000000.0
var rate := 64.0
var enabled := true
var flash_enabled := true
var flash_overlay: ColorRect
var camera: Camera3D
var sounds_enabled := true
var rendered_patches := 0
var rendered_voxels := 0
var particle_textures:Dictionary={}
var particle_frames:Dictionary={}
var owner_teams:Dictionary={}
var detail_noise:ImageTexture3D
var blast_events:Array=[]
var bullet_events:Array=[]
var bullet_ends:Dictionary={}
const SMOKE_VOLUME_LIMIT:int=32
var smoke_volumes:Dictionary={}
var smoke_volume_order:Array[String]=[]
var smoke_volume_uploads:int=0

func smoke_bullets(tick:float,center:Vector3) -> Array:
	var starts:=PackedVector4Array();var ends:=PackedVector4Array()
	for index in range(_upper(bullet_events,tick,"tick")-1,-1,-1):
		var shot:Dictionary=bullet_events[index];var age:float=(tick-float(shot.tick))/rate
		if age>.28 or starts.size()==4:break
		var origin:Vector3=world(shot.origin)
		var pitch:float=deg_to_rad(float(shot.angles[0]));var yaw:float=deg_to_rad(float(shot.angles[1]))
		var direction:=Vector3(sin(yaw)*cos(pitch),-sin(pitch),cos(yaw)*cos(pitch))
		var along:float=(center-origin).dot(direction)
		if along< -5 or along>100 or (origin+direction*maxf(0,along)).distance_to(center)>6:continue
		if not bullet_ends.has(index):
			var end:Vector3=origin+direction*100
			# Use the prepared map to stop cosmetic clearing at walls. This does
			# not turn a nominal aim ray into an authoritative demo impact.
			if is_inside_tree():
				# Player-only clip brushes constrain the chase camera, not bullets.
				var query:=PhysicsRayQueryParameters3D.create(origin,end);query.collision_mask=1
				var hit:Dictionary=get_world_3d().direct_space_state.intersect_ray(query)
				if hit.has("position"):end=hit.position
			bullet_ends[index]=end
		var endpoint:Vector3=bullet_ends[index]
		if endpoint.distance_to(origin)<maxf(0,along-5):continue
		starts.append(Vector4(origin.x,origin.y,origin.z,.14*(1.0-smoothstep(.04,.28,age))))
		ends.append(Vector4(endpoint.x,endpoint.y,endpoint.z,0))
	while starts.size()<4:starts.append(Vector4.ZERO);ends.append(Vector4.ZERO)
	return [starts,ends]

func _smoke_noise() -> ImageTexture3D:
	if detail_noise!=null:return detail_noise
	var layers:Array[Image]=[];var state:int=918273
	for z in range(32):
		var pixels:=PackedByteArray();pixels.resize(32*32)
		for i in range(pixels.size()):
			state=(state*1664525+1013904223)&0xffffffff;pixels[i]=(state>>24)&255
		layers.append(Image.create_from_data(32,32,false,Image.FORMAT_R8,pixels))
	detail_noise=ImageTexture3D.new()
	if detail_noise.create(Image.FORMAT_R8,32,32,32,false,layers)!=OK:detail_noise=null
	return detail_noise

static func smoke_tint(team:int) -> Color:
	# Display approximation calibrated against the accepted native reference;
	# this is not a claim to reproduce Valve's particle-lighting shader.
	# Input is before the authored tone curve. The old display-space tint
	# became too bright once Source post-processing was restored.
	return Color(.48,.37,.28) if team==2 else (Color(.36,.41,.47) if team==3 else Color(.40,.40,.40))

func configure(data: Dictionary, bank: Dictionary, sounds: Dictionary, view: Camera3D, overlay: ColorRect,images:Dictionary={},counts:Dictionary={}) -> void:
	for node in projectiles.values():node.free()
	for node in effects.values():node.free()
	projectiles.clear();effects.clear();active_projectiles.clear();active_effects.clear()
	throw_cursor=0;effect_cursor=0;last_tick=-1000000
	smoke_volumes.clear();smoke_volume_order.clear();smoke_volume_uploads=0;bullet_ends.clear()
	bullet_events=[];owner_teams={}
	recording = data
	scenes = bank
	streams = sounds
	camera = view
	flash_overlay = overlay
	rate = float(data.get("tickrate", 64))
	particle_textures=images;particle_frames=counts
	blast_events=data.get("effects",[]).filter(func(event:Dictionary):return event.kind=="he")

func smoke_blasts(tick:float,center:Vector3) -> Array[Vector4]:
	var holes:Array[Vector4]=[]
	for index in range(_upper(blast_events,tick)-1,-1,-1):
		var event:Dictionary=blast_events[index];var age:float=(tick-float(event.start))/rate
		if age>3.2:break
		var position:Vector3=world(event.position)
		if position.distance_to(center)>8:continue
		var radius:float=3.1*smoothstep(0.0,.10,age)*(1.0-smoothstep(1.0,3.2,age))
		holes.append(Vector4(position.x,position.y,position.z,radius))
		if holes.size()==2:break
	return holes

func world(point: Array) -> Vector3:
	return Vector3(float(point[1]), float(point[2]), float(point[0])) * UNIT

func _upper(items: Array, tick: float, key: String = "start") -> int:
	var low := 0
	var high := items.size()
	while low < high:
		var mid := (low + high) / 2
		if float(items[mid][key]) <= tick: low = mid + 1
		else: high = mid
	return low

func _reset(tick: float) -> void:
	active_projectiles.clear()
	active_effects.clear()
	var throws: Array = recording.get("throws", [])
	var events: Array = recording.get("effects", [])
	throw_cursor = _upper(throws, tick)
	effect_cursor = _upper(events, tick)
	for i in range(throw_cursor):
		if float(throws[i]["end"]) > tick: active_projectiles.append(throws[i])
	for i in range(effect_cursor):
		if float(events[i]["end"]) > tick: active_effects.append(events[i])
	# Reconstruct evidence first, then retain the intersection. Seeking within
	# the same smoke used to destroy and re-upload its texture and rebuild every
	# projectile/effect hierarchy, even when the target frame was unchanged.
	var wanted:Dictionary={}
	for item in active_projectiles:wanted[str(item.id)]=true
	for id in projectiles.keys():
		if not wanted.has(str(id)):projectiles[id].free();projectiles.erase(id)
	wanted.clear()
	for item in active_effects:wanted[str(item.id)]=true
	for id in effects.keys():
		if not wanted.has(str(id)):effects[id].free();effects.erase(id)

func _advance(tick: float) -> void:
	if tick < last_tick or tick-last_tick > rate*.5:
		_reset(tick)
	else:
		var throws: Array = recording.get("throws", [])
		while throw_cursor < throws.size() and float(throws[throw_cursor]["start"]) <= tick:
			if float(throws[throw_cursor]["end"]) > tick: active_projectiles.append(throws[throw_cursor])
			throw_cursor += 1
		var events: Array = recording.get("effects", [])
		while effect_cursor < events.size() and float(events[effect_cursor]["start"]) <= tick:
			if float(events[effect_cursor]["end"]) > tick: active_effects.append(events[effect_cursor])
			effect_cursor += 1
	last_tick = tick
	for i in range(active_projectiles.size()-1, -1, -1):
		var item: Dictionary = active_projectiles[i]
		if float(item["end"]) <= tick:
			if projectiles.has(item["id"]): projectiles[item["id"]].free(); projectiles.erase(item["id"])
			active_projectiles.remove_at(i)
	for i in range(active_effects.size()-1, -1, -1):
		var item: Dictionary = active_effects[i]
		if float(item["end"]) <= tick:
			if effects.has(item["id"]): effects[item["id"]].free(); effects.erase(item["id"])
			active_effects.remove_at(i)

func path_position(item: Dictionary, tick: float) -> Vector3:
	var path: Array = item["path"]
	var low := 0
	var high := path.size()
	while low < high:
		var mid := (low + high) / 2
		if float(path[mid][0]) <= tick: low = mid+1
		else: high = mid
	var a: Array = path[maxi(0,low-1)]
	var b: Array = path[mini(path.size()-1,low)]
	var fraction := clampf((tick-float(a[0]))/maxf(1,float(b[0])-float(a[0])),0,1)
	return world(a.slice(1)).lerp(world(b.slice(1)),fraction)

func _projectile(item: Dictionary) -> Node3D:
	var root := Node3D.new()
	add_child(root)
	if scenes.has(item["kind"]):
		var model: Node3D = scenes[item["kind"]].instantiate()
		root.add_child(model)
	else:
		var mesh := MeshInstance3D.new()
		var sphere := SphereMesh.new()
		sphere.radius = .045
		sphere.height = .09
		mesh.mesh = sphere
		root.add_child(mesh)
	projectiles[item["id"]] = root
	return root

func _solid(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = .9
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material

func _effect(item: Dictionary) -> Node3D:
	var root := Node3D.new()
	root.position = world(item["position"])
	root.set_meta("frame",-2)
	add_child(root)
	var mesh := MeshInstance3D.new()
	mesh.name = "Shape"
	root.add_child(mesh)
	var kind := str(item["kind"])
	if kind == "smoke":
		var box := BoxMesh.new()
		box.size = Vector3.ONE * 384 * UNIT
		mesh.mesh = box
		var material := ShaderMaterial.new()
		material.shader = SmokeShader
		# Integrate the smoke after other transparent effects, so flames and
		# muzzle sprites behind an opaque cloud cannot be composited on top.
		material.render_priority=5
		var noise:=_smoke_noise()
		material.set_shader_parameter("has_detail",noise!=null)
		if noise!=null:material.set_shader_parameter("detail_noise",noise)
		material.set_shader_parameter("box_min", root.position - box.size*.5)
		material.set_shader_parameter("box_size",box.size)
		mesh.material_override = material
		mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	elif kind == "fire":
		mesh.visible = false
		var flames := MultiMeshInstance3D.new()
		flames.name = "Flames"
		var multi := MultiMesh.new()
		multi.transform_format = MultiMesh.TRANSFORM_3D
		multi.use_custom_data = true
		var shape := QuadMesh.new()
		shape.size = Vector2(.78,.96)
		multi.mesh = shape
		flames.multimesh = multi
		var material := ShaderMaterial.new()
		material.shader = FireShader
		material.set_shader_parameter("flames",particle_textures.get("fire"))
		material.set_shader_parameter("use_layers",particle_textures.has("fire_layers"))
		if particle_textures.has("fire_layers"):material.set_shader_parameter("flame_layers",particle_textures.fire_layers)
		material.set_shader_parameter("frame_count",int(particle_frames.get("fire",1)))
		var sequences:Array=particle_frames.get("fire_sequences",[])
		if not sequences.is_empty():
			var ranges:=PackedVector2Array()
			for index in range(8):
				var sequence:Array=sequences[index%sequences.size()];ranges.append(Vector2(sequence[0],sequence[1]))
			material.set_shader_parameter("sequence_ranges",ranges);material.set_shader_parameter("sequence_count",mini(8,sequences.size()))
		material.set_shader_parameter("source_frames",particle_textures.has("fire"))
		flames.material_override = material
		flames.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		root.add_child(flames)
	else:
		var sphere := SphereMesh.new()
		sphere.radius = .5
		sphere.height = 1
		sphere.radial_segments = 16
		sphere.rings = 8
		mesh.mesh = sphere
		mesh.material_override = _solid(Color(1,.47,.12,.6) if kind == "he" else Color(1,1,.86,.8))
		mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	if kind == "decoy" and scenes.has("decoy"):
		mesh.visible = false
		root.add_child(scenes["decoy"].instantiate())
	if kind in ["he", "flash", "fire"]:
		var light := OmniLight3D.new()
		light.name = "Glow"
		light.position.y = .5
		light.light_color = Color(1,.38,.08) if kind != "flash" else Color(1,.95,.8)
		light.omni_range = 5 if kind == "fire" else 7
		light.shadow_enabled = false
		root.add_child(light)
	if kind in ["smoke","fire"] and streams.has("loop:"+kind):
		var voice := AudioStreamPlayer3D.new()
		voice.name = "Loop"
		voice.stream = streams["loop:"+kind]
		voice.volume_db = -21
		voice.unit_size = 4
		voice.max_distance = 80
		root.add_child(voice)
	effects[item["id"]] = root
	return root

func _smoke_frame(root: Node3D, item: Dictionary, frame: Dictionary, index:int=-1) -> void:
	var key:String=str(item.id)+":"+("i"+str(index) if index>=0 else "t"+str(frame.get("tick","fallback")))
	var cached:Dictionary=smoke_volumes.get(key,{})
	var mesh := root.get_node("Shape") as MeshInstance3D
	var material := mesh.material_override as ShaderMaterial
	if cached.is_empty():
		cached=_smoke_volume(frame);smoke_volumes[key]=cached
		smoke_volume_uploads+=1
	smoke_volume_order.erase(key);smoke_volume_order.append(key)
	while smoke_volume_order.size()>SMOKE_VOLUME_LIMIT:smoke_volumes.erase(smoke_volume_order.pop_front())
	material.set_shader_parameter("occupancy",cached.texture)
	var size:=Vector3.ONE*float(frame.get("cell",12))*float(frame.get("grid",32))*UNIT
	if frame.has("origin"):
		root.position=world(frame.origin)+size*.5
	elif frame.has("position"): root.position = world(frame["position"])
	(mesh.mesh as BoxMesh).size=size
	material.set_shader_parameter("box_size",size)
	material.set_shader_parameter("box_min",root.position-size*.5)
	root.set_meta("voxels",cached.voxels)

func _smoke_volume(frame:Dictionary) -> Dictionary:
	var pixels := PackedByteArray()
	pixels.resize(32*32*32)
	if frame.has("occupied"):
		var runs: Array = frame["occupied"]
		for i in range(0,runs.size(),2):
			for j in range(int(runs[i]), mini(pixels.size(),int(runs[i])+int(runs[i+1]))): pixels[j] = 255
	else:
		# Missing geometry stays visibly approximate, never an invented HE hole.
		for z in range(32):
			for y in range(32):
				for x in range(32):
					if Vector3(x-16,y-16,z-17).length() < 12: pixels[x+y*32+z*1024] = 255
	var layers: Array[Image] = []
	for z in range(32): layers.append(Image.create_from_data(32,32,false,Image.FORMAT_R8,pixels.slice(z*1024,(z+1)*1024)))
	var volume := ImageTexture3D.new()
	volume.create(Image.FORMAT_R8,32,32,32,false,layers)
	return {"texture":volume,"voxels":pixels.count(255)}

func _fire_frame(root: Node3D, frame: Dictionary) -> void:
	var multi: MultiMesh = root.get_node("Flames").multimesh
	var patches: Array = frame.get("patches", []).duplicate()
	# Alpha-blended instances also need a stable draw order. Reordering a
	# network list must not change compositing between surviving flame sheets.
	patches.sort_custom(func(a:Array,b:Array):
		for axis in range(3):
			if a[axis]!=b[axis]:return a[axis]<b[axis]
		return false)
	if root.has_meta("fire_patches") and root.get_meta("fire_patches")==patches:return
	root.set_meta("fire_patches",patches.duplicate(true))
	root.set_meta("fire_buffer_updates",int(root.get_meta("fire_buffer_updates",0))+1)
	# Shrinking/revisiting an inferno must not free and reallocate its GPU
	# instance buffer. Only grow capacity; visibility is the recorded count.
	var needed:int=patches.size()*3
	if needed>multi.instance_count:
		var capacity:int=maxi(3,multi.instance_count)
		while capacity<needed:capacity*=2
		multi.instance_count=capacity
		root.set_meta("fire_buffer_allocations",int(root.get_meta("fire_buffer_allocations",0))+1)
	multi.visible_instance_count=needed
	var bounds:=AABB();var have_bounds:bool=false
	for i in range(patches.size()):
		var point:Array=patches[i]
		# Source positions, not list indices, own a patch's identity. Network
		# additions/removals and backward seeks cannot reshuffle its variation.
		var identity:=Vector3(roundf(float(point[0])*8),roundf(float(point[1])*8),roundf(float(point[2])*8))
		var patch_seed:int=posmod(hash(identity),1048573)
		for layer in range(3):
			var seed:int=posmod(patch_seed+layer*104729,1048573)
			var angle:float=float(patch_seed)/1048573.0*TAU+float(layer)*TAU/3
			var local := world(patches[i])-root.position+Vector3(sin(angle)*.10,.47,cos(angle)*.10)
			multi.set_instance_transform(i*3+layer,Transform3D(Basis.IDENTITY,local))
			multi.set_instance_custom_data(i*3+layer,Color(float(seed)/1048573.0,0,0,1))
			var extent:=Vector3(.56,.50,.56)
			var box:=AABB(local-extent,extent*2)
			bounds=bounds.merge(box) if have_bounds else box;have_bounds=true
	# The vertex shader rotates each quad toward the camera. Its original
	# zero-depth mesh bounds do not enclose the rendered flame at side angles.
	multi.custom_aabb=bounds if have_bounds else AABB(Vector3.ZERO,Vector3.ONE*.001)
	root.set_meta("patches",patches.size())

func update_tick(tick: float, player: String, mode: int, audible: bool) -> void:
	_advance(tick)
	visible = enabled
	rendered_patches = 0
	rendered_voxels = 0
	for item in active_projectiles:
		var node: Node3D = projectiles.get(item["id"])
		if node == null: node = _projectile(item)
		node.position = path_position(item,tick)
		# The parser has positions, not networked angular orientation. Cosmetic spin only.
		node.rotation = Vector3((tick-float(item["start"]))/rate*6,0,(tick-float(item["start"]))/rate*3)
	for item in active_effects:
		var root: Node3D = effects.get(item["id"])
		if root == null: root = _effect(item)
		var frames: Array = item.get("frames",[])
		var index := _upper(frames,tick,"tick")-1
		var frame: Dictionary = frames[index] if index >= 0 else {}
		if int(root.get_meta("frame")) != index:
			if item["kind"] == "smoke": _smoke_frame(root,item,frame,index)
			elif item["kind"] == "fire":
				_fire_frame(root,frame if not frames.is_empty() else {"patches":[item["position"]]})
			root.set_meta("frame",index)
		var age := (tick-float(item["start"]))/rate
		var remaining := (float(item["end"])-tick)/rate
		var fire_opacity:float=smoothstep(0.0,.18,age)*smoothstep(0.0,.35,remaining)
		var mesh := root.get_node("Shape") as MeshInstance3D
		if item["kind"] == "smoke":
			var material := mesh.material_override as ShaderMaterial
			var palette:String=str(item.get("recorded_palette",""))
			var recorded_team:int=2 if palette=="warm" else (3 if palette=="cool" else 0)
			material.set_shader_parameter("smoke_color",smoke_tint(recorded_team if recorded_team in [2,3] else int(owner_teams.get(str(item.get("owner","")),0))))
			material.set_shader_parameter("demo_time",tick/rate)
			material.set_shader_parameter("bloom",smoothstep(0.0,1.25,age))
			material.set_shader_parameter("opacity", minf(1,remaining/1.0) if frame.get("fading",false) else 1.0)
			var blasts:Array[Vector4]=smoke_blasts(tick,world(item.position))
			material.set_shader_parameter("blast_a",blasts[0] if blasts.size()>0 else Vector4.ZERO)
			material.set_shader_parameter("blast_b",blasts[1] if blasts.size()>1 else Vector4.ZERO)
			var bullets:Array=smoke_bullets(tick,world(item.position))
			material.set_shader_parameter("bullet_start",bullets[0]);material.set_shader_parameter("bullet_end",bullets[1])
			rendered_voxels += int(root.get_meta("voxels",0))
		elif item["kind"] == "fire":
			var flames := root.get_node("Flames") as MultiMeshInstance3D
			(flames.material_override as ShaderMaterial).set_shader_parameter("demo_time",tick/rate)
			(flames.material_override as ShaderMaterial).set_shader_parameter("life_opacity",fire_opacity)
			rendered_patches += int(root.get_meta("patches",0))
		else:
			var amount := clampf(1.0-age/maxf(.01,(float(item["end"])-float(item["start"]))/rate),0,1)
			if item["kind"] == "decoy":
				mesh.scale = Vector3.ONE*.10
			else:
				mesh.scale = Vector3.ONE*(.15+age*5)
				var material := mesh.material_override as StandardMaterial3D
				material.albedo_color.a = amount*.7
		if root.has_node("Glow"):
			var glow := root.get_node("Glow") as OmniLight3D
			glow.light_energy = (.9*fire_opacity if int(root.get_meta("patches",0))>0 else 0.0) if item["kind"] == "fire" else maxf(0,1-age*6)*3
		if root.has_node("Loop"):
			var voice := root.get_node("Loop") as AudioStreamPlayer3D
			if audible and sounds_enabled and enabled and (item["kind"]!="fire" or int(root.get_meta("patches",0))>0):
				voice.volume_db=-21+linear_to_db(maxf(.001,fire_opacity)) if item["kind"]=="fire" else -21
				if not voice.playing: voice.play(fmod(age,maxf(.1,voice.stream.get_length())))
			else: voice.stop()
	var alpha := 0.0
	if mode == 0 and enabled and flash_enabled:
		for blind in recording.get("blinds",[]):
			if blind["player"] != player or tick < float(blind["start"]) or tick >= float(blind["end"]): continue
			var remaining := (float(blind["end"])-tick)/rate
			alpha = maxf(alpha,.28*clampf(remaining/1.5,0,1))
	if flash_overlay != null: flash_overlay.color = Color(1,1,1,alpha)

func silence() -> void:
	for effect in effects.values():
		if effect.has_node("Loop"): effect.get_node("Loop").stop()
