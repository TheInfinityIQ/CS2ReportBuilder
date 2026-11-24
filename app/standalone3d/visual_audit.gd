extends RefCounted

# Diagnostic captures of actual recorded moments, inside the owned renderer.
static func capture(viewer: Node, directory: String) -> Array:
	DirAccess.make_dir_recursive_absolute(directory)
	var saved_tick: float = viewer.clock_tick
	var saved_mode: int = viewer.camera_mode
	var saved_player: int = viewer.selected_player
	var saved_camera: Transform3D = viewer.camera.transform
	var saved_validation:bool=viewer.validation_active
	viewer.validation_active=true
	var cases: Array = []
	if viewer.replay.get("map","")=="de_anubis":
		var tracked: int = viewer.selected_player
		for index in range(viewer.replay["players"].size()):
			if str(viewer.replay["title"]).contains(str(viewer.replay["players"][index]["name"])): tracked=index
		for tick in [5578,6205,6345,6498,6684]:
			cases.append({"name":"reported-"+str(tick),"tick":float(tick),"mode":1,"player":tracked})
		cases.append({"name":"first-person-glock","tick":5885.0,"mode":0,"player":6})
		cases.append({"name":"anubis-arches","tick":6550.0,"mode":1,"player":7})
		cases.append({"name":"anubis-arches-culling-probe","tick":6550.0,"mode":1,"player":7,"culling_probe":true})
		cases.append({"name":"anubis-bridge","tick":5578.0,"center":Vector3(15.5,-1.3,28),"offset":Vector3(3.5,3,4)})
		cases.append({"name":"anubis-bridge-culling-probe","tick":5578.0,"center":Vector3(15.5,-1.3,28),"offset":Vector3(3.5,3,4),"culling_probe":true})
	for blind in viewer.replay.get("grenade_data",{}).get("blinds",[]):
		for index in range(viewer.replay["players"].size()):
			if str(viewer.replay["players"][index]["id"])==str(blind["player"]):
				cases.append({"name":"flash-review-haze","tick":float(blind["start"])+1,"mode":0,"player":index})
		if cases.any(func(item: Dictionary):return item.name=="flash-review-haze"):break
	var dust := _find_dust(viewer.map_scene)
	if dust!=null:
		var center: Vector3 = dust.global_transform*dust.get_aabb().get_center()
		cases.append({"name":"anubis-dust-sheet","tick":float(viewer.clock_tick),"center":center,"offset":Vector3(5,1,3)})
	for event in viewer.replay.get("gameplay",{}).get("events",[]):
		if event.kind=="weapon_fire" and event.weapon=="glock":
			cases.append({"name":"glock-fire","tick":float(event.tick)+4,"player":int(event.player)})
			break
	for event in viewer.replay.get("gameplay",{}).get("events",[]):
		if event.kind=="weapon_reload" and event.weapon=="glock":
			cases.append({"name":"first-person-reload","tick":float(event.tick)+viewer._tickrate()*.5,"mode":0,"player":int(event.player)})
			break
	for kind in ["smoke","fire"]:
		for effect in viewer.replay.get("grenade_data",{}).get("effects",[]):
			if effect.kind!=kind or effect.frames.is_empty(): continue
			for age in [.05,.6,1.8]:
				cases.append({"name":kind+"-"+str(age),"tick":float(effect.start)+age*viewer._tickrate(),"center":viewer.utility.world(effect.position)})
			break
	var output: Array = []
	for event in viewer.replay.get("hud",{}).get("events",[]):
		if event.kind=="bomb_planted":
			cases.append({"name":"hud-bomb-phase","tick":float(event.tick)+1,"mode":1,"player":saved_player});break
	for marker in viewer.replay.get("rounds",[]):
		if int(marker.number)==13:
			cases.append({"name":"hud-round-13","tick":float(marker.tick),"mode":1,"player":saved_player});break
	var inventory: Array = []
	_inventory(viewer.map_scene,inventory)
	var report := FileAccess.open(directory.path_join("asset-inventory.json"),FileAccess.WRITE)
	report.store_string(JSON.stringify(inventory,"\t"))
	for item in cases:
		var culling_changes:Array=[]
		if item.get("culling_probe",false):_culling_probe(viewer.map_scene,culling_changes)
		viewer.camera_mode=int(item.get("mode",2))
		if item.has("mode"): viewer.selected_player=item.player
		viewer._seek(item.tick)
		if item.has("mode"):
			pass
		elif item.has("player"):
			viewer.selected_player=item.player
			var center: Vector3 = viewer.figures[item.player].position+Vector3.UP
			viewer.camera.position=center+Vector3(2.5,1,2.5)
			viewer.camera.look_at(center)
		else:
			viewer.camera.position=item.center+item.get("offset",Vector3(5,3,6))
			viewer.camera.look_at(item.center+(Vector3.ZERO if item.has("offset") else Vector3.UP))
		await viewer.get_tree().process_frame
		await RenderingServer.frame_post_draw
		var path := directory.path_join(item.name+".png")
		viewer.get_viewport().get_texture().get_image().save_png(path)
		var record:Dictionary={"path":path,"tick":item.tick,"kind":item.name}
		if viewer.source_viewmodel!=null and viewer.camera_mode==0:record.viewmodel=viewer.source_viewmodel.debug_state()
		if item.name=="first-person-glock":
			for entry in viewer.collision_candidates:
				if entry.bounds.has_point(viewer.camera.global_position) and not entry.node.has_meta("viewer_collision"):
					entry.node.create_trimesh_collision();entry.node.set_meta("viewer_collision",true)
			await viewer.get_tree().physics_frame
			var pixel:Vector2=Vector2(viewer.get_viewport().get_visible_rect().size)*Vector2(.05,.20)
			var start:Vector3=viewer.camera.project_ray_origin(pixel)
			var test:=PhysicsRayQueryParameters3D.create(start,start+viewer.camera.project_ray_normal(pixel)*100)
			test.collision_mask=1
			test.hit_back_faces=true
			var surface:Dictionary=viewer.get_world_3d().direct_space_state.intersect_ray(test)
			if not surface.is_empty():record.left_surface={"node":str(surface.collider.get_parent().get_path()),"position":str(surface.position)}
			for settled_frame in range(6):await viewer.get_tree().process_frame
			await RenderingServer.frame_post_draw
			viewer.get_viewport().get_texture().get_image().save_png(directory.path_join("first-person-glock-settled.png"))
			viewer.source_viewmodel.viewport.get_texture().get_image().save_png(directory.path_join("first-person-layer.png"))
			viewer.source_viewmodel.picture.visible=false
			await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
			viewer.get_viewport().get_texture().get_image().save_png(directory.path_join("first-person-world-only.png"))
			viewer.source_viewmodel.picture.visible=true
			var surface_mesh:MeshInstance3D=viewer.collision_mesh_for_hit(surface)
			if surface_mesh!=null:
				var mesh:MeshInstance3D=surface_mesh
				record.left_surface["mesh"]=mesh.mesh.resource_name
				var changes:Array=[]
				for slot in range(mesh.mesh.get_surface_count()):
					var material:Material=mesh.get_active_material(slot)
					if not material is ShaderMaterial:continue
					var baked=material.get_shader_parameter("use_source_lightmap")
					if baked==null:continue
					changes.append({"material":material,"baked":baked})
					material.set_shader_parameter("use_source_lightmap",false)
				await viewer.get_tree().process_frame;await RenderingServer.frame_post_draw
				viewer.get_viewport().get_texture().get_image().save_png(directory.path_join("first-person-wall-no-lightmap.png"))
				for change in changes:change.material.set_shader_parameter("use_source_lightmap",change.baked)
		if item.name=="glock-fire":
			var point:=Vector2(viewer.get_viewport().get_visible_rect().size)*Vector2(.76,.34)
			var origin:Vector3=viewer.camera.project_ray_origin(point)
			var ray:=PhysicsRayQueryParameters3D.create(origin,origin+viewer.camera.project_ray_normal(point)*100)
			var hit:Dictionary=viewer.get_world_3d().direct_space_state.intersect_ray(ray)
			if not hit.is_empty():record.black_surface={"node":str(hit.collider.get_parent().get_path()),"position":str(hit.position)}
		output.append(record)
		if item.name=="reported-6345" and viewer.source_bounce.atlas!=null:
			RenderingServer.global_shader_parameter_set("source_bounce_strength",0.0)
			await RenderingServer.frame_post_draw
			viewer.get_viewport().get_texture().get_image().save_png(directory.path_join("bounce-disabled.png"))
			RenderingServer.global_shader_parameter_set("source_bounce_strength",viewer.review_brightness)
		if item.name=="reported-5578":
			# Isolate lighting artifacts at the identical recorded tick/camera.
			var shade:Node=viewer.camera.get_node_or_null("ReviewContactShade")
			if shade!=null:
				shade.visible=false
				await RenderingServer.frame_post_draw
				viewer.get_viewport().get_texture().get_image().save_png(directory.path_join("lighting-no-contact.png"))
				shade.visible=true
			for sun in viewer.map_suns:sun.shadow_enabled=false
			viewer.fallback_sun.shadow_enabled=false
			await RenderingServer.frame_post_draw
			viewer.get_viewport().get_texture().get_image().save_png(directory.path_join("lighting-no-shadows.png"))
			for sun in viewer.map_suns:sun.shadow_enabled=true
			viewer.fallback_sun.shadow_enabled=true
		for change in culling_changes:change.mesh.set_surface_override_material(change.surface,change.original)
	viewer.camera_mode=saved_mode
	viewer.selected_player=saved_player
	viewer._seek(saved_tick)
	viewer.camera.transform=saved_camera
	viewer.validation_active=saved_validation
	return output

static func _culling_probe(node:Node,changes:Array) -> void:
	if node is MeshInstance3D and node.mesh!=null:
		for index in range(node.mesh.get_surface_count()):
			var material:Material=node.get_active_material(index)
			if material==null or not ("arch" in material.resource_name or "plank" in material.resource_name):continue
			var altered:Material=material.duplicate()
			if altered is StandardMaterial3D:altered.cull_mode=BaseMaterial3D.CULL_DISABLED
			elif altered is ShaderMaterial:
				var shader:=Shader.new();var code:String=altered.shader.code
				if "cull_back" in code:code=code.replace("cull_back","cull_disabled")
				elif "cull_front" in code:code=code.replace("cull_front","cull_disabled")
				elif not "cull_disabled" in code:code=code.replace("shader_type spatial;","shader_type spatial;\nrender_mode cull_disabled;")
				shader.code=code
				altered.shader=shader
			else:continue
			changes.append({"mesh":node,"surface":index,"original":node.get_surface_override_material(index)})
			node.set_surface_override_material(index,altered)
	for child in node.get_children():_culling_probe(child,changes)

static func _find_dust(node: Node) -> MeshInstance3D:
	if node is MeshInstance3D and node.mesh!=null:
		for index in range(node.mesh.get_surface_count()):
			var material: Material = node.get_active_material(index)
			if material!=null and material.resource_name=="anubis_dust_001": return node
	for child in node.get_children():
		var found := _find_dust(child)
		if found!=null: return found
	return null

static func _inventory(node: Node, output: Array) -> void:
	if node is Light3D:
		output.append({"node":str(node.get_path()),"type":node.get_class(),"visible":node.visible,"energy":node.light_energy,"color":str(node.light_color)})
	if node is MeshInstance3D and node.mesh!=null:
		for index in range(node.mesh.get_surface_count()):
			var material: Material = node.get_active_material(index)
			if material is ShaderMaterial and material.resource_name in ["anubis_dust_001","lightshaft_001"]:
				output.append({"node":str(node.get_path()),"material":material.resource_name,"shader":material.shader.resource_path,"visible":node.is_visible_in_tree()})
			if material is StandardMaterial3D:
				var color: Color = material.albedo_color
				if "error" in material.resource_name.to_lower() or "missing" in material.resource_name.to_lower() or (color.r>.65 and color.g>.10 and color.g<.65 and color.b<.25):
					output.append({"node":str(node.get_path()),"material":material.resource_name,"visible":node.is_visible_in_tree(),"color":str(color),"texture":str(material.albedo_texture),"position":str(node.global_position)})
	for child in node.get_children(): _inventory(child,output)
