extends RefCounted

static func measure(viewer:Node) -> Dictionary:
	var cpu:Array=[];var gpu:Array=[];var intervals:Array=[];var draws:Array=[];var last:int=0
	for frame in range(40):
		await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
		var now:int=Time.get_ticks_usec()
		if frame>=20:
			cpu.append(RenderingServer.viewport_get_measured_render_time_cpu(viewer.get_viewport().get_viewport_rid()))
			gpu.append(RenderingServer.viewport_get_measured_render_time_gpu(viewer.get_viewport().get_viewport_rid()))
			intervals.append((now-last)/1000.0)
			draws.append(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))
		last=now
	return {"render_cpu":preload("res://motion_audit.gd").summary(cpu),"render_gpu":preload("res://motion_audit.gd").summary(gpu),"frame_intervals":preload("res://motion_audit.gd").summary(intervals),"draw_calls":preload("res://motion_audit.gd").summary(draws)}

static func measure_motion(viewer:Node) -> Dictionary:
	var result:Dictionary={};var runs:Dictionary={"enabled":[],"disabled":[]}
	# ABBA order balances warm caches and changing machine load. Keep both
	# repetitions visible rather than attributing every timing change to culling.
	for active in [false,true,true,false]:
		viewer.world_visibility.restore();viewer.world_visibility.enabled=active
		viewer.camera_mode=0;viewer.selected_player=5;viewer._seek(6400)
		var updates:Array=[];var intervals:Array=[];var changed:Array=[];var last:int=0
		for frame in range(128):
			var previous:int=viewer.world_visibility.state.updates
			viewer.clock_tick=6400.0+frame*64.0/60.0;viewer._update_picture()
			if frame>=16 and viewer.world_visibility.state.updates!=previous:
				updates.append(viewer.world_visibility.state.update_ms);changed.append(viewer.world_visibility.state.changed_targets)
			await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
			var now:int=Time.get_ticks_usec()
			if frame>=16:intervals.append((now-last)/1000.0)
			last=now
		runs["enabled" if active else "disabled"].append({"frame_intervals":preload("res://motion_audit.gd").summary(intervals),"visibility_update_ms":preload("res://motion_audit.gd").summary(updates),"changed_targets":preload("res://motion_audit.gd").summary(changed)})
	result["runs"]=runs;result["order"]=["disabled","enabled","enabled","disabled"]
	return result

static func inspect(viewer:Node) -> Dictionary:
	var result:Dictionary={"meshes":0,"surfaces":0,"triangles":0,"surface_histogram":{},"shader_histogram":{},"same_state_groups":0,"mergeable_surfaces":0}
	var groups:Dictionary={};var shader_fields:Dictionary={};var material_keys:Dictionary={};var names:Dictionary={}
	var stack:Array=[viewer.map_scene]
	while not stack.is_empty():
		var node:Node=stack.pop_back();stack.append_array(node.get_children())
		if not node is MeshInstance3D or node.mesh==null or not node.is_visible_in_tree():continue
		result.meshes+=1;var count:int=node.mesh.get_surface_count()
		result.surface_histogram[str(count)]=int(result.surface_histogram.get(str(count),0))+1
		for surface in range(count):
			result.surfaces+=1;result.triangles+=node.mesh.surface_get_array_index_len(surface)/3
			var material:Material=node.get_active_material(surface)
			if not material is ShaderMaterial:continue
			var shader_id:int=material.shader.get_instance_id()
			var shader_name:String=material.shader.resource_path
			if shader_name.is_empty():shader_name="generated/"+str(shader_id)
			result.shader_histogram[shader_name]=int(result.shader_histogram.get(shader_name,0))+1
			var key:int=material.get_instance_id()
			if not groups.has(key):groups[key]=[]
			groups[key].append([str(node.get_path()),surface,str(material.resource_name)])
			names[material.resource_name]=int(names.get(material.resource_name,0))+1
	var sizes:Array=[]
	for group in groups.values():
		sizes.append(group.size())
		if group.size()>=2:result.same_state_groups+=1;result.mergeable_surfaces+=group.size()
	sizes.sort();sizes.reverse();result["largest_groups"]=sizes.slice(0,15)
	result["unique_material_states"]=groups.size();result["unique_names"]=names.size()
	return result

static func run(viewer:Node,directory:String) -> Dictionary:
	DirAccess.make_dir_recursive_absolute(directory)
	var result:Dictionary=inspect(viewer)
	var payload:Dictionary=preload("res://world_visibility.gd").read_cache(str(viewer.replay.get("world_visibility_manifest","")))
	var visibility=viewer.world_visibility
	var saved_enabled:bool=visibility.enabled
	if not visibility.configure(viewer,payload):return {"ok":false,"failure":visibility.state,"inventory":result}
	var saved_tick:float=viewer.clock_tick;var saved_mode:int=viewer.camera_mode;var saved_player:int=viewer.selected_player
	var saved_validation:bool=viewer.validation_active;viewer.validation_active=true
	RenderingServer.viewport_set_measure_render_time(viewer.get_viewport().get_viewport_rid(),true)
	var failures:Array=[];var samples:Array=[]
	for item in viewer.replay.get("world_render_views",[[5578,0,5],[6345,1,5],[7003,0,5],[25000,0,0],[60000,1,3]]):
		viewer.camera_mode=item[1];viewer.selected_player=item[2]
		visibility.restore();visibility.enabled=false;viewer._seek(float(item[0]))
		var before_timing:Dictionary=await measure(viewer)
		var before:Image=viewer.get_viewport().get_texture().get_image()
		visibility.enabled=true;visibility.update(viewer.camera.global_position)
		var after_timing:Dictionary=await measure(viewer)
		var after:Image=viewer.get_viewport().get_texture().get_image();var bad:int=0;var tested:int=0;var maximum:float=0
		for y in range(before.get_height()):
			for x in range(before.get_width()):
				var a:Color=before.get_pixel(x,y);var b:Color=after.get_pixel(x,y)
				var error:float=maxf(absf(a.r-b.r),maxf(absf(a.g-b.g),absf(a.b-b.b)))
				if error>3.0/255.0:bad+=1
				maximum=maxf(maximum,error);tested+=1
			if y%32==0:await viewer.get_tree().process_frame
		samples.append({"tick":item[0],"mode":item[1],"player":item[2],"changed_pixels":bad,"tested_pixels":tested,"maximum_error":maximum,"before":before_timing,"after":after_timing,"state":visibility.state.duplicate()})
		if bad>6:
			failures.append("Visible scene changed at "+str(item[0]));before.save_png(directory.path_join(str(item[0])+"-before.png"));after.save_png(directory.path_join(str(item[0])+"-after.png"))
			var ray_origin:Vector3=viewer.camera.project_ray_origin(Vector2(390,188));var ray_direction:Vector3=viewer.camera.project_ray_normal(Vector2(390,188));var candidates:Array=[]
			for entry in visibility.targets:
				if entry.is_empty() or entry.light or entry.shown:continue
				var box:AABB=entry.node.global_transform*entry.node.mesh.get_aabb()
				var intersection:Variant=box.intersects_ray(ray_origin,ray_direction)
				if intersection!=null:candidates.append({"path":str(viewer.map_scene.get_path_to(entry.node)),"distance":ray_origin.distance_to(intersection),"box":str(box),"materials":str(entry.node.get_active_material(0).resource_name)})
			samples[-1]["candidates"]=candidates
	var motion:Dictionary={}
	if viewer.replay.get("world_render_motion",false):motion=await measure_motion(viewer)
	visibility.restore();visibility.enabled=false
	viewer.camera_mode=saved_mode;viewer.selected_player=saved_player;viewer._seek(saved_tick);viewer.validation_active=saved_validation
	visibility.enabled=saved_enabled
	if saved_enabled:visibility.update(viewer.camera.global_position)
	RenderingServer.viewport_set_measure_render_time(viewer.get_viewport().get_viewport_rid(),false)
	result={"ok":failures.is_empty(),"failures":failures,"inventory":result,"samples":samples,"revision":payload.manifest.get("revision",""),"motion":motion,"comparison":"full_viewport_every_pixel"}
	var file:=FileAccess.open(directory.path_join("inventory.json"),FileAccess.WRITE);file.store_string(JSON.stringify(result))
	return result
