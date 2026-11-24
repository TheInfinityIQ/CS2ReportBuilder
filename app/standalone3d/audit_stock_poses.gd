extends SceneTree
func _initialize() -> void:_run.call_deferred()
func _run() -> void:
	var args:=OS.get_cmdline_user_args()
	var bank:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var assets:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[1]))
	var overlay:=Control.new();root.add_child(overlay)
	var scenes:Dictionary={}
	for team in ["ct","t"]:
		scenes["vm_"+team]=load(assets.arms[team].scene)
		scenes[team]=load(bank.players[team])
	var view=load("res://source_viewmodel.gd").new();root.add_child(view);view.configure(overlay,assets,scenes)
	var actor=load("res://stock_actor.gd").new();root.add_child(actor);actor.configure(bank,scenes,"audit")
	var report:Dictionary={"weapons":[],"failures":[],"generic_pose_fallbacks":assets.get("generic_pose_fallbacks",[]),"audio":{}}
	for key in assets.viewmodels:
		# Utility paths are retained in the enriched replay stock dictionary.
		if not bank.weapons.has(key):continue
		if not bank.weapons[key].get("utility",false):
			for action in ["fire","reload"]:
				if action=="reload" and key in ["knife","taser"]:continue
				var sound_path:String=str(bank.sounds.get(action+":"+str(key),""))
				var stream:AudioStream
				if sound_path.ends_with(".wav"):stream=AudioStreamWAV.load_from_file(sound_path)
				elif sound_path.ends_with(".mp3"):stream=AudioStreamMP3.load_from_file(sound_path)
				report.audio[action+":"+str(key)]=stream!=null and stream.get_length()>0
				if not report.audio[action+":"+str(key)]:report.failures.append(str(key)+":"+action+" stock sound missing or invalid")
		scenes["weapon:"+str(key)]=load(bank.weapons[key].scene)
		for team in [2,3]:
			actor.set_team(team)
			actor.apply_pose(key,Vector3.ZERO,false,false,0,false,false,.1,-1000,-1000,0)
			var right:int=actor.skeleton.find_bone("hand_R");var left:int=actor.skeleton.find_bone("hand_L")
			var baseline:float=actor.skeleton.get_bone_global_pose(right).origin.distance_to(actor.skeleton.get_bone_global_pose(left).origin)
			actor.apply_pose(key,Vector3.ZERO,false,false,0,false,false,.1,.07,-1000,0)
			if not bank.weapons[key].get('utility',false):
				var firing:String=str(bank.weapons[key].get('fire_animation',''))
				if actor._clip(firing).is_empty():report.failures.append(str(key)+":"+str(team)+" authored world firing clip missing: "+firing)
			var fired:float=actor.skeleton.get_bone_global_pose(right).origin.distance_to(actor.skeleton.get_bone_global_pose(left).origin)
			if fired>baseline+.4:report.failures.append(str(key)+":"+str(team)+" world recoil separated hands")
			var head:int=actor.skeleton.find_bone("head_0")
			if actor.skeleton.get_bone_global_pose(head).origin.y<1.2:report.failures.append(str(key)+":"+str(team)+" world firing lost up axis")
			for action in ["idle","shoot1","reload","draw"]:
				if not assets.viewmodels[key].has(action):continue
				actor.apply_pose(key,Vector3.ZERO,false,false,0,action=="reload",false,.1,.07 if action=="shoot1" else -1000,0 if action=="reload" else -1000,0)
				if actor.skeleton.get_bone_global_pose(head).origin.y<1.2:report.failures.append(str(key)+":"+str(team)+":"+action+" world action lost up axis")
				view.update_pose(true,team,key,.1,action=="reload",.07 if action=="shoot1" else -1000,.0 if action=="reload" else -1000,.0 if action=="draw" else -1000)
				if not view.picture.visible or view.arm_skeleton==null or view.weapon_rig==null:
					report.failures.append(str(key)+":"+str(team)+":"+action+" missing rig")
				elif not view.muzzle.origin.is_finite() or view.muzzle.origin.z>.05 or view.muzzle.origin.length()>3:
					report.failures.append(str(key)+":"+str(team)+":"+action+" misplaced muzzle "+str(view.muzzle.origin))
		if view.weapon_rig!=null:view.weapon_rig.free();view.weapon_rig=null;view.weapon_skeleton=null
		actor._weapon("")
		scenes.erase("weapon:"+str(key))
		report.weapons.append(key)
	report.failures.append_array(view.sampler.failures)
	report.ok=report.failures.is_empty()
	var file:=FileAccess.open(args[2],FileAccess.WRITE);file.store_string(JSON.stringify(report,"\t"));file.close()
	actor.free();view.free();overlay.free();quit(0 if report.ok else 1)
