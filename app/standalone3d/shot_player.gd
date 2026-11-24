extends Node3D
var events:Array=[]
var flashes:Array[MeshInstance3D]=[]
var displayed:=0
var damage:Array=[]
var fires:Array=[]
var sprays:Array[MeshInstance3D]=[]
var casings:Array[MeshInstance3D]=[]
func configure(data:Dictionary) -> void:
	events=data.get("impacts",[])
	damage=data.get("damage",[]);fires=data.get("fires",[])
	for index in range(20):
		var mesh:=MeshInstance3D.new();var quad:=QuadMesh.new();quad.size=Vector2(.45,.45);mesh.mesh=quad
		var material:=ShaderMaterial.new();material.shader=preload("res://blood.gdshader");mesh.material_override=material;mesh.visible=false;mesh.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF;add_child(mesh);sprays.append(mesh)
	for index in range(32):
		var mesh:=MeshInstance3D.new();var shape:=CylinderMesh.new();shape.top_radius=.004;shape.bottom_radius=.004;shape.height=.017;shape.radial_segments=6;mesh.mesh=shape
		var material:=StandardMaterial3D.new();material.albedo_color=Color(.65,.43,.13);material.metallic=.8;material.roughness=.4
		mesh.material_override=material;mesh.visible=false;mesh.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF;add_child(mesh);casings.append(mesh)
	for index in range(32):
		var mesh:=MeshInstance3D.new();var sphere:=SphereMesh.new()
		sphere.radius=.018;sphere.height=.036;sphere.radial_segments=6;sphere.rings=3;mesh.mesh=sphere
		var material:=StandardMaterial3D.new();material.albedo_color=Color(1,.68,.25)
		material.shading_mode=BaseMaterial3D.SHADING_MODE_UNSHADED
		mesh.material_override=material;mesh.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mesh.visible=false;add_child(mesh);flashes.append(mesh)
func update_tick(tick:float,rate:float) -> void:
	var low:=0;var high:=events.size()
	while low<high:
		var middle:int=(low+high)/2
		if float(events[middle].tick)<=tick:low=middle+1
		else:high=middle
	displayed=0
	for index in range(low-1,-1,-1):
		var event:Dictionary=events[index]
		var age:float=(tick-float(event.tick))/rate
		if age>.075 or displayed==flashes.size():break
		var point:Array=event.position
		flashes[displayed].position=Vector3(point[1],point[2],point[0])*.0254
		flashes[displayed].scale=Vector3.ONE*(1.0-age/.075)
		flashes[displayed].visible=true;displayed+=1
	for index in range(displayed,flashes.size()):flashes[index].visible=false
	var count:int=0
	for index in range(upper(damage,tick)-1,-1,-1):
		var event:Dictionary=damage[index];var age:float=(tick-float(event.tick))/rate
		if age>.24 or count>=sprays.size():break
		var p:Array=event.position;var height:float=1.6 if event.get("hitgroup",0)==1 else 1.1
		sprays[count].position=Vector3(p[1],p[2],p[0])*.0254+Vector3(sin(float(index))*age,height+age*.5-age*age*2,cos(float(index))*age)
		sprays[count].scale=Vector3.ONE*(.6+age*3);(sprays[count].material_override as ShaderMaterial).set_shader_parameter("fade",1.0-age/.24);sprays[count].visible=true;count+=1
	for index in range(count,sprays.size()):sprays[index].visible=false
	count=0
	for index in range(upper(fires,tick)-1,-1,-1):
		var event:Dictionary=fires[index];var age:float=(tick-float(event.tick))/rate
		if age>1 or count>=casings.size():break
		if event.weapon in ["knife","smokegrenade","hegrenade","molotov","incgrenade","flashbang","decoy","taser"]:continue
		var p:Array=event.position;var yaw:float=deg_to_rad(float(event.get("yaw",0)))
		var side:=Vector3(cos(yaw),0,-sin(yaw));var origin:=Vector3(p[1],p[2],p[0])*.0254
		casings[count].position=origin+side*(.15+age*1.5)+Vector3.UP*maxf(.025,1.4+age*.7-age*age*4.9)
		casings[count].rotation=Vector3(age*13,index+age*9,age*7);casings[count].visible=true;count+=1
	for index in range(count,casings.size()):casings[index].visible=false

static func upper(items:Array,tick:float) -> int:
	var low:int=0;var high:int=items.size()
	while low<high:
		var middle:int=(low+high)/2
		if float(items[middle].tick)<=tick:low=middle+1
		else:high=middle
	return low

func hurt_amount(player:int,tick:float,rate:float) -> float:
	for index in range(upper(damage,tick)-1,-1,-1):
		var event:Dictionary=damage[index];var age:float=(tick-float(event.tick))/rate
		if age>.45:break
		if event.victim==player:return (1.0-age/.45)*clampf(float(event.amount)/70,.1,1)
	return 0
