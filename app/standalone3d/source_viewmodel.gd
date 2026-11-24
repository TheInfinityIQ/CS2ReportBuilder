extends Node

var manifest:Dictionary={}
var scenes:Dictionary={}
var sampler=preload("res://source_pose.gd").new()
var viewport:SubViewport
var picture:TextureRect
var pose_root:Node3D
var arm_rig:Node3D
var arm_skeleton:Skeleton3D
var weapon_rig:Node3D
var weapon_skeleton:Skeleton3D
var current_team:=-1
var current_weapon:=""
var active_clip:=""
var muzzle:Transform3D
var muzzle_sprite:Sprite3D
var review_environment:Environment
var review_sun:DirectionalLight3D
var recorded_state:Dictionary={}
var weapon_graph=preload("res://weapon_graph.gd").new()
var graph_state:Dictionary={}
var weapon_nodes:Dictionary={}
var arm_nodes:Dictionary={}
var node_reuses:int=0

func prepared_weapon(key:String,node:Node3D) -> void:
	if weapon_nodes.has(key):return
	node.reparent(pose_root);node.transform=Transform3D.IDENTITY;node.visible=false
	_configure_shadows(node);weapon_nodes[key]=node

func take_weapon(key:String) -> Node3D:
	if weapon_nodes.has(key):node_reuses+=1;return weapon_nodes[key]
	if not scenes.has("weapon:"+key):return null
	var node:Node3D=scenes["weapon:"+key].instantiate();pose_root.add_child(node)
	_configure_shadows(node);weapon_nodes[key]=node;return node

func set_recorded_state(value:Dictionary) -> void:recorded_state=value

func set_muzzle_texture(texture:Texture2D) -> void:
	if texture==null:return
	muzzle_sprite=Sprite3D.new();muzzle_sprite.texture=texture
	muzzle_sprite.billboard=BaseMaterial3D.BILLBOARD_ENABLED
	muzzle_sprite.no_depth_test=true;muzzle_sprite.shaded=false
	muzzle_sprite.pixel_size=.0004;muzzle_sprite.visible=false
	var material:=StandardMaterial3D.new();material.albedo_texture=texture
	material.shading_mode=BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency=BaseMaterial3D.TRANSPARENCY_ALPHA
	material.blend_mode=BaseMaterial3D.BLEND_MODE_ADD
	material.billboard_mode=BaseMaterial3D.BILLBOARD_ENABLED
	material.vertex_color_use_as_albedo=true
	muzzle_sprite.material_override=material
	viewport.get_child(0).add_child(muzzle_sprite)

func configure(overlay:Control,data:Dictionary,bank:Dictionary) -> void:
	manifest=data;scenes=bank
	viewport=SubViewport.new()
	viewport.msaa_3d=Viewport.MSAA_4X
	viewport.transparent_bg=true
	viewport.own_world_3d=true
	viewport.render_target_update_mode=SubViewport.UPDATE_DISABLED
	add_child(viewport)
	var world:=Node3D.new();viewport.add_child(world)
	var environment:=WorldEnvironment.new();environment.environment=Environment.new()
	review_environment=environment.environment
	environment.environment.background_mode=Environment.BG_CLEAR_COLOR
	environment.environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color=Color(.9,.91,.94)
	environment.environment.ambient_light_energy=.65
	environment.environment.tonemap_mode=Environment.TONE_MAPPER_FILMIC
	world.add_child(environment)
	var light:=DirectionalLight3D.new();light.light_energy=.7;light.rotation_degrees=Vector3(-45,-20,0);world.add_child(light)
	# The separate eye-space world needs its own weapon/hand shadows. World
	# occlusion still comes from the recorded eye's native shadow-probe sample.
	light.shadow_enabled=true
	light.directional_shadow_mode=DirectionalLight3D.SHADOW_ORTHOGONAL
	light.directional_shadow_max_distance=3.0
	light.shadow_normal_bias=.5
	review_sun=light
	var camera:=Camera3D.new();camera.fov=68;camera.near=.01;camera.current=true;world.add_child(camera)
	pose_root=Node3D.new();pose_root.rotation.y=PI;world.add_child(pose_root)
	picture=TextureRect.new();picture.name="SourceViewmodel";picture.texture=viewport.get_texture()
	picture.mouse_filter=Control.MOUSE_FILTER_IGNORE
	overlay.add_child(picture);overlay.move_child(picture,0)
	picture.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT);picture.visible=false

func set_review_lighting(environment:Environment,sun:DirectionalLight3D,view_camera:Camera3D) -> void:
	if review_environment==null or not picture.visible:return
	# The viewmodel has its own depth buffer, but should not have a fixed
	# studio sun that turns with the observer. Match the world sun in eye space.
	review_environment.ambient_light_color=environment.ambient_light_color
	review_environment.ambient_light_energy=environment.ambient_light_energy
	review_environment.tonemap_white=environment.tonemap_white
	review_environment.tonemap_mode=environment.tonemap_mode
	review_environment.tonemap_exposure=environment.tonemap_exposure
	review_sun.light_color=sun.light_color
	review_sun.light_energy=sun.light_energy
	review_sun.light_specular=sun.light_specular
	review_sun.basis=view_camera.global_basis.orthonormalized().inverse()*sun.global_basis.orthonormalized()

func _skeleton(node:Node,arms:bool) -> Skeleton3D:
	if node is Skeleton3D and node.find_bone("hand_R" if arms else "weapon")>=0:return node
	for child in node.get_children():
		var found:=_skeleton(child,arms)
		if found!=null:return found
	return null

func _configure_shadows(node:Node) -> void:
	# Only meshes cast: muzzle sprites and other effect geometry never do.
	if node is MeshInstance3D:node.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	elif node is GeometryInstance3D:node.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	for child in node.get_children():_configure_shadows(child)

func _duration(path:String) -> float:
	var data:Dictionary=sampler.variant(path,"arms")
	return float(data.get("frames",1))/maxf(1,float(data.get("fps",1)))

static func movement_offset(state:Dictionary) -> Vector3:
	if state.get("airborne",false):return Vector3.ZERO
	var strength:float=clampf(float(state.get("groundspeed",0))/250.0,0,1)
	var phase:float=float(state.get("travel_units",0))/90.0*TAU
	return Vector3(sin(phase)*.0045,-absf(sin(phase*2.0))*.004,0)*strength

func update_pose(enabled:bool,team:int,weapon:String,seconds:float,reloading:bool,fire_time:float,reload_time:float,equip_time:float) -> void:
	viewport.get_camera_3d().fov=preload("res://presentation_state.gd").vertical_fov(float(recorded_state.get("vm_fov",60)))
	pose_root.position=Vector3(float(recorded_state.get("vm_x",1.25)),float(recorded_state.get("vm_z",-1.5)),-float(recorded_state.get("vm_y",2)))*.0254
	pose_root.position+=movement_offset(recorded_state)
	picture.visible=enabled
	viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS if enabled else SubViewport.UPDATE_DISABLED
	if not enabled:return
	var size:Vector2i=Vector2i(picture.get_viewport_rect().size)
	if viewport.size!=size:viewport.size=size
	if current_team!=team:
		if arm_rig!=null:arm_rig.visible=false
		var key:="ct" if team==3 else "t"
		if arm_nodes.has(key):arm_rig=arm_nodes[key];node_reuses+=1
		else:
			arm_rig=scenes["vm_"+key].instantiate();pose_root.add_child(arm_rig);arm_nodes[key]=arm_rig
		arm_rig.visible=true
		arm_skeleton=_skeleton(arm_rig,true);_configure_shadows(arm_rig);current_team=team
	if current_weapon!=weapon or weapon_rig==null:
		if weapon_rig!=null:weapon_rig.visible=false
		weapon_rig=null;weapon_skeleton=null;current_weapon=weapon
		if scenes.has("weapon:"+weapon):
			weapon_rig=take_weapon(weapon);weapon_rig.visible=true
			weapon_skeleton=_skeleton(weapon_rig,false);_configure_shadows(weapon_rig)
	if arm_skeleton==null or not manifest.get("viewmodels",{}).has(weapon):
		picture.visible=false;return
	var clips:Dictionary=manifest.viewmodels[weapon]
	active_clip=str(clips.idle)
	var elapsed:=seconds
	var loop:=true
	var utility_action:String=preload("res://utility_pose.gd").action(recorded_state)
	if not utility_action.is_empty() and clips.has(utility_action):
		active_clip=clips[utility_action];elapsed=maxf(0,seconds-float(recorded_state.get("animation_seconds",seconds)));loop=false
		if utility_action=="pullpin" and elapsed>=_duration(active_clip):
			var charge:String=preload("res://utility_pose.gd").charge(recorded_state)
			if clips.has(charge):active_clip=clips[charge];loop=true
	elif reloading and clips.has("reload"):
		active_clip=clips.reload;elapsed=maxf(0,seconds-reload_time);loop=false
	elif clips.has("shoot1") and seconds-fire_time>=0 and seconds-fire_time<_duration(clips.shoot1):
		active_clip=clips.shoot1;elapsed=seconds-fire_time;loop=false
	elif clips.has("draw") and seconds-equip_time>=0 and seconds-equip_time<_duration(clips.draw):
		active_clip=clips.draw;elapsed=seconds-equip_time;loop=false
	elif clips.has("inspect") and float(recorded_state.get("inspect_seconds",-1000000))>=equip_time:
		var inspect_age:float=seconds-float(recorded_state.get("inspect_seconds",-1000000))
		if inspect_age>=0 and inspect_age<_duration(clips.inspect):
			active_clip=clips.inspect;elapsed=inspect_age;loop=false
	graph_state={}
	if manifest.get("weapon_graphs",{}).has(weapon):
		graph_state=weapon_graph.pose(manifest.weapon_graphs[weapon],recorded_state,seconds,sampler)
		if not graph_state.is_empty():
			active_clip=graph_state.path;elapsed=graph_state.elapsed;loop=graph_state.loop
	var primary:Dictionary=sampler.variant(active_clip,"arms")
	var globals:Dictionary=sampler.sample(primary,elapsed,loop)
	var key:="ct" if team==3 else "t"
	var arm_conversion:Transform3D=sampler.apply(arm_skeleton,sampler.model(manifest.arms[key].model),globals)
	var anchor:Transform3D=arm_conversion*globals.get("wpn",Transform3D.IDENTITY)
	muzzle=pose_root.transform*arm_conversion*globals.get("wpnTip",globals.get("wpn",Transform3D.IDENTITY))
	if muzzle_sprite!=null:
		muzzle_sprite.position=muzzle.origin
		muzzle_sprite.visible=seconds-fire_time>=0 and seconds-fire_time<.055 and weapon not in ["knife","smokegrenade","hegrenade","flashbang","molotov","incgrenade","decoy"]
		muzzle_sprite.modulate.a=.3 if weapon in ["usp_silencer","m4a1_silencer","mp5sd"] else .9
	if weapon_rig!=null:
		var conversion:=Transform3D(Basis(Vector3(0,0,1),Vector3(1,0,0),Vector3(0,1,0)),Vector3.ZERO)
		if weapon_skeleton!=null and manifest.get("weapon_models",{}).has(weapon):
			var metadata:Dictionary=sampler.model(manifest.weapon_models[weapon])
			conversion=sampler.calibration(weapon_skeleton,metadata)
			var secondary:Dictionary=sampler.variant(active_clip,"weapon")
			if not secondary.is_empty():sampler.apply(weapon_skeleton,metadata,sampler.sample(secondary,elapsed,loop))
		weapon_rig.transform=anchor*conversion.affine_inverse()

func debug_state() -> Dictionary:
	return {"visible":picture.visible,"arm_bones":arm_skeleton.get_bone_count() if arm_skeleton!=null else 0,"weapon":current_weapon,"clip":active_clip,"failures":sampler.failures,"graph":graph_state,"graph_gap":weapon_graph.failure}

func _exit_tree() -> void:
	if is_instance_valid(picture):picture.queue_free()
