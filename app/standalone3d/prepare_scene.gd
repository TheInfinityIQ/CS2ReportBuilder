extends SceneTree

# One approved map, one native cache, no game process or installed-asset writes.
func _initialize() -> void:
	_prepare.call_deferred()

func _prepare() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() < 2:
		quit(2)
		return
	var scene: Node
	if args[0].ends_with(".scn"):
		var existing := load(args[0]) as PackedScene
		if existing != null: scene = existing.instantiate()
	else:
		var document := GLTFDocument.new()
		var state := GLTFState.new()
		if document.append_from_file(args[0], state) != OK:
			quit(3)
			return
		scene = document.generate_scene(state)
	if scene == null:
		quit(4)
		return
	if args.size()>2 and args[2]=="view_arms":
		var meshes:Array[MeshInstance3D]=[]
		_collect_meshes(scene,meshes)
		for mesh in meshes:
			if "worldmodel" in str(mesh.name).to_lower():mesh.mesh=null
	if args.size() > 2 and args[2] == "stock":
		var meshes: Array[MeshInstance3D] = []
		_collect_meshes(scene, meshes)
		var has_hd := false
		for mesh in meshes:
			if "_hd" in str(mesh.name).to_lower(): has_hd = true
		for mesh in meshes:
			var name := str(mesh.name).to_lower()
			if "firstperson" in name or "empty_mesh_reference" in name or (has_hd and "_legacy" in name):
				mesh.mesh=null
	if "gpu" in args:
		var textures: Dictionary = {}
		_compress_textures(scene, textures)
	if "rgba8" in args:
		var textures:Dictionary={}
		_expand_rgb_textures(scene,textures)
	var flags := ResourceSaver.FLAG_BUNDLE_RESOURCES
	if "uncompressed" not in args:flags|=ResourceSaver.FLAG_COMPRESS
	if "parts" in args:
		# RSCC stores raw length in 32 bits. Share full-resolution textures
		# as individual native resources rather than exceeding 4 GiB in one.
		var directory := args[1].get_basename()+"_textures"
		DirAccess.make_dir_recursive_absolute(directory)
		var external: Dictionary = {}
		if not _external_textures(scene,directory,external): scene.free();quit(8);return
		# These caches live outside res://. Absolute private-cache references
		# avoid Godot rebasing a relative texture path twice on Windows.
		flags = ResourceSaver.FLAG_COMPRESS
	var packed := PackedScene.new()
	if packed.pack(scene) != OK:
		scene.free()
		quit(5)
		return
	var pending := args[1].get_basename() + ".pending.scn"
	var error := ResourceSaver.save(packed, pending, flags)
	scene.free()
	if error != OK:
		quit(6)
		return
	if DirAccess.rename_absolute(pending, args[1]) != OK:
		quit(7)
		return
	quit(0)

func _collect_meshes(node: Node, meshes: Array[MeshInstance3D]) -> void:
	if node is MeshInstance3D: meshes.append(node)
	for child in node.get_children(): _collect_meshes(child, meshes)

func _expand_rgb_textures(node:Node,cache:Dictionary) -> void:
	if node is MeshInstance3D and node.mesh!=null:
		for surface in range(node.mesh.get_surface_count()):
			var material:Material=node.get_active_material(surface)
			if not material is BaseMaterial3D:continue
			for slot in range(BaseMaterial3D.TEXTURE_MAX):
				var texture:Texture2D=material.get_texture(slot)
				if texture==null:continue
				var id:int=texture.get_instance_id()
				if not cache.has(id):
					cache[id]=texture;var image:Image=texture.get_image()
					if image!=null and image.get_format()==Image.FORMAT_RGB8:
						# Vulkan otherwise expands RGB to RGBA at every open. Add the
						# implicit opaque alpha once, without changing any color pixel.
						image.convert(Image.FORMAT_RGBA8)
						var expanded:=ImageTexture.create_from_image(image);expanded.resource_name=texture.resource_name;cache[id]=expanded
				material.set_texture(slot,cache[id])
	for child in node.get_children():_expand_rgb_textures(child,cache)

func _compress_textures(node: Node, cache: Dictionary) -> void:
	if node is MeshInstance3D and node.mesh!=null:
		for surface in range(node.mesh.get_surface_count()):
			var material: Material = node.get_active_material(surface)
			if not material is BaseMaterial3D: continue
			for slot in range(BaseMaterial3D.TEXTURE_MAX):
				var texture: Texture2D = material.get_texture(slot)
				if texture == null: continue
				var key := texture.get_instance_id()
				if not cache.has(key):
					var pixels := texture.get_image()
					if pixels == null: continue
					# Native-cache repacking must retain existing compressed data,
					# including tiny fallback textures that cannot be S3TC encoded.
					cache[key]=texture
					if not pixels.is_compressed() and pixels.get_width() >= 4 and pixels.get_height() >= 4:
						if not pixels.has_mipmaps(): pixels.generate_mipmaps()
						if pixels.compress(Image.COMPRESS_S3TC) != OK: continue
					cache[key] = ImageTexture.create_from_image(pixels)
				material.set_texture(slot, cache[key])
	for child in node.get_children(): _compress_textures(child, cache)

func _external_textures(node: Node, directory: String, cache: Dictionary) -> bool:
	if node is MeshInstance3D and node.mesh!=null:
		node.mesh.resource_path = ""
		if node.skin != null: node.skin.resource_path = ""
		for surface in range(node.mesh.get_surface_count()):
			var material: Material = node.get_active_material(surface)
			if material == null: continue
			material.resource_path = ""
			if not material is BaseMaterial3D: continue
			for slot in range(BaseMaterial3D.TEXTURE_MAX):
				var texture: Texture2D = material.get_texture(slot)
				if texture == null: continue
				var id := texture.get_instance_id()
				if not cache.has(id):
					var image := texture.get_image()
					if image == null: return false
					var hash := HashingContext.new()
					hash.start(HashingContext.HASH_SHA256)
					hash.update(image.get_data())
					var key := str(image.get_width())+"_"+str(image.get_height())+"_"+str(image.get_format())+"_"+hash.finish().hex_encode()
					if not cache.has(key):
						var path := directory.path_join(key+".res")
						var native := ImageTexture.create_from_image(image)
						if ResourceSaver.save(native,path,ResourceSaver.FLAG_BUNDLE_RESOURCES | ResourceSaver.FLAG_COMPRESS) != OK: return false
						native.take_over_path(path)
						cache[key] = native
					cache[id] = cache[key]
				material.set_texture(slot,cache[id])
	for child in node.get_children():
		if not _external_textures(child,directory,cache): return false
	return true
