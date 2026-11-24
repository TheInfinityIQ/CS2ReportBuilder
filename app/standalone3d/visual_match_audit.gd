extends RefCounted
# Diagnostic isolation only. Restore every light/material setting after capture.
static func materials(node:Node,output:Dictionary) -> void:
	if node is MeshInstance3D and node.mesh!=null:
		for surface in range(node.mesh.get_surface_count()):
			var material:Material=node.get_active_material(surface)
			if material is ShaderMaterial:output[material.get_instance_id()]=material
	for child in node.get_children():materials(child,output)

static func capture(viewer:Node,directory:String) -> Dictionary:
	DirAccess.make_dir_recursive_absolute(directory)
	var saved:Array=[viewer.clock_tick,viewer.camera_mode,viewer.selected_player,viewer.validation_active,viewer.source_viewmodel.viewport.size]
	viewer.validation_active=true;viewer.camera_mode=0
	for index in range(viewer.replay.players.size()):
		if str(viewer.replay.players[index].name)=="SmoodAimder":viewer.selected_player=index
	viewer._seek(6837)
	var viewport:=SubViewport.new();viewport.size=Vector2i(1280,720);viewport.msaa_3d=viewer.get_viewport().msaa_3d
	viewport.world_3d=viewer.get_world_3d();viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS;viewer.add_child(viewport)
	var camera:=Camera3D.new();camera.near=viewer.camera.near;camera.far=viewer.camera.far;camera.fov=viewer.camera.fov;camera.transform=viewer.camera.transform;camera.current=true;viewport.add_child(camera)
	viewer.source_viewmodel.viewport.size=viewport.size
	var picture:=TextureRect.new();picture.texture=viewer.source_viewmodel.viewport.get_texture();picture.size=Vector2(viewport.size);viewport.add_child(picture)
	viewer.source_post.attach(viewport)
	var bindings:Dictionary={};materials(viewer.map_scene,bindings)
	for actor in viewer.figures:materials(actor,bindings)
	materials(viewer.source_viewmodel.pose_root,bindings)
	var switches:Dictionary={}
	for id in bindings:
		var material:ShaderMaterial=bindings[id];var values:Dictionary={}
		for uniform in material.shader.get_shader_uniform_list():
			if uniform.name in ["source_direct_enabled","reflection_count"]:values[uniform.name]=material.get_shader_parameter(uniform.name)
		switches[id]=values
	var sun_state:Array=[];var suns:Array=[]
	for sun in viewer.map_suns:
		sun_state.append([sun,sun.visible,sun.shadow_enabled,sun.light_energy])
		var extra:Dictionary={}
		for property in sun.get_property_list():
			if "mask" in str(property.name):extra[property.name]=sun.get(property.name)
		suns.append({"basis":str(sun.global_basis),"direction":str(-sun.global_basis.z),"color":str(sun.light_color),"energy":sun.light_energy,"masks":extra})
	var results:Array=[]
	var saved_grading:Variant=viewer.source_post.material.get_shader_parameter("has_grading") if viewer.source_post.material!=null else false
	for condition in viewer.replay.get("visual_match_conditions",["baseline","no_sun_shadows","no_baked_shadow","no_reflections","no_sun","no_grading"]):
		for pair in sun_state:pair[0].visible=pair[1];pair[0].shadow_enabled=pair[2];pair[0].light_energy=pair[3]
		for id in switches:
			for key in switches[id]:bindings[id].set_shader_parameter(key,switches[id][key])
		if viewer.source_post.material!=null:viewer.source_post.material.set_shader_parameter("has_grading",saved_grading)
		if condition in ["authored_sun_over_pi","authored_sun"]:
			var source:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(str(viewer.options.cache).path_join("validation/visual-match/environment/resource.json")))
			var brightness:float=float(source.suns[0].properties.brightness)*float(source.suns[0].properties.brightnessscale)
			for pair in sun_state:pair[0].light_energy=brightness/(PI if condition=="authored_sun_over_pi" else 1.0)
		if condition=="no_sun_shadows":
			for pair in sun_state:pair[0].shadow_enabled=false
		if condition=="no_sun":
			for pair in sun_state:pair[0].visible=false
		if condition in ["no_baked_shadow","no_reflections"]:
			var key:String="source_direct_enabled" if condition=="no_baked_shadow" else "reflection_count"
			for id in switches:
				if switches[id].has(key):bindings[id].set_shader_parameter(key,false if key=="source_direct_enabled" else 0)
		if condition=="no_grading" and viewer.source_post.material!=null:viewer.source_post.material.set_shader_parameter("has_grading",false)
		for settle in range(3):await viewer.get_tree().process_frame
		await RenderingServer.frame_post_draw
		var path:String=directory.path_join(condition+".png");viewport.get_texture().get_image().save_png(path);results.append({"condition":condition,"path":path})
	for pair in sun_state:pair[0].visible=pair[1];pair[0].shadow_enabled=pair[2];pair[0].light_energy=pair[3]
	for id in switches:
		for key in switches[id]:bindings[id].set_shader_parameter(key,switches[id][key])
	if viewer.source_post.material!=null:viewer.source_post.material.set_shader_parameter("has_grading",saved_grading)
	viewport.free();viewer.source_viewmodel.viewport.size=saved[4];viewer.camera_mode=saved[1];viewer.selected_player=saved[2];viewer._seek(saved[0]);viewer.validation_active=saved[3]
	return {"suns":suns,"samples":results}
