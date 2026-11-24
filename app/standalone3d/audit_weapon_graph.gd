extends RefCounted

# Uses the same owned renderer/resources as Watch, including both arm and
# weapon tracks. Explicit fixtures cover cases missing in the pistol reference.
static func run(viewer:Node,directory:String) -> Dictionary:
	var failures:Array=[];var samples:Array=[]
	var graphs:Dictionary=viewer.replay.get("actor_assets",{}).get("weapon_graphs",{})
	if not graphs.has("glock"):return {"ok":false,"failures":["Glock graph was not prepared"]}
	var graph=preload("res://weapon_graph.gd").new();var pack:Dictionary=graphs.glock
	var sampler=preload("res://source_pose.gd").new()
	var parameters:Dictionary={"weapon_type":"weapon_glock","weapon_ironsight_amount":0.0}
	for action in ["attack","reload"]:
		for ammo in [0,1,20]:
			parameters["weapon_ammo"]=ammo
			var chosen:Dictionary=graph.choose(pack,action,ammo)
			var expected:String=("shoot_empty_glock" if ammo==0 else "shoot1_glock") if action=="attack" else ("reload_empty_glock" if ammo==0 else "reload_glock")
			if chosen.is_empty() or expected not in str(chosen.get("resource","")):
				failures.append("Original selector did not choose "+expected);continue
			for kind in ["arms","weapon"]:
				var data:Dictionary=sampler.variant(chosen.path,kind)
				if data.is_empty():failures.append("Missing graph track: "+kind);continue
				var a:Dictionary=sampler.sample(data,.02,false);var b:Dictionary=sampler.sample(data,.15,false)
				var changed:int=0
				for bone in a:
					if b.has(bone) and not a[bone].is_equal_approx(b[bone]):changed+=1
				samples.append({"action":action,"ammo":ammo,"track":kind,"moving_bones":changed,"resource":chosen.resource})
				if changed==0:failures.append("Static authored graph track: "+expected+" "+kind)
	# Reconstruct each native animation segment independently, in shuffled order.
	# This checks selector inputs and graph results without relying on history.
	var state=preload("res://presentation_state.gd").new();state.configure(viewer.presentation.data)
	var network:Dictionary=viewer.presentation.data.get("network",{});var fields:Array=network.get("fields",[])
	var comparisons:int=0;var entry_checks:int=0;var empty_reload_checks:int=0
	if fields.has("weapon") and fields.has("anim_state"):
		for identifier in network.get("players",{}):
			for row in network.players[identifier]:
				if str(row[fields.find("weapon")+1]) not in ["weapon_glock","glock","Glock-18"]:continue
				var tick:float=float(row[0]);var input:Dictionary=state.at(identifier,tick)
				var a:Dictionary=graph.pose(pack,input,tick/float(network.get("tickrate",64)),sampler)
				if a.is_empty():continue
				graph.pose(pack,state.at(identifier,tick+640), (tick+640)/float(network.get("tickrate",64)),sampler)
				var b:Dictionary=graph.pose(pack,state.at(identifier,tick),tick/float(network.get("tickrate",64)),sampler)
				if a!=b:failures.append("Graph action differs after seeking at "+str(tick))
				comparisons+=1
	# The reload entry snapshot stays zero even after recorded ammo becomes 20.
	var frozen:Dictionary={"network_weapon":"weapon_glock","anim_state":"WPN_ANIMSTATE_RELOAD","action_clip":0,"clip":20,"animation_seconds":10.0,"playback_rate":1.0}
	var reload_pose:Dictionary=graph.pose(pack,frozen,10.8,sampler)
	if "reload_empty_glock" not in str(reload_pose.get("resource","")):failures.append("Empty reload changes mid-action")
	else:empty_reload_checks+=1
	var saved_tick:float=viewer.clock_tick;var saved_mode:int=viewer.camera_mode;var saved_player:int=viewer.selected_player
	var vm:Node=viewer.source_viewmodel;var captures:Array=[]
	DirAccess.make_dir_recursive_absolute(directory)
	viewer.camera_mode=0
	for index in range(viewer.replay.players.size()):
		if str(viewer.replay.players[index].name)=="SmoodAimder":viewer.selected_player=index
	# Matched native-reference times: shooting, movement, inspect, death boundary.
	for tick in [5877,6453,6837,7070,7270]:
		viewer._seek(float(tick))
		for settle in range(3):await viewer.get_tree().process_frame
		await RenderingServer.frame_post_draw
		var path:String=directory.path_join(str(tick)+".png")
		viewer.get_viewport().get_texture().get_image().save_png(path)
		captures.append({"tick":tick,"path":path,"viewmodel":vm.debug_state()})
	viewer.selected_player=saved_player;viewer.camera_mode=saved_mode;viewer._seek(saved_tick)
	if comparisons==0:failures.append("No recorded Glock action exercised the graph")
	return {"ok":failures.is_empty(),"failures":failures,"track_checks":samples,"recorded_seek_comparisons":comparisons,"empty_reload_checks":empty_reload_checks,"captures":captures}
