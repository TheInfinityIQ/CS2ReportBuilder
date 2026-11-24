extends SceneTree

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var scene := Node3D.new()
	var node := MeshInstance3D.new()
	node.mesh = BoxMesh.new()
	var image := Image.create(16,16,false,Image.FORMAT_RGBA8)
	image.fill(Color(.3,.6,.8))
	var material := StandardMaterial3D.new()
	material.albedo_texture = ImageTexture.create_from_image(image)
	node.material_override = material
	scene.add_child(node)
	node.owner = scene
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	var error := document.append_from_scene(scene,state)
	if error == OK: error = document.write_to_filesystem(state,args[0])
	scene.free()
	quit(0 if error == OK else 1)
