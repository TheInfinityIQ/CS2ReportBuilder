extends RefCounted

static func snapshot(actor:Node) -> Array[Transform3D]:
	var result:Array[Transform3D]=[]
	for bone in range(actor.skeleton.get_bone_count()):result.append(actor.skeleton.get_bone_pose(bone))
	return result

static func difference(a:Array[Transform3D],b:Array[Transform3D]) -> Dictionary:
	var angle:float=0;var position:float=0
	for i in range(a.size()):
		if a[i].is_equal_approx(b[i]):continue
		angle=maxf(angle,rad_to_deg(a[i].basis.get_rotation_quaternion().angle_to(b[i].basis.get_rotation_quaternion())))
		position=maxf(position,a[i].origin.distance_to(b[i].origin))
	return {"degrees":angle,"metres":position}

static func pose(actor:Node,yaw:float,crouch:float=0,speed:float=220,seconds:float=1,weapon:String="glock") -> Array[Transform3D]:
	actor.apply_pose(weapon,Vector3(speed,0,0),false,false,crouch,false,false,seconds,-1000,-1000,yaw,0,-1,100,.37)
	return snapshot(actor)

static func run(actor:Node,weapon:String="glock") -> Dictionary:
	var failures:Array=[];var checks:Dictionary={}
	for boundary in [0.0,22.5,45.0,67.5,90.0,112.5,135.0,157.5,180.0,-157.5,-135.0,-112.5,-90.0,-67.5,-45.0,-22.5]:
		actor.reset_pose_history();var a:=pose(actor,boundary-.01,0,220,1,weapon)
		actor.reset_pose_history();var b:=pose(actor,boundary+.01,0,220,1,weapon)
		var delta:=difference(a,b);checks[str(boundary)]=delta
		if delta.degrees>1 or delta.metres>.003:failures.append("Directional pose snaps at "+str(boundary)+" degrees")
	actor.reset_pose_history();var a:=pose(actor,0,.4999,220,1,weapon)
	actor.reset_pose_history();var b:=pose(actor,0,.5001,220,1,weapon)
	var crouch:=difference(a,b)
	if crouch.degrees>1 or crouch.metres>.003:failures.append("Crouch pose snaps at half duck")
	actor.reset_pose_history();a=pose(actor,0,0,129.99,1,weapon)
	actor.reset_pose_history();b=pose(actor,0,0,130.01,1,weapon)
	var speed:=difference(a,b)
	if speed.degrees>1 or speed.metres>.003:failures.append("Walking/running pose snaps at speed threshold")
	actor.reset_pose_history();a=pose(actor,0,0,9.99,1,weapon)
	actor.reset_pose_history();b=pose(actor,0,0,10.01,1,weapon)
	var stop:=difference(a,b)
	if stop.degrees>1 or stop.metres>.003:failures.append("Starting/stopping pose snaps at speed threshold")
	actor.reset_pose_history();pose(actor,45,0,220,.99,weapon);a=pose(actor,22.49,0,220,1,weapon)
	actor.reset_pose_history();b=pose(actor,22.49,0,220,1,weapon)
	var history:=difference(a,b)
	if history.degrees>.01 or history.metres>.00001:failures.append("Same tick pose depends on the route taken to seek there")
	# At a single-clip endpoint, sampling must reproduce the imported animation,
	# including its axis conversion and sparse-track rest poses.
	var kind:String=actor.assets.weapons[weapon].class;var equivalent:int=0
	for action in ["idle","idle_crouch","walk_n","walk_s","run_n","run_s","crouch_n"]:
		var clip:String=actor._clip(action+"_"+kind)
		if clip.is_empty():failures.append("Prepared locomotion clip missing: "+action+"_"+kind);continue
		var time:float=actor.animator.get_animation(clip).length*.37
		actor.animator.play(clip);actor.skeleton.reset_bone_poses();actor.animator.seek(time,true)
		a=snapshot(actor)
		actor.locomotion_sampler.apply(actor.animator,actor.skeleton,[{"clip":clip,"time":time,"weight":1.0}]);b=snapshot(actor)
		var delta:=difference(a,b)
		if delta.degrees>.1 or delta.metres>.00001:failures.append("Body sampler altered authored clip: "+clip+" "+str(delta))
		else:equivalent+=1
	return {"ok":failures.is_empty(),"failures":failures,"direction_boundaries":checks,"crouch_boundary":crouch,"speed_boundary":speed,"stop_boundary":stop,"seek_history":history,"authored_clips_equivalent":equivalent}
