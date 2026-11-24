extends RefCounted
# Actual downloaded Anubis round, rendered in the owned main viewport. Unlike
# node-existence tests, flight checks compare pixels with the real model hidden.
static func settle(viewer:Node) -> void:
	for i in range(4):await viewer.get_tree().process_frame
	await RenderingServer.frame_post_draw

static func water_nodes(node:Node,output:Array) -> void:
	if node is MeshInstance3D and node.mesh!=null:
		for surface in range(node.mesh.get_surface_count()):
			var material:Material=node.get_active_material(surface)
			if material is ShaderMaterial and material.shader==preload("res://source_water.gdshader"):
				output.append([node,node.visible]);break
	for child in node.get_children():water_nodes(child,output)

static func overlay_nodes(node:Node,output:Array) -> void:
	if node is MeshInstance3D and node.mesh!=null:
		for surface in range(node.mesh.get_surface_count()):
			var material:Material=node.get_active_material(surface)
			if material is ShaderMaterial and material.shader==preload("res://source_overlay.gdshader"):
				output.append([node,node.visible]);break
	for child in node.get_children():overlay_nodes(child,output)

static func materials(node:Node,output:Dictionary) -> void:
	if node is MeshInstance3D and node.mesh!=null:
		for surface in range(node.mesh.get_surface_count()):
			var material:Material=node.get_active_material(surface)
			if material is ShaderMaterial:output[material.get_instance_id()]=material
	for child in node.get_children():materials(child,output)

static func run(viewer:Node,directory:String) -> Dictionary:
	DirAccess.make_dir_recursive_absolute(directory)
	var result:Dictionary={"ok":true,"failures":[],"captures":[],"flights":[]}
	var saved_tick:float=viewer.clock_tick;var saved_mode:int=viewer.camera_mode;var saved_player:int=viewer.selected_player
	var saved_validation:bool=viewer.validation_active;viewer.validation_active=true
	for index in range(viewer.actor_count):
		if str(viewer.replay.players[index].id)=="76561198062530225":viewer.selected_player=index
	var ao:Node=viewer.camera.get_node_or_null("ReviewContactShade")
	result["screen_contact_shade"]=ao!=null and ao.visible
	result["msaa"]=viewer.get_viewport().msaa_3d
	result["viewmodel_msaa"]=viewer.source_viewmodel.viewport.msaa_3d
	result["instant_exposure"]=viewer.source_post.state.get("exposure_mode","frame-average")=="frame-average"
	if result.instant_exposure:result.failures.append("Instantaneous screen exposure causes brightness pumping")
	if result.screen_contact_shade:result.failures.append("Approximate screen-depth contact shadows re-enabled")
	if result.msaa!=Viewport.MSAA_4X or result.viewmodel_msaa!=Viewport.MSAA_4X:result.failures.append("World/weapon anti-aliasing missing")
	for tick in [5200,5550,5660,5688,5778,5980]:
		viewer.camera_mode=0;viewer._seek(float(tick));await settle(viewer);viewer._update_picture();await settle(viewer)
		var path:String=directory.path_join(str(tick)+".png")
		viewer.get_viewport().get_texture().get_image().save_png(path)
		result.captures.append({"tick":tick,"path":path,"viewmodel":viewer.source_viewmodel.debug_state()})
		if tick==5660 or tick==5688:
			var action:String="pullpin" if tick==5660 else "throw_overhand"
			var clips:Dictionary=viewer.source_viewmodel.manifest.viewmodels.smokegrenade
			if not clips.has(action) or viewer.source_viewmodel.active_clip!=clips.get(action,""):result.failures.append("Actual smoke "+action+" not rendered")
	viewer.camera_mode=0;viewer._seek(5550);await settle(viewer)
	if viewer.replay.get("regression_isolation",false):
		var sun_states:Array=[]
		for sun in viewer.map_suns+[viewer.fallback_sun]:sun_states.append([sun,sun.shadow_enabled]);sun.shadow_enabled=false
		await settle(viewer)
		viewer.get_viewport().get_texture().get_image().save_png(directory.path_join("5550-no-live-shadow.png"))
		for item in sun_states:item[0].shadow_enabled=item[1]
		viewer.source_viewmodel.picture.visible=false;await settle(viewer)
		viewer.get_viewport().get_texture().get_image().save_png(directory.path_join("5550-no-viewmodel.png"))
		viewer.source_viewmodel.picture.visible=true
		var locals:Array=[]
		for light in viewer.source_direct.natives:locals.append([light,light.shadow_enabled]);light.shadow_enabled=false
		await settle(viewer)
		viewer.get_viewport().get_texture().get_image().save_png(directory.path_join("5550-no-local-shadows.png"))
		for item in locals:item[0].shadow_enabled=item[1]
		var waters:Array=[];water_nodes(viewer.map_scene,waters)
		for item in waters:item[0].visible=false
		await settle(viewer)
		viewer.get_viewport().get_texture().get_image().save_png(directory.path_join("5550-no-water.png"))
		for item in waters:item[0].visible=item[1]
		var overlays:Array=[];overlay_nodes(viewer.map_scene,overlays)
		for item in overlays:item[0].visible=false
		await settle(viewer)
		viewer.get_viewport().get_texture().get_image().save_png(directory.path_join("5550-no-overlays.png"))
		for item in overlays:item[0].visible=item[1]
		var bound:Dictionary={};materials(viewer.map_scene,bound)
		var uniforms:Dictionary={}
		for parameter in ["has_ao","source_direct_enabled"]:
			var changed:Array=[]
			for material in bound.values():
				var id:int=material.shader.get_instance_id()
				if not uniforms.has(id):uniforms[id]=material.shader.get_shader_uniform_list().map(func(u:Dictionary):return u.name)
				if parameter in uniforms[id] and material.get_shader_parameter(parameter)==true:
					changed.append(material);material.set_shader_parameter(parameter,false)
			await settle(viewer)
			viewer.get_viewport().get_texture().get_image().save_png(directory.path_join("5550-no-"+parameter+".png"))
			for material in changed:material.set_shader_parameter(parameter,true)
		result["surface_probes"]=[]
		for pixel in [Vector2(500,460),Vector2(670,295),Vector2(450,430)]:
			var origin:Vector3=viewer.camera.project_ray_origin(pixel);var ray:=PhysicsRayQueryParameters3D.create(origin,origin+viewer.camera.project_ray_normal(pixel)*150)
			ray.hit_back_faces=true
			var hit:Dictionary=viewer.get_world_3d().direct_space_state.intersect_ray(ray)
			if hit.is_empty():continue
			var node:Node=hit.collider.get_parent();var info:Dictionary={"pixel":str(pixel),"node":str(node.name),"materials":[]}
			if node is MeshInstance3D and node.mesh!=null:
				for surface in range(node.mesh.get_surface_count()):
					var original:Material=node.mesh.surface_get_material(surface)
					if original is StandardMaterial3D:info.materials.append({"name":original.resource_name,"ao_enabled":original.ao_enabled,"ao_uv2":original.ao_on_uv2})
			result.surface_probes.append(info)
	# One real recording flight for each of the six stock utility models.
	var kinds:Dictionary={}
	for item in viewer.utility.recording.get("throws",[]):
		if kinds.has(item.kind):continue
		kinds[item.kind]=true;viewer.camera_mode=2
		var tick:float=(float(item.start)+float(item.end))*.5;viewer._seek(tick)
		var model:Node3D=viewer.utility.projectiles.get(item.id)
		if model==null:result.failures.append("No flight node "+str(item.kind));continue
		viewer.camera.global_position=model.global_position+Vector3(.5,.3,.6);viewer.camera.look_at(model.global_position)
		viewer.source_viewmodel.picture.visible=false;await settle(viewer)
		var visible:Image=viewer.get_viewport().get_texture().get_image()
		model.visible=false;await settle(viewer)
		var hidden:Image=viewer.get_viewport().get_texture().get_image();var changed:int=0
		for y in range(int(visible.get_height()*.35),int(visible.get_height()*.65)):
			for x in range(int(visible.get_width()*.35),int(visible.get_width()*.65)):
				var a:Color=visible.get_pixel(x,y);var b:Color=hidden.get_pixel(x,y)
				if maxf(absf(a.r-b.r),maxf(absf(a.g-b.g),absf(a.b-b.b)))>.03:changed+=1
		model.visible=true
		visible.save_png(directory.path_join("flight-"+str(item.kind)+".png"))
		result.flights.append({"kind":item.kind,"changed_pixels":changed})
		if changed<20:result.failures.append("No rendered flight pixels "+str(item.kind))
	check_timeline(viewer,result)
	check_utility_poses(viewer,result)
	result["overlay_cycle"]=await check_overlay_cycle(viewer,directory)
	if not result.overlay_cycle.ok:result.failures.append("Dark overlay patches recur in the Anubis caustic cycle")
	result["camera_stability"]=await check_camera_stability(viewer)
	if not result.camera_stability.ok:result.failures.append("A stationary Anubis surface flickers during small camera movements")
	viewer.selected_player=saved_player;viewer.camera_mode=saved_mode;viewer._seek(saved_tick);viewer.validation_active=saved_validation
	result.ok=result.failures.is_empty();return result

static func check_timeline(viewer:Node,result:Dictionary) -> void:
	var items:Array=viewer.utility.recording.throws.filter(func(item:Dictionary):return item.start<7004 and item.end>4737)
	var missed:Dictionary={};var seen:Dictionary={}
	for tick in range(4737,7005):
		viewer.utility.update_tick(float(tick),"76561198062530225",2,false)
		for item in items:
			var active:bool=tick>=item.start and tick<item.end
			var model:Node3D=viewer.utility.projectiles.get(item.id)
			if active:
				seen[item.id]=true
				if model==null or not model.is_visible_in_tree():missed[item.id]=tick
			elif model!=null:missed[item.id]=tick
	for tick in [5700,5983,5510,7004]:
		viewer.utility.update_tick(float(tick),"76561198062530225",2,false)
		for item in items:
			if viewer.utility.projectiles.has(item.id)!=(tick>=item.start and tick<item.end):missed[item.id]=tick
	result["utility_timeline"]={"ticks":2268,"throws":items.size(),"seen":seen.size(),"missed":missed}
	if not missed.is_empty() or seen.size()!=items.size():result.failures.append("Normal playback or backward seeking loses a pistol-round projectile")

static func check_utility_poses(viewer:Node,result:Dictionary) -> void:
	var vm:Node=viewer.source_viewmodel;var actor:Node=viewer.figures[0];var cases:int=0
	var kind:Dictionary={"smokegrenade":"smoke","hegrenade":"he","flashbang":"flash","molotov":"molotov","incgrenade":"incendiary","decoy":"decoy"}
	for weapon in kind:
		viewer.stock_scenes["weapon:"+weapon]=viewer.utility.scenes[kind[weapon]]
		for team in [2,3]:
			for strength in [0.0,1.0]:
				var state:Dictionary={"anim_state":"WPN_ANIMSTATE_GRENADE_THROW","animation_seconds":0,"throw_strength":strength}
				vm.set_recorded_state(state);vm.update_pose(true,team,weapon,.08,false,-1000,-1000,-1000)
				var first:Vector3=vm.arm_skeleton.get_bone_global_pose(vm.arm_skeleton.find_bone("hand_R")).origin
				vm.update_pose(true,team,weapon,.30,false,-1000,-1000,-1000)
				var second:Vector3=vm.arm_skeleton.get_bone_global_pose(vm.arm_skeleton.find_bone("hand_R")).origin
				if not vm.picture.visible or vm.weapon_rig==null or first.distance_to(second)<.025:result.failures.append("Throw hand/model motion missing: "+weapon+" / "+str(team)+" / "+str(strength))
				actor.set_team(team);actor.utility_assets=viewer.replay.actor_assets
				for action in ["WPN_ANIMSTATE_IDLE","WPN_ANIMSTATE_GRENADE_PULL_PIN","WPN_ANIMSTATE_GRENADE_THROW"]:
					state.anim_state=action
					actor.apply_pose(weapon,Vector3(90,0,0),false,true,0,false,false,.3,-1000,-1000,0)
					var pelvis:int=actor.skeleton.find_bone("pelvis");var base:Transform3D=actor.skeleton.get_bone_pose(pelvis)
					actor.apply_utility(weapon,state,.3,0)
					var spine:int=actor.skeleton.find_bone("spine_3")
					if absf(actor.skeleton.get_bone_global_pose(spine).basis.determinant())<.00001 or not actor.skeleton.get_bone_pose(pelvis).is_equal_approx(base):result.failures.append("Utility layer collapses body or replaces locomotion: "+weapon+" / "+action)
				cases+=1
	result["utility_pose_cases"]=cases
	if not vm.sampler.failures.is_empty():result.failures.append("Utility skeleton correspondence failed")

static func check_overlay_cycle(viewer:Node,directory:String) -> Dictionary:
	viewer.camera_mode=0;viewer._seek(5550);await settle(viewer)
	var fractions:Array=[];var means:Array=[];var worst:float=-1;var worst_frame:int=0
	for frame in range(60):
		viewer.source_materials.update_tick(5550.0/64+frame*.05)
		await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
		var image:Image=viewer.get_viewport().get_texture().get_image();var dark:int=0;var total:int=0;var luminance:float=0
		for y in range(int(image.get_height()*.70),int(image.get_height()*.835),2):
			for x in range(int(image.get_width()*.46),int(image.get_width()*.635),2):
				var color:Color=image.get_pixel(x,y);var value:float=color.r*.2126+color.g*.7152+color.b*.0722
				if value<.06:dark+=1
				total+=1;luminance+=value
		var fraction:float=float(dark)/maxi(1,total);fractions.append(fraction);means.append(luminance/maxi(1,total))
		if fraction>worst:worst=fraction;worst_frame=frame;image.save_png(directory.path_join("caustic-cycle-worst.png"))
	viewer._update_picture()
	var variation:float=float(means.max())-float(means.min())
	return {"ok":worst<.03 and variation>.0003 and variation<.06,"frames":60,"max_dark_fraction":worst,"worst_frame":worst_frame,"mean_range":[means.min(),means.max()]}

static func check_camera_stability(viewer:Node) -> Dictionary:
	viewer.camera_mode=0;viewer._seek(5550);await settle(viewer)
	var saved:Transform3D=viewer.camera.global_transform
	var pixel:=Vector2(600,220);var origin:Vector3=viewer.camera.project_ray_origin(pixel)
	var ray:=PhysicsRayQueryParameters3D.create(origin,origin+viewer.camera.project_ray_normal(pixel)*150);ray.hit_back_faces=true
	var hit:Dictionary=viewer.get_world_3d().direct_space_state.intersect_ray(ray)
	if hit.is_empty():return {"ok":false,"reason":"Anubis wall anchor unavailable"}
	var values:Array=[];var anchor:Vector3=hit.position
	for cycle in range(3):
		for shift in [0.0,.01,-.01,.02,-.02,0.0]:
			viewer.camera.global_transform=saved;viewer.camera.global_position+=saved.basis.x*shift
			await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
			var point:Vector2=viewer.camera.unproject_position(anchor);var image:Image=viewer.get_viewport().get_texture().get_image();var sum:float=0
			for y in range(-2,3):
				for x in range(-2,3):
					var color:Color=image.get_pixel(clampi(roundi(point.x)+x,0,image.get_width()-1),clampi(roundi(point.y)+y,0,image.get_height()-1))
					sum+=color.r*.2126+color.g*.7152+color.b*.0722
			values.append(sum/25)
	viewer.camera.global_transform=saved
	var variation:float=float(values.max())-float(values.min())
	return {"ok":variation<.04,"frames":values.size(),"luminance_range":[values.min(),values.max()],"variation":variation}
