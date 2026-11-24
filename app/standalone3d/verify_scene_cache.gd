extends SceneTree
# Read-only verification of prepared stock assets against their retained source.
# Inspect one pair at a time; don't retain two entire banks in memory.
func _initialize() -> void:run.call_deferred()
func hash_bytes(bytes:PackedByteArray) -> String:
	var hash:=HashingContext.new();hash.start(HashingContext.HASH_SHA256);hash.update(bytes);return hash.finish().hex_encode()
func signature(root:Node) -> String:
	var hash:=HashingContext.new();hash.start(HashingContext.HASH_SHA256)
	var pending:Array=[root];var textures:Dictionary={}
	while not pending.is_empty():
		var node:Node=pending.pop_back();pending.append_array(node.get_children())
		hash.update(var_to_bytes([str(root.get_path_to(node)),node.get_class()]))
		if node is Node3D:hash.update(var_to_bytes(node.transform))
		if node is Skeleton3D:
			for bone in range(node.get_bone_count()):hash.update(var_to_bytes([node.get_bone_name(bone),node.get_bone_parent(bone),node.get_bone_rest(bone),node.get_bone_pose(bone)]))
		if node is MeshInstance3D and node.mesh!=null:
			hash.update(var_to_bytes([node.visible,node.cast_shadow,node.mesh.get_surface_count()]))
			if node.skin!=null:
				for bind in range(node.skin.get_bind_count()):hash.update(var_to_bytes([node.skin.get_bind_name(bind),node.skin.get_bind_bone(bind),node.skin.get_bind_pose(bind)]))
			for surface in range(node.mesh.get_surface_count()):
				hash.update(var_to_bytes(node.mesh.surface_get_arrays(surface)))
				var material:Material=node.get_active_material(surface)
				if material==null:continue
				for property in material.get_property_list():
					if not int(property.usage)&PROPERTY_USAGE_STORAGE or property.name in ["resource_path","resource_local_to_scene"]:continue
					var value:Variant=material.get(property.name)
					if value is Texture2D:
						var id:int=value.get_instance_id()
						if not textures.has(id):
							var image:Image=value.get_image()
							textures[id]=[image.get_width(),image.get_height(),image.get_format(),image.has_mipmaps(),hash_bytes(image.get_data())]
						hash.update(var_to_bytes([property.name,textures[id]]))
					elif not value is Object:hash.update(var_to_bytes([property.name,value]))
		if node is AnimationPlayer:
			for name in node.get_animation_list():
				var animation:Animation=node.get_animation(name);hash.update(var_to_bytes([name,animation.length,animation.loop_mode]))
				for track in range(animation.get_track_count()):
					hash.update(var_to_bytes([animation.track_get_path(track),animation.track_get_type(track),animation.track_get_interpolation_type(track)]))
					for key in range(animation.track_get_key_count(track)):hash.update(var_to_bytes([animation.track_get_key_time(track,key),animation.track_get_key_transition(track,key),animation.track_get_key_value(track,key)]))
	return hash.finish().hex_encode()
func one(path:String) -> String:
	var scene:=ResourceLoader.load(path,"PackedScene",ResourceLoader.CACHE_MODE_IGNORE_DEEP) as PackedScene
	if scene==null:return ""
	var node:Node=scene.instantiate();root.add_child(node);var result:String=signature(node);node.free();return result
func run() -> void:
	var args:PackedStringArray=OS.get_cmdline_user_args();var resolver=preload("res://native_resource_cache.gd").new();resolver.configure(args[0]);var results:Array=[]
	for original in resolver.items:
		var target:String=resolver.resolve(original)
		var source_hash:String=one(original);var target_hash:String=one(target)
		results.append({"source":original,"matches":not source_hash.is_empty() and target!=original and source_hash==target_hash,"signature":source_hash})
	var ok:bool=results.size()==33 and results.all(func(item:Dictionary):return item.matches)
	var file:=FileAccess.open(args[1],FileAccess.WRITE);file.store_string(JSON.stringify({"ok":ok,"scenes":results}));file.close()
	print(JSON.stringify({"ok":ok,"checked":results.size(),"failed":results.filter(func(item:Dictionary):return not item.matches)}));quit(0 if ok else 1)
