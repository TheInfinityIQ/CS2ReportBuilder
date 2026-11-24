extends SceneTree
var meshes:Array=[]
func _find(node:Node) -> Skeleton3D:
	if node is Skeleton3D:print("SKELETON ",node.get_bone_count())
	if node is Skeleton3D and node.find_bone("hand_R")>=0:return node
	for child in node.get_children():
		var found:=_find(child)
		if found!=null:return found
	return null
func _initialize() -> void:_run.call_deferred()
func _run() -> void:
	var args:=OS.get_cmdline_user_args()
	var manifest:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var rig=load(manifest.arms.ct.scene).instantiate()
	root.add_child(rig)
	var skeleton:=_find(rig)
	if skeleton==null:
		rig.print_tree_pretty();quit(2);return
	var sampler=load("res://source_pose.gd").new()
	var metadata:Dictionary=sampler.model(manifest.arms.ct.model)
	var clip:Dictionary=sampler.variant(manifest.viewmodels.glock.idle,"arms")
	var pose:Dictionary=sampler.sample(clip,0)
	var conversion:Transform3D=sampler.apply(skeleton,metadata,pose)
	print(JSON.stringify({"failures":sampler.failures,"bones":skeleton.get_bone_count(),"hand_R":str(skeleton.get_bone_global_pose(skeleton.find_bone("hand_R"))),"wpn":str(conversion*pose.get("wpn",Transform3D.IDENTITY))}))
	rig.free()
	quit(0 if sampler.failures.is_empty() else 1)
