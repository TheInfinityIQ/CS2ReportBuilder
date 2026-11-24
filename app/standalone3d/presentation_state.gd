extends RefCounted
var data:Dictionary={}
var indices:Dictionary={}
var inspections:Dictionary={}
var native_inspections:Dictionary={}
var action_entries:Dictionary={}

func configure(value:Dictionary) -> void:
	data=value;indices.clear();inspections.clear();native_inspections.clear();action_entries.clear()
	var column:int=data.get("fields",[]).find("inspect")+1
	for identifier in data.get("players",{}):
		if column<=0:continue
		var events:Array=[];var previous:bool=false
		for row in data.players[identifier]:
			var current:bool=row[column]!=null and float(row[column])>.5
			if current and not previous:events.append(float(row[0]))
			previous=current
		inspections[identifier]=events
	var network:Dictionary=data.get("network",{});var fields:Array=network.get("fields",[])
	if fields.find("anim_state")<0:return
	for identifier in network.get("players",{}):
		var entries:Array=[];var previous_key:Array=[];var entry:Dictionary={}
		for row in network.players[identifier]:
			var native:Dictionary={}
			for i in range(fields.size()):native[fields[i]]=row[i+1]
			var key:Array=[native.get("weapon"),native.get("anim_state"),native.get("anim_start_time")]
			if key!=previous_key:
				entry={"action_clip":native.get("clip"),"action_weapon":native.get("weapon"),"action_observed_tick":row[0]}
				previous_key=key
			entries.append(entry)
		action_entries[identifier]=entries
		var events:Array=[];var previous:float=-1000000
		for row in network.players[identifier]:
			if str(row[fields.find("anim_state")+1])!="WPN_ANIMSTATE_INSPECT":continue
			var start:float=float(row[fields.find("anim_start_time")+1])*float(network.get("tickrate",64))-(float(row[fields.find("network_tick")+1])-float(row[0]))
			if start!=previous:events.append([float(row[0]),start]);previous=start
		native_inspections[identifier]=events

func at(identifier:String,tick:float) -> Dictionary:
	var rows:Array=data.get("players",{}).get(identifier,[])
	var low:int=0;var high:int=rows.size()
	while low<high:
		var middle:int=(low+high)/2
		if float(rows[middle][0])<=tick:low=middle+1
		else:high=middle
	if low==0:return {}
	var result:Dictionary={};var fields:Array=data.get("fields",[])
	for i in range(fields.size()):
		if rows[low-1][i+1]!=null:result[fields[i]]=rows[low-1][i+1]
	var events:Array=inspections.get(identifier,[]);low=0;high=events.size()
	while low<high:
		var middle:int=(low+high)/2
		if float(events[middle])<=tick:low=middle+1
		else:high=middle
	if low>0:result["inspect_tick"]=events[low-1]
	var loadouts:Array=data.get("inventory",{}).get(identifier,[]);low=0;high=loadouts.size()
	while low<high:
		var middle:int=(low+high)/2
		if float(loadouts[middle][0])<=tick:low=middle+1
		else:high=middle
	if low>0:result["inventory"]=loadouts[low-1][1]
	var network:Dictionary=data.get("network",{})
	var weapon_rows:Array=network.get("players",{}).get(identifier,[]);low=0;high=weapon_rows.size()
	while low<high:
		var middle:int=(low+high)/2
		if float(weapon_rows[middle][0])<=tick:low=middle+1
		else:high=middle
	if low>0:
		var entries:Array=action_entries.get(identifier,[])
		if entries.size()>=low:
			for field in entries[low-1]:
				if entries[low-1][field]!=null:result[field]=entries[low-1][field]
		var native_fields:Array=network.get("fields",[])
		var native:Dictionary={}
		for index in range(native_fields.size()):native[native_fields[index]]=weapon_rows[low-1][index+1]
		for field in ["clip","reserve","secondary_reserve","anim_state","playback_rate","throw_strength"]:
			if native.has(field):result[field]=native[field]
		if native.has("weapon"):result["network_weapon"]=native.weapon
		if native.has("anim_start_time") and native.has("network_tick"):
			result["animation_seconds"]=float(native.anim_start_time)-(float(native.network_tick)-float(weapon_rows[low-1][0]))/float(network.get("tickrate",64))
		# Native weapon animation state is authoritative: an ended/cancelled
		# inspect must never resume from an older pending flag after a shot.
		result.erase("inspect_tick")
		if str(native.get("anim_state","")).begins_with("WPN_ANIMSTATE_INSPECT"):
			var starts:Array=native_inspections.get(identifier,[]);low=0;high=starts.size()
			while low<high:
				var middle:int=(low+high)/2
				if float(starts[middle][0])<=tick:low=middle+1
				else:high=middle
			if low>0:result["inspect_tick"]=starts[low-1][1]
	return result

static func vertical_fov(source_horizontal:float) -> float:
	return rad_to_deg(2.0*atan(tan(deg_to_rad(clampf(source_horizontal,20,140))*.5)*.75))
