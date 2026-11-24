extends SceneTree
func _initialize() -> void:_run.call_deferred()
func _run() -> void:
	root.size=Vector2i(904,586)
	root.content_scale_size=Vector2i.ZERO
	root.content_scale_mode=Window.CONTENT_SCALE_MODE_DISABLED
	var hud=load("res://review_hud.gd").new();root.add_child(hud)
	hud.configure({"events":[{"tick":100,"kind":"round_freeze_end","round":1.0,"ct_score":0.0,"t_score":0.0},{"tick":200,"kind":"bomb_planted","round":1,"ct_score":0,"t_score":0}],"kills":[{"tick":150,"attacker":"[danger]","victim":"Victim","weapon":"glock","headshot":true,"attacker_team":3,"victim_team":2}]})
	hud.update_state(151,64,24,{2:4,3:5},{"name":"Player","weapon":"glock","health":100,"team":3},0)
	var failures:Array=[]
	if not hud.crosshair_visible:failures.append("Living first-person view has no crosshair")
	hud.update_state(151,64,24,{2:4,3:5},{"health":100,"scoped":true},0)
	if hud.crosshair_visible:failures.append("Unscoped crosshair remains visible over a scope")
	hud.update_state(151,64,24,{2:4,3:5},{"name":"Player","weapon":"glock","health":100,"team":3},0)
	if hud.ct_score.text!="0" or not hud.phase_label.text.begins_with("ROUND 1 /"):failures.append("Score or round displayed a floating-point value")
	if not hud.rows[0].text.contains("[lb]danger]"):failures.append("Player name was interpreted as HUD markup")
	await process_frame;await process_frame
	if hud.get_node("MatchScore").get_global_rect().intersects(hud.panels[0].get_global_rect()):failures.append("Kill feed overlaps match score")
	if hud.get_node("MatchScore").get_global_rect().end.x>hud.get_viewport_rect().size.x:failures.append("Match score extends outside the viewport")
	hud.update_state(201,64,24,{2:4,3:5},{},2)
	if hud.crosshair_visible:failures.append("First-person crosshair remains in free camera")
	if hud.last_state.phase!="bomb_planted":failures.append("Bomb phase was lost")
	hud.update_state(100,64,24,{2:5,3:5},{},2)
	if hud.last_state.kills!=0 or hud.last_state.phase!="round_freeze_end":failures.append("Seek retained future HUD events")
	hud.update_state(0,64,24,{},{},2)
	if hud.ct_score.text!="—":failures.append("Missing score was invented")
	hud.configure({"events":[
		{"tick":640,"kind":"round_start","round":1},
		{"tick":4480,"kind":"round_start","round":2},
		{"tick":5120,"kind":"round_freeze_end","round":2}
	]})
	hud.update_state(4800,64,24,{},{},2)
	if hud.clock_label.text!="00:05":failures.append("Valid freeze countdown is missing")
	hud.update_state(768,64,24,{},{},2)
	if hud.clock_label.text!="00:02":failures.append("Missing freeze-end used the next round's countdown after a backward seek")
	print(JSON.stringify({"ok":failures.is_empty(),"failures":failures}))
	hud.free();quit(0 if failures.is_empty() else 1)
