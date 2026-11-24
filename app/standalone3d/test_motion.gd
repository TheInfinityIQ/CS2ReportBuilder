extends SceneTree
func _initialize() -> void:run.call_deferred()
func run() -> void:
	var failures:Array=[];var probe=preload("res://main.gd").new();probe.actor_count=1
	probe.samples=PackedFloat32Array([0,0,0,179,10,100,2,1,0,1,0,10,0,0,-179,30,100,2,1,1,1,0])
	if probe._motion_fraction(0,1,0,.25)!=.25:failures.append("Fractional motion snapped to a recorded tick")
	if absf(absf(probe._view_angles(0,1,0,.5).x)-180)>.001:failures.append("Yaw wraps the long way")
	for field in [6,7,9]:
		var old:float=probe.samples[11+field];probe.samples[11+field]=3 if field==6 else 0
		if probe._motion_fraction(0,1,0,.5)!=0:failures.append("Interpolation crosses a team/death/presence boundary")
		probe.samples[11+field]=old
	probe.samples[11]=10000
	if probe._motion_fraction(0,1,0,.5)!=0:failures.append("Interpolation crosses a teleport")
	probe.free();print(JSON.stringify({"ok":failures.is_empty(),"failures":failures}));quit(0 if failures.is_empty() else 1)
