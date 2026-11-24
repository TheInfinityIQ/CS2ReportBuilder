extends SceneTree
var failures:Array=[]
func _initialize() -> void:run.call_deferred()
func snapshot(actor:Node) -> Array:
	var poses:Array=[]
	for bone in range(actor.skeleton.get_bone_count()):poses.append(actor.skeleton.get_bone_pose(bone))
	return poses
func difference(a:Array,b:Array) -> float:
	var error:float=0
	for i in range(a.size()):
		error=maxf(error,a[i].origin.distance_to(b[i].origin))
		error=maxf(error,(a[i].basis.x-b[i].basis.x).length())
		error=maxf(error,(a[i].basis.y-b[i].basis.y).length())
		error=maxf(error,(a[i].basis.z-b[i].basis.z).length())
	return error
func run() -> void:
	var args:=OS.get_cmdline_user_args();var fixture:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var cache=preload("res://native_resource_cache.gd").new();cache.configure(args[1]);var scenes:Dictionary={}
	for team in ["t","ct"]:scenes[team]=cache.load_scene(fixture.stock.players[team])
	var actor=preload("res://stock_actor.gd").new();root.add_child(actor);actor.configure(fixture.stock,scenes,"handoff");actor.set_team(2)
	actor.apply_pose("glock",Vector3(-100,40,0),false,true,.65,false,false,2.5,2.45,-1000,35,17,-1,159,3.2,false)
	var living:Array=snapshot(actor);actor.capture_death_entry(101)
	var model:String=fixture.actor_assets.models.t;var clip:String=fixture.actor_assets.deaths.death_chest_a
	actor.apply_death(model,clip,0,101);var start_error:float=difference(living,snapshot(actor))
	if start_error>.00001:failures.append("Death start did not preserve the sampled living stance")
	if actor.held!=null:failures.append("Capturing a body-only pose allocated a held weapon")
	actor.apply_death(model,clip,.06,101);var early:Array=snapshot(actor)
	actor.apply_death(model,clip,2,101);actor.reset_pose_history();actor.apply_death(model,clip,.06,101)
	var seek_error:float=difference(early,snapshot(actor))
	if seek_error>.00001:failures.append("Death transition depends on previously displayed time")
	actor.apply_death(model,clip,1,101);var settled:Array=snapshot(actor);actor.reset_pose_history();actor.apply_death(model,clip,1)
	if difference(settled,snapshot(actor))>.00001:failures.append("Handoff changed the authored motion after its transition")
	for key in range(20):actor.capture_death_entry(key)
	if actor.death_entries.size()!=actor.DEATH_ENTRY_LIMIT:failures.append("Death entry cache exceeded its limit")
	actor.set_team(3)
	if not actor.death_entries.is_empty():failures.append("A different rig reused the old team's pose snapshots")
	actor.free();print(JSON.stringify({"ok":failures.is_empty(),"failures":failures,"initial_pose_error":start_error,"seek_pose_error":seek_error}));quit(0 if failures.is_empty() else 1)
