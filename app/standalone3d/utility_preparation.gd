extends RefCounted

static func read_poses(data:Dictionary) -> Dictionary:
	# The resource worker runs while playback is suspended. Populate immutable
	# shared pose data before the main thread can enter an inspect/reload/throw.
	var assets:Dictionary=data.get("actor_assets",{});var clips:Dictionary={};var models:Dictionary={}
	for group in [assets.get("viewmodels",{}),assets.get("utility_world",{})]:
		for actions in group.values():
			for path in actions.values():clips[str(path)]=true
	for path in assets.get("deaths",{}).values():clips[str(path)]=true
	for graph in assets.get("weapon_graphs",{}).values():
		for path in graph.get("clips",{}).values():clips[str(path)]=true
	for path in assets.get("models",{}).values():models[str(path)]=true
	for path in assets.get("weapon_models",{}).values():models[str(path)]=true
	for entry in assets.get("arms",{}).values():models[str(entry.model)]=true
	var sampler=preload("res://source_pose.gd").new()
	for path in models:
		if sampler.model(path).is_empty():return {"error":"A prepared player/weapon skeleton needs repair. Reopen this demo."}
	for path in clips:
		if sampler.clip(path).is_empty():return {"error":"A prepared animation needs repair. Reopen this demo."}
	return {"clips":clips.size(),"models":models.size()}

static func render_pipelines(viewer:Node) -> Dictionary:
	var started:int=Time.get_ticks_usec();var retained:Array=[]
	var viewport:=SubViewport.new();viewport.name="PipelinePreparation";viewport.size=Vector2i(64,64);viewport.own_world_3d=true
	viewport.msaa_3d=Viewport.MSAA_4X;viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS;viewer.add_child(viewport)
	viewport.mesh_lod_threshold=0.0
	var world:=Node3D.new();viewport.add_child(world)
	var environment:=WorldEnvironment.new();environment.environment=preparation_environment(viewer.world_environment);world.add_child(environment)
	var sun:=DirectionalLight3D.new();sun.rotation_degrees=Vector3(-55,-35,0);sun.shadow_enabled=true;sun.directional_shadow_mode=DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS;world.add_child(sun)
	var camera:=Camera3D.new();camera.position=Vector3(0,2,4);camera.look_at_from_position(camera.position,Vector3(0,1,0));camera.current=true;world.add_child(camera)
	var seeds:Array=world_pipeline_seeds(viewer.map_scene);var world_count:int=0
	var columns:int=maxi(1,ceili(sqrt(float(seeds.size()))));var spacing:float=minf(.2,1.6/columns)
	for original in seeds:
		var node:=MeshInstance3D.new();node.mesh=original.mesh;world.add_child(node)
		for surface in range(node.mesh.get_surface_count()):node.set_surface_override_material(surface,original.get_active_material(surface))
		var bounds:AABB=node.mesh.get_aabb();var factor:float=spacing*.6/maxf(.001,bounds.size[bounds.size.max_axis_index()])
		node.transform=Transform3D(Basis.from_scale(Vector3.ONE*factor),Vector3((world_count%columns-(columns-1)*.5)*spacing,.5+(world_count/columns)*spacing,0)-bounds.get_center()*factor)
		world_count+=1
	var utility=preload("res://grenade_player.gd").new();world.add_child(utility)
	utility.configure({"tickrate":64,"throws":[],"effects":[],"blinds":[]},viewer.utility.scenes,{},camera,null,viewer.utility.particle_textures,viewer.utility.particle_frames)
	var index:int=0
	for kind in utility.scenes:
		var model:Node3D=utility._projectile({"id":"prepare-"+kind,"kind":kind})
		model.position=Vector3((index%3-1)*.3,.8+(index/3)*.3,0);model.scale=Vector3.ONE*2;index+=1
	# Warm the same converted weapon shader paths used during Watch. Keep
	# geometry/textures shared; only short-lived nodes occupy this tiny viewport.
	var weapon_count:int=0;var warm_nodes:Dictionary={}
	for key in viewer.stock_scenes:
		if not str(key).begins_with("weapon:"):continue
		var weapon:Node3D=viewer.stock_scenes[key].instantiate();world.add_child(weapon)
		warm_nodes[str(key).trim_prefix("weapon:")]=weapon
		weapon.position=Vector3((weapon_count%8-3.5)*.15,.6+(weapon_count/8)*.15,0)
		var sample_position:Vector3=viewer.figures[0].position+Vector3.UP if not viewer.figures.is_empty() else Vector3.ZERO
		viewer.source_bounce.update_actor(weapon,sample_position)
		viewer.source_reflections.update_actor(weapon,sample_position);viewer.source_direct.update_actor(weapon)
		var materials:Array=[];viewer.source_reflections.collect(weapon,materials)
		retained.append_array(materials);weapon_count+=1
	var smoke:Dictionary={"id":"prepare-smoke","kind":"smoke","position":[0,0,0]}
	var cloud:Node3D=utility._effect(smoke)
	utility._smoke_frame(cloud,smoke,{"position":[0,0,0],"cell":12,"grid":32,"occupied":[0,32768]})
	var fire:Node3D=utility._effect({"id":"prepare-fire","kind":"fire","position":[0,0,0]})
	utility._fire_frame(fire,{"patches":[[0,0,0],[40,0,0]]})
	for kind in ["he","flash"]:utility._effect({"id":"prepare-"+kind,"kind":kind,"position":[0,0,0]})
	for root in utility.effects.values():
		for node in root.get_children():
			if node is GeometryInstance3D and node.material_override!=null:retained.append(node.material_override)
	for frame in range(3):await viewer.get_tree().process_frame
	await RenderingServer.frame_post_draw
	# Keep the instances already rendered, so later seeks don't rebuild the
	# first-person hierarchy. Inactive instances never draw; meshes/textures
	# remain shared with the existing PackedScenes.
	for key in warm_nodes:viewer.source_viewmodel.prepared_weapon(key,warm_nodes[key])
	viewport.free()
	return {"materials":retained,"milliseconds":(Time.get_ticks_usec()-started)/1000.0,"projectiles":index,"weapons":weapon_count,"world_pipelines":world_count}

static func world_pipeline_seeds(root:Node) -> Array:
	var stack:Array=[root];var choices:Dictionary={};var costs:Dictionary={}
	while not stack.is_empty():
		var node:Node=stack.pop_back();stack.append_array(node.get_children())
		if not node is MeshInstance3D or not node.is_visible_in_tree() or not node.mesh is ArrayMesh:continue
		var cost:int=0
		for surface in range(node.mesh.get_surface_count()):cost+=node.mesh.surface_get_array_len(surface)
		for surface in range(node.mesh.get_surface_count()):
			var material:Material=node.get_active_material(surface)
			if material==null:continue
			var shader_key:String
			if material is ShaderMaterial and material.shader!=null:shader_key=str(material.shader.get_rid())
			elif material.has_method("get_shader_rid"):shader_key=str(material.call("get_shader_rid"))
			else:shader_key=str(material.get_rid())
			var key:String=shader_key+":"+str(node.mesh.surface_get_format(surface))+":"+str(node.mesh.surface_get_primitive_type(surface))
			if not costs.has(key) or cost<int(costs[key]):choices[key]=node;costs[key]=cost
	var unique:Dictionary={}
	for node in choices.values():unique[node.get_instance_id()]=node
	return unique.values()

static func preparation_environment(original:Environment) -> Environment:
	var copy:=original.duplicate() as Environment
	# A separate sky RID prevents the temporary light/camera from rebaking the
	# main view's sky radiance. The authored material/textures stay shared.
	if original.sky!=null:copy.sky=original.sky.duplicate() as Sky
	return copy
