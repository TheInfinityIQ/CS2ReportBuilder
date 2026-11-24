extends SceneTree
func _initialize() -> void:
	var bind=preload("res://smoke_presentation.gd");var failures:Array=[]
	var effects:Array=[{"kind":"smoke","entity":7,"start":100},{"kind":"smoke","entity":7,"start":500}]
	var rows:Array=[{"entityIndex":7,"serial":11,"tick":100,"color":[75,127,155],"seed":1001},{"entityIndex":7,"serial":12,"tick":500,"color":[180,129,50],"seed":1002}]
	var stats:Dictionary=bind.bind(effects,rows)
	if stats.matched!=2 or effects[0].recorded_color!=[75.0/255,127.0/255,155.0/255] or effects[1].recorded_generation!=12:failures.append("Smoke colors crossed entity generations")
	if effects[0].recorded_palette!="cool" or effects[1].recorded_palette!="warm" or bind.stock_palette([1,2,3])!="":failures.append("Unknown colors were interpreted as a stock cloud category")
	var ambiguous:Array=effects.duplicate(true)
	for effect in ambiguous:effect.erase("recorded_color")
	rows.append({"entityIndex":7,"serial":13,"tick":101,"color":[1,2,3],"seed":1})
	stats=bind.bind(ambiguous,rows)
	if stats.ambiguous_generations!=1 or ambiguous[0].has("recorded_color"):failures.append("Ambiguous entity reuse picked an arbitrary cloud")
	stats=bind.bind([],[{"entityIndex":7,"color":[NAN,1,2]}])
	if stats.invalid_colors!=1:failures.append("Non-finite network color accepted")
	print(JSON.stringify({"ok":failures.is_empty(),"failures":failures}));quit(0 if failures.is_empty() else 1)
