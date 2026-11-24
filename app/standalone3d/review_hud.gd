extends Control

const CT=Color("69c7ff")
const T=Color("ffb36b")
const MUTED=Color("91a6b8")
var ct_score:Label
var t_score:Label
var ct_name:Label
var t_name:Label
var ct_alive:Label
var t_alive:Label
var weapon_definitions:Dictionary={}
var phase_label:Label
var clock_label:Label
var phase_state_label:Label
var observer:Label
var feed:VBoxContainer
var rows:Array[RichTextLabel]=[]
var panels:Array[PanelContainer]=[]
var feed_signature:=""
var team_signature:=""
var team_headers:Dictionary={}
var snapshots:Array=[]
var phases:Array=[]
var kills:Array=[]
var last_state:Dictionary={}
var crosshair_visible:bool=false
var equipment:Label
var radar:Control

func _draw() -> void:
	if not crosshair_visible:return
	var center:=size*.5
	for direction in [Vector2.RIGHT,Vector2.LEFT,Vector2.UP,Vector2.DOWN]:
		draw_line(center+direction*4,center+direction*9,Color(0,0,0,.8),3)
		draw_line(center+direction*4,center+direction*9,Color("6cde72"),1.25)

static func surface(color:Color=Color("101d29")) -> StyleBoxFlat:
	var style:=StyleBoxFlat.new();style.bg_color=color
	style.set_corner_radius_all(8);style.set_border_width_all(1);style.border_color=Color("2a3e50")
	style.content_margin_left=12;style.content_margin_right=12;style.content_margin_top=8;style.content_margin_bottom=8
	return style

static func skin() -> Theme:
	var theme:=Theme.new();theme.default_font_size=13
	for kind in ["Button","OptionButton","CheckButton"]:
		var normal:=surface(Color("182b3b"));normal.set_corner_radius_all(5)
		normal.content_margin_left=8;normal.content_margin_right=8;normal.content_margin_top=5;normal.content_margin_bottom=5
		theme.set_stylebox("normal",kind,normal)
		var hover:=normal.duplicate() as StyleBoxFlat;hover.bg_color=Color("24475d");hover.border_color=Color("52768e")
		theme.set_stylebox("hover",kind,hover)
		var pressed:=hover.duplicate() as StyleBoxFlat;pressed.bg_color=Color("24546d");pressed.border_color=CT
		theme.set_stylebox("pressed",kind,pressed)
		var focus:=normal.duplicate() as StyleBoxFlat;focus.bg_color=Color.TRANSPARENT;focus.border_color=CT
		theme.set_stylebox("focus",kind,focus)
		theme.set_color("font_color",kind,Color("e4edf4"))
	for kind in ["Label","RichTextLabel"]:theme.set_color("font_color" if kind=="Label" else "default_color",kind,Color("e4edf4"))
	return theme

func label(parent:Node,text:String,size:int=13,color:Color=Color("e4edf4")) -> Label:
	var item:=Label.new();item.text=text;item.add_theme_font_size_override("font_size",size);item.add_theme_color_override("font_color",color)
	parent.add_child(item);return item

func panel(parent:Node) -> PanelContainer:
	var box:=PanelContainer.new();box.add_theme_stylebox_override("panel",surface(Color(.035,.065,.095,.90)));parent.add_child(box);return box

func _ready() -> void:
	mouse_filter=Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var score:=panel(self);score.name="MatchScore"
	score.anchor_left=.5;score.anchor_right=.5;score.offset_left=-135;score.offset_right=135;score.offset_top=90;score.offset_bottom=168
	var layout:=HBoxContainer.new();layout.add_theme_constant_override("separation",12);score.add_child(layout)
	var left:=VBoxContainer.new();left.size_flags_horizontal=Control.SIZE_EXPAND_FILL;layout.add_child(left)
	ct_name=label(left,"COUNTER-TERRORISTS",11,CT);ct_name.clip_text=true
	ct_score=label(left,"—",26,CT)
	ct_alive=label(left,"5 ALIVE",10,MUTED)
	var center:=VBoxContainer.new();layout.add_child(center)
	phase_label=label(center,"ROUND —",11,MUTED);phase_label.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER
	clock_label=label(center,"00:00",20);clock_label.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER
	phase_state_label=label(center,"PRE-MATCH",10,MUTED);phase_state_label.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER
	var right:=VBoxContainer.new();right.size_flags_horizontal=Control.SIZE_EXPAND_FILL;layout.add_child(right)
	t_name=label(right,"TERRORISTS",11,T);t_name.horizontal_alignment=HORIZONTAL_ALIGNMENT_RIGHT;t_name.clip_text=true
	t_score=label(right,"—",26,T);t_score.horizontal_alignment=HORIZONTAL_ALIGNMENT_RIGHT
	t_alive=label(right,"5 ALIVE",10,MUTED);t_alive.horizontal_alignment=HORIZONTAL_ALIGNMENT_RIGHT
	feed=VBoxContainer.new();feed.name="KillFeed";add_child(feed)
	feed.anchor_left=1;feed.anchor_right=1;feed.offset_left=-310;feed.offset_right=-14;feed.offset_top=186
	feed.offset_top=90
	feed.add_theme_constant_override("separation",5)
	for index in range(5):
		var card:=panel(feed);card.visible=false;panels.append(card)
		var row:=RichTextLabel.new();row.bbcode_enabled=true;row.fit_content=true;row.scroll_active=false
		row.autowrap_mode=TextServer.AUTOWRAP_OFF;row.custom_minimum_size=Vector2(268,19);row.clip_contents=true
		row.add_theme_font_size_override("normal_font_size",12);card.add_child(row);rows.append(row)
	var watch:=panel(self);watch.name="ObservedPlayer"
	watch.anchor_left=0;watch.anchor_right=0;watch.anchor_top=1;watch.anchor_bottom=1
	watch.offset_left=14;watch.offset_right=354;watch.offset_top=-182;watch.offset_bottom=-150
	observer=label(watch,"Select a player to review",13);observer.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER
	observer.text_overrun_behavior=TextServer.OVERRUN_TRIM_ELLIPSIS
	var gear:=panel(self);gear.name="Equipment"
	gear.anchor_left=0;gear.anchor_right=0;gear.anchor_top=1;gear.anchor_bottom=1
	gear.offset_left=14;gear.offset_right=354;gear.offset_top=-148;gear.offset_bottom=-92
	equipment=label(gear,"Recorded equipment unavailable",12);equipment.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER
	equipment.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART
	radar=preload("res://radar.gd").new();radar.name="Radar";add_child(radar)
	radar.anchor_left=0;radar.anchor_right=0;radar.offset_left=14;radar.offset_right=184;radar.offset_top=90;radar.offset_bottom=260

func configure(data:Dictionary,definitions:Dictionary={}) -> void:
	weapon_definitions=definitions
	snapshots=data.get("events",[]);kills=data.get("kills",[]);phases=[]
	for event in snapshots:
		if event.kind!="player_death":phases.append(event)
	feed_signature="";team_signature="";last_state={}

static func upper(events:Array,tick:float) -> int:
	var low:=0;var high:=events.size()
	while low<high:
		var middle:int=(low+high)/2
		if float(events[middle].tick)<=tick:low=middle+1
		else:high=middle
	return low

static func shorten(value:String,count:int=15) -> String:return value if value.length()<=count else value.left(count-1)+"…"
static func escape(value:String) -> String:return value.replace("[","[lb]")
static func tint(team:int) -> String:return "#69c7ff" if team==3 else ("#ffb36b" if team==2 else "#d8e4ed")

func weapon_name(key:String) -> String:
	return str(weapon_definitions.get(key,{}).get("label",key.replace("_"," ")))

func update_state(tick:float,rate:float,total:int,alive:Dictionary,selected:Dictionary,mode:int) -> void:
	var gear:Array=[]
	if selected.has("clip") and selected.has("reserve") and int(selected.clip)>=0 and int(selected.reserve)>=0:gear.append("AMMO  "+str(int(selected.clip))+" / "+str(int(selected.reserve)))
	if selected.has("armor"):gear.append("ARMOR  "+str(int(selected.armor))+(" + HELMET" if selected.get("helmet",0)>0 else ""))
	if selected.has("cash"):gear.append("$"+str(int(selected.cash)))
	equipment.text="   ·   ".join(gear) if not gear.is_empty() else "Recorded equipment unavailable"
	if selected.has("inventory"):
		var counts:Dictionary={}
		for key in selected.inventory:counts[key]=int(counts.get(key,0))+1
		var items:PackedStringArray=[]
		for key in counts:items.append(weapon_name(key)+(" ×"+str(counts[key]) if counts[key]>1 else ""))
		equipment.text+="\n"+" · ".join(items)
	var show_crosshair:bool=mode==0 and int(selected.get("health",0))>0 and not selected.get("scoped",false)
	if show_crosshair!=crosshair_visible:crosshair_visible=show_crosshair;queue_redraw()
	var index:=upper(snapshots,tick)-1
	var state:Dictionary=snapshots[index] if index>=0 else {}
	var phase_index:=upper(phases,tick)-1
	var phase:Dictionary=phases[phase_index] if phase_index>=0 else {}
	var compact:bool=get_viewport_rect().size.x<1100
	ct_name.text="CT" if compact else shorten(str(state.get("ct_name","CT")).trim_prefix("team_"),9)+" · CT"
	t_name.text="T" if compact else shorten(str(state.get("t_name","T")).trim_prefix("team_"),9)+" · T"
	ct_name.tooltip_text=str(state.get("ct_name","CT"));t_name.tooltip_text=str(state.get("t_name","T"))
	ct_score.text=str(int(state.ct_score)) if state.get("ct_score")!=null else "—"
	t_score.text=str(int(state.t_score)) if state.get("t_score")!=null else "—"
	ct_alive.text=str(alive.get(3,0))+" ALIVE";t_alive.text=str(alive.get(2,0))+" ALIVE"
	phase_label.text="ROUND "+(str(int(state.round)) if state.get("round")!=null else "—")+(" / "+str(total) if total>0 else "")
	var elapsed:int=maxi(0,int((tick-float(phase.get("tick",tick)))/rate))
	var phase_names:Dictionary={"round_start":"FREEZE","round_freeze_end":"LIVE","round_end":"ROUND OVER","bomb_planted":"BOMB PLANTED","bomb_defused":"DEFUSED","bomb_exploded":"DETONATED"}
	clock_label.text="%02d:%02d"%[elapsed/60,elapsed%60]
	clock_label.tooltip_text="Elapsed time since the recorded phase began."
	if phase.get("kind")=="round_freeze_end" and selected.get("round_seconds",0)>0:
		var remaining:int=maxi(0,int(ceil(float(selected.round_seconds)-(tick-float(phase.tick))/rate)))
		clock_label.text="%02d:%02d"%[remaining/60,remaining%60];clock_label.tooltip_text="Remaining round time from the recorded game rules."
	elif phase.get("kind")=="round_start" and phase_index+1<phases.size():
		var next_phase:Dictionary=phases[phase_index+1]
		var round_number=phase.get("round")
		if next_phase.kind=="round_freeze_end" and (round_number==null or next_phase.get("round")==null or next_phase.round==round_number):
			var remaining:int=maxi(0,int(ceil((float(next_phase.tick)-tick)/rate)))
			clock_label.text="%02d:%02d"%[remaining/60,remaining%60]
			clock_label.tooltip_text="Time until the recorded freeze-end event."
	phase_state_label.text=str(phase_names.get(phase.get("kind",""),"PRE-MATCH"))
	phase_state_label.add_theme_color_override("font_color",T if phase.get("kind")=="bomb_planted" else MUTED)
	clock_label.add_theme_color_override("font_color",T if phase.get("kind")=="bomb_planted" else Color("e4edf4"))
	observer.text=shorten(str(selected.get("name","—")),24)+"   ·   "+str(selected.get("health",0))+" HP"
	observer.add_theme_color_override("font_color",CT if selected.get("team")==3 else T)
	observer.tooltip_text="SteamID64: "+str(selected.get("id",""))+"\n"+clock_label.tooltip_text
	var recent:Array=[]
	var maximum:int=4 if get_viewport_rect().size.y<680 else 5
	for kill_index in range(upper(kills,tick)-1,-1,-1):
		var kill:Dictionary=kills[kill_index]
		if tick-float(kill.tick)>8*rate or recent.size()==maximum:break
		recent.push_front(kill)
	var signature:=str(recent)
	if signature!=feed_signature:
		feed_signature=signature
		for row_index in range(rows.size()):
			panels[row_index].visible=row_index<recent.size()
			if row_index>=recent.size():continue
			var kill:Dictionary=recent[row_index]
			var flags:=""
			if kill.get("headshot",false):flags+="  HS"
			if kill.get("wallbang",false):flags+="  WALL"
			if kill.get("smoke",false):flags+="  SMOKE"
			if kill.get("noscope",false):flags+="  NS"
			rows[row_index].text="[color="+tint(int(kill.get("attacker_team",0)))+"]"+escape(shorten(str(kill.attacker),12))+"[/color]  [color=#a8bac8]"+escape(weapon_name(str(kill.weapon)).to_upper())+"[/color]  [color="+tint(int(kill.get("victim_team",0)))+"]"+escape(shorten(str(kill.victim),12))+"[/color]"+("\n[font_size=10][color=#a8bac8]"+flags.strip_edges()+"[/color][/font_size]" if not flags.is_empty() else "")
			panels[row_index].tooltip_text=str(kill.attacker)+" → "+str(kill.victim)+"\n"+str(kill.get("attacker_id",""))+" → "+str(kill.get("victim_id",""))+"\n"+flags
	last_state={"round":state.get("round"),"ct_score":state.get("ct_score"),"t_score":state.get("t_score"),"phase":phase.get("kind"),"kills":recent.size()}

func group_roster(container:VBoxContainer,buttons:Array[Button],teams:Array,selected:int) -> void:
	var signature:=str(teams)+str(buttons.map(func(button:Button):return button.get_instance_id()))
	if signature!=team_signature:
		team_signature=signature
		for heading in team_headers.values():heading.free()
		team_headers={};var position:=0
		for team in [3,2,0]:
			var members:Array=[]
			for index in range(teams.size()):
				if (int(teams[index]) if int(teams[index]) in [2,3] else 0)==team:members.append(index)
			if members.is_empty():continue
			var heading:=label(container,"CT SIDE" if team==3 else ("T SIDE" if team==2 else "SPECTATORS"),11,CT if team==3 else T)
			team_headers[team]=heading;container.move_child(heading,position);position+=1
			for index in members:container.move_child(buttons[index],position);position+=1
	for index in range(buttons.size()):buttons[index].set_pressed_no_signal(index==selected)
