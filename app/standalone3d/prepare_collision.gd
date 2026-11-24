extends SceneTree
func _initialize() -> void:run.call_deferred()
func run() -> void:
	var args:PackedStringArray=OS.get_cmdline_user_args()
	if args.size()!=1:quit(2);return
	var job:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[0]));var replacements:Dictionary={}
	for bank in job.geometry:
		var state:SceneState=(load(str(bank)) as PackedScene).get_state()
		for index in range(state.get_node_count()):
			for property in range(state.get_node_property_count(index)):
				if state.get_node_property_name(index,property)=="mesh":replacements[str(state.get_node_path(index)).trim_prefix("./")]=state.get_node_property_value(index,property)
	var world:Node3D
	var native:bool=job.has("physics")
	if native:
		var document:=GLTFDocument.new();var state:=GLTFState.new()
		if document.append_from_file(str(job.physics),state)!=OK:quit(7);return
		world=document.generate_scene(state)
	else:world=(load(str(job.scene)) as PackedScene).instantiate()
	root.add_child(world)
	var stack:Array=[world];var merged:=PackedVector3Array();var count:int=0;var mesh_paths:Array=[];var triangle_ends:Array=[]
	var clips:=PackedVector3Array()
	while not stack.is_empty():
		var node:Node=stack.pop_back();stack.append_array(node.get_children())
		if not node is MeshInstance3D or node.mesh==null or not node.visible:continue
		var name:String=str(node.name).to_lower();var excluded:bool=false
		if native:
			if name.begins_with("physics_npcclip_playerclip") or name.begins_with("physics_passbullets"):
				clips.append_array(node.global_transform*node.mesh.get_faces());continue
			if not name.begins_with("physics_group"):continue
		for token in ["blocklight","playerclip","nodraw","trigger"]:
			if token in name:excluded=true
		for surface in range(node.mesh.get_surface_count()):
			var material:Material=node.get_active_material(surface)
			if material!=null and str(material.resource_name).to_lower().begins_with("tools"):excluded=true
		if excluded:continue
		var mesh:Mesh=replacements.get(str(world.get_path_to(node)),node.mesh)
		if not mesh.get_aabb().position.is_equal_approx(node.mesh.get_aabb().position) or not mesh.get_aabb().size.is_equal_approx(node.mesh.get_aabb().size):quit(3);return
		var faces:PackedVector3Array=node.global_transform*mesh.get_faces()
		merged.append_array(faces);count+=1
		mesh_paths.append(str(world.get_path_to(node)));triangle_ends.append(merged.size()/3)
	var body:=StaticBody3D.new();body.name="PreparedMapCollision"
	var collision:=CollisionShape3D.new();collision.name="WorldTriangles";var shape:=ConcavePolygonShape3D.new();shape.set_faces(merged);collision.shape=shape
	body.add_child(collision);collision.owner=body
	var container:=Node3D.new();container.name="PreparedCollision";container.add_child(body);body.owner=container;collision.owner=container
	if not clips.is_empty():
		var clip_body:=StaticBody3D.new();clip_body.name="PlayerClip";clip_body.collision_layer=2
		var clip_collision:=CollisionShape3D.new();var clip_shape:=ConcavePolygonShape3D.new();clip_shape.set_faces(clips);clip_collision.shape=clip_shape
		container.add_child(clip_body);clip_body.owner=container;clip_body.add_child(clip_collision);clip_collision.owner=container
	var packed:=PackedScene.new()
	if packed.pack(container)!=OK:quit(4);return
	var pending:String=str(job.output)+".pending.scn"
	if ResourceSaver.save(packed,pending,ResourceSaver.FLAG_COMPRESS|ResourceSaver.FLAG_BUNDLE_RESOURCES)!=OK:quit(5);return
	if DirAccess.rename_absolute(pending,str(job.output))!=OK:quit(6);return
	var file:=FileAccess.open(str(job.output)+".json",FileAccess.WRITE);file.store_string(JSON.stringify({"meshes":count,"triangles":merged.size()/3,"clip_triangles":clips.size()/3,"mesh_paths":mesh_paths,"triangle_ends":triangle_ends,"source_type":"compiled_physics" if native else "render_geometry"}));file.close()
	container.free();world.free();quit(0)
