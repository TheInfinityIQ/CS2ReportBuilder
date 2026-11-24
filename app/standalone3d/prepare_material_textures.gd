extends SceneTree
func _initialize() -> void:
	var args:=OS.get_cmdline_user_args()
	var jobs:Variant=JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	if not jobs is Array:quit(2);return
	for job in jobs:
		var image:=Image.load_from_file(str(job.source))
		if image==null:quit(3);return
		image.generate_mipmaps()
		if image.compress(Image.COMPRESS_S3TC)!=OK:quit(4);return
		var texture:=ImageTexture.create_from_image(image)
		var path:=str(job.target)+".pending.res"
		if ResourceSaver.save(texture,path,ResourceSaver.FLAG_COMPRESS)!=OK:quit(5);return
		if DirAccess.rename_absolute(path,str(job.target))!=OK:quit(6);return
	quit()
