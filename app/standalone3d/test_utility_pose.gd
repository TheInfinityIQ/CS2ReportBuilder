extends SceneTree
func _initialize() -> void:run.call_deferred()
func run() -> void:
	var failures:Array=[];var selector=preload("res://utility_pose.gd")
	if selector.action({"anim_state":"WPN_ANIMSTATE_GRENADE_THROW","throw_strength":0})!="throw_underhand":failures.append("Underhand throw lost")
	if selector.action({"anim_state":"WPN_ANIMSTATE_GRENADE_THROW","throw_strength":1})!="throw_overhand":failures.append("Overhand throw lost")
	if selector.charge({"throw_strength":.5})!="throwcharge_mid":failures.append("Medium-strength hold lost")
	var skeleton:=Skeleton3D.new();root.add_child(skeleton)
	skeleton.add_bone("root_motion");skeleton.add_bone("spine_0");skeleton.set_bone_parent(1,0)
	skeleton.set_bone_pose_position(0,Vector3(1,2,3));skeleton.set_bone_pose_position(1,Vector3(0,1,0))
	var neutral:Dictionary={"frames":1,"fps":30,"bones":["root_motion","spine_0"],"samples":PackedFloat32Array([0,0,0,0,0,0,1,0,0,0,0,0,0,0,1,0])}
	var sampler=preload("res://source_pose.gd").new();sampler.apply_additive(skeleton,neutral,0,false,true)
	if not skeleton.get_bone_pose_scale(1).is_equal_approx(Vector3.ONE):failures.append("Neutral additive scale collapses the spine")
	if skeleton.get_bone_pose_position(0)!=Vector3(1,2,3):failures.append("Utility upper-body layer moves the root")
	if skeleton.get_bone_pose_position(1)!=Vector3(0,1,0):failures.append("Neutral additive pose changes stance")
	print(JSON.stringify({"ok":failures.is_empty(),"failures":failures}));quit(0 if failures.is_empty() else 1)
