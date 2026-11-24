extends SceneTree
func _initialize() -> void:_run.call_deferred()
func positions(actor:Node) -> Dictionary:
	var result:Dictionary={}
	for name in ["pelvis","head_0","hand_R","foot_L"]:
		var index:int=actor.skeleton.find_bone(name)
		if index>=0:result[name]=str(actor.skeleton.get_bone_global_pose(index).origin)
	return result
func _run() -> void:
	var args:=OS.get_cmdline_user_args()
	var bank:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var manifest:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[1]))
	var actor=load("res://stock_actor.gd").new();root.add_child(actor)
	actor.configure(bank,{"t":load(bank.players.t)},"audit");actor.set_team(2)
	print("RIG ",actor.skeleton.transform," ROOT ",actor.skeleton.get_bone_rest(0)," PELVIS ",actor.skeleton.get_bone_global_rest(actor.skeleton.find_bone("pelvis")))
	actor.apply_pose("glock",Vector3.ZERO,false,false,0,false,false,92,91.94,-1000,0)
	print("LIVE ",positions(actor))
	actor.apply_death(manifest.models.t,manifest.deaths.death_chest_a,3)
	print("DEAD ",positions(actor))
	actor.apply_pose("glock",Vector3.ZERO,false,false,0,false,false,92,91.94,-1000,0)
	print("REVIVED ",positions(actor))
	actor.animator.advance(0)
	print("ADVANCED ",positions(actor))
	actor.free();quit()
