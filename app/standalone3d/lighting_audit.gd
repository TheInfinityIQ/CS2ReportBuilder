extends RefCounted

# In-renderer regression: fixed camera, actual map pixels, no desktop automation.
static func run(viewer:Node,directory:String) -> Dictionary:
	var result:Dictionary={"failures":[],"brightness":[],"suns":[]}
	result.environment={"white_point":viewer.world_environment.tonemap_white,"ambient_sky_mix":viewer.world_environment.ambient_light_sky_contribution,"ambient_color":str(viewer.world_environment.ambient_light_color)}
	var original:float=viewer.review_brightness
	for value in [.65,1.0,1.35]:
		viewer._set_brightness(value)
		# Sky radiance is amortised across frames; let it settle before sampling.
		for frame in range(12):await viewer.get_tree().process_frame
		await RenderingServer.frame_post_draw
		var image:Image=viewer.get_viewport().get_texture().get_image()
		var total:float=0
		var count:int=0
		for y in range(int(image.get_height()*.34),int(image.get_height()*.70),3):
			for x in range(int(image.get_width()*.27),int(image.get_width()*.65),3):
				var color:Color=image.get_pixel(x,y)
				total+=color.r*.2126+color.g*.7152+color.b*.0722;count+=1
		result.brightness.append({"value":value,"mean_luminance":total/maxi(1,count)})
		image.save_png(directory.path_join("brightness-"+str(value)+".png"))
	viewer._set_brightness(original)
	var ambient_samples:Array=[]
	var ambient:float=viewer.world_environment.ambient_light_energy
	# Authored bounce correctly replaces ambient fill. Isolate the fallback
	# when testing the neutral ambient control, leaving sun and sky fixed.
	RenderingServer.global_shader_parameter_set("source_bounce_strength",0.0)
	for energy in [.15,.85]:
		viewer.world_environment.ambient_light_energy=energy
		await viewer.get_tree().process_frame
		await RenderingServer.frame_post_draw
		ambient_samples.append(mean_world(viewer.get_viewport().get_texture().get_image()))
	viewer.world_environment.ambient_light_energy=ambient
	RenderingServer.global_shader_parameter_set("source_bounce_strength",original)
	result.ambient_only_luminance=ambient_samples
	if ambient_samples[1]<=ambient_samples[0]+.005:
		result.failures.append("Ambient fill alone did not change map pixels")
	if result.brightness[2].mean_luminance<=result.brightness[0].mean_luminance+.015:
		result.failures.append("Lighting slider did not change actual map pixels")
	for sun in viewer.map_suns:
		result.suns.append({"shadow_enabled":sun.shadow_enabled,"bias":sun.shadow_bias,"normal_bias":sun.shadow_normal_bias,"split_blending":sun.directional_shadow_blend_splits,"color":str(sun.light_color),"basis":str(sun.global_basis)})
		if sun.shadow_enabled!=bool(sun.get_meta("authored_shadows",true)):result.failures.append("Authored sunlight shadow setting changed")
	if viewer.world_environment.ambient_light_sky_contribution>=1:
		result.failures.append("Ambient fill is ignored by the environment")
	result["ok"]=result.failures.is_empty()
	return result

static func mean_world(image:Image) -> float:
	var total:float=0;var count:int=0
	for y in range(int(image.get_height()*.34),int(image.get_height()*.70),3):
		for x in range(int(image.get_width()*.27),int(image.get_width()*.65),3):
			var color:Color=image.get_pixel(x,y)
			total+=color.r*.2126+color.g*.7152+color.b*.0722;count+=1
	return total/maxi(1,count)
