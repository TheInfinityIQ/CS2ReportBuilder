extends RefCounted

static func stock_palette(rgb:Array) -> String:
	# These two stock byte colors identify the cloud's authored category. Direct
	# byte-RGB scattering produced a yellow cloud: do not pretend that simple
	# normalization reproduces Source's color/lighting transfer. Keep the proven
	# review palette until that transfer is implemented and visually qualified.
	if rgb==[75,127,155] or rgb==[75.0,127.0,155.0]:return "cool"
	if rgb==[180,129,50] or rgb==[180.0,129.0,50.0]:return "warm"
	return ""

# The network records a cloud's RGB and seed independently of its owner's
# current team. Match the entity generation at detonation, never a nickname.
static func bind(effects:Array,rows:Array) -> Dictionary:
	var by_entity:Dictionary={};var matched:int=0;var ambiguous:int=0;var invalid:int=0
	for row in rows:
		if not row is Dictionary or not row.get("color") is Array or row.color.size()!=3:continue
		var valid:bool=true
		for component in row.color:
			if not (component is float or component is int) or not is_finite(float(component)) or float(component)<0 or float(component)>255:valid=false;break
		if not valid:invalid+=1;continue
		var entity:int=int(row.get("entityIndex",-1))
		if entity<0 or not row.has("serial") or not row.has("tick") or not row.has("seed"):continue
		if not by_entity.has(entity):by_entity[entity]=[]
		by_entity[entity].append(row)
	for effect in effects:
		if effect.get("kind","")!="smoke":continue
		for field in ["recorded_color","recorded_palette","recorded_seed","recorded_generation"]:effect.erase(field)
		var candidates:Array=[];var generations:Dictionary={}
		for row in by_entity.get(int(effect.get("entity",-1)),[]):
			if absf(float(row.tick)-float(effect.start))>4:continue
			candidates.append(row);generations[int(row.serial)]=true
		if generations.size()>1:ambiguous+=1;continue
		if candidates.is_empty():continue
		candidates.sort_custom(func(a:Dictionary,b:Dictionary):return absf(float(a.tick)-float(effect.start))<absf(float(b.tick)-float(effect.start)))
		var chosen:Dictionary=candidates[0]
		effect["recorded_color"]=[float(chosen.color[0])/255.0,float(chosen.color[1])/255.0,float(chosen.color[2])/255.0]
		effect["recorded_palette"]=stock_palette(chosen.color)
		effect["recorded_seed"]=chosen.seed;effect["recorded_generation"]=int(chosen.serial);matched+=1
	return {"matched":matched,"ambiguous_generations":ambiguous,"invalid_colors":invalid,"scope":"Recorded RGB retained; known stock color category selects the existing review palette. Native scattering transfer remains unresolved."}
