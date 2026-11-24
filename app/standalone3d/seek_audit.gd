extends RefCounted

# Regression for the reported pistol-round blackout and repeated +/-10s jumps.
# Runs inside the owned renderer, with the actual downloaded Anubis recording.
static func run(viewer:Node,directory:String) -> Dictionary:
	var result:Dictionary={"ok":true,"failures":[],"samples":[]}
	var probe=viewer.get_script().new();probe.actor_count=1
	probe.samples=PackedFloat32Array([100,100,100,179,10,100,2,1,0,1,0,100,100,100,-179,30,100,2,1,0,1,0])
	var angles:Vector2=probe._view_angles(0,1,0,.5)
	if absf(absf(angles.x)-180)>.001 or absf(angles.y-20)>.001:result.failures.append("Aim interpolation crosses yaw wrap incorrectly")
	probe.samples[18]=0
	if not probe._view_angles(0,1,0,.5).is_equal_approx(Vector2(179,10)):result.failures.append("Aim blends across a death boundary")
	probe.samples[18]=1;probe.samples[11]=10000
	if not probe._view_angles(0,1,0,.5).is_equal_approx(Vector2(179,10)):result.failures.append("Aim blends across a teleport")
	probe.free()
	var tick:float=viewer.clock_tick;var mode:int=viewer.camera_mode;var player:int=viewer.selected_player
	var saved_validation:bool=viewer.validation_active;viewer.validation_active=true
	var saved_profile:bool=viewer.profile_picture;viewer.profile_picture=true
	for index in range(viewer.replay.players.size()):
		if str(viewer.replay.players[index].name)=="SmoodAimder":viewer.selected_player=index
	DirAccess.make_dir_recursive_absolute(directory)
	for camera_mode in [0,1]:
		viewer.camera_mode=camera_mode
		for target in [4737,5377,6017,6657,7297,6657,6017,6657,7003,7200,7451,7568,6928,6288]:
			var began:int=Time.get_ticks_usec();viewer._seek(float(target))
			var update_ms:float=(Time.get_ticks_usec()-began)/1000.0
			var phases:Dictionary=viewer.picture_profile.duplicate()
			var collision_begin:int=Time.get_ticks_usec();viewer._extend_camera_collision()
			var collision_ms:float=(Time.get_ticks_usec()-collision_begin)/1000.0
			await RenderingServer.frame_post_draw
			var draw_ready_ms:float=(Time.get_ticks_usec()-began)/1000.0
			var image:=viewer.get_viewport().get_texture().get_image()
			var total:float=0;var count:int=0
			for y in range(int(image.get_height()*.36),int(image.get_height()*.66),8):
				for x in range(int(image.get_width()*.4),int(image.get_width()*.8),8):
					var color:=image.get_pixel(x,y);total+=color.r*.2126+color.g*.7152+color.b*.0722;count+=1
			var luminance:float=total/maxi(1,count)
			var frame:int=clampi(int(target/float(viewer.replay.step)),0,int(viewer.replay.frames)-1)
			result.samples.append({"mode":camera_mode,"tick":target,"update_ms":update_ms,"draw_ready_ms":draw_ready_ms,"cpu_phases":phases,"collision_ms":collision_ms,"luminance":luminance,
				"camera":str(viewer.camera.position),"present":viewer._sample(frame,viewer.selected_player,9),"alive":viewer._sample(frame,viewer.selected_player,7)})
			if update_ms>500:result.failures.append("Seek stalls main thread at "+str(target)+": "+str(update_ms)+" ms")
			if collision_ms>100:result.failures.append("Collision stalls after seek at "+str(target)+": "+str(collision_ms)+" ms")
			if luminance<.015:result.failures.append("Black world image at "+str(target)+", mode "+str(camera_mode))
			if target in [6657,7003,7200,7451,7568]:image.save_png(directory.path_join(str(camera_mode)+"-"+str(target)+".png"))
	for was_playing in [false,true]:
		viewer._seek(5377);viewer.playing=was_playing;viewer._skip(10.0)
		if viewer.playing!=was_playing or viewer.clock_tick!=6017:result.failures.append("Forward skip changed playback state or tick")
		viewer._skip(-10.0)
		if viewer.playing!=was_playing or viewer.clock_tick!=5377:result.failures.append("Backward skip changed playback state or tick")
	viewer.camera_mode=mode;viewer.selected_player=player;viewer._seek(tick);viewer.validation_active=saved_validation
	viewer.profile_picture=saved_profile
	result.ok=result.failures.is_empty();return result
