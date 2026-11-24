extends SceneTree
# Package already-prepared native resources; no conversion or game-file writes.
func _initialize() -> void:run.call_deferred()
var textures:Dictionary={}
var prefix:String
func visit(node:Node) -> bool:
	if node is MeshInstance3D and node.mesh!=null:
		for surface in range(node.mesh.get_surface_count()):
			var material:Material=node.get_active_material(surface)
			if not material is BaseMaterial3D:continue
			for slot in range(BaseMaterial3D.TEXTURE_MAX):
				var texture:Texture2D=material.get_texture(slot)
				if texture==null:continue
				var path:String=texture.resource_path
				if path.begins_with(prefix):continue
				if not FileAccess.file_exists(path):return false
				var virtual_path:String=prefix+path.get_file()
				textures[virtual_path]=path;texture.take_over_path(virtual_path)
	for child in node.get_children():
		if not visit(child):return false
	return true
func run() -> void:
	var args:=OS.get_cmdline_user_args()
	if args.size()!=4:quit(2);return
	var packed:=load(args[0]) as PackedScene
	if packed==null:quit(3);return
	var scene:Node=packed.instantiate();prefix="res://prepared/"+args[3]+"/"
	if not visit(scene):scene.free();quit(4);return
	var output:=PackedScene.new()
	if output.pack(scene)!=OK:scene.free();quit(5);return
	if ResourceSaver.save(output,args[1],ResourceSaver.FLAG_COMPRESS)!=OK:scene.free();quit(6);return
	var packer:=PCKPacker.new()
	if packer.pck_start(args[2])!=OK:scene.free();quit(7);return
	for path in textures:
		if packer.add_file(path,textures[path])!=OK:scene.free();quit(8);return
	if packer.add_file(prefix+"world.scn",args[1])!=OK:scene.free();quit(9);return
	var result:int=packer.flush();scene.free()
	print(JSON.stringify({"ok":result==OK,"textures":textures.size(),"scene":prefix+"world.scn"}));quit(0 if result==OK else 10)
