extends Node3D

var rig: Node3D
var animator: AnimationPlayer
var skeleton: Skeleton3D
var grip: Node3D
var held: Node3D
var team := -1
var weapon := ""
var current_clip := ""
var locomotion_sampler=preload("res://locomotion_pose.gd").new()
var locomotion_weights:Dictionary={}
var strides:Dictionary={}
var clip_cache:Dictionary={}

func reset_pose_history() -> void:death_pose_key=[]

func stride_for(clip:String,action:String) -> float:
	if assets.get("gait_strides",{}).has(clip):return float(assets.gait_strides[clip])
	if strides.has(clip):return strides[clip]
	var result:float=64 if action.begins_with("crouch") else (90 if action.begins_with("walk") else 128)
	var animation:=animator.get_animation(clip)
	for track in range(animation.get_track_count()):
		if animation.track_get_type(track)!=Animation.TYPE_POSITION_3D or not str(animation.track_get_path(track)).contains("root_motion"):continue
		var a:Vector3=animation.position_track_interpolate(track,0);var b:Vector3=animation.position_track_interpolate(track,maxf(0,animation.length-.001))
		if a.distance_to(b)>.0254:result=a.distance_to(b)/.0254
	strides[clip]=result;return result
var selected_animation := ""
var latest_fire := -1000000.0
var latest_reload := -1000000.0
var assets: Dictionary = {}
var scene_bank: Dictionary = {}
var reload_state := false
var available_clips: PackedStringArray
var defuser_meshes: Array[MeshInstance3D] = []
var weapon_skeleton: Skeleton3D
var held_pool:Dictionary={}
var held_order:Array[String]=[]
var held_reuses:int=0
var weapon_sources: Dictionary = {}
var weapon_bones_updated := 0
var nameplate:Label3D
var dead_state:=false
var death_pose_key:Array=[]
var death_pose_updates:int=0
const DEATH_ENTRY_LIMIT=8
var death_entries:Dictionary={}
var death_entry_order:Array=[]
var pose_sampler=preload("res://source_pose.gd").new()
var utility_assets:Dictionary={}
var utility_clip:String=""
var muzzle_sprite:Sprite3D

func set_muzzle_texture(texture:Texture2D) -> void:
	if texture==null:return
	muzzle_sprite=Sprite3D.new();muzzle_sprite.texture=texture
	muzzle_sprite.billboard=BaseMaterial3D.BILLBOARD_ENABLED
	muzzle_sprite.pixel_size=.0007;muzzle_sprite.shaded=false;muzzle_sprite.visible=false
	var material:=StandardMaterial3D.new();material.albedo_texture=texture
	material.shading_mode=BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency=BaseMaterial3D.TRANSPARENCY_ALPHA
	material.blend_mode=BaseMaterial3D.BLEND_MODE_ADD
	material.billboard_mode=BaseMaterial3D.BILLBOARD_ENABLED
	material.vertex_color_use_as_albedo=true
	muzzle_sprite.material_override=material
	add_child(muzzle_sprite)

func configure(bank: Dictionary, scenes: Dictionary, player_name: String) -> void:
	assets = bank
	scene_bank = scenes
	var label := Label3D.new()
	nameplate=label
	label.text = player_name
	label.position.y = 2.0
	label.pixel_size = 0.003
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	add_child(label)

func _find_rig_parts(node: Node) -> void:
	if node is AnimationPlayer:
		animator = node
		animator.speed_scale = 0
		animator.callback_mode_process=AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	if node is Skeleton3D and node.find_bone("hand_R") >= 0: skeleton = node
	if node is MeshInstance3D and "firstperson" in str(node.name).to_lower(): node.visible = false
	if node is MeshInstance3D and "empty_mesh_reference" in str(node.name).to_lower(): node.visible = false
	if node is MeshInstance3D and "defusekit" in str(node.name).to_lower(): defuser_meshes.append(node)
	for child in node.get_children(): _find_rig_parts(child)

func set_team(value: int) -> void:
	if value == team: return
	team = value
	held_pool.clear();held_order.clear()
	if rig != null: rig.free()
	animator = null
	skeleton = null
	held = null
	grip = null
	weapon = ""
	current_clip = ""
	dead_state=false
	death_entries.clear();death_entry_order.clear()
	defuser_meshes.clear()
	weapon_sources.clear()
	clip_cache.clear()
	locomotion_sampler.reset();locomotion_weights.clear()
	weapon_skeleton = null
	var key := "ct" if team == 3 else "t"
	if not scene_bank.has(key): return
	rig = scene_bank[key].instantiate()
	rig.rotation.y = PI
	add_child(rig)
	_find_rig_parts(rig)
	if animator != null: available_clips = animator.get_animation_list()
	if skeleton != null:
		var attachment := BoneAttachment3D.new()
		attachment.bone_name = "hand_R"
		skeleton.add_child(attachment)
		grip = Node3D.new()
		attachment.add_child(grip)

func _clip(suffix: String) -> String:
	if clip_cache.has(suffix):return clip_cache[suffix]
	for candidate in available_clips:
		if str(candidate).ends_with(suffix):clip_cache[suffix]=candidate;return candidate
	clip_cache[suffix]=""
	return ""

func _weapon(key: String) -> void:
	if key == weapon and (held != null or not scene_bank.has("weapon:" + key)): return
	weapon = key
	if held != null: held.visible=false
	held = null
	weapon_skeleton = null
	if grip != null and scene_bank.has("weapon:" + key):
		if held_pool.has(key):held=held_pool[key];held_reuses+=1
		else:
			held=scene_bank["weapon:" + key].instantiate();grip.add_child(held);held_pool[key]=held
		held.visible=true;held_order.erase(key);held_order.append(key)
		while held_order.size()>4:
			var old:String=held_order.pop_front();held_pool[old].free();held_pool.erase(old)
		weapon_skeleton = _find_weapon_skeleton(held)

func _find_weapon_skeleton(node: Node) -> Skeleton3D:
	if node is Skeleton3D and node.find_bone("weapon") >= 0: return node
	for child in node.get_children():
		var found := _find_weapon_skeleton(child)
		if found != null: return found
	return null

func _copy_weapon_pose(clip: String, active: bool, seconds: float) -> void:
	weapon_bones_updated = 0
	if weapon_skeleton == null: return
	weapon_skeleton.reset_bone_poses()
	if not active: return
	var animation := animator.get_animation(clip)
	if not weapon_sources.has(clip):
		var tracks: Array = []
		var animation_root := animator.get_node(animator.root_node)
		for track in range(animation.get_track_count()):
			var path := animation.track_get_path(track)
			if path.get_subname_count() < 1: continue
			var target := animation_root.get_node_or_null(NodePath(path.get_concatenated_names()))
			if not target is Skeleton3D or target == skeleton or target.find_bone("weapon") < 0: continue
			var bone := weapon_skeleton.find_bone(str(path.get_subname(0)))
			if bone < 0 or weapon_skeleton.get_bone_name(bone) in ["weapon", "weapon_offset"]: continue
			tracks.append({"track": track, "bone": bone})
		weapon_sources[clip] = tracks
	# Sample authored secondary weapon tracks directly. These source skeletons
	# have no visible skin, and need not be evaluated by the render mixer.
	var touched: Dictionary = {}
	for entry in weapon_sources[clip]:
		var track: int = entry["track"]
		var bone: int = entry["bone"]
		match animation.track_get_type(track):
			Animation.TYPE_POSITION_3D: weapon_skeleton.set_bone_pose_position(bone, animation.position_track_interpolate(track, seconds))
			Animation.TYPE_ROTATION_3D: weapon_skeleton.set_bone_pose_rotation(bone, animation.rotation_track_interpolate(track, seconds))
			Animation.TYPE_SCALE_3D: weapon_skeleton.set_bone_pose_scale(bone, animation.scale_track_interpolate(track, seconds))
		touched[bone] = true
	weapon_bones_updated = touched.size()

func _locomotion(kind:String,velocity:Vector3,crouch:float,yaw:float,seconds:float,travel_units:float,gait_phase:float) -> Array:
	var speed:float=Vector2(velocity.x,velocity.y).length()
	var direction:float=fposmod((atan2(velocity.y,velocity.x)-deg_to_rad(yaw))/(PI/4.0),8.0)
	var first:int=int(floor(direction));var fraction:float=direction-first
	var names:Array[String]=["n","nw","w","sw","s","se","e","ne"]
	# Presentation blend ranges, not an implementation of Valve's animation
	# graph. Actual recorded speed owns weight; a walk-button flag must not
	# instantly change the pose while the player is still decelerating.
	var movement:float=smoothstep(0,35,speed);var running:float=smoothstep(115,165,speed)
	var duck:float=clampf(crouch,0,1);var weights:Dictionary={}
	weights["idle_"+kind]=(1-duck)*(1-movement)
	weights["idle_crouch_"+kind]=duck*(1-movement)
	for offset in range(2):
		var side:float=(1-fraction) if offset==0 else fraction
		var suffix:String=names[(first+offset)%8]+"_"+kind
		weights["walk_"+suffix]=(1-duck)*movement*(1-running)*side
		weights["run_"+suffix]=(1-duck)*movement*running*side
		weights["crouch_"+suffix]=duck*movement*side
	var result:Array=[];locomotion_weights.clear()
	for suffix in weights:
		var weight:float=weights[suffix]
		if weight<=.000001:continue
		var clip:String=_clip(suffix)
		if clip.is_empty():clip=_clip("idle_"+kind)
		if clip.is_empty():continue
		var animation:Animation=animator.get_animation(clip);var time:float=fposmod(seconds,maxf(.001,animation.length))
		if not str(suffix).begins_with("idle"):
			if gait_phase>=0:time=fposmod(gait_phase,1.0)*animation.length
			elif travel_units>=0:time=fposmod(travel_units/stride_for(clip,suffix),1.0)*animation.length
		result.append({"clip":clip,"weight":weight,"time":time})
		locomotion_weights[clip]=float(locomotion_weights.get(clip,0))+weight
	return result

func apply_pose(key: String, velocity: Vector3, airborne: bool, walking: bool, crouch: float,
		reloading: bool, defuser: bool, seconds: float, fire_seconds: float, reload_seconds: float, yaw: float, pitch: float = 0.0, airborne_seconds: float = -1.0,travel_units:float=-1.0,gait_phase:float=-1.0,with_equipment:bool=true) -> void:
	if with_equipment:_weapon(key)
	dead_state=false
	if nameplate!=null:nameplate.visible=true
	if with_equipment and held!=null:held.visible=true
	if animator == null: return
	var definition: Dictionary = assets.get("weapons", {}).get(key, {})
	var kind := str(definition.get("class", "rifle"))
	var action := "idle_crouch" if crouch > 0.5 else "idle"
	var horizontal := Vector2(velocity.x, velocity.y).length()
	if airborne:
		action = "jump_stand"
	elif horizontal > 10:
		var relative := atan2(velocity.y, velocity.x) - deg_to_rad(yaw)
		var directions := ["n", "nw", "w", "sw", "s", "se", "e", "ne"]
		var direction: String = directions[posmod(roundi(relative / (PI / 4.0)), 8)]
		action = ("crouch" if crouch > 0.5 else ("walk" if walking or horizontal < 130 else "run")) + "_" + direction
	var clip := _clip(action + "_" + kind)
	var locomotion_clip:String=clip
	var time := seconds
	if airborne and airborne_seconds >= 0: time = airborne_seconds
	var weapon_clip := str(definition.get("clip", key))
	var fire_layer := ""
	var reload_layer:=""
	if reloading:
		var reload_clip := _clip("reload_" + weapon_clip)
		if not reload_clip.is_empty():
			reload_layer=reload_clip
	elif seconds - fire_seconds < 0.20:
		var shoot_clip := _clip(str(definition.get("fire_animation", "shoot_" + weapon_clip)))
		if not shoot_clip.is_empty():
			if kind=="knife":
				clip=shoot_clip
				time=maxf(0.0,seconds-fire_seconds)
			else: fire_layer = shoot_clip
	if clip.is_empty(): clip = _clip("idle_" + kind)
	if clip.is_empty(): return
	selected_animation = reload_layer if not reload_layer.is_empty() else (fire_layer if not fire_layer.is_empty() else clip)
	if current_clip != clip:
		animator.play(clip)
		current_clip = clip
	var length := animator.get_animation(clip).length
	var pose_time := minf(time, maxf(0, length - 0.001)) if airborne else fmod(time, maxf(.001, length))
	if clip==locomotion_clip and horizontal>10 and not airborne:
		if gait_phase>=0:pose_time=fposmod(gait_phase,1.0)*length
		elif travel_units>=0:pose_time=fposmod(travel_units/stride_for(clip,action),1.0)*length
	# Seeking the same tick repeatedly must not accumulate an additive layer,
	# including on bones omitted from a sparse locomotion clip.
	if skeleton!=null and not airborne and clip==locomotion_clip:
		# Godot processes a newly started clip even for seek(update=false).
		# Set its diagnostic clock before the stateless body pose owns bones.
		animator.seek(pose_time,false)
		locomotion_sampler.apply(animator,skeleton,_locomotion(kind,velocity,crouch,yaw,seconds,travel_units,gait_phase))
	else:
		locomotion_weights.clear()
		if skeleton != null:skeleton.reset_bone_poses()
		animator.seek(pose_time,true)
	if not reload_layer.is_empty():_apply_upper_body(reload_layer,maxf(0,seconds-reload_seconds))
	if not fire_layer.is_empty(): _apply_fire_layer(fire_layer, maxf(0.0, seconds-fire_seconds))
	if with_equipment:_copy_weapon_pose(selected_animation, reloading or not fire_layer.is_empty(), maxf(0.0,seconds-reload_seconds) if not reload_layer.is_empty() else (maxf(0.0, seconds-fire_seconds) if not fire_layer.is_empty() else pose_time))
	# Recorded demo positions own world motion, not animation root tracks.
	if skeleton != null:
		var root_bone := skeleton.find_bone("root_motion")
		if root_bone >= 0:
			skeleton.set_bone_pose_position(root_bone, Vector3.ZERO)
			# The imported root rotation converts Source's Z-up skeleton to
			# Godot's Y-up world. Clearing it lays living players on their side.
	if with_equipment and grip != null and held != null and is_inside_tree():
		var y := deg_to_rad(yaw)
		var p := deg_to_rad(clampf(pitch, -89, 89))
		var forward := Vector3(sin(y) * cos(p), -sin(p), cos(y) * cos(p))
		grip.look_at(grip.global_position + forward, Vector3.UP, true)
		if muzzle_sprite!=null:
			# BoneAttachment updates later in the frame. Sample the current hand
			# directly so a seek/equip does not flash at the previous hand pose.
			var hand:int=skeleton.find_bone("hand_R")
			var origin:Vector3=skeleton.global_transform*skeleton.get_bone_global_pose(hand).origin
			muzzle_sprite.global_position=origin+forward*(.48 if kind=="rifle" else .23)
			muzzle_sprite.visible=seconds-fire_seconds>=0 and seconds-fire_seconds<.055 and kind not in ["knife","grenade"]
			muzzle_sprite.modulate.a=.3 if key in ["usp_silencer","m4a1_silencer","mp5sd"] else .9
	for mesh in defuser_meshes: mesh.visible = defuser

func _apply_upper_body(clip:String,seconds:float) -> void:
	var animation:=animator.get_animation(clip)
	var time:=minf(seconds,maxf(0,animation.length-.001))
	var animation_root:=animator.get_node(animator.root_node)
	for track in range(animation.get_track_count()):
		var path:=animation.track_get_path(track)
		if path.get_subname_count()!=1:continue
		if animation_root.get_node_or_null(NodePath(path.get_concatenated_names()))!=skeleton:continue
		var bone:=skeleton.find_bone(str(path.get_subname(0)))
		var parent:=bone
		var upper:=false
		while parent>=0:
			if "spine" in str(skeleton.get_bone_name(parent)).to_lower():upper=true;break
			parent=skeleton.get_bone_parent(parent)
		if bone<0 or not upper:continue
		match animation.track_get_type(track):
			Animation.TYPE_POSITION_3D:skeleton.set_bone_pose_position(bone,animation.position_track_interpolate(track,time))
			Animation.TYPE_ROTATION_3D:skeleton.set_bone_pose_rotation(bone,animation.rotation_track_interpolate(track,time))
			Animation.TYPE_SCALE_3D:skeleton.set_bone_pose_scale(bone,animation.scale_track_interpolate(track,time))

func apply_utility(key:String,state:Dictionary,seconds:float,crouch:float) -> void:
	utility_clip=""
	if skeleton==null or not utility_assets.get("utility_world",{}).has(key):return
	var clips:Dictionary=utility_assets.utility_world[key]
	var action:String=preload("res://utility_pose.gd").action(state)
	if action.is_empty():action="idle_crouch" if crouch>.5 else "idle"
	elif action=="pullpin" and crouch>.5:action="pullpin_crouch"
	if not clips.has(action):return
	utility_clip=clips[action]
	var elapsed:float=maxf(0,seconds-float(state.get("animation_seconds",seconds)))
	var pose:Dictionary=pose_sampler.variant(utility_clip,"body")
	if pose.get("additive",false):
		pose_sampler.apply_additive(skeleton,pose,elapsed,action.begins_with("idle"),true);return
	var saved:Dictionary={}
	for bone in range(skeleton.get_bone_count()):
		var parent:int=bone;var upper:bool=false
		while parent>=0:
			if "spine" in str(skeleton.get_bone_name(parent)).to_lower():upper=true;break
			parent=skeleton.get_bone_parent(parent)
		if not upper:saved[bone]=skeleton.get_bone_pose(bone)
	pose_sampler.apply(skeleton,pose_sampler.model(utility_assets.models["ct" if team==3 else "t"]),pose_sampler.sample(pose,elapsed,action.begins_with("idle")))
	for bone in saved:skeleton.set_bone_pose(bone,saved[bone])

func capture_death_entry(key:int) -> void:
	if skeleton==null:return
	var positions:PackedVector3Array=[];var rotations:Array[Quaternion]=[];var scales:PackedVector3Array=[]
	for bone in range(skeleton.get_bone_count()):
		positions.append(skeleton.get_bone_pose_position(bone));rotations.append(skeleton.get_bone_pose_rotation(bone));scales.append(skeleton.get_bone_pose_scale(bone))
	death_entries[key]={"positions":positions,"rotations":rotations,"scales":scales}
	death_entry_order.erase(key);death_entry_order.append(key)
	while death_entry_order.size()>DEATH_ENTRY_LIMIT:death_entries.erase(death_entry_order.pop_front())

func apply_death(model_path:String,clip_path:String,seconds:float,entry_key:int=-1) -> void:
	if skeleton==null:return
	if not dead_state:
		if animator!=null:animator.stop()
		current_clip="";dead_state=true;death_pose_key=[]
	if held!=null:held.visible=false
	if nameplate!=null:nameplate.visible=false
	if muzzle_sprite!=null:muzzle_sprite.visible=false
	var variant:Dictionary=pose_sampler.variant(clip_path,"body")
	var frame:float=clampf(seconds*float(variant.get("fps",1)),0,float(variant.get("frames",1))-1)
	var key:Array=[skeleton.get_instance_id(),model_path,clip_path,frame,entry_key]
	if key==death_pose_key:return
	var pose:Dictionary=pose_sampler.sample(variant,seconds)
	pose_sampler.apply(skeleton,pose_sampler.model(model_path),pose)
	var blend:float=preload("res://death_pose.gd").transition(seconds)
	if blend<1.0 and death_entries.has(entry_key):
		var initial:Dictionary=death_entries[entry_key]
		for bone in range(skeleton.get_bone_count()):
			skeleton.set_bone_pose_position(bone,initial.positions[bone].lerp(skeleton.get_bone_pose_position(bone),blend))
			skeleton.set_bone_pose_rotation(bone,initial.rotations[bone].slerp(skeleton.get_bone_pose_rotation(bone),blend).normalized())
			skeleton.set_bone_pose_scale(bone,initial.scales[bone].lerp(skeleton.get_bone_pose_scale(bone),blend))
	death_pose_key=key;death_pose_updates+=1

func _apply_fire_layer(clip: String, seconds: float) -> void:
	# Exported recoil clips have a different reference from the imported rig.
	# Recover motion relative to their own first sample, then layer on stance.
	# Using skeleton rest here also rotates/translates the entire body incorrectly.
	if skeleton == null: return
	var animation := animator.get_animation(clip)
	var sample_time := minf(seconds,maxf(0,animation.length-.001))
	var animation_root := animator.get_node(animator.root_node)
	for track in range(animation.get_track_count()):
		var path := animation.track_get_path(track)
		if path.get_subname_count()!=1: continue
		if animation_root.get_node_or_null(NodePath(path.get_concatenated_names()))!=skeleton: continue
		var bone := skeleton.find_bone(str(path.get_subname(0)))
		if bone<0: continue
		match animation.track_get_type(track):
			Animation.TYPE_POSITION_3D:
				skeleton.set_bone_pose_position(bone,skeleton.get_bone_pose_position(bone)+animation.position_track_interpolate(track,sample_time)-animation.position_track_interpolate(track,0))
			Animation.TYPE_ROTATION_3D:
				skeleton.set_bone_pose_rotation(bone,(skeleton.get_bone_pose_rotation(bone)*animation.rotation_track_interpolate(track,0).inverse()*animation.rotation_track_interpolate(track,sample_time)).normalized())
			Animation.TYPE_SCALE_3D:
				skeleton.set_bone_pose_scale(bone,skeleton.get_bone_pose_scale(bone)*animation.scale_track_interpolate(track,sample_time)/animation.scale_track_interpolate(track,0))
