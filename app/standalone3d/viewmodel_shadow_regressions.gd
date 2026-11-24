extends RefCounted

# Loaded meshes under a controlled sun. Bypass native eye occlusion only for
# this witness; restore every light, material and timeline input afterwards.
static func run(viewer:Node) -> Dictionary:
	var vm:Node=viewer.source_viewmodel
	var saved_tick:float=viewer.clock_tick;var saved_mode:int=viewer.camera_mode
	viewer.camera_mode=0;viewer._seek(6400.0)
	var sun:DirectionalLight3D=vm.review_sun;var basis:Basis=sun.basis;var energy:float=sun.light_energy
	var bindings:Array=[];var seen:Dictionary={};var stack:Array=[vm.pose_root];var casters:int=0
	while not stack.is_empty():
		var node:Node=stack.pop_back();stack.append_array(node.get_children())
		if not node is MeshInstance3D or node.mesh==null or not node.is_visible_in_tree():continue
		if node.cast_shadow!=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF:casters+=1
		for surface in range(node.mesh.get_surface_count()):
			var material:Material=node.get_active_material(surface)
			if not material is ShaderMaterial or seen.has(material.get_instance_id()):continue
			seen[material.get_instance_id()]=true
			bindings.append([material,material.get_shader_parameter("source_direct_enabled")]);material.set_shader_parameter("source_direct_enabled",false)
	sun.basis=Basis.from_euler(Vector3(-PI/4,-PI/4,0));sun.light_energy=4.0
	var images:Array[Image]=[]
	for enabled in [false,true]:
		sun.shadow_enabled=enabled
		for frame in range(4):await viewer.get_tree().process_frame
		await RenderingServer.frame_post_draw
		images.append(vm.viewport.get_texture().get_image())
	var changed:int=0;var maximum:float=0
	for y in range(images[0].get_height()):
		for x in range(images[0].get_width()):
			var a:Color=images[0].get_pixel(x,y);var b:Color=images[1].get_pixel(x,y)
			var delta:float=maxf(absf(a.r-b.r),maxf(absf(a.g-b.g),absf(a.b-b.b)))
			if delta>.004:changed+=1
			maximum=maxf(maximum,delta)
	for pair in bindings:pair[0].set_shader_parameter("source_direct_enabled",pair[1])
	sun.basis=basis;sun.light_energy=energy;sun.shadow_enabled=true
	viewer.camera_mode=saved_mode;viewer._seek(saved_tick)
	var ok:bool=casters>0 and changed>8
	return {"ok":ok,"casters":casters,"changed_pixels":changed,"maximum_channel_change":maximum,"scope":"Loaded stock hands/weapon under controlled sunlight; not native lighting parity","failures":[] if ok else ["Stock viewmodel self-shadowing produced no rendered shadow"]}
