extends SceneTree
const Cache=preload("res://static_bindings.gd")
class Viewer extends Node:
	var source_bounce=preload("res://source_bounce.gd").new()
	var source_reflections=preload("res://source_reflections.gd").new()
var failures:Array=[]
func check(value:bool,message:String) -> void:
	if not value:failures.append(message)
func write(path:String,text:String) -> void:
	var file:=FileAccess.open(path,FileAccess.WRITE);file.store_string(text);file.close()
func _initialize() -> void:run.call_deferred()
func run() -> void:
	var args:=OS.get_cmdline_user_args()
	if args.size()!=1:quit(2);return
	var base:String=args[0].path_join("static-bindings-unit")
	var maps:String=base.path_join("maps/test");var lighting:String=base.path_join("lighting/test")
	DirAccess.make_dir_recursive_absolute(maps);DirAccess.make_dir_recursive_absolute(lighting)
	var asset:String=maps.path_join("world.glb");var scene:String=maps.path_join("world.scn")
	write(scene,"scene");write(lighting.path_join("probes.json"),"probes");write(lighting.path_join("reflections.json"),"reflections")
	var viewer:=Viewer.new();root.add_child(viewer)
	viewer.source_bounce.static_queries={"mesh":[2,7]};viewer.source_reflections.static_queries={"mesh":[3]}
	var data:Dictionary={"map_asset":asset,"native_scene":scene,"asset_info":{"fingerprint":"test"}}
	check(Cache.save_cache(viewer,data),"Computed lighting selections were not saved")
	var cached:Dictionary=Cache.read_cache(asset,scene,"test")
	check(not cached.is_empty() and cached.bounce.mesh.map(func(i):return int(i))==[2,7] and cached.reflections.mesh.map(func(i):return int(i))==[3],"Saved selections changed across reload")
	check(Cache.read_cache(asset,scene,"different-revision").is_empty(),"Changed asset revision reused old lighting selections")
	write(lighting.path_join("probes.json"),"changed")
	check(Cache.read_cache(asset,scene,"test").is_empty(),"Changed probe metadata reused stale selections")
	write(lighting.path_join("probes.json"),"probes");write(scene,"changed scene")
	check(Cache.read_cache(asset,scene,"test").is_empty(),"Changed scene reused stale lighting selections")
	data.native_scene=maps.path_join("missing.scn")
	check(not Cache.save_cache(viewer,data),"Missing scene published an unusable cache")
	print(JSON.stringify({"ok":failures.is_empty(),"failures":failures}));quit(0 if failures.is_empty() else 1)
