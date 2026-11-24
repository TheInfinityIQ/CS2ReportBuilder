extends RefCounted

# Sample only the visible body skeleton. The imported player animations also
# contain many invisible weapon skeleton tracks; a locomotion blend must not
# evaluate those or let a mixer retain their last pose after seeking.
var bindings:Dictionary={}
var rest_positions:=PackedVector3Array()
var rest_rotations:Array[Quaternion]=[]
var rest_scales:=PackedVector3Array()
var rig_id:int=0

func reset() -> void:
	bindings.clear();rig_id=0

func bind(animator:AnimationPlayer,skeleton:Skeleton3D,clip:String) -> Dictionary:
	if rig_id!=skeleton.get_instance_id():
		reset();rig_id=skeleton.get_instance_id()
		rest_positions.clear();rest_rotations.clear();rest_scales.clear()
		for bone in range(skeleton.get_bone_count()):
			var rest:Transform3D=skeleton.get_bone_rest(bone)
			rest_positions.append(rest.origin);rest_rotations.append(rest.basis.get_rotation_quaternion());rest_scales.append(rest.basis.get_scale())
	if bindings.has(clip):return bindings[clip]
	var animation:Animation=animator.get_animation(clip)
	var tracks:=PackedInt32Array();tracks.resize(skeleton.get_bone_count()*3);tracks.fill(-1)
	var animation_root:Node=animator.get_node(animator.root_node)
	for track in range(animation.get_track_count()):
		var type:int=animation.track_get_type(track)
		if type not in [Animation.TYPE_POSITION_3D,Animation.TYPE_ROTATION_3D,Animation.TYPE_SCALE_3D]:continue
		var path:NodePath=animation.track_get_path(track)
		if path.get_subname_count()!=1 or animation_root.get_node_or_null(NodePath(path.get_concatenated_names()))!=skeleton:continue
		var bone:int=skeleton.find_bone(str(path.get_subname(0)))
		if bone>=0:tracks[bone*3+(0 if type==Animation.TYPE_POSITION_3D else (1 if type==Animation.TYPE_ROTATION_3D else 2))]=track
	var result:Dictionary={"animation":animation,"tracks":tracks};bindings[clip]=result;return result

func apply(animator:AnimationPlayer,skeleton:Skeleton3D,entries:Array) -> void:
	if entries.is_empty():return
	# Positive normalized weights, a shared recorded gait phase and fixed clip
	# order make this independent of frame history, pause and seek direction.
	var positions:=PackedVector3Array();var rotations:Array[Quaternion]=[];var scales:=PackedVector3Array()
	var total:float=0
	for entry in entries:
		var binding:Dictionary=bind(animator,skeleton,entry.clip)
		var animation:Animation=binding.animation;var tracks:PackedInt32Array=binding.tracks
		var time:float=float(entry.time);var weight:float=float(entry.weight)
		if weight<=0:continue
		var fraction:float=weight/(total+weight)
		for bone in range(skeleton.get_bone_count()):
			var p:int=tracks[bone*3];var r:int=tracks[bone*3+1];var s:int=tracks[bone*3+2]
			var position:Vector3=animation.position_track_interpolate(p,time) if p>=0 else rest_positions[bone]
			var rotation:Quaternion=animation.rotation_track_interpolate(r,time).normalized() if r>=0 else rest_rotations[bone]
			var scale:Vector3=animation.scale_track_interpolate(s,time) if s>=0 else rest_scales[bone]
			if total==0:positions.append(position);rotations.append(rotation);scales.append(scale)
			else:
				positions[bone]=positions[bone].lerp(position,fraction)
				rotations[bone]=rotations[bone].slerp(rotation,fraction).normalized()
				scales[bone]=scales[bone].lerp(scale,fraction)
		total+=weight
	if total<=0:return
	for bone in range(skeleton.get_bone_count()):
		skeleton.set_bone_pose_position(bone,positions[bone]);skeleton.set_bone_pose_rotation(bone,rotations[bone]);skeleton.set_bone_pose_scale(bone,scales[bone])
