extends Node3D

# Independent renderer: this project never loads or launches the CS2 engine.
const INCH := 0.0254
const COLUMNS := 11
const T_COLOR := Color("f49b47")
const CT_COLOR := Color("50a8ff")
const StockActor := preload("res://stock_actor.gd")
const StockAudio := preload("res://stock_audio.gd")
const ReviewHUD=preload("res://review_hud.gd")
var review_hud:Control
const REVIEW_SUN := .65
const REVIEW_AMBIENT := .60
const MapDust := preload("res://map_dust.gdshader")
var map_effects: Dictionary = {}
var source_effects=preload("res://source_effects.gd").new()
var effect_materials: Array[ShaderMaterial] = []
var source_materials=preload("res://source_materials.gd").new()
var source_bounce=preload("res://source_bounce.gd").new()
var source_reflections=preload("res://source_reflections.gd").new()
var source_direct=preload("res://source_direct.gd").new()
var world_visibility=preload("res://world_visibility.gd").new()
var dynamic_world=preload("res://dynamic_world.gd").new()
var source_sky=preload("res://source_sky.gd").new()
const GrenadePlayer := preload("res://grenade_player.gd")
var options: Dictionary = {}
var replay: Dictionary = {}
var samples := PackedFloat32Array()
var figures: Array[Node3D] = []
var roster_buttons: Array[Button] = []
var map_scene: Node3D
var physics_scene: Node3D
var prepared_physics:Node3D
var camera: Camera3D
var playing := false
var clock_tick := 0.0
var profile_picture:=false
var picture_profile:Dictionary={}
var profile_frame_intervals:Array=[]
var speed := 1.0
var selected_player := 0
var camera_mode := 1
var chase_distance := 4.0
var orbit_angle := 0.0
var backend_pid := -1
var job_path := ""
var job_poll := 0.0
var updating := false
var smoke_started := false
var actor_count := 0
var frames_count := 0
var title_label: Label
var status_label: Label
var clock_label: Label
var feed_label: Label
var pause_button: Button
var timeline: HSlider
var progress_bar: ProgressBar
var roster: VBoxContainer
var round_menu: OptionButton
var dialog: ConfirmationDialog
var demo_list: ItemList
var library_items: Array = []
var visible_demos: Array = []
var camera_menu: OptionButton
var load_thread: Thread
var load_mutex := Mutex.new()
var worker_message := ""
var loading_active := false
var load_error := ""
var loaded_asset := ""
var status_poll := 0.0
var next_command_poll_us := 0
var status_sequence := 0
var request_sequence := 0
var load_max_frame_ms := 0.0
var load_frame_count := 0
var toolbox_command := 0
var collision_regions: Array[Vector3] = []
var collision_candidates: Array = []
var collision_cursor := 0
var load_started_us := 0
var load_profile: Dictionary = {}
var stock_scenes: Dictionary = {}
var stock_sounds: Dictionary = {}
var state_samples := PackedFloat32Array()
var sound_player: StockAudio
var weapon_requests: Dictionary = {}
var weapon_loading := ""
var action_events: Dictionary = {}
var death_events:Dictionary={}
var static_sun=preload("res://static_sun_shadows.gd").new()
var overlay_root:Control
var source_viewmodel:Node
var presentation=preload("res://presentation_state.gd").new()
var player_xray=preload("res://xray.gd").new()
var character_materials=preload("res://character_materials.gd").new()
var roster_panel:Control
var source_post=preload("res://source_post.gd").new()
var xray_enabled:bool=false
var view_punch:=PackedFloat32Array()
var travel_samples:=PackedFloat32Array()
var gait_phase_samples:=PackedFloat32Array()
var view_weapon: Node3D
var view_weapon_key := ""
var view_weapon_skeleton: Skeleton3D
var sound_enabled := true
var sound_toggle: Button
var utility: GrenadePlayer
var shot_player:Node3D
var flash_overlay: ColorRect
var damage_overlay:ColorRect
var world_environment: Environment
var fallback_sun: DirectionalLight3D
var map_suns: Array[DirectionalLight3D] = []
var review_brightness := 1.0
var utility_enabled := true
var prepared_utility_materials:Array=[]
var flash_enabled := true
var map_setup_pending := false
var validation_active:=false

func _ready() -> void:
	Engine.max_fps = 120
	get_viewport().msaa_3d=Viewport.MSAA_4X
	var args := OS.get_cmdline_user_args()
	var index := 0
	while index < args.size():
		if args[index].begins_with("--"):
			var key := args[index].trim_prefix("--")
			options[key] = args[index + 1] if index + 1 < args.size() and not args[index + 1].begins_with("--") else "true"
		index += 1
	if options.get("present","") in ["disabled","loading_only"]:
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED);Engine.max_fps=240
	elif options.get("present","")=="mailbox":DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_MAILBOX)
	if options.has("embedded"):
		get_window().content_scale_size = Vector2i.ZERO
		get_window().content_scale_mode = Window.CONTENT_SCALE_MODE_DISABLED
	else:
		get_window().min_size = Vector2i(1200, 720)
	_build_world()
	_build_ui()
	if options.has("smoke"): AudioServer.set_bus_volume_db(0, -65)
	if options.has("replay"):
		_load_replay(str(options["replay"]))
	elif options.has("demo"):
		_import_demo(str(options["demo"]))
	else:
		status_label.text = "Choose a downloaded demo to begin. CS2 will never be launched."
	get_window().title = "CS2 Demo Viewer"

func _build_world() -> void:
	var environment := WorldEnvironment.new()
	var settings := Environment.new()
	world_environment = settings
	settings.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var atmosphere := ProceduralSkyMaterial.new()
	atmosphere.sky_top_color = Color("638fad")
	atmosphere.sky_horizon_color = Color("c3d2d7")
	atmosphere.ground_horizon_color = Color("c3d2d7")
	atmosphere.ground_bottom_color = Color("635a4b")
	atmosphere.sky_energy_multiplier = .55
	atmosphere.ground_energy_multiplier = .35
	sky.sky_material = atmosphere
	sky.radiance_size = Sky.RADIANCE_SIZE_128
	settings.sky = sky
	settings.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	settings.ambient_light_color = Color("c5ced8")
	settings.ambient_light_energy = REVIEW_AMBIENT
	# At 1.0 the ambient colour/energy (and the review slider) are ignored.
	# Keep a neutral bounce approximation under the directional skylight.
	settings.ambient_light_sky_contribution=.35
	settings.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	settings.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	settings.tonemap_white=4.0
	settings.ambient_light_source=Environment.AMBIENT_SOURCE_SKY
	if RenderingServer.get_current_rendering_method()=="forward_plus":
		settings.ambient_light_source=Environment.AMBIENT_SOURCE_SKY
		settings.ssao_enabled=true
		settings.ssao_radius=.65;settings.ssao_intensity=1.3
		settings.ssao_power=1.4;settings.ssao_light_affect=.35
		settings.ssil_enabled=true;settings.ssil_intensity=.3;settings.ssil_radius=3.0
		settings.glow_enabled=true;settings.glow_intensity=.3
	environment.environment = settings
	add_child(environment)
	var sun := DirectionalLight3D.new()
	fallback_sun = sun
	sun.rotation_degrees = Vector3(-55, -35, 0)
	sun.light_color = Color("ffe0b8")
	sun.light_energy = REVIEW_SUN
	sun.shadow_enabled = true
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	_configure_sun_shadows(sun)
	add_child(sun)
	camera = Camera3D.new()
	camera.near = 0.03
	camera.far = 1500.0
	camera.fov = 78
	camera.position = Vector3(0, 10, 10)
	add_child(camera)
	camera.current = true
	# Rely on authored occlusion rather than layering the unverified screen-depth
	# contact approximation over it. Multiplicative effects must also account
	# for the Compatibility renderer's exposure; see source_overlay shaders.

func _panel(parent: Node, position: Vector2, size: Vector2) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.position = position
	panel.size = size
	var style := ReviewHUD.surface(Color(0.035, 0.055, 0.08, 0.90))
	style.content_margin_left = 12
	style.content_margin_right = 12
	style.content_margin_top = 10
	style.content_margin_bottom = 10
	panel.add_theme_stylebox_override("panel", style)
	parent.add_child(panel)
	return panel

func _button(parent: Node, text: String, action: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.pressed.connect(action)
	parent.add_child(button)
	return button

func _build_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var ui := Control.new()
	ui.theme=ReviewHUD.skin()
	overlay_root=ui
	ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(ui)
	flash_overlay = ColorRect.new()
	flash_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	flash_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	flash_overlay.color = Color(1,1,1,0)
	var haze := ShaderMaterial.new()
	haze.shader=preload("res://flash_haze.gdshader")
	flash_overlay.material=haze
	ui.add_child(flash_overlay)
	damage_overlay=ColorRect.new();damage_overlay.mouse_filter=Control.MOUSE_FILTER_IGNORE;damage_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var damage_material:=ShaderMaterial.new();damage_material.shader=preload("res://damage_haze.gdshader");damage_overlay.material=damage_material;ui.add_child(damage_overlay)
	var top := _panel(ui, Vector2(12, 12), Vector2(1416, 58))
	top.anchor_right = 1
	top.offset_right = -12
	var top_column := VBoxContainer.new()
	top.add_child(top_column)
	var top_row := HBoxContainer.new()
	top_column.add_child(top_row)
	if not options.has("embedded"):
		_button(top_row, "Downloaded demos", _choose_demo)
		_button(top_row, "Cancel import", _cancel_import)
	var mode := OptionButton.new()
	camera_menu = mode
	mode.add_item("Player view")
	mode.add_item("Chase camera")
	mode.add_item("Free camera")
	mode.select(1)
	mode.item_selected.connect(func(value: int): camera_mode = value; _update_picture())
	top_row.add_child(mode)
	var players_button:=Button.new();players_button.text="Players";players_button.toggle_mode=true
	players_button.toggled.connect(func(value:bool):
		if roster_panel!=null:roster_panel.visible=value
		if review_hud!=null:review_hud.radar.visible=not value and review_hud.radar.texture!=null)
	top_row.add_child(players_button)
	if not options.has("embedded"):
		_button(top_row, "Previous player", func(): _select_player((selected_player - 1 + figures.size()) % maxi(1, figures.size())))
		_button(top_row, "Next player", func(): _select_player((selected_player + 1) % maxi(1, figures.size())))
		_button(top_row, "Expand (F11)", _fullscreen)
	title_label = Label.new()
	title_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_label.text = "Demo viewer"
	title_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	title_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	top_row.add_child(title_label)
	status_label = Label.new()
	status_label.add_theme_font_size_override("font_size",11)
	status_label.add_theme_color_override("font_color",Color("91a6b8"))
	status_label.text = "Loading…"
	status_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	top_column.add_child(status_label)
	var side := _panel(ui, Vector2(12, 152), Vector2(208, 640))
	roster_panel=side;side.visible=false
	side.anchor_bottom = 1
	side.offset_bottom = -126
	var side_column := VBoxContainer.new()
	side.add_child(side_column)
	var heading := Label.new()
	heading.text = "PLAYERS"
	heading.add_theme_font_size_override("font_size", 13)
	side_column.add_child(heading)
	var utility_options := HBoxContainer.new()
	top_row.add_child(utility_options)
	var utility_button := CheckButton.new()
	utility_button.text = "Utility"
	utility_button.tooltip_text="Show recorded grenades, smoke and fire."
	utility_button.button_pressed = true
	utility_button.toggled.connect(func(value: bool): utility_enabled = value)
	utility_options.add_child(utility_button)
	var flash_button := CheckButton.new()
	flash_button.text = "Flash"
	flash_button.tooltip_text = "Review cue for the selected player's recorded flash. The scene stays visible; this does not simulate what that player could see."
	flash_button.button_pressed = true
	flash_button.toggled.connect(func(value: bool): flash_enabled = value)
	utility_options.add_child(flash_button)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	side_column.add_child(scroll)
	roster = VBoxContainer.new()
	roster.add_theme_constant_override("separation",1)
	roster.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(roster)
	var light_label := Label.new()
	light_label.text = "Light"
	light_label.add_theme_font_size_override("font_size",11)
	top_row.add_child(light_label)
	var brightness := HSlider.new()
	brightness.min_value = .65
	brightness.max_value = 1.65
	brightness.step = .05
	brightness.value = review_brightness
	brightness.custom_minimum_size.x=70
	brightness.tooltip_text = "Viewer lighting only; CS2 settings stay unchanged."
	brightness.value_changed.connect(_set_brightness)
	top_row.add_child(brightness)
	var xray_toggle:=CheckButton.new();xray_toggle.text="X-ray";xray_toggle.tooltip_text="Review outlines through geometry and smoke; this does not represent player visibility."
	xray_toggle.toggled.connect(func(value:bool):xray_enabled=value);top_row.add_child(xray_toggle)
	var bottom := _panel(ui, Vector2(12, 782), Vector2(1416, 106))
	bottom.anchor_top = 1
	bottom.anchor_bottom = 1
	bottom.anchor_right = 1
	bottom.offset_top = -88
	bottom.offset_bottom = -12
	bottom.offset_right = -12
	var transport := VBoxContainer.new()
	bottom.add_child(transport)
	var controls := HBoxContainer.new()
	transport.add_child(controls)
	pause_button = _button(controls, "Play", _toggle_play)
	var primary:=ReviewHUD.surface(Color("20566b"));primary.set_corner_radius_all(5)
	pause_button.add_theme_stylebox_override("normal",primary)
	_button(controls, "−10 s", func(): _skip(-10.0))
	_button(controls, "+10 s", func(): _skip(10.0))
	_button(controls, "Tick −1", func(): _seek(floor(clock_tick) - 1))
	_button(controls, "Tick +1", func(): _seek(floor(clock_tick) + 1))
	var speed_menu := OptionButton.new()
	for value in [0.25, 0.5, 1.0, 2.0, 4.0, 8.0]: speed_menu.add_item(str(value) + "×")
	speed_menu.select(2)
	speed_menu.item_selected.connect(func(value: int): speed = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0][value])
	controls.add_child(speed_menu)
	sound_toggle = _button(controls, "Sound: on (1×)", func():
		sound_enabled = not sound_enabled
		sound_toggle.text = "Sound: on (1×)" if sound_enabled else "Sound: off"
		if sound_player != null: sound_player.reset(clock_tick))
	sound_toggle.tooltip_text = "Recorded spatial sound at normal speed. Other speeds are muted."
	round_menu = OptionButton.new()
	round_menu.add_item("Round")
	# Popup activation also fires when choosing the current round again.
	round_menu.get_popup().index_pressed.connect(func(value: int):
		if value > 0: _seek(float(replay.get("rounds", [])[value - 1]["tick"])))
	controls.add_child(round_menu)
	clock_label = Label.new()
	clock_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	clock_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	clock_label.add_theme_font_size_override("font_size", 12)
	controls.add_child(clock_label)
	timeline = HSlider.new()
	timeline.step = 1
	timeline.max_value = 1
	timeline.value_changed.connect(func(value: float):
		if not updating: _seek(value))
	transport.add_child(timeline)
	var hint := Label.new()
	hint.text = "Space: play/pause · Arrows: seek · Right-drag: look · WASD/QE: free fly · Esc: release mouse"
	hint.add_theme_font_size_override("font_size", 10)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	transport.add_child(hint)
	review_hud=ReviewHUD.new();ui.add_child(review_hud)
	progress_bar = ProgressBar.new()
	progress_bar.show_percentage = true
	progress_bar.visible = false
	top_column.add_child(progress_bar)
	dialog = ConfirmationDialog.new()
	dialog.title = "Downloaded demos · replays"
	dialog.ok_button_text = "Open demo"
	dialog.min_size = Vector2i(1000, 560)
	var library_ui := VBoxContainer.new()
	library_ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	dialog.add_child(library_ui)
	var search := LineEdit.new()
	search.placeholder_text = "Search player, team, map or date"
	library_ui.add_child(search)
	search.text_changed.connect(_filter_demos)
	demo_list = ItemList.new()
	demo_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	library_ui.add_child(demo_list)
	demo_list.item_activated.connect(func(_item: int): _open_selected_demo())
	dialog.confirmed.connect(_open_selected_demo)
	add_child(dialog)

func _choose_demo() -> void:
	if options.has("embedded"):
		_request_toolbox("library")
		return
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	playing = false
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(str(options.get("library", ""))))
	library_items = data if data is Array else []
	_filter_demos("")
	dialog.popup_centered(Vector2i(1100, 650))

func _filter_demos(query: String) -> void:
	demo_list.clear()
	visible_demos.clear()
	for entry in library_items:
		if (query.is_empty() or query.to_lower() in str(entry["label"]).to_lower()) and FileAccess.file_exists(str(entry["path"]).replace("\\", "/")):
			visible_demos.append(entry)
			demo_list.add_item(str(entry["label"]))
	if visible_demos.is_empty(): demo_list.add_item("No downloaded CS2 demos found. Download a demo in Toolbox first.")

func _open_selected_demo() -> void:
	var selected := demo_list.get_selected_items()
	if selected.is_empty() or selected[0] >= visible_demos.size(): return
	dialog.hide()
	_import_demo(str(visible_demos[selected[0]]["path"]))

func _import_demo(path: String) -> void:
	if load_thread != null or loading_active or (backend_pid > 0 and OS.is_process_running(backend_pid)):
		status_label.text = "A demo is already being prepared. Wait for it to finish."
		return
	if not options.has("python") or not options.has("backend") or not options.has("cache"):
		status_label.text = "Start this application using Open Standalone CS2 Viewer."
		return
	playing = false
	map_setup_pending = false
	loading_active = true
	load_error = ""
	if sound_player != null: sound_player.reset(clock_tick)
	if utility != null: utility.silence(); utility.visible = false
	if source_viewmodel!=null:source_viewmodel.picture.visible=false
	if flash_overlay != null: flash_overlay.color.a = 0
	replay = {}
	job_path = str(options["cache"]).path_join("jobs").path_join(str(Time.get_ticks_usec()))
	DirAccess.make_dir_recursive_absolute(job_path)
	var arguments := PackedStringArray([str(options["backend"]), "--demo", path, "--game", str(options.get("game", "")), "--job", job_path])
	backend_pid = OS.create_process(str(options["python"]), arguments, false)
	status_label.text = "Preparing this demo in the background. CS2 is not running."
	progress_bar.visible = true
	progress_bar.value = 0
	if backend_pid < 0: _loading_error("Could not start the demo reader.")

func _cancel_import() -> void:
	if options.has("embedded"):
		_request_toolbox("stop")
		return
	if backend_pid > 0 and OS.is_process_running(backend_pid):
		OS.kill(backend_pid)
		backend_pid = -1
		progress_bar.visible = false
		status_label.text = "Import cancelled. Original demo and installed assets are unchanged."

func _process(delta: float) -> void:
	frames_count += 1
	var frame_started := Time.get_ticks_usec() if profile_picture else 0
	var seek_applied := false
	if options.has("session") and not loading_active:
		var now := Time.get_ticks_usec()
		if now >= next_command_poll_us:
			next_command_poll_us = now + 33000
			seek_applied = _poll_toolbox()
	status_poll += delta
	if status_poll > 0.2:
		status_poll = 0
		_publish_status()
	if backend_pid > 0:
		job_poll += delta
		if job_poll > 0.2:
			job_poll = 0
			_poll_job()
	if loading_active:
		load_max_frame_ms = maxf(load_max_frame_ms, delta * 1000.0)
		load_frame_count += 1
		if load_thread != null:
			if load_thread.is_alive():
				load_mutex.lock()
				status_label.text = worker_message
				load_mutex.unlock()
			else:
				var payload: Variant = load_thread.wait_to_finish()
				load_thread = null
				if payload is Dictionary:
					_finish_load(payload)
				else:
					_loading_error("The background loader stopped. Cancel and reopen this demo; see the session log for details.")
		return
	if replay.is_empty(): return
	if validation_active:return
	if profile_picture and playing and profile_frame_intervals.size()<8192:profile_frame_intervals.append(delta*1000.0)
	var simulation_started := Time.get_ticks_usec() if profile_picture else 0
	_extend_camera_collision()
	if playing:
		clock_tick = minf(clock_tick + delta * _tickrate() * speed, float(replay["info"]["ticks"]))
		if clock_tick >= float(replay["info"]["ticks"]): playing = false
	if sound_player != null:
		sound_player.enabled = sound_enabled
		if playing and is_equal_approx(speed, 1.0): sound_player.emit_until(clock_tick)
		else: sound_player.reset(clock_tick)
	_poll_weapons()
	var picture_started := Time.get_ticks_usec() if profile_picture else 0
	if not seek_applied:
		_update_picture()
	if profile_picture:
		picture_profile["command_and_status_ms"] = (simulation_started-frame_started)/1000.0
		picture_profile["simulation_ms"] = (picture_started-simulation_started)/1000.0
		picture_profile["process_ms"] = (Time.get_ticks_usec()-frame_started)/1000.0
	if options.has("smoke") and not smoke_started:
		smoke_started = true
		_run_smoke.call_deferred()

func _poll_job() -> void:
	var file := job_path.path_join("progress.json")
	if FileAccess.file_exists(file):
		var state: Variant = JSON.parse_string(FileAccess.get_file_as_string(file))
		if state is Dictionary:
			status_label.text = str(state.get("message", "Preparing…"))
			progress_bar.value = float(state.get("percent", 0))
			if state.get("state") == "complete":
				backend_pid = -1
				progress_bar.visible = false
				_load_replay(str(state["replay"]))
			elif state.get("state") == "error":
				backend_pid = -1
				_loading_error(str(state.get("message", "Could not read this demo.")))
			elif state.get("state") == "permission_required":
				backend_pid = -1
				loading_active = false
				map_setup_pending = true
				progress_bar.visible = false
				request_sequence += 1
				_write_session("request.json", {"id":request_sequence,"action":"map_setup","map_setup":state.get("map_setup",{})})
				_publish_status(true)
	if backend_pid > 0 and not OS.is_process_running(backend_pid):
		backend_pid = -1
		_loading_error("The demo reader stopped before producing a replay.")

func _write_session(name: String, data: Dictionary) -> void:
	if not options.has("session"): return
	var path := str(options["session"]).path_join(name)
	var file := FileAccess.open(path + ".tmp", FileAccess.WRITE)
	if file == null: return
	file.store_string(JSON.stringify(data))
	file.close()
	DirAccess.rename_absolute(path + ".tmp", path)

func _publish_status(_force: bool = false) -> void:
	status_sequence += 1
	var state := "loading" if loading_active or backend_pid > 0 else ("ready" if not replay.is_empty() else "idle")
	if map_setup_pending: state = "permission_required"
	if not load_error.is_empty(): state = "error"
	_write_session("status.json", {"sequence": status_sequence, "state": state,
		"message": status_label.text, "percent": progress_bar.value,
		"load_max_frame_ms": load_max_frame_ms, "load_frames": load_frame_count,
		"command_ack": toolbox_command, "tick": clock_tick})

func _request_toolbox(action: String) -> void:
	request_sequence += 1
	_write_session("request.json", {"id": request_sequence, "action": action})

func _poll_toolbox() -> bool:
	if not options.has("session") or loading_active: return false
	var path := str(options["session"]).path_join("command.json")
	if not FileAccess.file_exists(path): return false
	# A replace/read sharing violation can yield an empty transient IPC read on
	# Windows. Retry without acknowledging it or emitting a renderer failure.
	var parser:=JSON.new()
	if parser.parse(FileAccess.get_file_as_string(path))!=OK:return false
	var command:Variant=parser.data
	if not command is Dictionary or int(command.get("id", 0)) <= toolbox_command: return false
	toolbox_command = int(command["id"])
	if command.get("action") == "seek":
		_seek(float(command.get("tick", 0)))
		if options.has("smoke"):
			RenderingServer.frame_post_draw.connect(_report_seek_draw.bind(toolbox_command,clock_tick),CONNECT_ONE_SHOT)
	elif command.get("action") == "pause":
		playing = false
		if sound_player != null: sound_player.reset(clock_tick)
		if utility != null: utility.silence()
	elif command.get("action") == "load": _import_demo(str(command.get("demo", "")))
	elif command.get("action") == "quit":
		playing=false
		if sound_player!=null:sound_player.reset(clock_tick)
		if utility!=null:utility.silence()
		get_tree().quit()
	_publish_status(true)
	return command.get("action") == "seek"

func _report_seek_draw(command_id:int,tick:float) -> void:
	if toolbox_command == command_id and clock_tick == tick:
		_write_session("seek-draw.json", {"id":command_id,"tick":tick})

func _loading_error(message: String) -> void:
	Engine.max_fps=240 if options.get("present","") in ["disabled","loading_only"] else 120
	loading_active = false
	if options.get("present","")=="loading_only":DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED);Engine.max_fps=120
	load_error = message
	status_label.text = message
	progress_bar.visible = false
	_publish_status(true)

func _worker_phase(message: String) -> void:
	load_mutex.lock()
	worker_message = message
	load_mutex.unlock()

func _read_lighting(asset:String,signature:String) -> Dictionary:
	var started:=Time.get_ticks_usec()
	return {"source_bounce":preload("res://source_bounce.gd").read_cache(asset,signature),
		"source_reflections":preload("res://source_reflections.gd").read_cache(asset,signature),
		"source_direct":preload("res://source_direct.gd").read_cache(asset,signature),
		"read_started":started}

func _read_replay(path: String, existing_asset: String,mount:Dictionary={}) -> Dictionary:
	# Resource workers never access the active scene tree or controls.
	var read_start:=Time.get_ticks_usec()
	_worker_phase("Reading player tracks…")
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not data is Dictionary or int(data.get("schema", 0)) != 1:
		return {"error": "The replay cache is incomplete. Select the downloaded demo again."}
	if not data.get("players") is Array or data["players"].is_empty() or data["players"].size() > 64 or int(data.get("frames", 0)) < 1:
		return {"error": "The replay cache has invalid player or frame metadata."}
	# Read the independent prepared map while this worker reads tracks and
	# shared actor/lighting resources. Scene attachment remains on the main thread.
	var native_path:=str(data.get("native_scene",""))
	var collision_metadata:Dictionary=preload("res://prepared_collision.gd").read_metadata(str(data.get("map_asset","")),native_path,str(data.get("asset_info",{}).get("fingerprint","")))
	data["prepared_collision_info"]=collision_metadata
	var collision_started:bool=false
	if not collision_metadata.is_empty() and str(data.get("map_asset",""))!=existing_asset:
		collision_started=ResourceLoader.load_threaded_request(collision_metadata.path,"PackedScene",false)==OK
	if mount.get("source_demo","")==data.get("sha256","") and mount.get("fingerprint","")==data.get("asset_info",{}).get("fingerprint",""):
		native_path=str(mount.get("scene",native_path))
	var threaded_map:bool=false
	if str(data.get("map_asset",""))!=existing_asset and not native_path.is_empty() and FileAccess.file_exists(native_path):
		threaded_map=ResourceLoader.load_threaded_request(native_path,"PackedScene",false,ResourceLoader.CACHE_MODE_IGNORE)==OK
	var tracks := FileAccess.open(str(data.get("tracks", "")), FileAccess.READ)
	if tracks == null: return {"error": "Replay track data is missing."}
	if tracks.get_length() > 512 * 1024 * 1024 + 24:
		return {"error": "The recording exceeds this viewer's track memory limit."}
	var bytes := tracks.get_buffer(tracks.get_length())
	if bytes.size() < 24 or bytes.slice(0, 4).get_string_from_ascii() != "SRP1":
		return {"error": "Invalid player track data."}
	var frame_count := bytes.decode_u32(4)
	var player_count := bytes.decode_u32(8)
	var columns := bytes.decode_u32(12)
	if columns != COLUMNS or player_count != data["players"].size() or frame_count != int(data["frames"]) or bytes.size() != 24 + frame_count * player_count * COLUMNS * 4:
		return {"error": "Replay data failed its size check."}
	var decoded := bytes.slice(24).to_float32_array()
	if data.has("postprocess"):
		for profile in data.postprocess.get("profiles",[]):
			if not profile.get("master",false) or not profile.get("color_correction",false):continue
			var dimension:int=int(profile.get("lut_dimension",0))
			if dimension<1 or dimension>64:return {"error":"Unsupported source color-grading dimensions."}
			var lut_data:=FileAccess.get_file_as_bytes(str(profile.get("lut","")))
			if lut_data.size()!=dimension*dimension*dimension*4:return {"error":"Source color-grading data needs preparation."}
			var slices:Array[Image]=[];var layer_bytes:int=dimension*dimension*4
			for z in range(dimension):slices.append(Image.create_from_data(dimension,dimension,false,Image.FORMAT_RGBA8,lut_data.slice(z*layer_bytes,(z+1)*layer_bytes)))
			var lut:=ImageTexture3D.new();lut.create(Image.FORMAT_RGBA8,dimension,dimension,dimension,false,slices)
			data.postprocess["lut_texture"]=lut;break
	if data.has("network_presentation"):
		var network_file:=FileAccess.open(str(data.network_presentation),FileAccess.READ)
		if network_file==null or network_file.get_length()>64*1024*1024:return {"error":"Recorded weapon state needs preparation."}
		var network:Variant=JSON.parse_string(network_file.get_as_text())
		if not network is Dictionary or network.get("source","")!=data.sha256:return {"error":"Recorded weapon identity mismatch."}
		data.presentation["network"]=network
	if data.has("inventory"):
		var inventory_file:=FileAccess.open(str(data.inventory),FileAccess.READ)
		if inventory_file==null or inventory_file.get_length()>32*1024*1024:return {"error":"Recorded loadout data needs preparation."}
		var inventory:Variant=JSON.parse_string(inventory_file.get_as_text())
		if not inventory is Dictionary or inventory.get("identity",[]).size()<2 or inventory.identity[1]!=data.sha256:return {"error":"Recorded loadout identity mismatch."}
		data.presentation["inventory"]=inventory.get("players",{})
	if data.has("presentation"):
		var pose_file:=FileAccess.open(str(data.presentation.get("punch","")),FileAccess.READ)
		var expected:int=16+int(data.frames)*data.players.size()*12
		if pose_file==null or pose_file.get_length()!=expected:return {"error":"Recorded camera state needs preparation."}
		var poses:=pose_file.get_buffer(expected)
		if poses.slice(0,4).get_string_from_ascii()!="VPS1" or poses.decode_u32(4)!=int(data.frames) or poses.decode_u32(8)!=data.players.size() or poses.decode_u32(12)!=3:return {"error":"Recorded camera state header mismatch."}
		data["view_punch_samples"]=poses.slice(16).to_float32_array()
		var travel_path:String=str(data.presentation.get("travel",""))
		if FileAccess.file_exists(travel_path):
			var travel:=FileAccess.get_file_as_bytes(travel_path)
			if travel.size()!=16+int(data.frames)*data.players.size()*4 or travel.slice(0,4).get_string_from_ascii()!="GDT1":return {"error":"Recorded travel state is invalid."}
			data["travel_samples"]=travel.slice(16).to_float32_array()
		var gait_path:String=str(data.presentation.get("gait_phase",""))
		if not gait_path.is_empty():
			var gait:=FileAccess.get_file_as_bytes(gait_path)
			if gait.size()!=16+int(data.frames)*data.players.size()*4 or gait.slice(0,4).get_string_from_ascii()!="GPH1":return {"error":"Recorded gait phase needs preparation."}
			data["gait_phase_samples"]=gait.slice(16).to_float32_array()
	var lighting_thread:=Thread.new()
	var lighting_started:bool=false
	if str(data.get("map_asset",""))!=existing_asset:
		lighting_started=lighting_thread.start(_read_lighting.bind(str(data.get("map_asset","")),str(data.get("asset_info",{}).get("fingerprint",""))))==OK
	var model_cache=preload("res://native_resource_cache.gd").new();model_cache.configure(str(options.get("cache","")))
	var stock := _read_stock(data, decoded,model_cache)
	# Join on both success and failure: never leave a resource worker behind.
	var lighting:Dictionary=lighting_thread.wait_to_finish() if lighting_started else {}
	if stock.has("error"): return stock
	data["read_profile"]=stock.get("read_profile",{})
	data.read_profile["tracks_stock_ms"]=(Time.get_ticks_usec()-read_start)/1000.0
	stock["particles"]={}
	for kind in data.get("particle_assets",{}).get("textures",{}):
		var texture:=ResourceLoader.load(str(data.particle_assets.textures[kind]))
		if texture==null:return {"error":"Prepared stock particle imagery could not be loaded."}
		stock.particles[kind]=texture
		if kind=="fire":
			var bank_path:String=str(data.particle_assets.get("fire_bank",str(data.particle_assets.textures[kind]).get_base_dir().path_join("fire-layers-v1.json")))
			if data.particle_assets.has("fire_bank") and not FileAccess.file_exists(bank_path):return {"error":"Prepared flame frames are missing. Prepare this demo again."}
			var bank:Dictionary=preload("res://particle_bank.gd").read_bank(bank_path,int(data.particle_assets.get("frames",{}).get("fire",0)),data.particle_assets.has("fire_bank"))
			if bank.has("error"):return bank
			if bank.has("texture"):
				if bank.layers!=int(data.particle_assets.get("frames",{}).get("fire",0)):return {"error":"Particle animation frame count mismatch"}
				stock.particles["fire_layers"]=bank.texture;data.read_profile["prepared_fire_layers"]=bank.layers
	if data.has("grenades"):
		var utility_path := str(data["grenades"].get("recording", ""))
		var utility_file := FileAccess.open(utility_path, FileAccess.READ)
		if utility_file == null or utility_file.get_length() > 64*1024*1024:
			return {"error": "Recorded grenade data is missing or exceeds the viewer limit. Prepare this demo again."}
		var utility_data: Variant = JSON.parse_string(utility_file.get_as_text())
		if not utility_data is Dictionary: return {"error": "Recorded grenade data is invalid."}
		data["grenade_data"] = utility_data
		stock["utility_models"] = {}
		for key in data["grenades"].get("models", {}):
			var scene := model_cache.load_scene(str(data["grenades"]["models"][key])) as PackedScene
			if scene == null: return {"error": "A prepared stock grenade model could not be loaded."}
			stock["utility_models"][key] = scene
			var weapon_id: String = {"smoke":"smokegrenade","he":"hegrenade","flash":"flashbang","molotov":"molotov","incendiary":"incgrenade","decoy":"decoy"}.get(key,key)
			stock["scenes"]["weapon:"+weapon_id] = scene
		for key in data["grenades"].get("sounds", {}):
			var audio_path := str(data["grenades"]["sounds"][key])
			var stream: AudioStream
			if audio_path.ends_with(".wav"): stream = AudioStreamWAV.load_from_file(audio_path)
			elif audio_path.ends_with(".mp3"): stream = AudioStreamMP3.load_from_file(audio_path)
			if stream != null: stock["sounds"][key] = stream
	if stock.has("sounds"):
		stock["sounds"].merge(_read_sound_bank(data.get("replay_audio",{}).get("sounds",{})),true)
	var asset := str(data.get("map_asset", ""))
	var smoke_path:String=str(data.get("smoke_presentation",""))
	var death_path:String=str(data.get("death_presentation",""))
	if FileAccess.file_exists(death_path):
		var deaths:Variant=JSON.parse_string(FileAccess.get_file_as_string(death_path))
		if not deaths is Dictionary or deaths.get("identity",[]).size()<2 or deaths.identity[1]!=data.sha256:return {"error":"Death presentation belongs to another recording."}
		data["recorded_deaths"]=deaths.get("deaths",{})
		data["recorded_world"]=deaths.get("world",[])
		data["recorded_smoke_colors"]=preload("res://smoke_presentation.gd").bind(data.get("grenade_data",{}).get("effects",[]),deaths.get("smokes",[]))
	if FileAccess.file_exists(smoke_path):
		var smoke_data:Variant=JSON.parse_string(FileAccess.get_file_as_string(smoke_path))
		if smoke_data is Dictionary and smoke_data.get("identity",[]).size()>1 and smoke_data.identity[1]==data.sha256:
			for effect in data.get("grenade_data",{}).get("effects",[]):
				if smoke_data.get("effects",{}).has(effect.id):
					effect.frames=smoke_data.effects[effect.id];effect["geometry"]="reconstructed_collision_seed_fill"
	var light_start:=Time.get_ticks_usec()
	if not lighting_started and asset!=existing_asset:lighting=_read_lighting(asset,str(data.get("asset_info",{}).get("fingerprint","")))
	for key in ["source_bounce","source_reflections","source_direct"]:data[key]=lighting.get(key,{})
	data["source_sky"]=preload("res://source_sky.gd").read_cache(asset,str(data.get("asset_info",{}).get("fingerprint","")))
	data["source_environment"]=preload("res://source_environment.gd").read_cache(asset,str(data.get("asset_info",{}).get("fingerprint","")))
	data["static_bindings"]=preload("res://static_bindings.gd").read_cache(asset,str(data.get("native_scene","")),str(data.get("asset_info",{}).get("fingerprint","")))
	data["world_visibility_data"]=preload("res://world_visibility.gd").read_for_map(asset,str(data.get("native_scene","")),str(data.get("asset_info",{}).get("fingerprint","")))
	data.read_profile["lighting_join_ms"]=(Time.get_ticks_usec()-light_start)/1000.0
	data.read_profile["lighting_overlapped"]=lighting_started
	var material_start:=Time.get_ticks_usec()
	var source_path:=asset.get_base_dir().path_join("source-materials.json")
	var source_data:Variant=JSON.parse_string(FileAccess.get_file_as_string(source_path)) if FileAccess.file_exists(source_path) else {}
	data["source_materials"]=source_data if source_data is Dictionary else {}
	if not data["source_materials"].is_empty():
		var geometry_bank:=ResourceLoader.load(str(source_data["geometry"]),"PackedScene") as PackedScene
		if geometry_bank==null:return {"error":"Prepared source blend geometry is missing."}
		var geometry_meshes:Dictionary={}
		var scene_state:=geometry_bank.get_state()
		for node_index in range(scene_state.get_node_count()):
			for property_index in range(scene_state.get_node_property_count(node_index)):
				if scene_state.get_node_property_name(node_index,property_index)=="mesh":
					geometry_meshes[str(scene_state.get_node_path(node_index)).trim_prefix("./")]=scene_state.get_node_property_value(node_index,property_index)
		data["source_materials"]["geometry_meshes"]=geometry_meshes
		var uv_path:=str(data["source_bounce"].get("uv_geometry",""))
		if not uv_path.is_empty():
			if data["source_bounce"].get("uv_geometry_source_fingerprint","")!=data.get("asset_info",{}).get("fingerprint",""):return {"error":"Prepared lightmap geometry revision mismatch."}
			var uv_bank:=ResourceLoader.load(uv_path,"PackedScene") as PackedScene
			if uv_bank==null:return {"error":"Prepared lightmap geometry is missing."}
			var uv_state:=uv_bank.get_state()
			for index in range(uv_state.get_node_count()):
				for property in range(uv_state.get_node_property_count(index)):
					if uv_state.get_node_property_name(index,property)=="mesh":
						geometry_meshes[str(uv_state.get_node_path(index)).trim_prefix("./")]=uv_state.get_node_property_value(index,property)
		for definition in data["source_materials"]["materials"].values():
			var loaded:Dictionary={}
			for semantic in definition.get("native_textures",{}):
				var resource=ResourceLoader.load(str(definition["native_textures"][semantic]),"Texture2D")
				if resource==null:return {"error":"A prepared source material texture is missing."}
				loaded[semantic]=resource
			definition["loaded_textures"]=loaded
	var effect_path := asset.get_base_dir().path_join("effects.json")
	data.read_profile["materials_ms"]=(Time.get_ticks_usec()-material_start)/1000.0
	var effect_definitions: Variant = JSON.parse_string(FileAccess.get_file_as_string(effect_path)) if FileAccess.file_exists(effect_path) else {}
	data["map_effects"] = effect_definitions.get("materials",{}) if effect_definitions is Dictionary else {}
	data["source_effects"]=preload("res://source_effects.gd").read_cache(asset,str(data.get("asset_info",{}).get("fingerprint","")))
	for definition in data["map_effects"].values():
		var textures: Array = []
		for path_to_mask in definition["masks"]:
			var image := Image.load_from_file(str(path_to_mask))
			if image==null: return {"error":"A prepared atmospheric dust mask is missing. Reopen the downloaded demo to repair it."}
			image.generate_mipmaps()
			textures.append(ImageTexture.create_from_image(image))
		definition["textures"] = textures
	if asset == existing_asset:
		return {"data": data, "samples": decoded, "stock": stock, "reuse": true}
	data.read_profile["dependencies_ms"]=(Time.get_ticks_usec()-read_start)/1000.0-float(data.read_profile.tracks_stock_ms)
	if not native_path.is_empty() and FileAccess.file_exists(native_path):
		_worker_phase("Loading the prepared map…")
		var packed:PackedScene=(ResourceLoader.load_threaded_get(native_path) if threaded_map else ResourceLoader.load(native_path,"PackedScene",ResourceLoader.CACHE_MODE_IGNORE)) as PackedScene
		if packed == null: return {"error": "Prepared map could not be read. Prepare this map again."}
		data.read_profile["map_ms"]=(Time.get_ticks_usec()-read_start)/1000.0-float(data.read_profile.tracks_stock_ms)-float(data.read_profile.dependencies_ms)
		data.read_profile["map_overlapped"]=threaded_map
		var output:Dictionary={"data": data, "samples": decoded, "stock": stock, "packed": packed, "reuse": false}
		if collision_started:
			var collision_packed:=ResourceLoader.load_threaded_get(collision_metadata.path) as PackedScene
			if collision_packed!=null:output["collision_packed"]=collision_packed
		return output
	_worker_phase("Loading map textures and geometry in the background…")
	var loader := GLTFDocument.new()
	var state := GLTFState.new()
	var error := loader.append_from_file(asset, state)
	if error != OK: return {"error": "The map could not be loaded (" + str(error) + ")."}
	return {"data": data, "samples": decoded, "stock": stock, "loader": loader, "gltf": state, "reuse": false}

func _read_sound_bank(paths:Dictionary) -> Dictionary:
	# File decoding is independent of mesh/texture loading and uses no scene nodes.
	var sounds:Dictionary={}
	for key in paths:
		var path:=str(paths[key]);var stream:AudioStream
		if path.ends_with(".wav"):stream=AudioStreamWAV.load_from_file(path)
		elif path.ends_with(".mp3"):stream=AudioStreamMP3.load_from_file(path)
		if stream!=null:sounds[key]=stream
	return sounds

func _read_stock(data: Dictionary, decoded: PackedFloat32Array,model_cache:RefCounted) -> Dictionary:
	if not data.has("stock") or not data.has("gameplay"): return {}
	var started:int=Time.get_ticks_usec();var profile:Dictionary={}
	_worker_phase("Loading shared players and this demo’s weapons…")
	var bank: Dictionary = data["stock"]
	var sound_thread:=Thread.new()
	var sound_started:bool=sound_thread.start(_read_sound_bank.bind(bank["sounds"]))==OK
	var models=preload("res://scene_bank.gd").new()
	models.resolver=model_cache
	models.background_reads=bool(data.get("stock_background_reads",true))
	for team in data.get("actor_assets",{}).get("arms",{}):models.add("vm_"+str(team),str(data.actor_assets.arms[team].scene))
	for team in bank["players"]:models.add(str(team),str(bank.players[team]))
	for name_value in data.get("weapons",[]):
		var key:String=str(bank.get("aliases",{}).get(str(name_value),str(name_value)))
		if bank.weapons.has(key):models.add("weapon:"+key,str(bank.weapons[key].scene))
	models.start()
	var phase:int=Time.get_ticks_usec()
	_worker_phase("Preparing player and grenade animations…")
	var pose_preparation:Dictionary=preload("res://utility_preparation.gd").read_poses(data)
	if pose_preparation.has("error"):
		models.drain()
		if sound_started:sound_thread.wait_to_finish()
		return pose_preparation
	data["pose_preparation"]=pose_preparation
	profile["poses_ms"]=(Time.get_ticks_usec()-phase)/1000.0;phase=Time.get_ticks_usec()
	_worker_phase("Loading shared players and this demo’s weapons…")
	var loaded:Dictionary=models.read_all()
	if loaded.has("error"):
		if sound_started:sound_thread.wait_to_finish()
		return loaded
	var scenes:Dictionary=loaded.scenes
	profile["models_join_ms"]=(Time.get_ticks_usec()-phase)/1000.0;profile["unique_scenes"]=loaded.unique;profile["model_reads_peak"]=loaded.peak_pending;phase=Time.get_ticks_usec()
	var sounds:Dictionary=sound_thread.wait_to_finish() if sound_started else _read_sound_bank(bank["sounds"])
	profile["audio_join_ms"]=(Time.get_ticks_usec()-phase)/1000.0;phase=Time.get_ticks_usec()
	var state_file := FileAccess.open(str(data["gameplay"]["states"]), FileAccess.READ)
	if state_file == null: return {"error": "Recorded gameplay state is missing."}
	if state_file.get_length() != 16 + int(data["frames"]) * data["players"].size() * 8 * 4:
		return {"error": "Recorded gameplay state failed its size check."}
	var raw := state_file.get_buffer(state_file.get_length())
	if raw.size() != 16 + int(data["frames"]) * data["players"].size() * 8 * 4 or raw.slice(0, 4).get_string_from_ascii() != "GSA1":
		return {"error": "Recorded gameplay state failed its format check."}
	profile["state_read_ms"]=(Time.get_ticks_usec()-phase)/1000.0;profile["stock_total_ms"]=(Time.get_ticks_usec()-started)/1000.0
	profile["fast_scene_hits"]=model_cache.hits;profile["fast_scene_fallbacks"]=model_cache.fallbacks
	return {"scenes": scenes, "sounds": sounds, "states": raw.slice(16).to_float32_array(),"read_profile":profile}

func _load_replay(path: String) -> void:
	if load_thread != null:
		status_label.text = "A demo is already loading. Cancel it in Toolbox before choosing another."
		return
	playing = false
	if sound_player != null: sound_player.reset(clock_tick)
	if utility != null: utility.silence(); utility.visible = false
	if flash_overlay != null: flash_overlay.color.a = 0
	replay = {}
	loading_active = true
	load_error = ""
	load_max_frame_ms = 0
	load_frame_count = 0
	load_started_us = Time.get_ticks_usec()
	load_profile = {}
	progress_bar.visible = true
	progress_bar.value = 84
	_worker_phase("Reading player tracks…")
	status_label.text = "Reading player tracks…"
	var mount:Dictionary={}
	var mount_path:String=path.get_basename()+".pack.json"
	if FileAccess.file_exists(mount_path):
		var reader:=FileAccess.open(mount_path,FileAccess.READ)
		if reader!=null and reader.get_length()<64*1024:
			var candidate:Variant=JSON.parse_string(reader.get_as_text())
			if candidate is Dictionary and candidate.get("schema",0)==1 and str(candidate.get("scene","")).begins_with("res://prepared/"):
				if FileAccess.file_exists(str(candidate.get("pack",""))) and ProjectSettings.load_resource_pack(str(candidate.get("pack","")),false):mount=candidate
	load_thread = Thread.new()
	var error := load_thread.start(_read_replay.bind(path, loaded_asset,mount))
	if error != OK:
		load_thread = null
		_loading_error("Could not start the background map loader.")

func _finish_load(payload: Dictionary) -> void:
	if payload.has("error"):
		_loading_error(str(payload["error"]))
		return
	var data: Dictionary = payload["data"]
	world_visibility.restore();world_visibility.enabled=false
	dynamic_world.restore()
	load_profile["read_ms"] = (Time.get_ticks_usec() - load_started_us) / 1000.0
	var stage_started:int=Time.get_ticks_usec()
	if not payload.get("reuse", false):
		source_materials=preload("res://source_materials.gd").new()
		source_materials.configure(data.get("source_materials",{}))
		source_bounce=preload("res://source_bounce.gd").new()
		source_bounce.configure(data.get("source_bounce",{}))
		source_reflections=preload("res://source_reflections.gd").new()
		source_reflections.configure(data.get("source_reflections",{}))
		if source_direct.root!=null:source_direct.root.free()
		source_direct=preload("res://source_direct.gd").new()
		source_direct.configure(data.get("source_direct",{}),self)
		load_profile["lighting_setup_ms"]=(Time.get_ticks_usec()-stage_started)/1000.0
		map_effects=data.get("map_effects",{})
		source_effects=preload("res://source_effects.gd").new();source_effects.configure(data.get("source_effects",{}),map_effects)
		effect_materials.clear()
		status_label.text = "Preparing the 3D scene…"
		progress_bar.value = 88
		await get_tree().process_frame
		stage_started=Time.get_ticks_usec()
		var world: Node3D
		if payload.has("packed"):
			world = payload["packed"].instantiate() as Node3D
		else:
			world = payload["loader"].generate_scene(payload["gltf"]) as Node3D
		load_profile["instantiate_ms"]=(Time.get_ticks_usec()-stage_started)/1000.0
		if world == null:
			_loading_error("The map import did not contain a 3D scene.")
			return
		if map_scene != null: map_scene.queue_free()
		map_scene = world
		if prepared_physics!=null:prepared_physics.free();prepared_physics=null
		if payload.has("collision_packed"):
			prepared_physics=payload.collision_packed.instantiate() as Node3D;add_child(prepared_physics)
		load_profile["prepared_collision"]=prepared_physics!=null
		source_materials.root=world
		source_bounce.map_root=world;source_reflections.map_root=world
		if not data.get("static_bindings",{}).is_empty() and not data.get("ignore_static_bindings",false):
			source_bounce.static_queries=data.static_bindings.bounce;source_reflections.static_queries=data.static_bindings.reflections
		load_profile["prepared_static_bindings"]=not source_reflections.static_queries.is_empty()
		collision_regions.clear()
		collision_candidates.clear()
		collision_cursor = 0
		map_suns.clear()
		fallback_sun.visible = true
		var initial := int(data["rounds"][0]["tick"]) / int(data["step"]) if not data["rounds"].is_empty() else 0
		var initial_samples: PackedFloat32Array = payload["samples"]
		for player in range(data["players"].size()):
			var base: int = (initial * data["players"].size() + player) * COLUMNS
			collision_regions.append(Vector3(initial_samples[base + 1], initial_samples[base + 2], initial_samples[base]) * INCH)
		var branches := world.get_children()
		var authoring: Dictionary = {}
		if prepared_physics==null:
			authoring = dynamic_world.read_authoring(str(data.get("map_asset","")),str(data.get("asset_info",{}).get("fingerprint","")))
		stage_started=Time.get_ticks_usec()
		for branch in branches:
			_clear_ownership(branch)
			world.remove_child(branch)
		world.visible = false
		add_child(world)
		var batch_started := Time.get_ticks_usec()
		var attached := 0
		for branch in branches:
			world.add_child(branch)
			_style_map(branch, bool(data.get("asset_info", {}).get("geometry_only", true)))
			if prepared_physics==null and authoring.is_empty():
				_build_collision(branch)
			attached += 1
			if Time.get_ticks_usec() - batch_started > 16000:
				status_label.text = "Preparing camera collision · " + str(attached) + " / " + str(branches.size())
				progress_bar.value = 88.0 + 10.0 * attached / maxi(1, branches.size())
				await get_tree().process_frame
				batch_started = Time.get_ticks_usec()
		physics_scene = map_scene
		loaded_asset = str(data["map_asset"])
		world.visible = true
		load_profile["static_material_pool"]=preload("res://static_material_pool.gd").apply(world,bool(data.get("pool_static_materials",true)))
		load_profile["scene_bind_ms"]=(Time.get_ticks_usec()-stage_started)/1000.0
		load_profile["surface_shader_variants"]=source_bounce.shaders.keys()
		# The small revision-bound query memo was previously regenerated only by
		# a diagnostic flag. A renderer update therefore made every normal open
		# repeat thousands of identical probe/reflection selections indefinitely.
		if not authoring.is_empty():
			world.set_meta("replay_dynamic_bindings",dynamic_world.install(world,authoring))
			var collision_batch := Time.get_ticks_usec()
			for branch in world.get_children():
				_build_collision(branch)
				if Time.get_ticks_usec()-collision_batch > 16000:
					await get_tree().process_frame
					collision_batch = Time.get_ticks_usec()
		if data.get("prepare_static_bindings",false) or (not load_profile.prepared_static_bindings and not data.get("ignore_static_bindings",false)):
			load_profile["saved_static_bindings"]=preload("res://static_bindings.gd").save_cache(self,data)
	stage_started=Time.get_ticks_usec()
	for figure in figures: figure.queue_free()
	for button in roster_buttons: button.queue_free()
	figures.clear()
	roster_buttons.clear()
	replay = data
	fallback_sun.rotation_degrees=Vector3(-55,-35,0);fallback_sun.light_color=Color("ffe0b8")
	preload("res://source_environment.gd").configure_sun(fallback_sun,{},REVIEW_SUN)
	if map_suns.is_empty() and not data.get("source_environment",{}).is_empty():map_suns.append(fallback_sun);fallback_sun.visible=true
	for sun in map_suns:preload("res://source_environment.gd").configure_sun(sun,data.get("source_environment",{}),REVIEW_SUN)
	var visibility_started:int=Time.get_ticks_usec()
	world_visibility.configure(self,data.get("world_visibility_data",{}))
	data["dynamic_bindings"] = map_scene.get_meta("replay_dynamic_bindings",{})
	var bindings := FileAccess.open(str(data.get("map_asset","")).get_base_dir().path_join("dynamic-bindings.json"),FileAccess.READ)
	if bindings != null and bindings.get_length() <= 1024*1024:
		var manifest:Variant = JSON.parse_string(bindings.get_as_text())
		if manifest is Dictionary:
			data["dynamic_bindings"] = manifest
	if dynamic_world.configure(map_scene,prepared_physics!=null,data)>0:
		# Static culling must not overwrite a recorded object's visibility.
		world_visibility.restore()
		world_visibility.enabled=false
	load_profile["visibility_bind_ms"]=(Time.get_ticks_usec()-visibility_started)/1000.0
	load_profile["visibility_enabled"]=world_visibility.enabled
	load_profile["native_static_sun"]=static_sun.configure(self,bool(data.get("native_static_shadows",preload("res://static_sun_shadows.gd").qualified(data))) and RenderingServer.get_current_rendering_method()=="mobile")
	load_profile["visibility_cullable_meshes"]=world_visibility.state.get("cullable_meshes",0)
	world_environment.tonemap_mode=Environment.TONE_MAPPER_FILMIC;world_environment.tonemap_exposure=1.0
	source_post.configure(data.get("postprocess",{}),world_environment)
	source_sky.configure(data.get("source_sky",{}),world_environment)
	source_sky.set_brightness(review_brightness)
	var color_pass:ColorRect=source_post.attach(overlay_root)
	if color_pass!=null:overlay_root.move_child(color_pass,0)
	presentation.configure(data.get("presentation",{}));view_punch=data.get("view_punch_samples",PackedFloat32Array())
	character_materials=preload("res://character_materials.gd").new();character_materials.configure(data.get("character_materials",{}))
	travel_samples=data.get("travel_samples",PackedFloat32Array())
	gait_phase_samples=data.get("gait_phase_samples",PackedFloat32Array())
	review_hud.configure(data.get("hud",{}),data.get("stock",{}).get("weapons",{}))
	review_hud.radar.configure(str(data.get("map","")))
	samples = payload["samples"]
	stock_scenes = payload.get("stock", {}).get("scenes", {})
	stock_sounds = payload.get("stock", {}).get("sounds", {})
	state_samples = payload.get("stock", {}).get("states", PackedFloat32Array())
	actor_count=data["players"].size()
	if utility != null: utility.free()
	utility = GrenadePlayer.new()
	add_child(utility)
	utility.configure(data.get("grenade_data", {}), payload.get("stock", {}).get("utility_models", {}), stock_sounds, camera, flash_overlay,payload.get("stock",{}).get("particles",{}),data.get("particle_assets",{}).get("frames",{}))
	utility.bullet_events=data.get("presentation",{}).get("network",{}).get("shots",[])
	if shot_player!=null:shot_player.free()
	shot_player=preload("res://shot_player.gd").new();add_child(shot_player)
	shot_player.configure(data.get("shots",{}))
	shot_player.fires=data.get("gameplay",{}).get("events",[]).filter(func(event:Dictionary):return event.kind=="weapon_fire")
	for event in shot_player.fires:
		var frame:int=clampi(int(event.tick)/int(data.step),0,int(data.frames)-1)
		event["yaw"]=_sample(frame,int(event.player),3)
	weapon_requests.clear()
	weapon_loading = ""
	action_events.clear()
	death_events.clear()
	if sound_player != null: sound_player.free()
	sound_player = null
	if source_viewmodel!=null:
		source_viewmodel.free();source_viewmodel=null;view_weapon=null
	elif view_weapon != null: view_weapon.free()
	view_weapon = null
	view_weapon_key = ""
	view_weapon_skeleton = null
	if not data.get("actor_assets",{}).is_empty():
		source_viewmodel=preload("res://source_viewmodel.gd").new()
		add_child(source_viewmodel)
		source_viewmodel.configure(overlay_root,data.actor_assets,stock_scenes)
		source_viewmodel.set_muzzle_texture(payload.get("stock",{}).get("particles",{}).get("muzzle"))
	if not stock_scenes.is_empty():
		sound_player = StockAudio.new()
		add_child(sound_player)
		var audio_events: Array = data["gameplay"]["events"].duplicate()
		audio_events.append_array(data.get("replay_audio",{}).get("events",[]))
		audio_events.append_array(dynamic_world.audio_events())
		for event in data.get("grenade_data", {}).get("audio", []):
			# Sustained smoke is handled by a seekable loop, avoiding duplicate starts.
			if event.get("sound") == "grenade:smoke" and stock_sounds.has("loop:smoke"): continue
			audio_events.append(event)
		audio_events.sort_custom(func(a: Dictionary, b: Dictionary): return float(a["tick"]) < float(b["tick"]))
		sound_player.configure(stock_sounds, audio_events, camera,data.get("replay_audio",{}).get("zones",[]))
		for event in data["gameplay"]["events"]:
			if event.kind=="player_death":
				var victim:=int(event.player)
				var death_key:String=str(victim)+":"+str(int(event.tick))
				if data.get("recorded_deaths",{}).has(death_key):event["recorded"]=data.recorded_deaths[death_key]
				if not death_events.has(victim):death_events[victim]=[]
				event["until"]=float(data.info.ticks)+1
				for frame in range(maxi(0,int(event.tick/float(data.step))+1),int(data.frames)):
					if _sample(frame,victim,7)>.5:
						event.until=float(frame)*float(data.step);break
				death_events[victim].append(event)
			if event["kind"] not in ["weapon_fire", "weapon_reload", "item_equip"]: continue
			var key := str(int(event["player"])) + ":" + str(event["kind"]) + ":" + str(event["weapon"])
			if not action_events.has(key): action_events[key] = []
			action_events[key].append(int(event["tick"]))
	actor_count = data["players"].size()
	for player in range(actor_count):
		figures.append(_figure(str(data["players"][player]["name"])))
		if figures[-1] is StockActor:figures[-1].set_muzzle_texture(payload.get("stock",{}).get("particles",{}).get("muzzle"))
		var button := _button(roster, str(data["players"][player]["name"]), func(): _select_player(player))
		button.clip_text = true
		button.toggle_mode=true;button.alignment=HORIZONTAL_ALIGNMENT_LEFT
		button.custom_minimum_size.y=22;button.add_theme_font_size_override("font_size",12)
		var row_style:=ReviewHUD.surface(Color(.06,.10,.14,.7));row_style.set_corner_radius_all(4)
		row_style.content_margin_top=2;row_style.content_margin_bottom=2
		button.add_theme_stylebox_override("normal",row_style)
		button.tooltip_text = "SteamID64: " + str(data["players"][player]["id"])
		roster_buttons.append(button)
	selected_player = 0
	camera_mode = 1
	camera_menu.select(1)
	for player in range(actor_count):
		if str(data["title"]).to_lower().contains(str(data["players"][player]["name"]).to_lower()): selected_player = player
	clock_tick = float(data["rounds"][0]["tick"]) if not data["rounds"].is_empty() else 0
	if sound_player != null: sound_player.reset(clock_tick)
	round_menu.clear()
	round_menu.add_item("Round")
	for item in data["rounds"]: round_menu.add_item("Round " + str(int(item["number"])))
	timeline.max_value = float(data["info"]["ticks"])
	playing = false
	title_label.text = str(data["map"]).trim_prefix("de_").to_upper() + " · " + str(actor_count) + " players"
	status_label.text = "Ready · Map version unverified"
	status_label.tooltip_text = "Standalone review uses authored stock assets and recorded events. Lighting, ragdolls and effects remain approximate. The installed map revision is not verified against this recording."
	if source_bounce.atlas!=null:
		status_label.text="Ready · Map version unverified"
		status_label.tooltip_text+=" Source lightmaps and spatial bounce probes are loaded for this installed map revision."
	else:
		status_label.text="Ready · Approximate lighting · Map version unverified"
		status_label.tooltip_text+=" Authored baked lighting has not been prepared for this map revision."
		if not source_bounce.state.failures.is_empty():status_label.tooltip_text+=" "+str(source_bounce.state.failures)
	if not bool(data.get("map_in_selected_pool", true)):
		status_label.text = "Warning: outside your selected map pool · " + status_label.text
		status_label.add_theme_color_override("font_color", Color("ffce83"))
	else:
		status_label.remove_theme_color_override("font_color")
	if not data.get("map_preparation_warnings",[]).is_empty():
		status_label.text+=" · Some map details use fallback"
		status_label.tooltip_text+="\n"+"\n".join(data.map_preparation_warnings)
		status_label.add_theme_color_override("font_color",Color("ffce83"))
	_set_brightness(review_brightness)
	load_profile["gameplay_setup_ms"]=(Time.get_ticks_usec()-stage_started)/1000.0
	Engine.max_fps=240 if options.get("present","") in ["disabled","loading_only"] else 120
	stage_started=Time.get_ticks_usec()
	_update_picture()
	load_profile["initial_pose_ms"]=(Time.get_ticks_usec()-stage_started)/1000.0
	# Loading resources is not the same as rendering them. Finish first-use
	# pipeline work before inviting the host to attach our Windows input queue.
	var ready_message:String=status_label.text
	status_label.text="Preparing grenade playback…";_publish_status(true)
	var prepared:Dictionary=await preload("res://utility_preparation.gd").render_pipelines(self)
	if not prepared.has("materials"):
		var abandoned:Node=get_node_or_null("PipelinePreparation")
		if abandoned!=null:abandoned.free()
		_loading_error("Graphics preparation could not finish. Stop playback and reopen the demo; see the session log for details.");return
	prepared_utility_materials=prepared.materials
	load_profile["utility_preparation_ms"]=prepared.milliseconds
	load_profile["prepared_projectile_kinds"]=prepared.projectiles
	load_profile["prepared_weapon_models"]=prepared.weapons
	load_profile["prepared_world_pipeline_seeds"]=prepared.world_pipelines
	load_profile["prepared_pose_clips"]=data.get("pose_preparation",{}).get("clips",0)
	status_label.text="Preparing the first rendered frame…"
	var frame_started:int=Time.get_ticks_usec()
	await RenderingServer.frame_post_draw
	load_profile["first_gpu_frame_ms"]=(Time.get_ticks_usec()-frame_started)/1000.0
	frame_started=Time.get_ticks_usec()
	await get_tree().process_frame
	load_profile["next_frame_wait_ms"]=(Time.get_ticks_usec()-frame_started)/1000.0
	frame_started=Time.get_ticks_usec()
	await RenderingServer.frame_post_draw
	load_profile["second_gpu_frame_ms"]=(Time.get_ticks_usec()-frame_started)/1000.0
	status_label.text=ready_message
	load_profile["first_draw_ms"]=(Time.get_ticks_usec()-stage_started)/1000.0
	loading_active = false
	if options.get("present","")=="loading_only":DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED);Engine.max_fps=120
	load_profile["total_ms"] = (Time.get_ticks_usec() - load_started_us) / 1000.0
	load_profile["collision_meshes"] = collision_candidates.size()
	load_profile["video_memory_mib"]=Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED)/1048576.0
	load_profile["texture_memory_mib"]=Performance.get_monitor(Performance.RENDER_TEXTURE_MEM_USED)/1048576.0
	progress_bar.visible = false
	_publish_status(true)

func _style_map(node: Node, geometry_only: bool) -> void:
	# Keep the map's authored sunlight direction/color, normalized from lux.
	if node is DirectionalLight3D:
		map_suns.append(node)
		node.light_energy = REVIEW_SUN*review_brightness
		_configure_sun_shadows(node)
		fallback_sun.visible = false
	elif node is Light3D:
		# Preserve local fixtures if a newer import supplies them. Their position
		# and color remain authored; cap exposure for approximate review lighting.
		node.light_energy = clampf(node.light_energy,0,1)
	if node is MeshInstance3D:
		source_materials.apply_mesh(node)
		source_effects.apply_mesh(node)
		var named := str(node.name).to_lower()
		var tool_surface := false
		for surface in range(node.mesh.get_surface_count()):
			var source_material: Material = node.get_active_material(surface)
			if source_material is StandardMaterial3D and map_effects.has(source_material.resource_name):
				var definition: Dictionary = map_effects[source_material.resource_name]
				var effect := ShaderMaterial.new()
				effect.resource_name=source_material.resource_name
				effect.shader=MapDust
				effect.set_shader_parameter("tint",source_material.albedo_color)
				for layer in range(3):
					var index := mini(layer,definition["textures"].size()-1)
					effect.set_shader_parameter("mask"+str(layer+1),definition["textures"][index])
					var scale_data: Array = definition["scales"][index]
					var pan_data: Array = definition["speeds"][index]
					effect.set_shader_parameter("scale"+str(layer+1),Vector2(scale_data[0],scale_data[1]))
					effect.set_shader_parameter("pan"+str(layer+1),Vector2(pan_data[0],pan_data[1]))
				node.set_surface_override_material(surface,effect)
				node.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				effect_materials.append(effect)
			if source_material is StandardMaterial3D:
				# Source foliage vertex colors encode wind, not surface color.
				var material_name := str(source_material.resource_name).to_lower()
				if "palm" in material_name or "foliage" in material_name or "bush" in material_name or "grass" in material_name:
					source_material.vertex_color_use_as_albedo = false
			if source_material != null and str(source_material.resource_name).to_lower().begins_with("tools"):
				tool_surface = true
		if "blocklight" in named:
			# Authored invisible light blockers must still cast shadows. Hiding
			# the node entirely leaks sunlight through roofs and interiors.
			node.visible=true
			node.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY
		elif tool_surface or "playerclip" in named or "nodraw" in named or "trigger" in named:
			node.visible = false
		elif geometry_only:
			var material := StandardMaterial3D.new()
			material.albedo_color = Color(0.6, 0.57, 0.48) if "dust" in str(replay.get("map", "dust")) else Color(0.56, 0.6, 0.64)
			material.roughness = 0.9
			material.cull_mode = BaseMaterial3D.CULL_BACK
			node.material_override = material
		if not geometry_only and node.visible and node.cast_shadow!=GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY:source_bounce.apply_mesh(node)
		if not geometry_only and node.visible and node.cast_shadow!=GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY:source_reflections.apply_mesh(node)
		if not geometry_only and node.visible and node.cast_shadow!=GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY:source_direct.apply_mesh(node)
	for child in node.get_children(): _style_map(child, geometry_only)

func _configure_sun_shadows(sun:DirectionalLight3D) -> void:
	# Bias is in shadow-map units, not metres. The previous .015/.15
	# values caused self-shadowing bands across flat walls and floors.
	sun.shadow_enabled=true
	sun.shadow_bias=.1
	sun.shadow_normal_bias=1.5
	sun.directional_shadow_mode=DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	sun.directional_shadow_max_distance=100
	sun.directional_shadow_blend_splits=true
	sun.directional_shadow_fade_start=.85

func _set_brightness(value: float) -> void:
	review_brightness = value
	source_direct.set_brightness(value)
	source_sky.set_brightness(value)
	RenderingServer.global_shader_parameter_set("source_bounce_strength",value)
	world_environment.ambient_light_energy = REVIEW_AMBIENT*value
	var atmosphere:=world_environment.sky.sky_material as ProceduralSkyMaterial
	if atmosphere!=null:
		atmosphere.sky_energy_multiplier=.55*value
		atmosphere.ground_energy_multiplier=.35*value
	fallback_sun.light_energy = preload("res://source_environment.gd").base_energy(fallback_sun,REVIEW_SUN)*value
	for sun in map_suns:
		if is_instance_valid(sun): sun.light_energy = preload("res://source_environment.gd").base_energy(sun,REVIEW_SUN)*value

func _build_collision(node: Node, parent_transform: Transform3D = Transform3D.IDENTITY) -> void:
	var placement := parent_transform
	if node is Node3D: placement = parent_transform * node.transform
	var authored_collider:bool = node.name == &"Visual" and node.get_parent() is StaticBody3D and node.get_parent().get_node_or_null("Collision") is CollisionShape3D
	if node is MeshInstance3D and node.visible and not authored_collider and node.cast_shadow!=GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY:
		var bounds: AABB = placement * node.get_aabb()
		collision_candidates.append({"node": node, "bounds": bounds.grow(8.0)})
		for position in collision_regions:
			if bounds.grow(3.5).has_point(position):
				node.create_trimesh_collision()
				node.set_meta("viewer_collision", true)
				break
	for child in node.get_children(): _build_collision(child, placement)

func _extend_camera_collision() -> void:
	var started := Time.get_ticks_usec()
	var checked := 0
	while checked < collision_candidates.size() and Time.get_ticks_usec() - started < 1500:
		collision_cursor = (collision_cursor + 1) % collision_candidates.size()
		var entry: Dictionary = collision_candidates[collision_cursor]
		var mesh: MeshInstance3D = entry["node"]
		if not mesh.has_meta("viewer_collision") and entry["bounds"].has_point(camera.position):
			mesh.create_trimesh_collision()
			mesh.set_meta("viewer_collision", true)
		checked += 1

func collision_mesh_for_hit(hit:Dictionary) -> MeshInstance3D:
	if hit.is_empty():return null
	var node:Node=hit.collider.get_parent()
	if node is MeshInstance3D:return node
	var path:String=preload("res://prepared_collision.gd").mesh_for_face(replay.get("prepared_collision_info",{}),int(hit.get("face_index",-1)))
	var mesh:MeshInstance3D=map_scene.get_node_or_null(NodePath(path)) as MeshInstance3D if not path.is_empty() else null
	if mesh!=null:return mesh
	# Compiled collision surfaces need not share render-mesh topology. Resolve
	# diagnostic material inspection by the hit point, without affecting replay.
	var stack:Array=[map_scene];var closest:MeshInstance3D;var distance:float=INF
	while not stack.is_empty():
		var current:Node=stack.pop_back();stack.append_array(current.get_children())
		if not current is MeshInstance3D or current.mesh==null or not current.visible:continue
		var box:AABB=(current.global_transform*current.mesh.get_aabb()).grow(.1)
		if box.has_point(hit.position):
			var candidate:float=box.get_center().distance_to(hit.position)
			if candidate<distance:distance=candidate;closest=current
	return closest

func _clear_ownership(node: Node) -> void:
	node.owner = null
	for child in node.get_children(): _clear_ownership(child)

func _figure(player_name: String) -> Node3D:
	if not stock_scenes.is_empty():
		var actor := StockActor.new()
		add_child(actor)
		actor.configure(replay["stock"], stock_scenes, player_name)
		return actor
	var root := Node3D.new()
	add_child(root)
	var body := MeshInstance3D.new()
	var mesh := CapsuleMesh.new()
	mesh.radius = 0.23
	mesh.height = 1.75
	body.mesh = mesh
	body.position.y = 0.875
	var material := StandardMaterial3D.new()
	material.albedo_color = CT_COLOR
	body.material_override = material
	root.add_child(body)
	var aim := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = Vector3(0.12, 0.12, 0.65)
	aim.mesh = box
	aim.position = Vector3(0, 1.2, -0.35)
	aim.material_override = material
	root.add_child(aim)
	var nameplate := Label3D.new()
	nameplate.text = player_name
	nameplate.position.y = 2.0
	nameplate.pixel_size = 0.003
	nameplate.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	root.add_child(nameplate)
	return root

func _tickrate() -> float:
	return float(replay.get("info", {}).get("tickrate", 64.0))

func _weapon_key(frame: int, player: int) -> String:
	var name := str(replay["weapons"][int(_sample(frame, player, 10))])
	return str(replay.get("stock", {}).get("aliases", {}).get(name, name))

func _queue_weapon(key: String) -> void:
	if stock_scenes.has("weapon:" + key) or weapon_requests.has(key): return
	var definitions: Dictionary = replay.get("stock", {}).get("weapons", {})
	if not definitions.has(key): return
	var path := str(definitions[key]["scene"])
	weapon_requests[key] = path

func _poll_weapons() -> void:
	if replay.is_empty(): return
	var required: Dictionary = {}
	var frame := clampi(int(clock_tick / float(replay["step"])), 0, int(replay["frames"]) - 1)
	for player in range(actor_count):
		if _sample(frame, player, 9) > .5 and _sample(frame, player, 7) > .5: required[_weapon_key(frame, player)] = true
	for key in weapon_requests.keys():
		if key != weapon_loading and not required.has(key): weapon_requests.erase(key)
	if not weapon_loading.is_empty():
		var path := str(weapon_requests[weapon_loading])
		var status := ResourceLoader.load_threaded_get_status(path)
		if status == ResourceLoader.THREAD_LOAD_LOADED:
			stock_scenes["weapon:" + weapon_loading] = ResourceLoader.load_threaded_get(path)
			weapon_requests.erase(weapon_loading)
			weapon_loading = ""
		elif status == ResourceLoader.THREAD_LOAD_FAILED or status == ResourceLoader.THREAD_LOAD_INVALID_RESOURCE:
			weapon_requests.erase(weapon_loading)
			weapon_loading = ""
	if weapon_loading.is_empty() and not weapon_requests.is_empty():
		var selected := _weapon_key(frame, selected_player)
		var key := selected if weapon_requests.has(selected) else str(weapon_requests.keys()[0])
		if ResourceLoader.load_threaded_request(str(weapon_requests[key]), "PackedScene") == OK: weapon_loading = key
		else: weapon_requests.erase(key)

func _action_time(player: int, kind: String, weapon_key: String,at_tick:float=-1.0) -> float:
	if at_tick<0:at_tick=clock_tick
	var ticks: Array = action_events.get(str(player) + ":" + kind + ":" + weapon_key, [])
	var low := 0
	var high := ticks.size()
	while low < high:
		var middle := (low + high) / 2
		if float(ticks[middle]) <= at_tick: low = middle + 1
		else: high = middle
	return float(ticks[low - 1]) / _tickrate() if low > 0 else -1000000.0

func _air_time(frame: int, player: int,at_tick:float=-1.0) -> float:
	if at_tick<0:at_tick=clock_tick
	if state_samples[(frame * actor_count + player) * 8 + 3] < .5: return 0
	var first := frame
	var limit := maxi(0, frame - ceili(4.0 * _tickrate() / float(replay["step"])))
	while first > limit and state_samples[((first - 1) * actor_count + player) * 8 + 3] > .5: first -= 1
	return (at_tick - first * float(replay["step"])) / _tickrate()

func _update_view_weapon(frame:int,second:int=-1,alpha:float=0.0) -> void:
	if stock_scenes.is_empty(): return
	if second<0:second=frame
	var fraction:float=_motion_fraction(frame,second,selected_player,alpha)
	var key := _weapon_key(frame, selected_player)
	if source_viewmodel!=null:
		var base: int=(frame*actor_count+selected_player)*8
		var view_state:Dictionary=presentation.at(str(replay.players[selected_player].id),clock_tick)
		if view_state.has("inspect_tick"):
			var inspect_frame:int=clampi(int(float(view_state.inspect_tick)/float(replay.step)),0,int(replay.frames)-1)
			if _weapon_key(inspect_frame,selected_player)==key:view_state["inspect_seconds"]=float(view_state.inspect_tick)/_tickrate()
		if not travel_samples.is_empty():view_state["travel_units"]=lerpf(travel_samples[frame*actor_count+selected_player],travel_samples[second*actor_count+selected_player],fraction)
		var next:int=(second*actor_count+selected_player)*8
		view_state["groundspeed"]=Vector2(lerpf(state_samples[base],state_samples[next],fraction),lerpf(state_samples[base+1],state_samples[next+1],fraction)).length()
		view_state["airborne"]=state_samples[base+3]>.5
		source_viewmodel.set_recorded_state(view_state)
		source_viewmodel.update_pose(camera_mode==0 and _sample(frame,selected_player,7)>.5,int(_sample(frame,selected_player,6)),key,clock_tick/_tickrate(),state_samples[base+5]>.5,_action_time(selected_player,"weapon_fire",key),_action_time(selected_player,"weapon_reload",key),_action_time(selected_player,"item_equip",key))
		view_weapon=source_viewmodel.weapon_rig
		return
	if key != view_weapon_key or (view_weapon == null and stock_scenes.has("weapon:" + key)):
		if view_weapon != null: view_weapon.free()
		view_weapon = null
		view_weapon_skeleton = null
		view_weapon_key = key
		if stock_scenes.has("weapon:" + key):
			view_weapon = stock_scenes["weapon:" + key].instantiate()
			camera.add_child(view_weapon)
			view_weapon.position = Vector3(0.18, -0.23, -0.42)
			view_weapon.rotation.y = PI
			if figures[selected_player] is StockActor:
				view_weapon_skeleton = figures[selected_player]._find_weapon_skeleton(view_weapon)
	if view_weapon != null:
		view_weapon.visible = camera_mode == 0 and _sample(frame, selected_player, 7) > .5
		var actor: StockActor = figures[selected_player] as StockActor
		if actor != null and actor.weapon_skeleton != null and view_weapon_skeleton != null:
			for bone in range(view_weapon_skeleton.get_bone_count()):
				var source_bone := actor.weapon_skeleton.find_bone(view_weapon_skeleton.get_bone_name(bone))
				if source_bone >= 0:
					view_weapon_skeleton.set_bone_pose_position(bone, actor.weapon_skeleton.get_bone_pose_position(source_bone))
					view_weapon_skeleton.set_bone_pose_rotation(bone, actor.weapon_skeleton.get_bone_pose_rotation(source_bone))
					view_weapon_skeleton.set_bone_pose_scale(bone, actor.weapon_skeleton.get_bone_pose_scale(source_bone))

func _sample(frame: int, player: int, field: int) -> float:
	return samples[(frame * actor_count + player) * COLUMNS + field]

func _source_position(frame: int, player: int) -> Vector3:
	# Source2Viewer 20.1 bakes (Source Y, Source Z, Source X) into glTF.
	return Vector3(_sample(frame, player, 1), _sample(frame, player, 2), _sample(frame, player, 0)) * INCH

func _forward(yaw: float, pitch: float = 0.0) -> Vector3:
	var y := deg_to_rad(yaw)
	var p := deg_to_rad(clampf(pitch, -89.0, 89.0))
	return Vector3(sin(y) * cos(p), -sin(p), cos(y) * cos(p)).normalized()

func _motion_fraction(first:int,second:int,player:int,alpha:float) -> float:
	# Continuous quantities share one segment boundary. Never blend a respawn,
	# teleport, team change or absent/dead player into the preceding life.
	if _sample(first,player,7)<=.5 or _sample(second,player,7)<=.5 or _sample(first,player,9)<=.5 or _sample(second,player,9)<=.5 or _sample(first,player,6)!=_sample(second,player,6):return 0.0
	if _source_position(first,player).distance_squared_to(_source_position(second,player))>=25.0:return 0.0
	return clampf(alpha,0.0,1.0)

func _view_angles(first:int,second:int,player:int,alpha:float) -> Vector2:
	return _interpolated_angles(first,second,player,_motion_fraction(first,second,player,alpha))

func _interpolated_angles(first:int,second:int,player:int,fraction:float) -> Vector2:
	var angles:=Vector2(_sample(first,player,3),_sample(first,player,4))
	# Interpolate only a continuous living segment; respawns and teleports must
	# not sweep the camera between unrelated positions or through a full turn.
	angles.x=rad_to_deg(lerp_angle(deg_to_rad(angles.x),deg_to_rad(_sample(second,player,3)),fraction))
	angles.y=lerpf(angles.y,_sample(second,player,4),fraction)
	return angles

func _death_at(player:int) -> Dictionary:
	var events:Array=death_events.get(player,[])
	var low:=0;var high:=events.size()
	while low<high:
		var middle:int=(low+high)/2
		if float(events[middle].tick)<=clock_tick:low=middle+1
		else:high=middle
	if low==0:return {}
	var event:Dictionary=events[low-1]
	# Lifetimes are indexed once from recorded respawns, including buy periods.
	return event if clock_tick<float(event.until) else {}

func _pose_actor(figure:StockActor,player:int,first:int,second:int,fraction:float,angles:Vector2,tick:float,with_equipment:bool=true) -> void:
	var weapon_key:String=_weapon_key(first,player)
	var base:int=(first*actor_count+player)*8;var next_base:int=(second*actor_count+player)*8
	var velocity:=Vector3(state_samples[base],state_samples[base+1],state_samples[base+2]).lerp(Vector3(state_samples[next_base],state_samples[next_base+1],state_samples[next_base+2]),fraction)
	figure.apply_pose(weapon_key,velocity,state_samples[base+3]>.5,state_samples[base+4]>.5,
		lerpf(_sample(first,player,8),_sample(second,player,8),fraction),state_samples[base+5]>.5,state_samples[base+7]>.5,tick/_tickrate(),
		_action_time(player,"weapon_fire",weapon_key,tick),_action_time(player,"weapon_reload",weapon_key,tick),angles.x,angles.y,_air_time(first,player,tick),
		lerpf(travel_samples[first*actor_count+player],travel_samples[second*actor_count+player],fraction) if not travel_samples.is_empty() else -1.0,
		lerpf(gait_phase_samples[first*actor_count+player],gait_phase_samples[second*actor_count+player],fraction) if not gait_phase_samples.is_empty() else -1.0,with_equipment)
	if replay.get("actor_assets",{}).get("utility_world",{}).has(weapon_key):
		figure.utility_assets=replay.actor_assets
		figure.apply_utility(weapon_key,presentation.at(str(replay.players[player].id),tick),tick/_tickrate(),_sample(first,player,8))

func _update_picture() -> void:
	if replay.is_empty(): return
	dynamic_world.at_tick(clock_tick)
	var profile_start:int=Time.get_ticks_usec() if profile_picture else 0
	source_materials.update_tick(clock_tick/_tickrate())
	source_effects.update_tick(clock_tick/_tickrate())
	for material in effect_materials: material.set_shader_parameter("demo_time",clock_tick/_tickrate())
	if camera_menu.get_selected() != camera_mode: camera_menu.select(camera_mode)
	var offset := clock_tick / float(replay["step"])
	var first := clampi(int(floor(offset)), 0, int(replay["frames"]) - 1)
	var second := mini(first + 1, int(replay["frames"]) - 1)
	var alpha := clampf(offset - first, 0.0, 1.0)
	var selected_fraction := 0.0
	var selected_angles := Vector2.ZERO
	for player in range(actor_count):
		var motion_fraction:float=_motion_fraction(first,second,player,alpha)
		# The body and observer camera use the same continuous segment.
		var angles:=_interpolated_angles(first,second,player,motion_fraction)
		if player == selected_player:
			selected_fraction = motion_fraction
			selected_angles = angles
		var present := _sample(first, player, 9) > 0.5
		var alive := _sample(first, player, 7) > 0.5
		var team := int(_sample(first, player, 6))
		if utility!=null:utility.owner_teams[str(replay.players[player].id)]=team
		var figure := figures[player]
		roster_buttons[player].self_modulate.a=1.0 if alive else .55
		var death:Dictionary=_death_at(player) if not alive and replay.has("actor_assets") else {}
		figure.visible = (present and alive or not death.is_empty()) and not (camera_mode == 0 and player == selected_player)
		if not death.is_empty() and figure is StockActor:
			var prior:int=maxi(0,int((float(death.tick)-1)/float(replay.step)))
			team=int(_sample(prior,player,6))
			figure.set_team(team)
			var age:float=(clock_tick-float(death.tick))/_tickrate()
			var transition:float=preload("res://death_pose.gd").transition(age)
			if transition<1.0 and not figure.death_entries.has(int(death.tick)):
				# Recreate the same final living pose even when the first visit is
				# a direct/backward seek. Never capture a previously rendered pose.
				figure.position=_source_position(prior,player)
				figure.rotation.y=deg_to_rad(_sample(prior,player,3)+180)
				_pose_actor(figure,player,prior,prior,0.0,Vector2(_sample(prior,player,3),_sample(prior,player,4)),maxf(0,float(death.tick)-.0001),false)
				figure.capture_death_entry(int(death.tick))
			var recorded:Dictionary=death.get("recorded",{})
			var origin:Array=recorded.get("serverOrigin",death.position)
			figure.position=_source_position(prior,player).lerp(Vector3(float(origin[1]),float(origin[2]),float(origin[0]))*INCH,transition)
			var yaw:float=float(recorded.eyeAngles[1]) if recorded.has("eyeAngles") else _sample(prior,player,3)
			figure.rotation.y=lerp_angle(deg_to_rad(_sample(prior,player,3)+180),deg_to_rad(yaw+180),transition)
			var clips:Dictionary=replay.actor_assets.deaths
			# Select by the recorded hit region, never player slot/tick randomness.
			# These source collapse clips remain a fallback, not saved physics.
			var clip:String=preload("res://death_pose.gd").select_clip(clips,recorded)
			figure.apply_death(replay.actor_assets.models["ct" if team==3 else "t"],clip,age,int(death.tick))
			roster_buttons[player].text=str(replay.players[player].name)+"   OUT"
			continue
		var pos := _source_position(first, player)
		pos=pos.lerp(_source_position(second,player),motion_fraction)
		figure.position = pos
		var yaw:float=angles.x
		figure.rotation.y = deg_to_rad(yaw + 180.0)
		if figure is StockActor:
			figure.set_team(team)
			var weapon_key := _weapon_key(first, player)
			if present and alive: _queue_weapon(weapon_key)
			_pose_actor(figure,player,first,second,motion_fraction,angles,clock_tick)
		else:
			figure.scale.y = 1.0 - 0.3 * clampf(_sample(first, player, 8), 0, 1)
			var material := (figure.get_child(0) as MeshInstance3D).material_override as StandardMaterial3D
			material.albedo_color = T_COLOR if team == 2 else CT_COLOR
		roster_buttons[player].text = str(replay["players"][player]["name"])+"   "+str(int(_sample(first, player, 5)))+" HP"
		var team_color := T_COLOR if team == 2 else CT_COLOR
		var roster_button := roster_buttons[player]
		if not roster_button.has_theme_color_override("font_color") or roster_button.get_theme_color("font_color") != team_color:
			roster_button.add_theme_color_override("font_color", team_color)
	if profile_picture:picture_profile["actors_ms"]=(Time.get_ticks_usec()-profile_start)/1000.0
	var profile_mark:int=Time.get_ticks_usec() if profile_picture else 0
	if selected_player < figures.size() and camera_mode < 2:
		var motion_fraction := selected_fraction
		var angles := selected_angles
		var duck:float=lerpf(_sample(first,selected_player,8),_sample(second,selected_player,8),motion_fraction)
		var eye := figures[selected_player].position + Vector3.UP * (64.0 - 18.0 * duck) * INCH
		var direction := _forward(angles.x,angles.y)
		var state:Dictionary=presentation.at(str(replay.players[selected_player].id),clock_tick)
		var source_fov:float=float(state.get("fov",90));source_fov=90 if source_fov<=0 else source_fov
		camera.fov=preload("res://presentation_state.gd").vertical_fov(source_fov)
		if not view_punch.is_empty():
			var base:int=(first*actor_count+selected_player)*3
			var next:int=(second*actor_count+selected_player)*3
			angles.y+=lerpf(view_punch[base],view_punch[next],motion_fraction)
			angles.x+=lerpf(view_punch[base+1],view_punch[next+1],motion_fraction)
			direction=_forward(angles.x,angles.y)
		if camera_mode == 0:
			camera.position = eye
			camera.look_at(eye + direction)
		else:
			var behind := _forward(angles.x + orbit_angle)
			var desired := eye - behind * chase_distance + Vector3.UP * 0.9
			if physics_scene != null and is_inside_tree():
				var query := PhysicsRayQueryParameters3D.create(eye, desired)
				var hit := get_world_3d().direct_space_state.intersect_ray(query)
				if not hit.is_empty(): desired = hit["position"] + hit["normal"] * 0.15
			camera.position = desired
			camera.look_at(eye + direction * 0.7)
	_update_view_weapon(first,second,alpha)
	if world_visibility.enabled:world_visibility.update(camera.global_position)
	if profile_picture:picture_profile["camera_viewmodel_ms"]=(Time.get_ticks_usec()-profile_mark)/1000.0
	profile_mark=Time.get_ticks_usec() if profile_picture else 0
	if source_bounce.atlas!=null:
		for figure in figures:
			if figure is StockActor:
				source_bounce.update_actor(figure.rig,figure.position+Vector3.UP)
				source_bounce.update_actor(figure.held,figure.position+Vector3.UP)
				source_reflections.update_actor(figure.rig,figure.position+Vector3.UP)
				source_reflections.update_actor(figure.held,figure.position+Vector3.UP)
				source_direct.update_actor(figure.rig);source_direct.update_actor(figure.held)
				player_xray.update(figure.rig,figure.team,xray_enabled);player_xray.update(figure.held,figure.team,xray_enabled)
				character_materials.apply(figure.rig)
		if source_viewmodel!=null and source_viewmodel.picture.visible:
			var eye:Vector3=figures[selected_player].position+Vector3.UP*1.5
			source_bounce.update_actor(source_viewmodel.arm_rig,eye,true,camera.global_basis)
			source_bounce.update_actor(source_viewmodel.weapon_rig,eye,true,camera.global_basis)
			source_reflections.update_actor(source_viewmodel.arm_rig,eye)
			source_reflections.update_actor(source_viewmodel.weapon_rig,eye)
			source_direct.update_actor(source_viewmodel.arm_rig);source_direct.update_actor(source_viewmodel.weapon_rig)
	if source_viewmodel!=null:
		var sun:DirectionalLight3D=map_suns[0] if not map_suns.is_empty() else fallback_sun
		source_viewmodel.set_review_lighting(world_environment,sun,camera)
	if profile_picture:picture_profile["lighting_ms"]=(Time.get_ticks_usec()-profile_mark)/1000.0
	profile_mark=Time.get_ticks_usec() if profile_picture else 0
	if shot_player!=null:shot_player.update_tick(clock_tick,_tickrate())
	if damage_overlay!=null and shot_player!=null:
		(damage_overlay.material as ShaderMaterial).set_shader_parameter("damage",shot_player.hurt_amount(selected_player,clock_tick,_tickrate()) if camera_mode==0 else 0.0)
	if utility != null:
		utility.enabled = utility_enabled
		utility.flash_enabled = flash_enabled
		utility.sounds_enabled = sound_enabled
		utility.update_tick(clock_tick,str(replay["players"][selected_player]["id"]),camera_mode,playing and is_equal_approx(speed,1.0))
	if profile_picture:picture_profile["effects_ms"]=(Time.get_ticks_usec()-profile_mark)/1000.0
	profile_mark=Time.get_ticks_usec() if profile_picture else 0
	updating = true
	timeline.set_value_no_signal(clock_tick)
	updating = false
	pause_button.text = "Pause" if playing else "Play"
	var seconds := int(clock_tick / _tickrate())
	var duration:int=int(float(replay.info.ticks)/_tickrate())
	clock_label.text = "%02d:%02d / %02d:%02d" % [seconds / 60, seconds % 60,duration/60,duration%60]
	clock_label.tooltip_text="Tick %d / %d"%[int(clock_tick),int(replay.info.ticks)]
	var alive_counts:Dictionary={2:0,3:0};var teams:Array=[]
	var radar_points:Array=[]
	for player in range(actor_count):
		var team:int=int(_sample(first,player,6));teams.append(team)
		if team in [2,3] and _sample(first,player,9)>.5:
			radar_points.append({"x":_sample(first,player,0),"y":_sample(first,player,1),"yaw":_sample(first,player,3),"team":team,"alive":_sample(first,player,7)>.5,"selected":player==selected_player})
		if team in [2,3] and _sample(first,player,7)>.5 and _sample(first,player,9)>.5:alive_counts[team]+=1
	var selected:Dictionary=replay.players[selected_player].duplicate()
	selected["team"]=int(_sample(first,selected_player,6));selected["health"]=int(_sample(first,selected_player,5))
	selected["weapon"]=_weapon_key(first,selected_player)
	selected.merge(presentation.at(str(selected.id),clock_tick),true)
	selected["scoped"]=not state_samples.is_empty() and state_samples[(first*actor_count+selected_player)*8+6]>.5
	review_hud.group_roster(roster,roster_buttons,teams,selected_player)
	review_hud.radar.set_points(radar_points)
	var total:int=int(replay.rounds[-1].number) if not replay.rounds.is_empty() else 0
	review_hud.update_state(clock_tick,_tickrate(),total,alive_counts,selected,camera_mode)
	var round_index:=0
	for index in range(replay.rounds.size()):
		if replay.rounds[index].number==review_hud.last_state.get("round"):
			round_index=index+1
			break
	if round_menu.selected!=round_index:
		round_menu.select(round_index)
	if profile_picture:
		picture_profile["hud_ms"]=(Time.get_ticks_usec()-profile_mark)/1000.0
		picture_profile["total_ms"]=(Time.get_ticks_usec()-profile_start)/1000.0

func _select_player(player: int) -> void:
	selected_player = clampi(player, 0, maxi(0, actor_count - 1))
	_update_picture()

func _seek(value: float) -> void:
	if replay.is_empty(): return
	clock_tick = clampf(value, 0, float(replay["info"]["ticks"]))
	playing = false
	if sound_player != null: sound_player.reset(clock_tick)
	if utility != null: utility.silence()
	for figure in figures:
		if figure is StockActor:figure.reset_pose_history()
	_update_picture()

func _toggle_play() -> void:
	if not replay.is_empty(): playing = not playing

func _skip(seconds:float) -> void:
	var resume_after:bool=playing
	_seek(clock_tick+_tickrate()*seconds)
	playing=resume_after and clock_tick<float(replay.get("info",{}).get("ticks",0))
	pause_button.text="Pause" if playing else "Play"

func _fullscreen() -> void:
	if options.has("embedded"):
		_request_toolbox("expand")
		return
	get_window().mode = Window.MODE_WINDOWED if get_window().mode == Window.MODE_FULLSCREEN else Window.MODE_FULLSCREEN

func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.ctrl_pressed and event.keycode == KEY_F: _request_toolbox("search"); return
		if event.alt_pressed and event.keycode == KEY_LEFT: _request_toolbox("library"); return
		match event.keycode:
			KEY_SPACE: _toggle_play()
			KEY_LEFT: _skip(-10.0)
			KEY_RIGHT: _skip(10.0)
			KEY_F11: _fullscreen()
			KEY_ESCAPE: Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
			KEY_1: camera_mode = 0
			KEY_2: camera_mode = 1
			KEY_3: camera_mode = 2

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_RIGHT:
			Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if event.pressed else Input.MOUSE_MODE_VISIBLE
		if event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_UP: chase_distance = maxf(1, chase_distance - 0.5)
		if event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_DOWN: chase_distance = minf(15, chase_distance + 0.5)
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		if camera_mode == 2:
			camera.rotation.y -= event.relative.x * 0.003
			camera.rotation.x = clampf(camera.rotation.x - event.relative.y * 0.003, -1.5, 1.5)
		else: orbit_angle -= event.relative.x * 0.3

func _physics_process(delta: float) -> void:
	if camera_mode != 2 or not get_window().has_focus() or Input.mouse_mode != Input.MOUSE_MODE_CAPTURED: return
	var movement := Vector3.ZERO
	if Input.is_physical_key_pressed(KEY_W): movement -= camera.basis.z
	if Input.is_physical_key_pressed(KEY_S): movement += camera.basis.z
	if Input.is_physical_key_pressed(KEY_A): movement -= camera.basis.x
	if Input.is_physical_key_pressed(KEY_D): movement += camera.basis.x
	if Input.is_physical_key_pressed(KEY_Q): movement -= Vector3.UP
	if Input.is_physical_key_pressed(KEY_E): movement += Vector3.UP
	var rate := 20.0 if Input.is_physical_key_pressed(KEY_SHIFT) else 6.0
	camera.position += movement.normalized() * delta * rate

func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_WINDOW_FOCUS_OUT: Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		if backend_pid > 0 and OS.is_process_running(backend_pid): OS.kill(backend_pid)

func _light_state(node: Node) -> Array:
	var lights: Array = []
	if node is Light3D:
		lights.append({"name": str(node.name), "energy": node.light_energy, "visible": node.visible})
	for child in node.get_children(): lights.append_array(_light_state(child))
	return lights

func _run_smoke() -> void:
	if replay.has("validation_fixture"):
		await preload("res://map_validation.gd").run(self)
		return
	await get_tree().process_frame
	var cold_seek_audit:Dictionary={}
	if options.has("screenshot") and str(replay.get("sha256","")).begins_with("1c0db4765ef6"):
		cold_seek_audit=await preload("res://seek_audit.gd").run(self,str(options["screenshot"]).get_base_dir().path_join("seek-audit"))
	var start := clock_tick
	playing = true
	await get_tree().create_timer(0.6).timeout
	var advanced := clock_tick > start
	_seek(start + 64)
	var seek_ok := clock_tick == start + 64
	var selected := mini(1, actor_count - 1)
	_select_player(selected)
	var selected_ok := selected_player == selected
	camera_mode = 0
	_update_picture()
	var camera_ok := camera.position.is_equal_approx(figures[selected_player].position + Vector3.UP * (64.0 - 18.0 * _sample(clampi(int(clock_tick / float(replay["step"])), 0, int(replay["frames"]) - 1), selected_player, 8)) * INCH)
	var player_weapon_ok := stock_scenes.is_empty() or (view_weapon != null and view_weapon.visible)
	if options.has("screenshot"):
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png(str(options["screenshot"]).get_basename() + "_player.png")
	camera_mode = 1
	_update_picture()
	await get_tree().create_timer(0.5).timeout
	await RenderingServer.frame_post_draw
	if options.has("screenshot"): get_viewport().get_texture().get_image().save_png(str(options["screenshot"]))
	var result := {"ok": advanced and seek_ok and selected_ok and camera_ok and map_scene != null, "clock_advanced": advanced, "seek_exact": seek_ok,
		"player_selection": selected_ok, "player_camera": camera_ok, "actors": actor_count, "render_frames": frames_count,
		"map": replay["map"], "cs2_process_required": false, "camera_position": str(camera.position)}
	result["player_weapon_visible"] = player_weapon_ok
	result["ok"] = result["ok"] and player_weapon_ok
	if replay.get("seek_draw_fixture",false):
		result["scope"] = "Embedded playback and seek drawing only"
		var report := FileAccess.open(str(options["smoke"]),FileAccess.WRITE)
		if report != null:report.store_string(JSON.stringify(result))
		return
	if replay.get("require_fast_scenes",false) and int(replay.get("read_profile",{}).get("fast_scene_hits",0))<33:result["ok"]=false
	result["world_visibility"]=world_visibility.state.duplicate()
	result["source_sky"]=source_sky.state.duplicate()
	if replay.get("require_source_sky",false) and not source_sky.state.available:result["ok"]=false
	if replay.get("require_world_visibility",false) and not world_visibility.enabled:result["ok"]=false
	var floor_checks: Array = []
	var test_frame := clampi(int(clock_tick / float(replay["step"])), 0, int(replay["frames"]) - 1)
	if physics_scene != null:
		for player in range(actor_count):
			var pos := _source_position(test_frame, player)
			var query := PhysicsRayQueryParameters3D.create(pos + Vector3.UP * 0.2, pos - Vector3.UP * 3.0)
			var hit := get_world_3d().direct_space_state.intersect_ray(query)
			floor_checks.append({"player": player, "floor_distance": pos.y - hit["position"].y if not hit.is_empty() else null})
	result["floor_checks"] = floor_checks
	result["load_profile"] = load_profile
	if not cold_seek_audit.is_empty():
		result["seek_audit"]=cold_seek_audit
		if not cold_seek_audit.ok:result["ok"]=false
	result["read_profile"]=replay.get("read_profile",{})
	result["source_materials"]={"applied":source_materials.applied,"failures":source_materials.failures,"detail_gaps":source_materials.detail_gaps}
	result["source_effects"]=source_effects.state
	result["effects_regressions"]=await preload("res://effects_regressions.gd").run(self)
	if not result.effects_regressions.ok:result["ok"]=false
	result["utility_regressions"]=await preload("res://utility_regressions.gd").run(self)
	result["recorded_smoke_colors"]=replay.get("recorded_smoke_colors",{})
	if not result.utility_regressions.ok:result["ok"]=false
	result["viewmodel_shadow_regressions"]=await preload("res://viewmodel_shadow_regressions.gd").run(self)
	if not result.viewmodel_shadow_regressions.ok:result["ok"]=false
	result["source_bounce"]=source_bounce.state
	result["source_reflections"]=source_reflections.state
	result["source_direct"]=source_direct.state
	result["character_materials"]=character_materials.state
	result["source_post"]=source_post.state
	if source_post.state.available:
		result["post_regressions"]=await preload("res://post_regressions.gd").run(self)
		if not result.post_regressions.ok:result["ok"]=false
	if not source_direct.state.failures.is_empty():result["ok"]=false
	if not source_reflections.state.failures.is_empty():result["ok"]=false
	if source_reflections.atlas!=null and source_reflections.state.surfaces<1:result["ok"]=false
	if source_bounce.atlas!=null:
		result["bounce_regressions"]=await preload("res://bounce_regressions.gd").run(self)
		if not result.bounce_regressions.ok:result["ok"]=false
		result["lighting_regressions"]=await preload("res://lighting_regressions.gd").run(self)
		if not result.lighting_regressions.ok:result["ok"]=false
	if not source_bounce.state.failures.is_empty():result["ok"]=false
	if not source_materials.failures.is_empty():result["ok"]=false
	if not stock_scenes.is_empty():
		var rigs := 0
		var animated := 0
		for figure in figures:
			if figure is StockActor and figure.rig != null:
				rigs += 1
				if not figure.selected_animation.is_empty(): animated += 1
		result["stock_player_rigs"] = rigs
		result["animated_players"] = animated
		result["initial_weapon_models"] = stock_scenes.size() - 2
		result["stock_sound_samples"] = stock_sounds.size()
		var audio_ok := false
		var silence_ok := false
		for event in replay["gameplay"]["events"]:
			if event["kind"] == "weapon_fire" and stock_sounds.has("fire:" + str(event["weapon"])):
				sound_player.reset(float(event["tick"]) - 1)
				var before := sound_player.played_count
				sound_player.emit_until(float(event["tick"]))
				audio_ok = sound_player.played_count > before
				sound_player.reset(clock_tick)
				silence_ok = true
				for voice in sound_player.voices:
					if voice.playing: silence_ok = false
				break
		result["spatial_sound_event"] = audio_ok
		result["seek_stops_sound"] = silence_ok
		var reload_ok := false
		var weapon_parts := 0
		var weapon_motion := 0
		var motion_debug: Array = []
		var original_tick := clock_tick
		for event in replay["gameplay"]["events"]:
			if event["kind"] != "weapon_reload" or not stock_scenes.has("weapon:" + str(event["weapon"])): continue
			var definition: Dictionary = replay["stock"]["weapons"].get(str(event["weapon"]), {})
			var expected_clip := "reload_" + str(definition.get("clip", ""))
			var candidate_frame := clampi(int((float(event["tick"]) + 16) / float(replay["step"])), 0, int(replay["frames"]) - 1)
			var candidate_player := int(event["player"])
			if state_samples[(candidate_frame * actor_count + candidate_player) * 8 + 5] < .5: continue
			var later_frame := clampi(int((float(event["tick"]) + 96) / float(replay["step"])), 0, int(replay["frames"]) - 1)
			if state_samples[(later_frame * actor_count + candidate_player) * 8 + 5] < .5 or _weapon_key(later_frame, candidate_player) != str(event["weapon"]): continue
			_seek(float(event["tick"]) + 16)
			var actor: StockActor = figures[int(event["player"])]
			reload_ok = actor.selected_animation.ends_with(expected_clip)
			weapon_parts = actor.weapon_bones_updated
			if reload_ok and actor.weapon_skeleton != null:
				var detail := {"weapon": str(event["weapon"]), "clip": actor.selected_animation, "before_time": actor.animator.current_animation_position, "parts": actor.weapon_bones_updated}
				var initial_parts: Array = []
				for bone in range(actor.weapon_skeleton.get_bone_count()):
					initial_parts.append([actor.weapon_skeleton.get_bone_pose_position(bone), actor.weapon_skeleton.get_bone_pose_rotation(bone), actor.weapon_skeleton.get_bone_pose_scale(bone)])
				_seek(float(event["tick"]) + 96)
				detail["after_time"] = actor.animator.current_animation_position
				for bone in range(actor.weapon_skeleton.get_bone_count()):
					if not actor.weapon_skeleton.get_bone_pose_position(bone).is_equal_approx(initial_parts[bone][0]) or not actor.weapon_skeleton.get_bone_pose_rotation(bone).is_equal_approx(initial_parts[bone][1]) or not actor.weapon_skeleton.get_bone_pose_scale(bone).is_equal_approx(initial_parts[bone][2]): weapon_motion += 1
				if motion_debug.size() < 2: motion_debug.append(detail)
				if weapon_motion > 0: break
		_seek(original_tick)
		result["recorded_reload_animation"] = reload_ok
		result["weapon_parts_animated"] = weapon_parts
		result["weapon_bones_changed"] = weapon_motion
		result["weapon_motion_debug"] = motion_debug
		var motion_actor: StockActor = figures[0]
		motion_actor.apply_pose("knife", Vector3(220, 0, 0), false, false, 0, false, false, 0.1, -1000, -1000, 0)
		var bones: Array = []
		for bone in range(motion_actor.skeleton.get_bone_count()): bones.append(motion_actor.skeleton.get_bone_pose(bone))
		motion_actor.apply_pose("knife", Vector3(220, 0, 0), false, false, 0, false, false, 0.4, -1000, -1000, 0)
		var moved := 0
		for bone in range(motion_actor.skeleton.get_bone_count()):
			if not motion_actor.skeleton.get_bone_pose(bone).is_equal_approx(bones[bone]): moved += 1
		result["animated_bones_changed"] = moved
		result["actor_regressions"]=preload("res://actor_regressions.gd").run(self)
		result["ok"]=result["ok"] and result.actor_regressions.ok
		_update_picture()
		result["ok"] = result["ok"] and rigs == actor_count and animated == actor_count and audio_ok and silence_ok and reload_ok and moved > 0 and weapon_parts > 0 and weapon_motion > 0
	result["lights"] = _light_state(self)
	if options.has("embedded"):
		var library_data: Variant = JSON.parse_string(FileAccess.get_file_as_string(str(options.get("library", ""))))
		library_items = library_data if library_data is Array else []
		_filter_demos("")
	else:
		_choose_demo()
	await get_tree().process_frame
	var library_ok := false
	for entry in visible_demos:
		if str(entry["path"]) == str(replay["source"]): library_ok = true
	result["library_current_demo"] = library_ok
	result["library_count"] = visible_demos.size()
	result["ok"] = result["ok"] and library_ok
	dialog.hide()
	var aligned := 0
	for check in floor_checks:
		if check["floor_distance"] != null and absf(float(check["floor_distance"])) < 0.25: aligned += 1
	result["map_alignment"] = aligned >= ceili(actor_count * 0.7)
	result["ok"] = result["ok"] and result["map_alignment"]
	if replay.has("grenade_data"):
		var utility_result: Dictionary = await _check_utility()
		result["utility"] = utility_result
		result["ok"] = result["ok"] and utility_result["ok"]
	if options.has("screenshot"):
		if replay.get("visual_match_audit",false):
			result["visual_match_audit"]=await preload("res://visual_match_audit.gd").capture(self,str(options["screenshot"]).get_base_dir().path_join("visual-match"))
		if replay.get("world_render_audit",false):
			result["world_render_audit"]=await preload("res://world_render_audit.gd").run(self,str(options["screenshot"]).get_base_dir().path_join("world-render-audit"))
			if not result.world_render_audit.get("ok",false):result["ok"]=false
		if replay.get("motion_audit",false):
			result["motion_audit"]=await preload("res://motion_audit.gd").run(self)
			if not result.motion_audit.ok:result["ok"]=false
		if replay.get("world_geometry_audit",false):result["world_geometry_audit"]=preload("res://world_geometry_audit.gd").inventory(map_scene)
		if replay.get("weapon_graph_audit",false):
			result["layer_shader_audit"]=await preload("res://layer_shader_regressions.gd").run(self)
			if not result.layer_shader_audit.ok:result["ok"]=false
			result["weapon_graph_audit"]=await preload("res://audit_weapon_graph.gd").run(self,str(options["screenshot"]).get_base_dir().path_join("weapon-graph-audit"))
			if not result.weapon_graph_audit.ok:result["ok"]=false
		result["visual_frames"] = await preload("res://visual_audit.gd").capture(self,str(options["screenshot"]).get_base_dir().path_join("visual-frames"))
		if replay.get("reference_audit",false):
			result["reference_audit"]=await preload("res://reference_audit.gd").capture(self,str(options["screenshot"]).get_base_dir().path_join("reference-audit"))
		if replay.get("asset_load_audit",{}) is Dictionary and not replay.get("asset_load_audit",{}).is_empty():
			result["asset_load_audit"]=await preload("res://asset_load_gpu.gd").run(self,replay.asset_load_audit)
		if replay.get("blackout_audit",false):
			result["blackout_audit"]=await preload("res://blackout_audit.gd").run(self,str(options["screenshot"]).get_base_dir().path_join("blackout-audit"))
			if not result.blackout_audit.ok:result["ok"]=false
		if replay.get("regression_audit",false):
			result["regression_audit"]=await preload("res://regression_audit.gd").run(self,str(options["screenshot"]).get_base_dir().path_join("regression-audit"))
			if not result.regression_audit.ok:result["ok"]=false
	if replay.has("native_color_probe"):
		result["native_color_probe"]=await preload("res://native_texture_regressions.gd").run(self,str(replay.native_color_probe))
		if not result.native_color_probe.ok:result["ok"]=false
	var file := FileAccess.open(str(options["smoke"]), FileAccess.WRITE)
	if file != null: file.store_string(JSON.stringify(result))
	if not options.has("embedded"): get_tree().quit(0 if result["ok"] else 1)

func _check_utility() -> Dictionary:
	var before := clock_tick
	var before_player := selected_player
	var before_mode := camera_mode
	var failures: Array = []
	var kinds: Dictionary = {}
	for item in replay["grenade_data"]["throws"]:
		if kinds.has(item["kind"]): continue
		_seek((float(item["start"])+float(item["end"]))*0.5)
		var node: Node3D = utility.projectiles.get(item["id"])
		kinds[item["kind"]] = node != null and node.position.is_equal_approx(utility.path_position(item,clock_tick))
		if not kinds[item["kind"]]: failures.append("Projectile "+str(item["kind"]))
	var counts: Dictionary = {}
	camera_mode = 2
	for kind in ["smoke", "fire"]:
		var chosen: Dictionary = {}
		for item in replay["grenade_data"]["effects"]:
			if item["kind"] == kind and not item["frames"].is_empty(): chosen = item; break
		if chosen.is_empty(): continue
		var tick := minf(float(chosen["end"])-1,float(chosen["start"])+_tickrate()*2)
		_seek(tick)
		var count: int = utility.rendered_voxels if kind == "smoke" else utility.rendered_patches
		counts[kind] = count
		if count <= 0: failures.append("Recorded geometry "+kind)
		var center := utility.world(chosen["position"])
		camera.position = center + Vector3(6,4,7)
		camera.look_at(center+Vector3.UP*.7)
		await get_tree().process_frame
		await RenderingServer.frame_post_draw
		if options.has("screenshot"):
			get_viewport().get_texture().get_image().save_png(str(options["screenshot"]).get_basename()+"_"+kind+".png")
		# Sustained effects resume at their current age and stop on pause/seek.
		utility.update_tick(tick,str(replay["players"][selected_player]["id"]),camera_mode,true)
		var root: Node3D = utility.effects.get(chosen["id"])
		if root != null and root.has_node("Loop"):
			if not root.get_node("Loop").playing: failures.append("Utility loop start "+kind)
			_seek(tick)
			if root.get_node("Loop").playing: failures.append("Utility loop seek silence "+kind)
		_seek(float(chosen["end"]))
		if utility.effects.has(chosen["id"]): failures.append("Expiry "+kind)
		_seek(tick)
		var restored: int = utility.rendered_voxels if kind == "smoke" else utility.rendered_patches
		if restored != count: failures.append("Repeat seek "+kind)
	var flash_ok := false
	for blind in replay["grenade_data"]["blinds"]:
		for index in range(actor_count):
			if str(replay["players"][index]["id"]) != blind["player"]: continue
			selected_player = index
			camera_mode = 0
			_seek(float(blind["start"])+1)
			flash_ok = flash_overlay.color.a > 0 and flash_overlay.color.a <= .281
			camera_mode = 1
			_update_picture()
			flash_ok = flash_ok and flash_overlay.color.a == 0
			camera_mode = 0
			_seek(float(blind["end"]))
			flash_ok = flash_ok and flash_overlay.color.a == 0
			break
		if flash_ok: break
	if not flash_ok: failures.append("Player-specific flash duration/camera")
	var stock_audio_ok := true
	for event in replay["grenade_data"]["audio"]:
		if not stock_sounds.has(event["sound"]): continue
		if event["sound"] == "grenade:smoke" and stock_sounds.has("loop:smoke"): continue
		var started := sound_player.played_count
		sound_player.reset(float(event["tick"])-1)
		sound_player.emit_until(float(event["tick"]))
		stock_audio_ok = sound_player.played_count > started
		break
	if not stock_audio_ok: failures.append("Grenade spatial audio")
	_set_brightness(.65)
	var lighting_ok := is_equal_approx(world_environment.ambient_light_energy,REVIEW_AMBIENT*.65) and world_environment.ambient_light_sky_contribution<1
	for sun in map_suns: lighting_ok = lighting_ok and sun.visible and sun.shadow_enabled==bool(sun.get_meta("authored_shadows",true)) and is_equal_approx(sun.light_energy,preload("res://source_environment.gd").base_energy(sun,REVIEW_SUN)*.65)
	_set_brightness(1)
	if not lighting_ok: failures.append("Map sunlight/review brightness")
	selected_player = before_player
	camera_mode = before_mode
	_seek(before)
	return {"ok":failures.is_empty(),"failures":failures,"projectiles":kinds,"geometry":counts,
		"flash_camera_duration":flash_ok,"grenade_audio":stock_audio_ok,"map_suns":map_suns.size(),"lighting":lighting_ok}
