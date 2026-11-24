extends RefCounted

# Fixed 16:9 captures for comparison with the accepted native first-person MP4.
# Uses the existing world and viewmodel resources inside the owned renderer.
static func capture(viewer:Node,directory:String) -> Dictionary:
	DirAccess.make_dir_recursive_absolute(directory)
	var saved_tick:float=viewer.clock_tick;var saved_mode:int=viewer.camera_mode
	var saved_player:int=viewer.selected_player;var saved_validation:bool=viewer.validation_active
	var saved_size:Vector2i=viewer.source_viewmodel.viewport.size
	var vm_camera:Camera3D=viewer.source_viewmodel.viewport.get_camera_3d()
	var saved_vm_fov:float=vm_camera.fov
	viewer.validation_active=true;viewer.camera_mode=0
	for index in range(viewer.replay.players.size()):
		if str(viewer.replay.players[index].name)=="SmoodAimder":viewer.selected_player=index
	var viewport:=SubViewport.new();viewport.size=Vector2i(1280,720)
	viewport.msaa_3d=viewer.get_viewport().msaa_3d
	viewport.world_3d=viewer.get_world_3d();viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS;viewer.add_child(viewport)
	var camera:=Camera3D.new();camera.near=viewer.camera.near;camera.far=viewer.camera.far;camera.current=true;viewport.add_child(camera)
	var picture:=TextureRect.new();picture.texture=viewer.source_viewmodel.viewport.get_texture();picture.size=Vector2(1280,720);viewport.add_child(picture)
	viewer.source_post.attach(viewport)
	var result:Dictionary={"samples":[],"size":[1280,720],"player":"SmoodAimder"}
	var targets:Array=[4737,5877,6453,6837,7070,7270]
	if viewer.replay.get("reference_death_transition",false):targets.append_array([6818,6819,6821,6823,6827])
	for target in targets:
		viewer._seek(float(target));camera.global_transform=viewer.camera.global_transform
		viewer.source_viewmodel.viewport.size=Vector2i(1280,720)
		picture.visible=viewer.source_viewmodel.picture.visible
		var views:Array=[{"name":"baseline","world":viewer.camera.fov,"weapon":saved_vm_fov},
			{"name":"vm60","world":73.739795,"weapon":60.0},
			{"name":"vm53","world":73.739795,"weapon":53.130102},
			{"name":"vm47","world":73.739795,"weapon":46.826449}]
		if viewer.replay.get("reference_single_fov",false):views=views.slice(0,1)
		for view in views:
			camera.fov=view.world;vm_camera.fov=view.weapon
			for settle in range(3):await viewer.get_tree().process_frame
			await RenderingServer.frame_post_draw
			var path:String=directory.path_join(str(target)+"-"+str(view.name)+".png")
			viewport.get_texture().get_image().save_png(path)
			if target==6837 and view.name=="baseline" and viewer.replay.get("reference_viewmodel_shadow",false):
				viewer.source_viewmodel.review_sun.shadow_enabled=false
				for settle in range(3):await viewer.get_tree().process_frame
				await RenderingServer.frame_post_draw
				viewport.get_texture().get_image().save_png(directory.path_join("6837-no-viewmodel-shadow.png"))
				viewer.source_viewmodel.review_sun.shadow_enabled=true
			if target==4737 and view.name=="baseline" and viewer.replay.get("reference_mesh_pick",false):result["mesh_pick"]=preload("res://reference_mesh_pick.gd").pick(viewer.map_scene,camera,Vector2(640,140))
			if target==4737 and view.name=="baseline" and viewer.replay.get("reference_visual_isolation",false):
				var saved_visibility:Array=[]
				for figure in viewer.figures:saved_visibility.append(figure.visible);figure.visible=false
				for settle in range(3):await viewer.get_tree().process_frame
				await RenderingServer.frame_post_draw;viewport.get_texture().get_image().save_png(directory.path_join("4737-actors-hidden.png"))
				for i in range(viewer.figures.size()):viewer.figures[i].visible=saved_visibility[i]
				var shown:bool=picture.visible;picture.visible=false
				for settle in range(3):await viewer.get_tree().process_frame
				await RenderingServer.frame_post_draw;viewport.get_texture().get_image().save_png(directory.path_join("4737-viewmodel-hidden.png"))
				picture.visible=shown;viewer.map_scene.visible=false
				for settle in range(3):await viewer.get_tree().process_frame
				await RenderingServer.frame_post_draw;viewport.get_texture().get_image().save_png(directory.path_join("4737-map-hidden.png"))
				viewer.map_scene.visible=true
			result.samples.append({"tick":target,"path":path,"world_fov":view.world,"weapon_fov":view.weapon,"eye":str(camera.global_position)})
			if viewer.replay.get("reference_stability",false) and target in [6453,6837] and view.name=="baseline":
				for frame in range(12):
					await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
					if frame in [5,11]:viewport.get_texture().get_image().save_png(directory.path_join(str(target)+"-paused-"+str(frame)+".png"))
				viewer._seek(float(target)-640);viewer._seek(float(target));camera.global_transform=viewer.camera.global_transform
				viewer.source_viewmodel.viewport.size=Vector2i(1280,720);vm_camera.fov=view.weapon
				for settle in range(3):await viewer.get_tree().process_frame
				await RenderingServer.frame_post_draw
				viewport.get_texture().get_image().save_png(directory.path_join(str(target)+"-repeated-seek.png"))
	if viewer.replay.get("reference_actor_motion",false):
		var motion_directory:String=directory.path_join("actor-motion");DirAccess.make_dir_recursive_absolute(motion_directory)
		viewer.camera_mode=1;picture.visible=false
		for frame in range(32):
			var target:float=4900.0+float(frame)*2.0
			viewer._seek(target);camera.global_transform=viewer.camera.global_transform;camera.fov=viewer.camera.fov
			await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
			viewport.get_texture().get_image().save_png(motion_directory.path_join("%03d.png"%frame))
		result["actor_motion"]={"directory":motion_directory,"start_tick":4900,"tick_step":2,"frames":32,"camera":"chase","note":"Fixed-tick rendered samples, not a live frame-cadence benchmark"}
	vm_camera.fov=saved_vm_fov;viewer.source_viewmodel.viewport.size=saved_size;viewport.free()
	var previous_xray:bool=viewer.xray_enabled;viewer.xray_enabled=true;viewer._seek(6453)
	await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
	viewer.get_viewport().get_texture().get_image().save_png(directory.path_join("xray-hud.png"))
	viewer.xray_enabled=previous_xray
	viewer.selected_player=saved_player;viewer.camera_mode=saved_mode;viewer._seek(saved_tick);viewer.validation_active=saved_validation
	return result
