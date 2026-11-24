extends SceneTree
func _initialize() -> void:run.call_deferred()
func run() -> void:
	var args:=OS.get_cmdline_user_args()
	if args.size()!=2:quit(2);return
	var fixture:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var cache=preload("res://native_resource_cache.gd").new();cache.configure(args[1])
	var bank:Dictionary={}
	for team in ["ct","t"]:bank[team]=cache.load_scene(fixture.stock.players[team])
	var results:Dictionary={};var ok:bool=true
	for team in [3,2]:
		var actor=preload("res://stock_actor.gd").new();root.add_child(actor)
		actor.configure(fixture.stock,bank,"Locomotion test");actor.set_team(team)
		results[str(team)]={}
		for weapon in ["glock","ak47","knife"]:
			results[str(team)][weapon]=preload("res://locomotion_audit.gd").run(actor,weapon)
			ok=ok and results[str(team)][weapon].ok
		actor.free()
	print(JSON.stringify({"ok":ok,"teams":results}));quit(0 if ok else 1)
