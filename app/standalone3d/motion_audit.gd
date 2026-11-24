extends RefCounted

static func summary(values:Array) -> Dictionary:
	if values.is_empty():return {}
	var sorted:Array=values.duplicate();sorted.sort();var total:float=0
	for value in sorted:total+=float(value)
	return {"count":sorted.size(),"mean_ms":total/sorted.size(),"p50_ms":sorted[int((sorted.size()-1)*.5)],"p95_ms":sorted[int((sorted.size()-1)*.95)],"p99_ms":sorted[int((sorted.size()-1)*.99)],"max_ms":sorted[-1]}

static func compare_presentation(viewer:Node) -> Array:
	var original_mode := DisplayServer.window_get_vsync_mode()
	var original_cap := Engine.max_fps
	var original_sound:bool = viewer.sound_enabled
	var reports:Array = []
	Engine.max_fps = 120
	viewer.sound_enabled = false
	for mode in [DisplayServer.VSYNC_MAILBOX,DisplayServer.VSYNC_DISABLED,DisplayServer.VSYNC_DISABLED,DisplayServer.VSYNC_MAILBOX]:
		DisplayServer.window_set_vsync_mode(mode)
		viewer._seek(7100.0)
		viewer.validation_active = false
		viewer.playing = true
		var intervals:Array = []
		var before_process:Array = []
		var process_to_draw:Array = []
		var previous_draw := 0
		var started := Time.get_ticks_usec()
		var frame := 0
		while Time.get_ticks_usec()-started<9000000 and frame<2200:
			await viewer.get_tree().process_frame
			var process_entered := Time.get_ticks_usec()
			await RenderingServer.frame_post_draw
			var draw_finished := Time.get_ticks_usec()
			if frame>=20:
				intervals.append((draw_finished-previous_draw)/1000.0)
				before_process.append((process_entered-previous_draw)/1000.0)
				process_to_draw.append((draw_finished-process_entered)/1000.0)
			previous_draw = draw_finished
			frame += 1
		viewer.playing = false
		viewer.validation_active = true
		reports.append({"requested_mode":mode,"reported_mode":DisplayServer.window_get_vsync_mode(),
			"fps_cap":Engine.max_fps,"intervals":summary(intervals),"before_process":summary(before_process),
			"process_to_draw":summary(process_to_draw),"last_tick":viewer.clock_tick})
	DisplayServer.window_set_vsync_mode(original_mode)
	Engine.max_fps = original_cap
	viewer.sound_enabled = original_sound
	return reports

static func run(viewer:Node) -> Dictionary:
	var tick:float=viewer.clock_tick;var mode:int=viewer.camera_mode;var player:int=viewer.selected_player
	var validation:bool=viewer.validation_active;var profiling:bool=viewer.profile_picture
	viewer.validation_active=true;viewer.profile_picture=true
	for index in range(viewer.replay.players.size()):
		if str(viewer.replay.players[index].name)=="SmoodAimder":viewer.selected_player=index
	var failures:Array=[]
	# Exercise the real camera and first-person pose path between recorded ticks.
	# Synthetic values are restored immediately and never written to demo/cache.
	viewer.camera_mode=0
	var first:int=int(6400/float(viewer.replay.step));var second:int=first+1;var slot:int=viewer.selected_player
	var a:int=(first*viewer.actor_count+slot)*11+8;var b:int=(second*viewer.actor_count+slot)*11+8
	var old_a:float=viewer.samples[a];var old_b:float=viewer.samples[b]
	var ta:int=first*viewer.actor_count+slot;var tb:int=second*viewer.actor_count+slot
	var old_ta:float=viewer.travel_samples[ta];var old_tb:float=viewer.travel_samples[tb]
	viewer.samples[a]=.2;viewer.samples[b]=.8;viewer.travel_samples[ta]=10;viewer.travel_samples[tb]=14
	viewer._seek((first+.25)*float(viewer.replay.step))
	var expected_height:float=(64.0-18.0*.35)*.0254
	var height_error:float=absf(viewer.camera.position.y-viewer.figures[slot].position.y-expected_height)
	if height_error>.0001:failures.append("Crouch eye height still steps between ticks")
	var bob_error:float=absf(float(viewer.source_viewmodel.recorded_state.get("travel_units",0))-11)
	if bob_error>.0001:failures.append("First-person movement bob still steps between ticks")
	viewer.samples[a]=old_a;viewer.samples[b]=old_b;viewer.travel_samples[ta]=old_ta;viewer.travel_samples[tb]=old_tb
	var reports:Array=[]
	RenderingServer.viewport_set_measure_render_time(viewer.get_viewport().get_viewport_rid(),true)
	RenderingServer.viewport_set_measure_render_time(viewer.source_viewmodel.viewport.get_viewport_rid(),true)
	for camera_mode in ([] if viewer.replay.get("motion_quick",false) else [0,1]):
		viewer.camera_mode=camera_mode
		var phases:Dictionary={};var intervals:Array=[];var previous:int=0
		for frame in range(96):
			# Fractional ticks expose motion stepping hidden by integer-only tests.
			viewer.clock_tick=6400.0+frame*(64.0/120.0)
			viewer._update_picture()
			await viewer.get_tree().process_frame
			await RenderingServer.frame_post_draw
			var now:int=Time.get_ticks_usec()
			viewer.picture_profile["render_cpu_ms"]=RenderingServer.viewport_get_measured_render_time_cpu(viewer.get_viewport().get_viewport_rid())
			viewer.picture_profile["render_gpu_ms"]=RenderingServer.viewport_get_measured_render_time_gpu(viewer.get_viewport().get_viewport_rid())
			viewer.picture_profile["viewmodel_gpu_ms"]=RenderingServer.viewport_get_measured_render_time_gpu(viewer.source_viewmodel.viewport.get_viewport_rid())
			if frame>=16:
				if previous>0:intervals.append((now-previous)/1000.0)
				for key in viewer.picture_profile:
					if not phases.has(key):phases[key]=[]
					phases[key].append(viewer.picture_profile[key])
			previous=now
		var profile:Dictionary={}
		for key in phases:profile[key]=summary(phases[key])
		reports.append({"camera_mode":camera_mode,"cpu":profile,"submitted_frame_intervals":summary(intervals)})
	var isolation:Array=[];viewer.camera_mode=0;viewer.clock_tick=6450;viewer._update_picture()
	var lights:Array=[]
	for light in viewer.source_direct.natives:lights.append([light,light.shadow_enabled])
	var suns:Array=[]
	for sun in viewer.map_suns:suns.append([sun,sun.directional_shadow_max_distance,sun.shadow_enabled])
	for feature in ([] if viewer.replay.get("motion_quick",false) else ["baseline","utility_hidden","local_shadows_disabled","post_hidden","viewmodel_hidden","sun_shadows_35m","sun_shadows_disabled"]):
		if feature=="sun_shadows_35m":
			for pair in suns:pair[0].directional_shadow_max_distance=35
		if feature=="sun_shadows_disabled":
			for pair in suns:pair[0].shadow_enabled=false
		if feature=="utility_hidden":viewer.utility.visible=false
		if feature=="local_shadows_disabled":
			for pair in lights:pair[0].shadow_enabled=false
		if feature=="post_hidden":
			for rectangle in viewer.source_post.rectangles:rectangle.visible=false
		if feature=="viewmodel_hidden":viewer.source_viewmodel.viewport.render_target_update_mode=SubViewport.UPDATE_DISABLED
		var gpu:Array=[];var cpu:Array=[];var intervals:Array=[];var last:int=0
		for frame in range(16):
			await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
			var now:int=Time.get_ticks_usec()
			if frame>3:
				intervals.append((now-last)/1000.0)
				gpu.append(RenderingServer.viewport_get_measured_render_time_gpu(viewer.get_viewport().get_viewport_rid()))
				cpu.append(RenderingServer.viewport_get_measured_render_time_cpu(viewer.get_viewport().get_viewport_rid()))
			last=now
		isolation.append({"feature":feature,"gpu":summary(gpu),"render_cpu":summary(cpu),"submitted_frame_intervals":summary(intervals),"draw_calls":Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),"primitives":Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)})
		viewer.utility.visible=true
		for pair in lights:pair[0].shadow_enabled=pair[1]
		for rectangle in viewer.source_post.rectangles:rectangle.visible=true
		viewer.source_viewmodel.viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS
		for pair in suns:pair[0].directional_shadow_max_distance=pair[1];pair[0].shadow_enabled=pair[2]
	var live_intervals:Array=[];var live_cpu:Array=[];var slow_frames:Array=[]
	var old_sound:bool=viewer.sound_enabled;viewer.sound_enabled=false
	viewer._seek(6400.0);viewer.profile_frame_intervals.clear();viewer.validation_active=false;viewer.playing=true
	if viewer.replay.get("motion_cold_death_entries",false):
		for actor in viewer.figures:actor.death_entries.clear();actor.death_entry_order.clear()
	var live_seconds:float=clampf(float(viewer.replay.get("motion_live_seconds",0)),0,30)
	var live_started:int=Time.get_ticks_usec();var target_end:int=live_started+int(live_seconds*1000000)
	var previous:int=0
	var live_frame:int=0
	var draw_boundary:Dictionary={"us":0}
	var on_pre_draw := func() -> void:draw_boundary.us=Time.get_ticks_usec()
	RenderingServer.frame_pre_draw.connect(on_pre_draw)
	while (live_frame<144 if live_seconds<=0 else Time.get_ticks_usec()<target_end) and live_frame<8192:
		await viewer.get_tree().process_frame
		var process_entered := Time.get_ticks_usec()
		await RenderingServer.frame_post_draw
		var now:int=Time.get_ticks_usec()
		if live_frame>=16 and previous>0:
			var interval:float=(now-previous)/1000.0
			live_intervals.append(interval)
			live_cpu.append(float(viewer.picture_profile.get("total_ms",0)))
			if interval>1000.0/60.0:
				var viewport:RID=viewer.get_viewport().get_viewport_rid()
				slow_frames.append({"tick":viewer.clock_tick,"interval_ms":interval,
					"before_process_ms":(process_entered-previous)/1000.0,
					"process_to_pre_draw_ms":(draw_boundary.us-process_entered)/1000.0,
					"pre_draw_to_post_draw_ms":(now-draw_boundary.us)/1000.0,
					"picture_cpu":viewer.picture_profile.duplicate(),
					"render_cpu_ms":RenderingServer.viewport_get_measured_render_time_cpu(viewport),
					"render_gpu_ms":RenderingServer.viewport_get_measured_render_time_gpu(viewport),
					"draw_calls":Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)})
		previous=now
		live_frame+=1
	RenderingServer.frame_pre_draw.disconnect(on_pre_draw)
	viewer.validation_active=true;viewer.playing=false;viewer.sound_enabled=old_sound
	var live:Dictionary={"frame_intervals":summary(live_intervals),"picture_cpu":summary(live_cpu)}
	slow_frames.sort_custom(func(a:Dictionary,b:Dictionary):return a.interval_ms>b.interval_ms)
	live["over_budget_submissions"]=slow_frames.size()
	live["slow_frame_samples"]=slow_frames.slice(0,12)
	live["elapsed_seconds"]=(Time.get_ticks_usec()-live_started)/1000000.0
	live["last_tick"]=viewer.clock_tick
	live["death_entry_snapshots"]=0
	for actor in viewer.figures:live.death_entry_snapshots+=actor.death_entries.size()
	live["engine_process_intervals"]=summary(viewer.profile_frame_intervals.slice(16))
	var frame_budget_ms:float=1000.0/60.0
	live["engine_within_60hz_p99"]=float(live.engine_process_intervals.get("p99_ms",INF))<=frame_budget_ms
	live["submitted_within_60hz_p99"]=float(live.frame_intervals.get("p99_ms",INF))<=frame_budget_ms
	live["meets_60fps_p99"]=live.engine_within_60hz_p99 and live.submitted_within_60hz_p99
	var seeks:Array=[];var checked:Dictionary={}
	viewer.camera_mode=0
	for event in viewer.replay.get("gameplay",{}).get("events",[]):
		if event.kind!="weapon_fire" or event.weapon not in ["ak47","awp","m4a1","m4a1_silencer","deagle"] or checked.has(event.weapon):continue
		var frame:int=clampi(int(event.tick)/int(viewer.replay.step),0,int(viewer.replay.frames)-1)
		if viewer._weapon_key(frame,int(event.player))!=event.weapon:continue
		viewer.selected_player=int(event.player)
		var started:int=Time.get_ticks_usec();viewer._seek(float(event.tick)+.25)
		var update_ms:float=(Time.get_ticks_usec()-started)/1000.0
		await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
		var ready_ms:float=(Time.get_ticks_usec()-started)/1000.0
		var ready:bool=viewer.stock_scenes.has("weapon:"+str(event.weapon)) and viewer.source_viewmodel.weapon_rig!=null
		if not ready:failures.append("Seek lands on an unprepared weapon: "+str(event.weapon))
		seeks.append({"weapon":event.weapon,"tick":event.tick,"update_ms":update_ms,"draw_ready_ms":ready_ms,"model_ready":ready})
		checked[event.weapon]=true
	var repeated:Array=[];var world_reuses:int=0;var fp_reuses:int=viewer.source_viewmodel.node_reuses
	for actor in viewer.figures:world_reuses+=actor.held_reuses
	for target in [6450.25,7090.25,6450.25,7090.25]:
		var started:int=Time.get_ticks_usec();viewer._seek(target)
		var cpu:float=(Time.get_ticks_usec()-started)/1000.0
		await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
		repeated.append({"tick":target,"update_ms":cpu,"draw_ready_ms":(Time.get_ticks_usec()-started)/1000.0})
	var world_after:int=0
	for actor in viewer.figures:world_after+=actor.held_reuses
	var reuse:Dictionary={"seeks":repeated,"world_instance_reuses":world_after-world_reuses,"first_person_instance_reuses":viewer.source_viewmodel.node_reuses-fp_reuses}
	if reuse.world_instance_reuses==0:failures.append("Repeated seeks never reused held weapon instances")
	var presentation_comparison:Array=[]
	if viewer.replay.get("motion_compare_presentation",false):
		presentation_comparison=await compare_presentation(viewer)
	viewer.profile_picture=profiling;viewer.camera_mode=mode;viewer.selected_player=player;viewer._seek(tick);viewer.validation_active=validation
	RenderingServer.viewport_set_measure_render_time(viewer.get_viewport().get_viewport_rid(),false)
	RenderingServer.viewport_set_measure_render_time(viewer.source_viewmodel.viewport.get_viewport_rid(),false)
	return {"ok":failures.is_empty(),"failures":failures,"fractional_eye_error_metres":height_error,"fractional_bob_error":bob_error,"scope":"Actual owned renderer, fractional-tick CPU sections and submitted frame intervals; not a native-CS2 parity result", "samples":reports,"isolation":isolation,"live_playback":live,"weapon_seeks":seeks,"repeated_seeks":reuse,"presentation_comparison":presentation_comparison,"renderer":RenderingServer.get_current_rendering_method()}
