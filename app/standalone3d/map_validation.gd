extends RefCounted

static func floor_candidates(node:Node,output:Array) -> void:
	if node is MeshInstance3D and node.mesh!=null and node.visible and node.cast_shadow!=GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY:
		var bounds:AABB=node.global_transform*node.get_aabb()
		if bounds.size.y<.6 and bounds.size.x>3 and bounds.size.z>3 and bounds.size.x<45 and bounds.size.z<45:
			output.append({"node":node,"point":bounds.get_center(),"score":Vector2(bounds.get_center().x,bounds.get_center().z).length()+absf(bounds.get_center().y)*.2})
	for child in node.get_children():floor_candidates(child,output)

static func cast(viewer:Node,from:Vector3,to:Vector3) -> Dictionary:
	var ray:=PhysicsRayQueryParameters3D.create(from,to);ray.hit_back_faces=true
	return viewer.get_world_3d().direct_space_state.intersect_ray(ray)

static func gallery(viewer:Node,candidates:Array) -> Dictionary:
	for candidate in candidates.slice(0,60):
		var point:Vector3=candidate.point
		for entry in viewer.collision_candidates:
			if entry.bounds.has_point(point) and not entry.node.has_meta("viewer_collision"):
				entry.node.create_trimesh_collision();entry.node.set_meta("viewer_collision",true)
		await viewer.get_tree().physics_frame
		var floor_hit:=cast(viewer,point+Vector3.UP*.35,point-Vector3.UP*1.2)
		if floor_hit.is_empty() or floor_hit.normal.y<.7:continue
		point=floor_hit.position
		if not cast(viewer,point+Vector3.UP*.1,point+Vector3.UP*2.2).is_empty():continue
		for index in range(12):
			var angle:float=TAU*index/12
			var spots:Array=[]
			var side:=Vector3(cos(angle),0,-sin(angle))
			for offset in [-.65,.65]:
				var p:Vector3=point+side*offset
				var hit:=cast(viewer,p+Vector3.UP*.3,p-Vector3.UP*.5)
				if not hit.is_empty() and hit.normal.y>.7 and cast(viewer,hit.position+Vector3.UP*.1,hit.position+Vector3.UP*2.0).is_empty():spots.append(hit.position)
			if spots.size()!=2:continue
			var eye:Vector3=point+Vector3(sin(angle)*4,1.65,cos(angle)*4)
			var clear:=true
			for spot in spots:
				if not cast(viewer,eye,spot+Vector3.UP*1.3).is_empty():clear=false
			if clear:return {"point":point,"eye":eye,"spots":spots}
	return {}

static func run(viewer:Node) -> void:
	viewer.validation_active=true
	var result:Dictionary={"ok":true,"map":viewer.replay.map,"fixture_type":"synthetic_map_weapon_rendering","cs2_process_required":false,"failures":[],"weapon_cases":[],"load_profile":viewer.load_profile}
	var candidates:Array=[];floor_candidates(viewer.map_scene,candidates)
	result["read_profile"]=viewer.replay.get("read_profile",{})
	if candidates.is_empty():result.failures.append("No bounded gallery floor was found")
	candidates.sort_custom(func(a:Dictionary,b:Dictionary):return a.score<b.score)
	var placement:Dictionary=await gallery(viewer,candidates)
	if placement.is_empty():
		result.failures.append("No clear, collision-checked gallery camera was found")
		placement={"point":Vector3.ZERO,"eye":Vector3(3,2,4),"spots":[Vector3.ZERO,Vector3(1,0,0)]}
	var point:Vector3=placement.point
	result.gallery={"clear":not result.failures.has("No clear, collision-checked gallery camera was found"),"point":str(point),"eye":str(placement.eye)}
	for frame in range(int(viewer.replay.frames)):
		for player in range(2):
			var position:Vector3=placement.spots[player]
			var offset:int=(frame*2+player)*11
			viewer.samples[offset]=position.z/.0254;viewer.samples[offset+1]=position.x/.0254;viewer.samples[offset+2]=position.y/.0254
	viewer.camera_mode=2;viewer._update_picture()
	viewer.camera.position=placement.eye;viewer.camera.look_at(point+Vector3.UP*1.1)
	var lighting_only:bool=viewer.replay.validation_fixture.get("lighting_audit",false)
	var directory:String=str(viewer.options.smoke).get_base_dir().path_join(("lighting-" if lighting_only else "matrix-")+str(viewer.replay.map))
	DirAccess.make_dir_recursive_absolute(directory)
	var definitions:Array=viewer.replay.validation_fixture.get("weapons",viewer.replay.stock.weapons.keys())
	for weapon in definitions:
		viewer.status_label.text="Validation · "+str(viewer.replay.map)+" · "+str(weapon)
		var key:String="weapon:"+str(weapon)
		var path:String=viewer.replay.stock.weapons[weapon].scene
		if not viewer.stock_scenes.has(key):
			var error:=ResourceLoader.load_threaded_request(path,"PackedScene")
			if error!=OK:result.failures.append(str(weapon)+": load request failed");continue
			while ResourceLoader.load_threaded_get_status(path)==ResourceLoader.THREAD_LOAD_IN_PROGRESS:await viewer.get_tree().process_frame
			var resource=ResourceLoader.load_threaded_get(path)
			if resource==null:result.failures.append(str(weapon)+": model missing");continue
			viewer.stock_scenes[key]=resource
		for player in range(2):
			var actor=viewer.figures[player]
			actor.apply_pose(weapon,Vector3.ZERO,false,false,0,false,false,.1,.07,-1000,0)
			var head:int=actor.skeleton.find_bone("head_0")
			if actor.skeleton.get_bone_global_pose(head).origin.y<1.2:result.failures.append(str(weapon)+": world pose lost up axis")
			viewer.source_viewmodel.update_pose(true,3-player,weapon,.1,false,.07,-1000,-1000)
			if viewer.source_bounce.atlas!=null:
				var sample_point:Vector3=actor.position+Vector3.UP*1.4
				viewer.source_bounce.update_actor(actor.rig,sample_point)
				viewer.source_bounce.update_actor(actor.held,sample_point)
				viewer.source_bounce.update_actor(viewer.source_viewmodel.arm_rig,sample_point,true,viewer.camera.global_basis)
				viewer.source_bounce.update_actor(viewer.source_viewmodel.weapon_rig,sample_point,true,viewer.camera.global_basis)
				for root in [actor.rig,actor.held,viewer.source_viewmodel.arm_rig,viewer.source_viewmodel.weapon_rig]:
					viewer.source_reflections.update_actor(root,sample_point)
					viewer.source_direct.update_actor(root)
			var sun:DirectionalLight3D=viewer.map_suns[0] if not viewer.map_suns.is_empty() else viewer.fallback_sun
			viewer.source_viewmodel.set_review_lighting(viewer.world_environment,sun,viewer.camera)
			viewer.camera_menu.select(0)
			viewer.review_hud.update_state(0,64,1,{2:1,3:1},{"name":"CT stock model" if player==0 else "T stock model","weapon":weapon,"health":100,"team":3-player},0)
			var state:Dictionary=viewer.source_viewmodel.debug_state()
			if not state.visible or not state.failures.is_empty():result.failures.append(str(weapon)+": first-person pose failed")
			await viewer.get_tree().process_frame
			await RenderingServer.frame_post_draw
			var shot:String=directory.path_join(str(weapon)+("-ct.png" if player==0 else "-t.png"))
			viewer.get_viewport().get_texture().get_image().save_png(shot)
			result.weapon_cases.append({"weapon":weapon,"team":3-player,"capture":shot,"arm_bones":state.arm_bones})
		viewer.source_viewmodel.update_pose(false,3,weapon,0,false,-1000,-1000,-1000)
		viewer.camera_menu.select(2)
		viewer.review_hud.update_state(0,64,1,{2:1,3:1},{"name":"CT stock model","weapon":weapon,"health":100,"team":3},2)
		if weapon in ["ak47","glock","awp","m249","knife","smokegrenade"]:
			await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
			viewer.get_viewport().get_texture().get_image().save_png(directory.path_join(str(weapon)+"-world.png"))
		for actor in viewer.figures:actor._weapon("")
		if viewer.source_viewmodel.weapon_rig!=null:
			viewer.source_viewmodel.weapon_rig.free();viewer.source_viewmodel.weapon_rig=null;viewer.source_viewmodel.weapon_skeleton=null
		viewer.stock_scenes.erase(key)
	result.source_materials={"applied":viewer.source_materials.applied,"failures":viewer.source_materials.failures}
	result.source_bounce=viewer.source_bounce.state
	result.failures.append_array(viewer.source_bounce.state.failures)
	result.source_reflections=viewer.source_reflections.state
	result.source_direct=viewer.source_direct.state
	if viewer.source_post.state.available:
		result.postprocess=await preload("res://post_regressions.gd").run(viewer)
		result.failures.append_array(result.postprocess.failures)
	result.failures.append_array(viewer.source_reflections.state.failures)
	result.failures.append_array(viewer.source_direct.state.failures)
	result.failures.append_array(viewer.source_materials.failures)
	for family in viewer.replay.validation_fixture.expected_materials:
		if int(viewer.source_materials.applied[family])!=int(viewer.replay.validation_fixture.expected_materials[family]):result.failures.append("Source "+family+" surface coverage mismatch")
	if result.weapon_cases.size()!=definitions.size()*2:result.failures.append("Expected every requested definition on both teams")
	if lighting_only:
		result.lighting=await preload("res://lighting_audit.gd").run(viewer,directory)
		result.failures.append_array(result.lighting.failures)
		result.gpu_contract=await preload("res://lighting_regressions.gd").run(viewer)
		result.failures.append_array(result.gpu_contract.failures)
		result.effects=await preload("res://effects_regressions.gd").run(viewer)
		result.failures.append_array(result.effects.failures)
		result.source_effects=viewer.source_effects.state
	result.ok=result.failures.is_empty()
	viewer.validation_active=false;viewer._update_picture()
	if viewer.options.has("screenshot"):
		await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
		viewer.get_viewport().get_texture().get_image().save_png(str(viewer.options.screenshot))
	var file:=FileAccess.open(str(viewer.options.smoke),FileAccess.WRITE);file.store_string(JSON.stringify(result,"\t"));file.close()
