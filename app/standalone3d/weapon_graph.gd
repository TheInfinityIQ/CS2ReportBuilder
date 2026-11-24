extends RefCounted

# A deliberately bounded graph program: selectors and their value expressions.
# Action routing, layers and prediction are NOT a full Source graph interpreter.
var failure:String=""

func evaluate(program:Dictionary,parameters:Dictionary) -> Variant:
	match str(program.get("op","")):
		"param":
			if not parameters.has(program.name):failure="Missing graph input: "+str(program.name);return null
			return parameters[program.name]
		"const":return program.value
		"clip":return program
		"not":
			var value:Variant=evaluate(program.args[0],parameters)
			return not value if value!=null else null
		"and","or":
			var is_and:bool=program.op=="and"
			for arg in program.args:
				var value:Variant=evaluate(arg,parameters)
				if value==null:return null
				if is_and and not value:return false
				if not is_and and value:return true
			return is_and
		"in":
			var value:Variant=evaluate(program.arg,parameters)
			return value in program.values if value!=null else null
		"compare":
			var a:Variant=evaluate(program.a,parameters);var b:Variant=evaluate(program.b,parameters)
			if a==null or b==null:return null
			match str(program.comparison):
				"NearEqual":return absf(float(a)-float(b))<=float(program.epsilon)
				"GreaterThanEqual":return a>=b
				"LessThanEqual":return a<=b
				"GreaterThan":return a>b
				"LessThan":return a<b
		"select":
			for option in program.options:
				var allowed:Variant=evaluate(option.when,parameters)
				if allowed==null:return null
				if allowed:return evaluate(option.pose,parameters)
			failure="No supported graph selector branch";return null
		"blend":
			var value:Variant=evaluate(program.value,parameters)
			if value==null:return null
			for point in program.points:
				if absf(float(value)-float(point.at))<.00000001:return evaluate(point.pose,parameters)
			failure="Interpolated graph blend is outside action proof";return null

	failure="Unsupported graph operation: "+str(program.get("op",""));return null

func choose(pack:Dictionary,action:String,ammo:float) -> Dictionary:
	failure=""
	if pack.get("schema")!=1 or pack.get("weapon")!="glock" or not pack.get("programs",{}).has(action):
		failure="Unrecognized Glock graph program";return {}
	var parameters:Dictionary={"weapon_type":"weapon_glock","weapon_ammo":ammo,"weapon_ironsight_amount":0.0}
	var result:Variant=evaluate(pack.programs[action],parameters)
	if not result is Dictionary or str(result.get("resource","")).is_empty():
		if failure.is_empty():failure="Selected graph branch has no authored clip"
		return {}
	if not pack.get("clips",{}).has(result.resource):failure="Selected graph clip was not prepared";return {}
	return {"path":pack.clips[result.resource],"speed":result.speed,"loop":result.loop,"fixed":result.fixed,"resource":result.resource}

func pose(pack:Dictionary,state:Dictionary,seconds:float,sampler:RefCounted) -> Dictionary:
	# Evaluate against the ammunition on ENTRY, not the current ammunition.
	# A reload updates clip ammo before its animation ends; reevaluating that
	# selector mid-action switches poses and makes seeks depend on history.
	failure=""
	if not state.has("animation_seconds") or not state.has("action_clip"):return {}
	var native_weapon:String=str(state.get("network_weapon",""))
	if native_weapon not in ["weapon_glock","glock","Glock-18"]:return {}
	var native:String=str(state.get("anim_state",""))
	var action:String=""
	if native.begins_with("WPN_ANIMSTATE_SHOOT"):action="attack"
	elif native=="WPN_ANIMSTATE_RELOAD":action="reload"
	elif native=="WPN_ANIMSTATE_IDLE":action="idle"
	else:return {} # Draw/inspect/utility remain on the existing authored path.
	var rate:float=float(state.get("playback_rate",1.0))
	if not is_finite(rate) or rate<=0:failure="Invalid recorded animation rate";return {}
	var elapsed:float=(seconds-float(state.animation_seconds))*rate
	if elapsed<0:return {}
	var chosen:Dictionary=choose(pack,action,float(state.action_clip))
	if chosen.is_empty():return {}
	var duration_data:Dictionary=sampler.variant(chosen.path,"arms")
	if duration_data.is_empty():failure="Graph clip has no authored arm track";return {}
	var duration:float=float(maxi(0,int(duration_data.frames)-1))/maxf(1,float(duration_data.fps))
	if action in ["attack","reload"] and elapsed*float(chosen.speed)>=duration:
		chosen=choose(pack,"empty" if float(state.get("clip",1))==0 else "idle",float(state.get("clip",1)))
		elapsed=0.0 if float(state.get("clip",1))==0 else elapsed-duration
	elif action=="idle" and float(state.get("clip",1))==0:
		chosen=choose(pack,"empty",0)
	if chosen.is_empty():return {}
	chosen["elapsed"]=float(chosen.fixed) if chosen.fixed!=null else elapsed*float(chosen.speed)
	chosen["action"]=action
	return chosen
