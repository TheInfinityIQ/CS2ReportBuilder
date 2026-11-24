extends Control
var texture:Texture2D
var calibration:Dictionary={}
var points:Array=[]
var map_name:String=""
var floors:Dictionary={}
var lower:bool=false
var floor_button:Button

func _ready() -> void:
	floor_button=Button.new();floor_button.text="UPPER  ↕";floor_button.tooltip_text="Switch radar floor"
	floor_button.add_theme_font_size_override("font_size",10)
	floor_button.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	floor_button.offset_top=-23;floor_button.offset_bottom=0
	floor_button.pressed.connect(func():set_floor(not lower))
	add_child(floor_button);floor_button.visible=false

func set_floor(value:bool) -> void:
	lower=value and floors.has("lower")
	if floors.has("lower" if lower else "upper"):texture=floors["lower" if lower else "upper"]
	if floor_button!=null:floor_button.text="LOWER  ↕" if lower else "UPPER  ↕"
	queue_redraw()

func configure(map:String) -> void:
	map_name=map.get_file();mouse_filter=Control.MOUSE_FILTER_IGNORE
	texture=null;floors.clear();lower=false
	var folder:=ProjectSettings.globalize_path("res://").path_join("../assets/maps")
	var metadata:Variant=JSON.parse_string(FileAccess.get_file_as_string(folder.path_join("map-data.json")))
	calibration=metadata.get(map_name,{}) if metadata is Dictionary else {}
	for floor_name in ["upper","lower"]:
		for suffix in [".png","_radar_psd.png","_v1_radar_psd.png"]:
			var path:=folder.path_join(map_name+("_lower" if floor_name=="lower" else "")+suffix)
			if FileAccess.file_exists(path):
				var image:=Image.load_from_file(path)
				if image!=null:floors[floor_name]=ImageTexture.create_from_image(image);break
	set_floor(false)
	if floor_button!=null:floor_button.visible=floors.has("lower")
	visible=texture!=null and not calibration.is_empty()
	queue_redraw()

func set_points(value:Array) -> void:
	if points == value:
		return
	points = value
	queue_redraw()

func _draw() -> void:
	if texture==null or calibration.is_empty():return
	draw_rect(Rect2(Vector2.ZERO,size),Color(.015,.025,.04,.95))
	draw_texture_rect(texture,Rect2(Vector2(3,3),size-Vector2(6,6)),false,Color(.85,.85,.85,.95))
	for player in points:
		var xy:Vector2=(Vector2(float(player.x)-float(calibration.pos_x),float(calibration.pos_y)-float(player.y))/(float(calibration.scale)*1024))*(size-Vector2(6,6))+Vector2(3,3)
		if not Rect2(Vector2.ZERO,size).has_point(xy):continue
		var color:=Color("ffb36b") if player.team==2 else Color("69c7ff")
		if not player.alive:
			draw_line(xy-Vector2(2,2),xy+Vector2(2,2),color*.6,1.5);draw_line(xy-Vector2(-2,2),xy+Vector2(-2,2),color*.6,1.5);continue
		draw_circle(xy,4 if player.selected else 3,color)
		if player.selected:draw_arc(xy,6,0,TAU,20,Color.WHITE,1.5)
		var angle:float=deg_to_rad(float(player.yaw));draw_line(xy,xy+Vector2(cos(angle),-sin(angle))*8,color,1.5)
