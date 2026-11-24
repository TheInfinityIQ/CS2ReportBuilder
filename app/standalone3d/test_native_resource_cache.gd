extends SceneTree
func _initialize() -> void:run.call_deferred()
func run() -> void:
	var args:PackedStringArray=OS.get_cmdline_user_args();var resolver=preload("res://native_resource_cache.gd").new();resolver.configure(args[0])
	var failed:Array=[]
	for path in resolver.items:
		if resolver.resolve(path)==path:failed.append(path)
	var real_hits:int=resolver.hits
	var folder:String=args[0].path_join("test-fixtures/resource-"+str(Time.get_ticks_usec()));DirAccess.make_dir_recursive_absolute(folder)
	var original:String=folder.path_join("original.scn");var file:=FileAccess.open(original,FileAccess.WRITE);file.store_string("RSCCoriginal");file.close()
	var name:String="a".repeat(64)+".scn";var target:String=folder.path_join(name)
	file=FileAccess.open(target,FileAccess.WRITE);file.store_string("RSRCprepared");file.close()
	var entry:Dictionary={"schema":4,"path":name,"source_bytes":12,"source_modified":FileAccess.get_modified_time(original),"bytes":12,"modified":FileAccess.get_modified_time(target)}
	original=original.replace("\\","/");folder=folder.replace("\\","/");target=target.replace("\\","/")
	resolver.folder=folder;resolver.items={original:JSON.parse_string(JSON.stringify(entry))}
	if resolver.resolve(original)!=target:failed.append("JSON numeric fields rejected a matching cache")
	for change in [{"path":"../"+name},{"source_bytes":13},{"bytes":13},{"source_modified":0},{"modified":0},{"schema":3}]:
		resolver.items[original]=entry.merged(change,true)
		if resolver.resolve(original)!=original:failed.append("Invalid cache was accepted: "+str(change))
	resolver.items[original]=entry
	file=FileAccess.open(target,FileAccess.WRITE);file.store_string("BAD!prepared");file.close()
	resolver.items[original].modified=FileAccess.get_modified_time(target)
	if resolver.resolve(original)!=original:failed.append("Invalid binary header accepted")
	DirAccess.remove_absolute(target);DirAccess.remove_absolute(original);DirAccess.remove_absolute(folder)
	var result:Dictionary={"ok":failed.is_empty() and real_hits==33,"hits":real_hits,"failures":failed}
	print(JSON.stringify(result));quit(0 if result.ok else 1)
