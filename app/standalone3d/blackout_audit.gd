extends RefCounted
static func run(viewer:Node,directory:String) -> Dictionary:
	var result:Dictionary={"ok":true,"frames":0,"black":[],"minimum":1.0,"max_seek_ms":0.0}
	var saved_tick:float=viewer.clock_tick;var saved_player:int=viewer.selected_player;var saved_mode:int=viewer.camera_mode
	var validation:bool=viewer.validation_active;viewer.validation_active=true
	DirAccess.make_dir_recursive_absolute(directory)
	for player in range(viewer.actor_count):
		viewer.selected_player=player
		for mode in [0,1]:
			viewer.camera_mode=mode
			for tick in range(6400,7489,32):
				var start:int=Time.get_ticks_usec();viewer._seek(float(tick))
				result.max_seek_ms=maxf(result.max_seek_ms,(Time.get_ticks_usec()-start)/1000.0)
				await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
				var image:=viewer.get_viewport().get_texture().get_image();var total:float=0;var count:int=0
				for y in range(int(image.get_height()*.35),int(image.get_height()*.65),12):
					for x in range(int(image.get_width()*.35),int(image.get_width()*.75),12):
						var color:=image.get_pixel(x,y);total+=color.r*.2126+color.g*.7152+color.b*.0722;count+=1
				var luminance:float=total/maxi(1,count);result.minimum=minf(result.minimum,luminance);result.frames+=1
				if luminance<.015:
					var path:String=directory.path_join(str(player)+"-"+str(mode)+"-"+str(tick)+".png");image.save_png(path)
					result.black.append({"player":player,"mode":mode,"tick":tick,"luminance":luminance,"path":path})
	viewer.selected_player=saved_player;viewer.camera_mode=saved_mode;viewer._seek(saved_tick);viewer.validation_active=validation
	result.ok=result.black.is_empty();return result
