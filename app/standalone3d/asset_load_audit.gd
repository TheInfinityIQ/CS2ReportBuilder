extends SceneTree
func _initialize() -> void:run.call_deferred()
func run() -> void:
	var args:PackedStringArray=OS.get_cmdline_user_args()
	if args.size()!=2:quit(2);return
	var fixture:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var bank:Dictionary=fixture.stock;var paths:Dictionary={}
	for team in fixture.actor_assets.arms:paths["arms_"+team]=fixture.actor_assets.arms[team].scene
	for team in bank.players:paths[team]=bank.players[team]
	for weapon in fixture.weapons:
		var key:String=str(bank.aliases.get(weapon,weapon))
		if bank.weapons.has(key):paths[key]=bank.weapons[key].scene
	var start:int=Time.get_ticks_usec();var result:Array=[];var retained:Array=[]
	var resolver=preload("res://native_resource_cache.gd").new();resolver.configure(str(fixture.get("asset_load_cache","")))
	for key in paths:
		if fixture.has("asset_load_keys") and key not in fixture.asset_load_keys:continue
		var path:String=str(paths[key])
		if fixture.has("asset_load_cache"):path=resolver.resolve(path)
		var began:int=Time.get_ticks_usec();var packed:=load(path) as PackedScene
		if packed==null:quit(3);return
		retained.append(packed)
		var item:Dictionary={"key":key,"ms":(Time.get_ticks_usec()-began)/1000.0}
		if key=="glock":
			var node:Node=packed.instantiate();var stack:Array=[node];var textures:Dictionary={}
			while not stack.is_empty():
				var next:Node=stack.pop_back();stack.append_array(next.get_children())
				if not next is MeshInstance3D or next.mesh==null:continue
				for surface in range(next.mesh.get_surface_count()):
					var material:Material=next.get_active_material(surface)
					if not material is BaseMaterial3D:continue
					for slot in range(BaseMaterial3D.TEXTURE_MAX):
						var texture:Texture2D=material.get_texture(slot)
						if texture==null or textures.has(texture.get_instance_id()):continue
						var image:Image=texture.get_image()
						if image.get_format()==Image.FORMAT_RGB8:image.convert(Image.FORMAT_RGBA8)
						var hash:=HashingContext.new();hash.start(HashingContext.HASH_SHA256);hash.update(image.get_data())
						textures[texture.get_instance_id()]={"name":texture.resource_name,"material":material.resource_name,"slot":slot,"width":texture.get_width(),"height":texture.get_height(),"format":image.get_format(),"bytes":image.get_data_size(),"sha256":hash.finish().hex_encode()}
			item["textures"]=textures.values();node.free()
		result.append(item)
	var output:=FileAccess.open(args[1],FileAccess.WRITE);output.store_string(JSON.stringify({"total_ms":(Time.get_ticks_usec()-start)/1000.0,"items":result}));output.close();quit(0)
