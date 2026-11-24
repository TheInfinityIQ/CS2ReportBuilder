extends RefCounted
static func action(state:Dictionary) -> String:
	match str(state.get("anim_state","")):
		"WPN_ANIMSTATE_GRENADE_PULL_PIN":return "pullpin"
		"WPN_ANIMSTATE_GRENADE_THROW":return "throw_underhand" if float(state.get("throw_strength",1))<.5 else "throw_overhand"
	return ""

static func charge(state:Dictionary) -> String:
	var strength:float=float(state.get("throw_strength",1))
	return "throwcharge_low" if strength<.25 else ("throwcharge_mid" if strength<.75 else "throwcharge_high")
