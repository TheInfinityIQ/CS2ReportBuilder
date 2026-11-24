extends SceneTree
func _initialize() -> void:
	var bank=preload("res://particle_bank.gd");var args:=OS.get_cmdline_user_args()
	if args.size()!=1:quit(2);return
	DirAccess.make_dir_recursive_absolute(args[0]);var path:String=args[0].path_join("test-bank.json");var failures:Array=[]
	var missing:String=args[0].path_join("never-written-bank.json")
	if bank.read_bank(missing,32,false)!={} or not bank.read_bank(missing,32,true).get("error","").contains("missing"):failures.append("Missing required/optional bank contracts differ")
	var file:=FileAccess.open(path,FileAccess.WRITE);file.store_string(JSON.stringify({"schema":1,"layers":131}));file.close()
	if bank.read_bank(path,32,false)!={} or not bank.read_bank(path,32,true).has("error"):failures.append("Legacy sequence used an incompatible frame bank")
	if bank.read_bank(path,0,false)!={}:failures.append("Unknown legacy sequence loaded a new bank")
	file=FileAccess.open(path,FileAccess.WRITE);file.store_string(JSON.stringify({"schema":1,"layers":2,"width":4,"height":4,"format":Image.FORMAT_DXT5,"stride":17}));file.close()
	if not bank.read_bank(path,2,true).get("error","").contains("mip chain"):failures.append("Invalid mip lengths accepted")
	print(JSON.stringify({"ok":failures.is_empty(),"failures":failures}));quit(0 if failures.is_empty() else 1)
