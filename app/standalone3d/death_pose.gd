extends RefCounted
const TRANSITION_SECONDS=.12

static func transition(seconds:float) -> float:
	return smoothstep(0.0,TRANSITION_SECONDS,seconds)

static func select_clip(clips:Dictionary,recorded:Dictionary) -> String:
	if clips.is_empty():return ""
	var region:String="gut" if int(recorded.get("bone",-1)) in [1,2] else "chest"
	var candidates:Array=[]
	for name in clips:
		if region in str(name).to_lower():candidates.append(str(name))
	if candidates.is_empty():candidates=clips.keys()
	candidates.sort()
	return str(clips[candidates[0]])
