extends SceneTree
func _initialize() -> void:run.call_deferred()
func run() -> void:
	var args:PackedStringArray=OS.get_cmdline_user_args()
	if args.size()!=2:quit(2);return
	var packed:=load(args[0]) as PackedScene
	if packed==null:quit(3);return
	var world:Node3D=packed.instantiate();root.add_child(world)
	var output:Array=[];var stack:Array=[world]
	while not stack.is_empty():
		var node:Node=stack.pop_back();stack.append_array(node.get_children())
		if not node is MeshInstance3D or node.mesh==null:continue
		var box:AABB=node.global_transform*node.mesh.get_aabb()
		# Existing Source->Godot import maps XYZ to YZX in metres.
		var a:Vector3=box.position;var b:Vector3=box.end
		output.append({"path":str(world.get_path_to(node)),"min":[a.z/.0254,a.x/.0254,a.y/.0254],"max":[b.z/.0254,b.x/.0254,b.y/.0254]})
	var file:=FileAccess.open(args[1],FileAccess.WRITE)
	if file==null:quit(4);return
	file.store_string(JSON.stringify(output));world.free();quit(0)
