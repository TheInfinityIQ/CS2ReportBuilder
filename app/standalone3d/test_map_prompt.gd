extends SceneTree

const Viewer := preload("res://main.gd")

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty(): quit(2); return
	var folder: String = args[0]
	DirAccess.make_dir_recursive_absolute(folder)
	var viewer := Viewer.new()
	root.add_child(viewer)
	viewer.options["session"] = folder
	viewer.job_path = folder
	viewer.loading_active = true
	var file := FileAccess.open(folder.path_join("progress.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify({"state":"permission_required","message":"Overpass needs preparation",
		"map_setup":{"map":"de_overpass","label":"Overpass","in_pool":false,"fingerprint":"test"}}))
	file.close()
	viewer._poll_job()
	var request: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(folder.path_join("request.json")))
	var state: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(folder.path_join("status.json")))
	var ok: bool = viewer.map_setup_pending and not viewer.loading_active and viewer.backend_pid == -1
	ok = ok and request["action"] == "map_setup" and request["map_setup"]["map"] == "de_overpass"
	ok = ok and state["state"] == "permission_required"
	file = FileAccess.open(folder.path_join("command.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify({"id":7,"action":"pause"}));file.close()
	viewer.playing = true
	viewer._poll_toolbox()
	ok = ok and not viewer.playing and viewer.toolbox_command == 7
	var search := InputEventKey.new()
	search.pressed = true;search.ctrl_pressed = true;search.keycode = KEY_F
	viewer._unhandled_key_input(search)
	request = JSON.parse_string(FileAccess.get_file_as_string(folder.path_join("request.json")))
	ok = ok and request["action"] == "search"
	print(JSON.stringify({"ok":ok,"request":request["action"],"state":state["state"],"no_import":viewer.backend_pid == -1}))
	quit(0 if ok else 1)
