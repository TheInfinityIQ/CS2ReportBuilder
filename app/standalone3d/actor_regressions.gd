extends RefCounted
const StockActor=preload("res://stock_actor.gd")

static func bone_poses(actor:Node) -> Array:
	var result:Array=[]
	for bone in range(actor.skeleton.get_bone_count()):result.append(actor.skeleton.get_bone_pose(bone))
	return result

static func pose_error(a:Array,b:Array) -> float:
	var result:float=0
	for i in range(a.size()):
		result=maxf(result,a[i].origin.distance_to(b[i].origin))
		for axis in range(3):result=maxf(result,(a[i].basis[axis]-b[i].basis[axis]).length())
	return result

static func run(viewer:Node) -> Dictionary:
	var result:Dictionary={"failures":[]}
	var actor=viewer.figures[0]
	if not actor is StockActor:return {"ok":false,"failures":["Stock actor missing"]}
	var skeleton:Skeleton3D=actor.skeleton
	actor.apply_pose("glock",Vector3.ZERO,false,false,0,false,false,.1,-1000,-1000,0)
	var head:int=skeleton.find_bone("head_0")
	result.upright_height=skeleton.get_bone_global_pose(head).origin.y
	if result.upright_height<1.2:result.failures.append("Living player lost the Source-to-Godot up-axis conversion")
	actor.apply_pose("glock",Vector3.ZERO,false,false,0,false,false,.1,.07,-1000,0)
	var right:int=skeleton.find_bone("hand_R");var left:int=skeleton.find_bone("hand_L")
	result.firing_hand_distance=skeleton.get_bone_global_pose(right).origin.distance_to(skeleton.get_bone_global_pose(left).origin)
	if result.firing_hand_distance>.45:result.failures.append("Firing recoil separated the hands from the grip")
	actor.apply_pose("glock",Vector3.ZERO,false,false,1,false,false,.1,.07,-1000,0)
	var hand_world:Vector3=skeleton.global_transform*skeleton.get_bone_global_pose(right).origin
	result.world_muzzle_follows_pose=actor.muzzle_sprite!=null and actor.muzzle_sprite.global_position.distance_to(hand_world)<.6
	if not result.world_muzzle_follows_pose:result.failures.append("World muzzle flash retained the previous hand pose")
	var ankle:int=skeleton.find_bone("ankle_L")
	actor.apply_pose("glock",Vector3(-90,0,0),false,true,0,false,false,.1,-1000,-1000,0)
	var foot:Transform3D=skeleton.get_bone_global_pose(ankle)
	result.backward_clip=actor.current_clip
	actor.apply_pose("glock",Vector3(-90,0,0),false,true,0,true,false,.4,-1000,.1,0)
	result.backward_leg_motion=foot.origin.distance_to(skeleton.get_bone_global_pose(ankle).origin)
	if not str(result.backward_clip).ends_with("walk_s_pistol") or result.backward_leg_motion<.01:
		result.failures.append("Backward gait did not move the legs while reloading")
	result.locomotion=preload("res://locomotion_audit.gd").run(actor)
	result.failures.append_array(result.locomotion.failures)
	if not viewer.replay.get("actor_assets",{}).is_empty():
		var data:Dictionary=viewer.replay.actor_assets
		var team:String="ct" if actor.team==3 else "t"
		actor.apply_death(data.models[team],data.deaths.death_chest_a,3)
		actor.apply_death(data.models[team],data.deaths.death_chest_a,100)
		var updates:int=actor.death_pose_updates
		actor.apply_death(data.models[team],data.deaths.death_chest_a,101)
		result["settled_pose_reused"]=actor.death_pose_updates==updates
		if not result.settled_pose_reused:result.failures.append("Unchanged settled death pose was rebuilt")
		result.corpse_head_height=skeleton.get_bone_global_pose(head).origin.y
		if result.corpse_head_height>.6 or result.corpse_head_height<-.2:result.failures.append("Death pose did not settle near the floor")
		if not actor.pose_sampler.failures.is_empty():result.failures.append_array(actor.pose_sampler.failures)
		actor.apply_pose("glock",Vector3.ZERO,false,false,0,false,false,.1,-1000,-1000,0)
		result.revived_upright=skeleton.get_bone_global_pose(head).origin.y>1.2
		if not result.revived_upright:result.failures.append("Seeking back from death retained the corpse pose")
		var vm=viewer.source_viewmodel
		vm.update_pose(true,3,"glock",.1,false,.07,-1000,-1000)
		result.viewmodel=vm.debug_state()
		if not result.viewmodel.visible or result.viewmodel.arm_bones!=52 or not result.viewmodel.failures.is_empty():
			result.failures.append("Authored first-person arms or weapon pose failed")
		result.muzzle_flash=vm.muzzle_sprite!=null and vm.muzzle_sprite.visible
		if not result.muzzle_flash:result.failures.append("Recorded shot did not show a muzzle flash")
		var saved_state:Dictionary=vm.recorded_state;var inspect_checks:int=0
		for weapon in ["knife","glock"]:
			if not vm.manifest.viewmodels.get(weapon,{}).has("inspect"):continue
			vm.set_recorded_state({"inspect_seconds":0})
			vm.update_pose(true,2,weapon,.3,false,-1000,-1000,-1000)
			var before:Transform3D=vm.muzzle
			vm.update_pose(true,2,weapon,.8,false,-1000,-1000,-1000)
			if vm.active_clip!=vm.manifest.viewmodels[weapon].inspect or before.is_equal_approx(vm.muzzle):result.failures.append("Authored inspect motion failed: "+weapon)
			inspect_checks+=1
		vm.set_recorded_state(saved_state);result["inspect_checks"]=inspect_checks
		var saved_tick:float=viewer.clock_tick;var saved_mode:int=viewer.camera_mode
		viewer.camera_mode=2
		var lifecycle_checked:=false
		for events in viewer.death_events.values():
			if lifecycle_checked:break
			for event in events:
				if float(event.until)>float(viewer.replay.info.ticks) or float(event.until)-float(event.tick)<viewer._tickrate():continue
				var victim=viewer.figures[int(event.player)]
				viewer._seek(maxf(0,float(event.tick)-.0001))
				var live_pose:Array=bone_poses(victim);var live_position:Vector3=victim.position;var live_rotation:Basis=victim.basis
				viewer._seek(float(event.tick))
				result["death_entry_pose_error"]=pose_error(live_pose,bone_poses(victim))
				result["death_entry_root_error"]=live_position.distance_to(victim.position)
				result["death_entry_rotation_error"]=(live_rotation.x-victim.basis.x).length()
				if result.death_entry_pose_error>.0001 or result.death_entry_root_error>.0001 or result.death_entry_rotation_error>.0001:result.failures.append("Recorded death still snaps from its last living pose/root")
				viewer._seek(float(event.tick)+viewer._tickrate()*.06)
				var early_pose:Array=bone_poses(victim);var early_position:Vector3=victim.position
				viewer._seek(float(event.tick)+viewer._tickrate()*3)
				viewer._seek(float(event.tick)+viewer._tickrate()*.06)
				result["death_seek_pose_error"]=pose_error(early_pose,bone_poses(victim))
				if result.death_seek_pose_error>.0001 or early_position.distance_to(victim.position)>.0001:result.failures.append("Seeking changed the recorded death handoff")
				viewer._seek(float(event.tick)+viewer._tickrate()*.5)
				result.body_persists=victim.visible and victim.dead_state
				viewer._seek(maxf(0,float(event.tick)-1))
				result.seek_before_death=victim.visible and not victim.dead_state
				viewer._seek(float(event.until))
				result.body_cleared_on_respawn=not victim.dead_state and viewer._death_at(int(event.player)).is_empty()
				if not result.body_persists or not result.seek_before_death or not result.body_cleared_on_respawn:result.failures.append("Recorded corpse lifetime or seek reconstruction failed")
				lifecycle_checked=true;break
		viewer.camera_mode=saved_mode;viewer._seek(saved_tick)
		if not lifecycle_checked:result.failures.append("No recorded death/respawn interval was available for acceptance")
	viewer._update_picture()
	if not viewer.replay.rounds.is_empty():
		var tick_before:float=viewer.clock_tick
		var start:float=float(viewer.replay.rounds[0].tick)
		viewer._seek(start+viewer._tickrate())
		viewer.round_menu.get_popup().index_pressed.emit(1)
		result.current_round_restart=is_equal_approx(viewer.clock_tick,start)
		if not result.current_round_restart:result.failures.append("Activating the current round did not restart it")
		viewer._seek(tick_before)
	result.ok=result.failures.is_empty()
	return result
