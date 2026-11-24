extends SceneTree
var failures:Array=[]
func check(value:bool,message:String) -> void:
	if not value:failures.append(message)
func _initialize() -> void:run.call_deferred()
func run() -> void:
	var sun:=DirectionalLight3D.new();root.add_child(sun)
	var authored=preload("res://source_environment.gd")
	authored.configure_sun(sun,{"energy":6.35,"angles":[61,75,0],"color":[1,.8117647,.6117647]},.65)
	check(is_equal_approx(authored.base_energy(sun,.65),6.35),"Authored sunlight replaced by review approximation")
	check((-sun.global_basis.z).is_equal_approx(Vector3(.46829,-.87462,.125478)),"Sun direction lost Source axes")
	authored.configure_sun(sun,{},.65)
	check(is_equal_approx(authored.base_energy(sun,.65),.65),"Missing map metadata retained the previous map's sunlight")
	sun.free()
	var collision=preload("res://prepared_collision.gd")
	var data:Dictionary={"triangle_ends":[2,5,7],"mesh_paths":["first","middle","last"]}
	for index in range(7):check(collision.mesh_for_face(data,index)==(["first","first","middle","middle","middle","last","last"][index]),"Collision face range boundary failed")
	for index in [-1,7,999]:check(collision.mesh_for_face(data,index)=="","Out-of-range collision face accepted")
	var sky=preload("res://source_sky.gd").new()
	check((sky.source_rotation([0,90,0])*Vector3.RIGHT).is_equal_approx(Vector3.DOWN),"Sky yaw did not rotate around Source Z")
	check(sky.source_rotation([0,0,0]).is_equal_approx(Basis.IDENTITY),"Neutral sky rotation changed")
	var environment:=Environment.new();var original:=Sky.new();environment.sky=original
	var image:=Image.create(4,4,false,Image.FORMAT_RGBA8);image.fill(Color.WHITE)
	var slices:Array[Image]=[image,image,image,image,image,image];var texture:=Texture2DArray.new();texture.create_from_images(slices)
	sky.configure({"texture":texture,"width":4,"resource":"test","material":"sky","sky":{"brightness":1.45}},environment)
	check(sky.state.available and environment.sky!=original,"Authored sky did not replace fallback")
	sky.set_brightness(.5);check(is_equal_approx(sky.material.get_shader_parameter("intensity"),.725),"Review brightness ignored authored sky")
	sky.configure({},environment);check(environment.sky==original and not sky.state.available,"Missing sky did not restore procedural fallback")
	print(JSON.stringify({"ok":failures.is_empty(),"failures":failures}));quit(0 if failures.is_empty() else 1)
