extends SceneTree
func _initialize() -> void:
	var args:=OS.get_cmdline_user_args()
	var meta:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var replay:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[1]))
	var output:Dictionary={}
	for pair in [["bank",str(meta.geometry)],["original",str(replay.native_scene)]]:
		var packed:=load(pair[1]) as PackedScene
		var state:=packed.get_state()
		var paths:Array=[]
		for index in range(state.get_node_count()):
			for prop in range(state.get_node_property_count(index)):
				if state.get_node_property_name(index,prop)=="mesh":paths.append(str(state.get_node_path(index)))
		output[pair[0]]=paths
	var matches:=0
	for path in output.bank:
		if path in output.original:matches+=1
	print(JSON.stringify({"matches":matches,"bank":output.bank.slice(0,4),"original":output.original.slice(0,4)}))
	quit()
