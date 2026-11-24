extends SceneTree
# Calibrate locomotion from the authored planted-foot velocity, not arbitrary
# inches-per-cycle constants. Reads shared actors; emits only small metadata.
func _initialize() -> void:run.call_deferred()
func run() -> void:
	var args:=OS.get_cmdline_user_args()
	if args.size()!=2:quit(2);return
	var bank:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var actor=preload("res://stock_actor.gd").new();root.add_child(actor)
	actor.configure(bank,{"ct":load(bank.players.ct)},"gait calibration");actor.set_team(3)
	if actor.animator==null or actor.skeleton==null:quit(3);return
	var pattern:=RegEx.new();pattern.compile("(walk|run|crouch)_(n|nw|w|sw|s|se|e|ne)_(pistol|rifle|knife)$")
	var left:int=actor.skeleton.find_bone("ankle_L");var right:int=actor.skeleton.find_bone("ankle_R")
	var root_bone:int=actor.skeleton.find_bone("root_motion");var strides:Dictionary={};var details:Dictionary={}
	for clip in actor.animator.get_animation_list():
		if pattern.search(clip)==null:continue
		var animation:Animation=actor.animator.get_animation(clip);var length:float=animation.length
		if length<=0:continue
		var feet:Array=[[],[]];var minimum:Array=[INF,INF]
		actor.animator.play(clip)
		for index in range(49):
			actor.skeleton.reset_bone_poses();actor.animator.seek(minf(length-.0001,float(index)/48*length),true)
			if root_bone>=0:actor.skeleton.set_bone_pose_position(root_bone,Vector3.ZERO)
			for side in range(2):
				var point:Vector3=actor.skeleton.get_bone_global_pose(left if side==0 else right).origin
				feet[side].append(point);minimum[side]=minf(minimum[side],point.y)
		var velocities:Array[float]=[]
		for side in range(2):
			for index in range(48):
				var a:Vector3=feet[side][index];var b:Vector3=feet[side][index+1]
				if a.y>minimum[side]+.045 or b.y>minimum[side]+.045:continue
				var speed:float=Vector2(b.x-a.x,b.z-a.z).length()*48/length
				if speed>.05 and speed<12:velocities.append(speed)
		if velocities.size()<4:continue
		velocities.sort();var distance:float=velocities[velocities.size()/2]*length
		if distance<.20 or distance>6:continue
		strides[clip]=distance/.0254
		details[clip]={"cycle_seconds":length,"stride_units":distance/.0254,"contact_samples":velocities.size()}
	var output:=FileAccess.open(args[1],FileAccess.WRITE)
	output.store_string(JSON.stringify({"schema":1,"strides":strides,"details":details}));output.close()
	print(JSON.stringify({"ok":strides.size()>=24,"clips":strides.size()}));quit(0 if strides.size()>=24 else 4)
