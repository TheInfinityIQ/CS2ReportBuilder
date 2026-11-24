extends SceneTree
func _initialize() -> void:
	var jobs:Array=JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
	for job in jobs:
		var frames:Array[Image]=[]
		var width:=0;var height:=0
		for path in job.frames:
			var source:=Image.load_from_file(path)
			if source==null:quit(2);return
			width=maxi(width,source.get_width());height=maxi(height,source.get_height())
		width=ceili(width/4.0)*4;height=ceili(height/4.0)*4
		for path in job.frames:
			var image:=Image.load_from_file(path)
			if image==null:quit(2);return
			image.convert(Image.FORMAT_RGBA8)
			var canvas:=Image.create(width,height,false,Image.FORMAT_RGBA8)
			canvas.fill(Color.TRANSPARENT)
			canvas.blit_rect(image,Rect2i(Vector2i.ZERO,image.get_size()),Vector2i((width-image.get_width())/2,height-image.get_height()))
			image=canvas
			if job.frames.size()==1:
				# This source muzzle texture is authored for additive blending;
				# its opaque black background must not become a solid billboard.
				var pixels:=image.get_data()
				for index in range(0,pixels.size(),4):pixels[index+3]=maxi(pixels[index],maxi(pixels[index+1],pixels[index+2]))
				image=Image.create_from_data(width,height,false,Image.FORMAT_RGBA8,pixels)
			image.generate_mipmaps()
			if image.compress(Image.COMPRESS_S3TC)!=OK:quit(3);return
			frames.append(image)
		var texture:Resource
		if frames.size()==1:texture=ImageTexture.create_from_image(frames[0])
		elif job.get("layer_bank",false):
			# Keep CPU-backed, independently filtered images. Serializing a
			# Texture2DArray on the headless dummy GPU loses its layer data.
			# A shared compressed bank can be uploaded as an array at playback.
			var bytes:=PackedByteArray()
			for frame in frames:bytes.append_array(frame.get_data())
			var output:=FileAccess.open(str(job.target)+".blocks",FileAccess.WRITE)
			if output==null:quit(5);return
			output.store_buffer(bytes);output.close()
			var meta:=FileAccess.open(str(job.target)+".json",FileAccess.WRITE)
			var digest:=HashingContext.new();digest.start(HashingContext.HASH_SHA256);digest.update(bytes)
			meta.store_string(JSON.stringify({"schema":1,"width":width,"height":height,"layers":frames.size(),"format":frames[0].get_format(),"stride":frames[0].get_data_size(),"bytes":bytes.size(),"sha256":digest.finish().hex_encode()}));meta.close()
			continue
		else:
			# Headless Texture2DArray serialization reads back from a dummy GPU,
			# producing null layers. A native atlas retains its CPU backing data
			# and is safe to prepare offline and load on the worker thread.
			var atlas:=Image.create(width*8,height*ceili(frames.size()/8.0),false,Image.FORMAT_RGBA8)
			atlas.fill(Color.TRANSPARENT)
			for index in range(frames.size()):
				var frame:=frames[index].duplicate() as Image
				frame.decompress();frame.clear_mipmaps()
				atlas.blit_rect(frame,Rect2i(0,0,width,height),Vector2i(index%8*width,index/8*height))
			atlas.generate_mipmaps();atlas.compress(Image.COMPRESS_S3TC)
			texture=ImageTexture.create_from_image(atlas)
		if ResourceSaver.save(texture,job.target,ResourceSaver.FLAG_COMPRESS)!=OK:quit(5);return
	quit()
