extends SceneTree
var failures:Array=[]
func check(condition:bool,message:String) -> void:
	if not condition:failures.append(message)
func _initialize() -> void:run.call_deferred()
func run() -> void:
	var probe=preload("res://source_bounce.gd").new()
	var random:=RandomNumberGenerator.new();random.seed=47901
	var source_to_world:=Transform3D(Basis(Vector3(0,0,1),Vector3(1,0,0),Vector3(0,1,0)).scaled(Vector3.ONE*.0254),Vector3.ZERO)
	for index in range(90):
		var position:=Vector3(random.randf_range(-100,100),random.randf_range(-30,30),random.randf_range(-100,100))
		var size:=Vector3.ONE*random.randf_range(10,60)
		var transform:=Transform3D(Basis.from_scale(Vector3.ONE/size),-position/size)*source_to_world
		probe.volumes.append({"index":index,"bounds":AABB(position,size),"transform":transform})
	probe.build_grid();var grid:Dictionary=probe.volume_grid
	var hits:int=0
	for index in range(1000):
		var box:=AABB(Vector3(random.randf_range(-110,110),random.randf_range(-40,40),random.randf_range(-110,110)),Vector3.ONE*(.01 if index%2 else 30))
		if index==999:box=AABB(Vector3.ONE*-200,Vector3.ONE*400)
		probe.volume_grid={};var linear:Array=probe.candidates(box).map(func(v:Dictionary):return v.index)
		probe.volume_grid=grid;var indexed:Array=probe.candidates(box).map(func(v:Dictionary):return v.index)
		check(linear==indexed,"Spatial index omitted or reordered lighting candidates at query "+str(index));hits+=linear.size()
	check(hits>100,"Index test had no positive lighting coverage")
	# Source IDs deliberately differ from priority-sorted array positions.
	probe.volumes.reverse();probe.build_grid()
	var box:AABB=AABB(Vector3.ONE*-200,Vector3.ONE*400)
	var expected:Array=probe.candidates(box).map(func(v:Dictionary):return v.index)
	probe.static_candidates(box,"sorted")
	check(probe.static_candidates(box,"sorted").map(func(v:Dictionary):return v.index)==expected,"Persisted lighting choices treated source IDs as sorted offsets")
	for invalid in [[9999],[-1],[1.5],["1"],null]:
		probe.static_queries["invalid"]=invalid
		check(probe.static_candidates(box,"invalid").map(func(v:Dictionary):return v.index)==expected,"Invalid static choices did not recompute")
	probe=preload("res://source_bounce.gd").new();probe.atlas=Texture2DArray.new()
	probe.state["lightmapped_surfaces"]=0;probe.white_texture=ImageTexture.new()
	probe.lightmaps={"irradiance":ImageTexture.new(),"directional_irradiance":ImageTexture.new()}
	var material:=StandardMaterial3D.new()
	var meshes:Array=[]
	for index in range(3):
		var arrays:Array=[];arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX]=PackedVector3Array([Vector3.ZERO,Vector3.RIGHT,Vector3.UP])
		arrays[Mesh.ARRAY_NORMAL]=PackedVector3Array([Vector3.BACK,Vector3.BACK,Vector3.BACK])
		arrays[Mesh.ARRAY_TEX_UV2]=PackedVector2Array([Vector2.ZERO,Vector2.RIGHT,Vector2.UP])
		var mesh:=ArrayMesh.new();mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
		mesh.resource_name="mesh"+str(index);mesh.surface_set_material(0,material)
		var node:=MeshInstance3D.new();node.mesh=mesh;root.add_child(node);meshes.append(node)
		probe.eligibility[mesh.resource_name]=[index<2];probe.apply_mesh(node)
	check(meshes[0].get_active_material(0)==meshes[1].get_active_material(0),"Identical lightmapped surfaces no longer share their binding")
	check(meshes[0].get_active_material(0)!=meshes[2].get_active_material(0),"Probe and lightmap bindings overwrite each other")
	check(meshes[0].get_active_material(0).get_shader_parameter("use_source_lightmap"),"Baked surface lost its authored lightmap")
	check(not meshes[2].get_active_material(0).get_shader_parameter("use_source_lightmap"),"Unbaked surface inherited a lightmap")
	print(JSON.stringify({"ok":failures.is_empty(),"failures":failures,"queries":1000,"positive_candidates":hits}));quit(0 if failures.is_empty() else 1)
