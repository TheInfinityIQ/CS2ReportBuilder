extends RefCounted

# Bounded background reads of the existing shared resources. A scene is fetched
# exactly once even when aliases/utility use the same resource path. No new cache,
# lossy conversion, asset omission or scene-tree work is involved.
const MAX_PENDING=2
var paths:Array[String]=[]
var keys:Dictionary={}
var pending:Dictionary={}
var completed:Dictionary={}
var next:int=0
var peak_pending:int=0
var resolver:RefCounted
var originals:Dictionary={}
var background_reads:bool=true

func add(key:String,path:String) -> void:
	var original:String=path
	if resolver!=null:path=resolver.resolve(path)
	originals[path]=original
	if not keys.has(path):keys[path]=[];paths.append(path)
	keys[path].append(key)

func start() -> void:
	while next<paths.size() and pending.size()<MAX_PENDING:
		var path:String=paths[next];next+=1
		pending[path]=background_reads and ResourceLoader.load_threaded_request(path,"PackedScene",false)==OK
		peak_pending=maxi(peak_pending,pending.size())

func read_all() -> Dictionary:
	var scenes:Dictionary={}
	while not pending.is_empty():
		var path:String=pending.keys()[0]
		var scene:PackedScene=(ResourceLoader.load_threaded_get(path) if pending[path] else ResourceLoader.load(path,"PackedScene")) as PackedScene
		pending.erase(path)
		if scene==null and originals.get(path,path)!=path:
			resolver.fallbacks+=1;scene=ResourceLoader.load(originals[path],"PackedScene") as PackedScene
		if scene==null:drain();return {"error":"A prepared stock model could not be loaded."}
		completed[path]=scene
		for key in keys[path]:scenes[key]=scene
		start()
	return {"scenes":scenes,"unique":paths.size(),"peak_pending":peak_pending}

func drain() -> void:
	# Join already-started reads on an error; do not queue the unused remainder.
	for path in pending:
		if pending[path]:ResourceLoader.load_threaded_get(path)
	pending.clear()
