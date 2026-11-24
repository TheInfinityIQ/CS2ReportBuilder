extends SceneTree
var failures:Array=[]
func check(value:bool,message:String) -> void:
	if not value:failures.append(message)
func _initialize() -> void:run.call_deferred()
func run() -> void:
	var prototype:=Node3D.new();var packed:=PackedScene.new();packed.pack(prototype);prototype.free()
	var actor=preload("res://stock_actor.gd").new();root.add_child(actor)
	actor.grip=Node3D.new();actor.add_child(actor.grip)
	for key in ["glock","knife","ak47","awp","usp_silencer"]:actor.scene_bank["weapon:"+key]=packed
	actor._weapon("glock");var original:Node3D=actor.held
	actor._weapon("knife");check(not original.visible,"Inactive held weapon still draws")
	actor._weapon("glock");check(actor.held==original and actor.held.visible,"Returning to a weapon rebuilt its hierarchy")
	for key in ["ak47","awp","usp_silencer"]:actor._weapon(key)
	check(actor.held_pool.size()==4,"Held instance pool exceeded its bound")
	check(not actor.held_pool.has("knife"),"Held pool did not evict the least recent weapon")
	actor.set_team(3);check(actor.held_pool.is_empty(),"Team change retained stale grip instances")
	actor.free()
	var view=preload("res://source_viewmodel.gd").new();root.add_child(view)
	view.pose_root=Node3D.new();view.add_child(view.pose_root);view.scenes={"weapon:glock":packed}
	var source:=Node3D.new();root.add_child(source);var warm:=Node3D.new();source.add_child(warm)
	view.prepared_weapon("glock",warm)
	check(warm.get_parent()==view.pose_root and not warm.visible,"Prepared weapon was not transferred as inactive")
	check(view.take_weapon("glock")==warm,"First-person weapon did not reuse the prepared instance")
	check(view.take_weapon("missing")==null,"Missing weapon created an invalid hierarchy")
	view.free();source.free()
	print(JSON.stringify({"ok":failures.is_empty(),"failures":failures}));quit(0 if failures.is_empty() else 1)
