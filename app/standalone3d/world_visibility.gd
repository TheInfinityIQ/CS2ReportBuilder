extends RefCounted

# Voxel/octant ordering follows the pinned VRF 20.1 reader (MIT;
# third_party/VRF_LICENSE.txt). No camera smoothing, geometry or shading changes.
const SUB1=[0,2,8,10,32,34,40,42]
const SUB2=[0,1,4,5,16,17,20,21]
const ALGORITHM=2
var data:Dictionary={}
var nodes:PackedByteArray
var regions:PackedByteArray
var masks:PackedByteArray
var rows:PackedByteArray
var targets:Array=[]
var enabled:=false
var current_key:=""
var shader_safety:Dictionary={}
var static_materials:Dictionary={}
var deformation_pattern:=RegEx.create_from_string("\\b(VERTEX|POSITION|MODELVIEW_MATRIX)\\b(?:\\.[xyzwrgba]+)?\\s*[-+*/]?=")
var always_bits:PackedByteArray
var shown_bits:PackedByteArray
var state:Dictionary={"available":false,"bound":0,"hidden_meshes":0,"hidden_lights":0,"updates":0,"update_ms":0.0,"failure":""}

static func read_for_map(asset:String,scene:String,fingerprint:String) -> Dictionary:
	var folder:String=asset.get_base_dir()
	var base:String=folder.get_base_dir().get_base_dir().path_join("visibility").path_join(folder.get_file())
	var selected:Variant=JSON.parse_string(FileAccess.get_file_as_string(base.path_join("active.json"))) if FileAccess.file_exists(base.path_join("active.json")) else null
	if not selected is Dictionary or selected.get("schema",0)!=2:return {}
	var relative:String=str(selected.get("manifest",""));var parts:PackedStringArray=relative.split("/")
	if parts.size()!=2 or parts[0].length()!=20 or not parts[0].is_valid_hex_number(false) or parts[1]!="manifest.json":return {}
	var output:Dictionary=read_cache(base.path_join(relative))
	if output.is_empty():return {}
	var manifest:Dictionary=output.manifest
	if manifest.get("source_fingerprint","")!=fingerprint or manifest.get("verified",{}).get("revision","")!=manifest.get("revision","") or selected.get("revision","")!=manifest.get("revision",""):return {}
	var file:=FileAccess.open(scene,FileAccess.READ)
	var identity:Dictionary=manifest.get("scene",{})
	# JSON numbers are floats; Dictionary equality is type-sensitive in Godot.
	# Compare the bounded scene identity fields as integers instead.
	if file==null or identity.get("name","")!=scene.get_file() or int(identity.get("bytes",0))!=file.get_length() or int(identity.get("modified",0))!=FileAccess.get_modified_time(scene):return {}
	var direct:String=folder.get_base_dir().get_base_dir().path_join("lighting").path_join(folder.get_file()).path_join("direct.json")
	if FileAccess.get_sha256(direct)!=manifest.get("light_sha256",""):return {}
	if FileAccess.get_sha256(folder.path_join("fidelity.json"))!=manifest.get("material_sha256",""):return {}
	return output

static func read_cache(path:String) -> Dictionary:
	if path.is_empty() or not FileAccess.file_exists(path):return {}
	var header:=FileAccess.open(path,FileAccess.READ)
	if header==null or header.get_length()>8*1024*1024:return {}
	var parsed:Variant=JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary or parsed.get("schema",0)!=2 or parsed.get("algorithm",0)!=ALGORITHM or parsed.get("clusters",0)!=4096:return {}
	if not parsed.get("objects") is Array or parsed.objects.is_empty() or parsed.objects.size()>50000 or parsed.get("row_bytes",0)!=(parsed.objects.size()+7)/8:return {}
	if not parsed.get("files") is Dictionary or parsed.files.size()!=5 or parsed.get("nodes",0)<1 or parsed.get("regions",0)<1 or parsed.get("masks",0)<1:return {}
	if not parsed.get("min") is Array or not parsed.get("max") is Array or parsed.min.size()!=3 or parsed.max.size()!=3:return {}
	if not parsed.get("probes") is Array or parsed.probes.is_empty() or parsed.probes.size()>1024:return {}
	var folder:String=path.get_base_dir();var output:Dictionary={"manifest":parsed}
	var sizes:Dictionary={"nodes.bin":int(parsed.nodes)*12,"regions.bin":int(parsed.regions)*8,"masks.bin":int(parsed.masks)*8,"object-visibility.bin":int(parsed.row_bytes)*int(parsed.clusters),"pvs.bin":512*(int(parsed.clusters)+2)}
	for name in sizes:
		var file:=FileAccess.open(folder.path_join(name),FileAccess.READ)
		if file==null or sizes[name]<=0 or file.get_length()!=sizes[name] or file.get_length()>32*1024*1024:return {}
		var bytes:PackedByteArray=file.get_buffer(file.get_length());var hash:=HashingContext.new();hash.start(HashingContext.HASH_SHA256);hash.update(bytes)
		if hash.finish().hex_encode()!=str(parsed.files.get(name,"")):return {}
		output[name]=bytes
	return output

func camera_clusters(point:Vector3) -> Array:
	var a:Array=data.get("min",[]);var b:Array=data.get("max",[])
	if a.size()!=3 or b.size()!=3:return []
	var low:=Vector3(a[0],a[1],a[2]);var high:=Vector3(b[0],b[1],b[2])
	if point.x<low.x or point.y<low.y or point.z<low.z or point.x>high.x or point.y>high.y or point.z>high.z:return []
	var index:int=0
	for level in range(32):
		if index<0 or index>=int(data.nodes):return []
		var offset:int=nodes.decode_u32(index*12+4)
		if nodes.decode_u32(index*12)==1:
			var count:int=nodes.decode_u32(index*12+8)
			var octants:Array=[]
			for subdivision in range(2):
				var middle:Vector3=(low+high)*.5;var octant:int=0
				for axis in range(3):
					if middle[axis]<point[axis]:octant|=1<<axis;low[axis]=middle[axis]
					else:high[axis]=middle[axis]
				octants.append(octant)
			var bit:int=SUB1[octants[0]]+SUB2[octants[1]];var clusters:Array=[]
			for region in range(offset,mini(offset+count,int(data.regions))):
				var cluster:int=regions.decode_u32(region*8);var mask:int=regions.decode_u32(region*8+4)
				if mask>=int(data.masks):return []
				if cluster<int(data.clusters) and (masks[mask*8+bit/8]&(1<<(bit%8)))!=0 and cluster not in clusters:clusters.append(cluster)
			clusters.sort();return clusters
		var middle:Vector3=(low+high)*.5;var octant:int=0
		for axis in range(3):
			if middle[axis]<point[axis]:octant|=1<<axis;low[axis]=middle[axis]
			else:high[axis]=middle[axis]
		index=offset+octant
	return []

func load_data(payload:Dictionary) -> bool:
	if payload.is_empty():return false
	data=payload.manifest;nodes=payload["nodes.bin"];regions=payload["regions.bin"];masks=payload["masks.bin"];rows=payload["object-visibility.bin"]
	# Cross-check our point queries against the existing C# reader, including
	# overlapping regions and unknown points. Failure leaves full drawing intact.
	for probe in data.get("probes",[]):
		if not probe is Dictionary or not probe.get("point") is Array or probe.point.size()!=3:return false
		var p:Array=probe.point;var clusters:Array=camera_clusters(Vector3(p[0],p[1],p[2]))
		if probe.pvs==null:
			if not clusters.is_empty():state.failure="Native visibility point-query mismatch";return false
			continue
		if clusters.is_empty():state.failure="Missing native visibility region";return false
		var expected:PackedByteArray=Marshalls.base64_to_raw(probe.pvs)
		if expected.size()!=512:return false
		for byte in range(512):
			var actual:int=0
			for cluster in clusters:actual|=payload["pvs.bin"][cluster*512+byte]
			if byte>=expected.size() or actual!=expected[byte]:state.failure="Native visibility row mismatch";return false
	return true

func configure(viewer:Node,payload:Dictionary) -> bool:
	restore();enabled=false
	targets.clear();shader_safety.clear();static_materials.clear();state.available=false
	if not load_data(payload):return false
	for name in data.get("opaque_materials",[]):static_materials[str(name)]=true
	for path in data.objects:
		var node:Node
		if str(path).begins_with("!light:"):
			var index:int=int(str(path).trim_prefix("!light:"))
			if index<viewer.source_direct.natives.size():node=viewer.source_direct.natives[index]
		else:node=viewer.map_scene.get_node_or_null(NodePath(str(path)))
		if node==null:state.failure="Visibility scene topology mismatch";targets.clear();return false
		if node is MeshInstance3D and node.is_visible_in_tree():targets.append({"node":node,"light":false,"shadow":node.cast_shadow,"shown":true,"always":not opaque_static(node)})
		elif node is Light3D and node.visible:targets.append({"node":node,"light":true,"shown":true})
		else:targets.append({})
	state.bound=targets.filter(func(v:Dictionary):return not v.is_empty()).size()
	state["cullable_meshes"]=targets.filter(func(v:Dictionary):return not v.is_empty() and not v.light and not v.get("always",false)).size()
	always_bits.resize(int(data.row_bytes));always_bits.fill(255)
	for index in range(targets.size()):
		if not targets[index].is_empty() and not targets[index].get("always",false):always_bits[index/8]&=255^(1<<(index%8))
	shown_bits.resize(int(data.row_bytes));shown_bits.fill(255)
	state.available=state.bound>0;enabled=state.available;return enabled

func opaque_static(mesh:MeshInstance3D) -> bool:
	# Source's free-space visibility is not a reliable boundary for translucent
	# ambient cards, water, screen-reading overlays or displaced/billboard meshes.
	# Keep these drawing in full; only static opaque world geometry is eligible.
	if mesh.mesh.get_blend_shape_count()>0 or mesh.mesh is PrimitiveMesh or mesh.custom_aabb.size!=Vector3.ZERO or mesh.extra_cull_margin>0:return false
	for surface in range(mesh.mesh.get_surface_count()):
		var material:Material=mesh.get_active_material(surface)
		if material==null or not static_materials.has(str(material.resource_name)):return false
		if material is BaseMaterial3D:
			if material.transparency!=BaseMaterial3D.TRANSPARENCY_DISABLED or material.billboard_mode!=BaseMaterial3D.BILLBOARD_DISABLED or material.shading_mode==BaseMaterial3D.SHADING_MODE_UNSHADED:return false
		elif material is ShaderMaterial:
			var id:int=material.shader.get_instance_id()
			if not shader_safety.has(id):
				var code:String=material.shader.code
				shader_safety[id]=not ("ALPHA" in code or "SCREEN_UV" in code or deformation_pattern.search(code)!=null or "unshaded" in code)
			if not shader_safety[id]:return false
		else:return false
	return true

func update(godot_position:Vector3) -> void:
	if not enabled:return
	var started:int=Time.get_ticks_usec()
	var point:=Vector3(godot_position.z,godot_position.x,godot_position.y)/.0254
	var clusters:Array=camera_clusters(point);var key:String=str(clusters)
	if current_key==key:return
	current_key=key;var hidden:int=int(state.hidden_meshes);var lights:int=int(state.hidden_lights);var changed_count:int=0
	var selected:PackedByteArray
	for cluster in clusters:
		var row:PackedByteArray=rows.slice(cluster*int(data.row_bytes),(cluster+1)*int(data.row_bytes))
		if selected.is_empty():selected=row
		else:
			for byte in range(selected.size()):selected[byte]|=row[byte]
	# Compare packed visibility bytes first. Usually only a handful of targets
	# change between neighbouring cells; do not walk 5,000 scene nodes per step.
	for byte in range(shown_bits.size()):
		var desired:int=255 if clusters.is_empty() else selected[byte]|always_bits[byte]
		var changed:int=shown_bits[byte]^desired
		if changed==0:continue
		shown_bits[byte]=desired
		for bit in range(8):
			if (changed&(1<<bit))==0:continue
			var index:int=byte*8+bit
			if index>=targets.size():continue
			var entry:Dictionary=targets[index]
			if entry.is_empty():continue
			var visible:bool=(desired&(1<<bit))!=0;entry.shown=visible;changed_count+=1
			if entry.light:lights+=-1 if visible else 1;entry.node.visible=visible
			else:
				hidden+=-1 if visible else 1
				if int(entry.shadow)==GeometryInstance3D.SHADOW_CASTING_SETTING_OFF:entry.node.visible=visible
				else:
					# Camera-hidden geometry can still cast visible shadows.
					entry.node.cast_shadow=int(entry.shadow) if visible else GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY
	state.hidden_meshes=hidden;state.hidden_lights=lights;state.updates+=1;state["changed_targets"]=changed_count;state.update_ms=(Time.get_ticks_usec()-started)/1000.0

func restore() -> void:
	for entry in targets:
		if entry.is_empty() or not is_instance_valid(entry.node):continue
		entry.node.visible=true
		if not entry.light:entry.node.cast_shadow=entry.shadow
		entry.shown=true
	shown_bits.fill(255)
	current_key="";state.hidden_meshes=0;state.hidden_lights=0
