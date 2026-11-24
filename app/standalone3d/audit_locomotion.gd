extends SceneTree
func _initialize() -> void: _run.call_deferred()
func _run() -> void:
	var args:=OS.get_cmdline_user_args()
	var bank: Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var actor=load("res://stock_actor.gd").new()
	root.add_child(actor)
	actor.configure(bank,{"t":load(bank.players.t)},"audit")
	actor.set_team(2)
	var result:Array=[]
	for direction in ["n","ne","e","se","s","sw","w","nw"]:
		var clip:String=actor._clip("walk_"+direction+"_pistol")
		if clip=="":result.append({"direction":direction,"missing":true});continue
		var animation:Animation=actor.animator.get_animation(clip)
		var motion:Dictionary={}
		for track in range(animation.get_track_count()):
			if str(animation.track_get_path(track)).ends_with(":root_motion") and animation.track_get_type(track)==Animation.TYPE_POSITION_3D:
				var delta:Vector3=animation.position_track_interpolate(track,animation.length-.001)-animation.position_track_interpolate(track,0)
				motion={"local":str(delta),"world":str(actor.skeleton.global_basis*delta)}
		result.append({"direction":direction,"clip":clip,"root_motion":motion})
	var file:=FileAccess.open(args[1],FileAccess.WRITE)
	file.store_string(JSON.stringify(result,"\t"))
	actor.free()
	quit()
