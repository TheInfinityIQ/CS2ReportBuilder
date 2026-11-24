extends SceneTree
func _initialize() -> void:
	var selector=preload("res://death_pose.gd")
	var clips:Dictionary={"death_gut_a":"gut","death_chest_b":"b","death_chest_a":"a"}
	var ok:bool=selector.select_clip(clips,{"bone":1})=="gut" and selector.select_clip(clips,{"bone":7,"headshot":true})=="a" and selector.select_clip(clips,{})=="a"
	print(JSON.stringify({"ok":ok,"scope":"Deterministic hit-region fallback selection, not physics parity"}));quit(0 if ok else 1)
