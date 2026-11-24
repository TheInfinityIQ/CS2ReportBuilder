extends RefCounted
var material:ShaderMaterial
var rectangles:Array=[]
var state:Dictionary={"available":false,"resource":"","local_profiles":0}

func configure(data:Dictionary,environment:Environment) -> void:
	RenderingServer.global_shader_parameter_set("review_modulation_exposure",1.0)
	material=null;state={"available":false,"resource":"","local_profiles":0}
	for rectangle in rectangles:
		if is_instance_valid(rectangle):rectangle.queue_free()
	rectangles.clear()
	var profiles:Array=data.get("profiles",[]);var chosen:Dictionary={}
	for profile in profiles:
		if profile.get("master",false):chosen=profile;break
	if chosen.is_empty():return
	var tone:Dictionary=chosen.get("tone",{})
	if tone.is_empty():return
	material=ShaderMaterial.new();material.shader=preload("res://source_post.gdshader")
	var fields:Dictionary={"shoulder":"m_flShoulderStrength","linear_strength":"m_flLinearStrength","linear_angle":"m_flLinearAngle","toe":"m_flToeStrength","toe_num":"m_flToeNum","toe_denom":"m_flToeDenom","white_point":"m_flWhitePoint"}
	for key in fields:
		if tone.has(fields[key]):material.set_shader_parameter(key,float(tone[fields[key]]))
	material.set_shader_parameter("bias",pow(2,float(tone.get("m_flExposureBias",0))))
	var low:float=maxf(.01,float(chosen.get("min_exposure",1)))
	var high:float=maxf(.01,float(chosen.get("max_exposure",1)))
	# Some installed profiles have reversed endpoints; retain their finite range.
	material.set_shader_parameter("exposure",clampf(1.0,minf(low,high),maxf(low,high)))
	if chosen.get("color_correction",false) and data.has("lut_texture"):
		material.set_shader_parameter("grading",data.lut_texture);material.set_shader_parameter("has_grading",true)
		material.set_shader_parameter("dimension",float(chosen.lut_dimension))
	environment.tonemap_mode=Environment.TONE_MAPPER_LINEAR;environment.tonemap_exposure=.25
	RenderingServer.global_shader_parameter_set("review_modulation_exposure",4.0)
	# An instantaneous screen average is not native eye adaptation: gun flashes,
	# smoke and small camera movements made the entire view pump in brightness.
	# Use a fixed in-range review exposure until a stable adaptation path exists.
	state={"available":true,"resource":chosen.resource,"exposure_mode":"fixed","exposure":clampf(1.0,minf(low,high),maxf(low,high)),"local_profiles":profiles.filter(func(p:Dictionary):return not p.get("master",false)).size()}

func attach(parent:Node) -> ColorRect:
	if material==null:return null
	var rectangle:=ColorRect.new();rectangle.name="AuthoredPostProcessing"
	rectangle.material=material;rectangle.mouse_filter=Control.MOUSE_FILTER_IGNORE
	parent.add_child(rectangle);rectangle.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	rectangles.append(rectangle);return rectangle
