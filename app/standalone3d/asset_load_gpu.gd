extends RefCounted
static func run(viewer:Node,cases:Dictionary) -> Dictionary:
	var saved:bool=viewer.validation_active;viewer.validation_active=true;var results:Array=[];var retained:Array=[]
	for name in cases:
		var began:int=Time.get_ticks_usec()
		var scene:=ResourceLoader.load(str(cases[name]),"PackedScene",ResourceLoader.CACHE_MODE_IGNORE_DEEP) as PackedScene
		retained.append(scene)
		await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
		results.append({"case":name,"load_and_upload_ms":(Time.get_ticks_usec()-began)/1000.0,"loaded":scene!=null})
	viewer.validation_active=saved
	return {"cases":results,"renderer":RenderingServer.get_current_rendering_method()}
