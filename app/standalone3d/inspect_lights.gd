extends SceneTree
func _initialize() -> void:run.call_deferred()
func run() -> void:
	var args:PackedStringArray=OS.get_cmdline_user_args()
	var world:Node=(load(args[0]) as PackedScene).instantiate();var stack:Array=[world];var lights:Array=[]
	while not stack.is_empty():
		var node:Node=stack.pop_back();stack.append_array(node.get_children())
		if node is Light3D:lights.append({"name":str(node.name),"color":[node.light_color.r,node.light_color.g,node.light_color.b],"energy":node.light_energy})
	var file:=FileAccess.open(args[1],FileAccess.WRITE);file.store_string(JSON.stringify(lights));file.close();world.free();quit(0)
