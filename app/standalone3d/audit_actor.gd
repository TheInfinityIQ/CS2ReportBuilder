extends SceneTree

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var bank: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var scenes: Dictionary = {}
	for team in bank.players: scenes[team] = load(bank.players[team])
	for key in bank.weapons:
		scenes["weapon:"+key] = load(bank.weapons[key].scene)
	var results: Array = []
	var failures: Array = []
	var capabilities: Array = []
	for team in [2,3]:
		var actor = load("res://stock_actor.gd").new()
		root.add_child(actor)
		actor.configure(bank,scenes,"audit")
		actor.set_team(team)
		for key in bank.weapons:
			for action in ["idle","run","jump","fire","reload"]:
				actor.apply_pose(key,Vector3(220,0,0) if action=="run" else Vector3.ZERO,action=="jump",false,0,action=="reload",false,2,.0 if action!="fire" else 1.9,1.5,0,0,.2)
				var bones: Dictionary = {}
				for name in ["upperarm_L","upperarm_R","hand_L","hand_R"]:
					var index: int = actor.skeleton.find_bone(name)
					if index>=0: bones[name] = str(actor.skeleton.get_bone_global_pose(index))
				var clip: String = actor.selected_animation
				if clip=="" or actor.held==null: failures.append({"team":team,"weapon":key,"action":action,"reason":"Missing clip or held model"})
				if not bank.weapons[key].get("utility",false):
					var expected := str(bank.weapons[key].get("fire_animation","shoot_"+str(bank.weapons[key].get("clip",key)))) if action=="fire" else "reload_"+str(bank.weapons[key].get("clip",key))
					if action in ["fire","reload"] and not (key=="knife" and action=="reload") and not clip.ends_with(expected):
						capabilities.append({"team":team,"weapon":key,"action":action,"expected":expected,"actual":clip})
				if action=="fire" and bank.weapons[key].get("class")=="pistol":
					var left: Vector3 = actor.skeleton.get_bone_global_pose(actor.skeleton.find_bone("hand_L")).origin
					var right: Vector3 = actor.skeleton.get_bone_global_pose(actor.skeleton.find_bone("hand_R")).origin
					if left.distance_to(right)>.8 or maxf(left.z,right.z)>2.0:
						failures.append({"team":team,"weapon":key,"reason":"Pistol firing posture invalid","hand_span":left.distance_to(right)})
				if action=="fire":
					var before: Array = []
					for bone in range(actor.skeleton.get_bone_count()): before.append(actor.skeleton.get_bone_pose(bone))
					actor.apply_pose(key,Vector3.ZERO,false,false,0,false,false,2,1.9,1.5,0)
					for bone in range(before.size()):
						if not before[bone].is_equal_approx(actor.skeleton.get_bone_pose(bone)):
							failures.append({"team":team,"weapon":key,"reason":"Repeated-tick pose drift","bone":bone})
				results.append({"team":team,"weapon":key,"action":action,"clip":clip,"bones":bones,"tracks":actor.animator.get_animation(clip).get_track_count() if clip!="" else 0})
		actor.free()
	var file := FileAccess.open(args[1],FileAccess.WRITE)
	file.store_string(JSON.stringify({"poses":results,"failures":failures,"capability_gaps":capabilities,"ok":failures.is_empty()},"\t"))
	quit(0 if failures.is_empty() else 1)
