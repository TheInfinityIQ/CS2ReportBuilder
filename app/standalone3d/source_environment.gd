extends RefCounted
static func read_cache(asset:String,fingerprint:String) -> Dictionary:
	var folder:String=asset.get_base_dir();var file:=FileAccess.open(folder.get_base_dir().get_base_dir().path_join("environment").path_join(folder.get_file()).path_join("environment.json"),FileAccess.READ)
	if file==null or file.get_length()>64*1024:return {}
	var data:Variant=JSON.parse_string(file.get_as_text())
	if not data is Dictionary or data.get("schema",0)!=1 or data.get("source_fingerprint","")!=fingerprint or not data.get("suns") is Array or data.suns.size()>1:return {}
	if data.suns.is_empty():return {"energy":0.0,"color":[1,1,1],"angles":[45,0,0],"shadows":false,"specular":false}
	var sun:Variant=data.suns[0]
	if not sun is Dictionary or not sun.get("energy") is float or not is_finite(sun.energy) or sun.energy<0 or sun.energy>128:return {}
	for key in ["angles","color"]:
		if not sun.get(key) is Array or sun[key].size()!=3:return {}
		for value in sun[key]:
			if typeof(value) not in [TYPE_FLOAT,TYPE_INT] or not is_finite(float(value)):return {}
			if key=="color" and (float(value)<0 or float(value)>1):return {}
	return sun

static func configure_sun(sun:DirectionalLight3D,data:Dictionary,fallback:float) -> void:
	if data.is_empty():
		sun.set_meta("authored_energy",fallback);sun.set_meta("authored_shadows",true);sun.light_specular=1.0;sun.shadow_enabled=true;return
	var color:Array=data.color;sun.light_color=Color(color[0],color[1],color[2])
	var angles:Array=data.angles;var yaw:float=deg_to_rad(float(angles[1]));var pitch:float=deg_to_rad(float(angles[0]))
	var direction:=Vector3(sin(yaw)*cos(pitch),-sin(pitch),cos(yaw)*cos(pitch))
	sun.global_basis=Basis.looking_at(direction,Vector3.UP if absf(direction.y)<.999 else Vector3.RIGHT)
	sun.set_meta("authored_energy",float(data.energy))
	sun.light_specular=1.0 if data.get("specular",true) else 0.0
	sun.shadow_enabled=bool(data.get("shadows",true))
	sun.set_meta("authored_shadows",sun.shadow_enabled)

static func base_energy(sun:DirectionalLight3D,fallback:float) -> float:return float(sun.get_meta("authored_energy",fallback))
