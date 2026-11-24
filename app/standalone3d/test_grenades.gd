extends SceneTree

const Utility := preload("res://grenade_player.gd")
const Main := preload("res://main.gd")
var failures: Array = []

func check(condition: bool, message: String) -> void:
	if not condition: failures.append(message)

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	var utility := Utility.new()
	root.add_child(utility)
	var overlay := ColorRect.new()
	root.add_child(overlay)
	var data := {"tickrate":64,"throws":[],"effects":[],"blinds":[{"player":"p","start":64,"end":192}]}
	for kind in ["he","flash","smoke","molotov","incendiary","decoy"]:
		data["throws"].append({"id":kind,"kind":kind,"start":64,"end":128,"path":[[64,0,0,0],[128,100,200,300]]})
	data["effects"] = [{"id":"s","kind":"smoke","start":128,"end":256,"position":[0,0,0],
		"frames":[{"tick":128,"occupied":[0,2],"position":[0,0,0]}]},
		{"id":"f","kind":"fire","start":128,"end":256,"position":[0,0,0],
		"frames":[{"tick":128,"patches":[[0,0,0],[10,0,0]]},{"tick":192,"patches":[]}]}]
	utility.configure(data,{}, {},null,overlay)
	utility.update_tick(96,"p",0,false)
	check(utility.projectiles.size()==6,"all six projectiles")
	check(utility.path_position(data["throws"][0],96).is_equal_approx(Vector3(100,150,50)*.0254),"source axes and tick interpolation")
	check(overlay.color.a>0 and overlay.color.a<=.28001,"review blindness remains a translucent haze")
	utility.update_tick(130,"p",1,false)
	var smoke:Node3D=utility.effects.s
	var occupancy:Texture3D=smoke.get_node("Shape").material_override.get_shader_parameter("occupancy")
	var uploads:int=utility.smoke_volume_uploads
	check(utility.projectiles.is_empty(),"projectiles disappear at detonation")
	check(utility.effects.size()==2 and utility.rendered_voxels==2 and utility.rendered_patches==2,"recorded smoke masks and fire patches")
	check(overlay.color.a==0,"chase camera never blinded")
	utility.update_tick(200,"p",0,false)
	check(utility.rendered_patches==0 and overlay.color.a==0,"extinguished patches and expired flash")
	check(utility.effects.f.get_node("Glow").light_energy==0,"Extinguished fire left a phantom light")
	utility.update_tick(130,"p",0,false)
	check(utility.rendered_patches==2,"backward seeking reconstructs fire")
	var fire:Node3D=utility.effects.f;var multi:MultiMesh=fire.get_node("Flames").multimesh
	var capacity:int=multi.instance_count;var allocations:int=int(fire.get_meta("fire_buffer_allocations"))
	var first_seed:Color=multi.get_instance_custom_data(0);var first_transform:Transform3D=multi.get_instance_transform(0)
	var updates:int=int(fire.get_meta("fire_buffer_updates"))
	utility._fire_frame(fire,{"patches":[[10,0,0],[0,0,0]]})
	check(multi.get_instance_custom_data(0)==first_seed and multi.get_instance_transform(0).is_equal_approx(first_transform) and int(fire.get_meta("fire_buffer_updates"))==updates,"Fire reshuffling changed a surviving patch's phase, draw order or placement")
	utility._fire_frame(fire,{"patches":[[0,0,0]]})
	check(multi.instance_count==capacity and multi.visible_instance_count==3 and int(fire.get_meta("fire_buffer_allocations"))==allocations,"Shrinking fire reallocated its instance buffer")
	check(multi.custom_aabb.has_point(first_transform.origin+Vector3(0,.48,.39)),"Side-facing billboard extends outside the fire culling bounds")
	utility._fire_frame(fire,{"patches":[[0,0,0],[10,0,0]]})
	check(utility.effects.s==smoke,"Backward seek rebuilt an already active smoke hierarchy")
	check(utility.effects.s.get_node("Shape").material_override.get_shader_parameter("occupancy")==occupancy and utility.smoke_volume_uploads==uploads,"Backward seek re-uploaded an unchanged smoke volume")
	utility.update_tick(256,"p",0,false)
	check(utility.effects.is_empty(),"expiry removes utility")
	utility.update_tick(130,"p",0,false)
	check(utility.effects.size()==2 and utility.rendered_voxels==2,"repeat seek restores exact geometry")
	check(utility.effects.s.get_node("Shape").material_override.get_shader_parameter("occupancy")==occupancy and utility.smoke_volume_uploads==uploads,"Returning to an expired smoke did not reuse its exact recorded volume")
	data.effects[0]["recorded_color"]=[75.0/255,127.0/255,155.0/255]
	data.effects[0]["recorded_palette"]="cool"
	utility.owner_teams[""]=2;utility.update_tick(130,"p",0,false)
	var recorded_color:Color=utility.effects.s.get_node("Shape").material_override.get_shader_parameter("smoke_color")
	utility.owner_teams[""]=3;utility.update_tick(131,"p",0,false)
	check(utility.effects.s.get_node("Shape").material_override.get_shader_parameter("smoke_color")==recorded_color and recorded_color.is_equal_approx(utility.smoke_tint(3)),"Existing smoke changed color when its owner switched team")
	utility.enabled=false
	utility.update_tick(130,"p",0,false)
	check(not utility.visible and overlay.color.a==0,"review toggle")
	utility.blast_events=[{"kind":"he","start":128,"position":[0,0,0]}]
	var holes:Array[Vector4]=utility.smoke_blasts(160,Vector3.ZERO)
	check(holes.size()==1 and holes[0].w>0,"Recorded HE opens smoke")
	check(utility.smoke_blasts(120,Vector3.ZERO).is_empty(),"HE clears smoke before detonation")
	check(utility.smoke_blasts(400,Vector3.ZERO).is_empty(),"Smoke clearing never recovers")
	check(utility.smoke_blasts(160,Vector3.ONE*100).is_empty(),"Distant blast clears unrelated smoke")
	check(utility.smoke_blasts(160,Vector3.ZERO)==holes,"HE recovery retains state after backward seek")
	utility.bullet_events=[{"tick":128,"origin":[0,0,0],"angles":[0,0]}]
	var bullet:Array=utility.smoke_bullets(132,Vector3(0,0,2))
	check(bullet[0][0].w>0,"Recorded firing ray does not open smoke")
	check(utility.smoke_bullets(127,Vector3(0,0,2))[0][0].w==0,"Future shot opens smoke")
	check(utility.smoke_bullets(160,Vector3(0,0,2))[0][0].w==0,"Bullet channel never recovers")
	check(utility.smoke_bullets(132,Vector3(20,0,2))[0][0].w==0,"Distant shot clears unrelated smoke")
	check(utility.smoke_bullets(132,Vector3(0,0,2))==bullet,"Shot clearing changes across seeks")
	# A new recording may reuse every ID and tick; it must never inherit the
	# previous recording's occupancy, ray endpoints or live effect instances.
	utility.configure({"tickrate":64,"throws":[],"effects":[{"id":"s","kind":"smoke","start":128,"end":256,"position":[0,0,0],"frames":[{"tick":128,"occupied":[0,4]}]}]}, {},{},null,overlay)
	utility.enabled=true;utility.update_tick(130,"p",0,false)
	check(utility.rendered_voxels==4 and utility.smoke_volume_uploads==1 and utility.bullet_ends.is_empty(),"Smoke/ray state leaked between recordings")
	for i in range(40):utility._smoke_frame(utility.effects.s,{"id":"s"},{"tick":300+i,"occupied":[0,1]})
	check(utility.smoke_volumes.size()==utility.SMOKE_VOLUME_LIMIT and utility.smoke_volume_order.size()==utility.SMOKE_VOLUME_LIMIT,"Smoke volume cache exceeded its bound")
	print(JSON.stringify({"ok":failures.is_empty(),"failures":failures}))
	quit(0 if failures.is_empty() else 1)
