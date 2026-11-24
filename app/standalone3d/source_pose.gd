extends RefCounted

const UNIT:=.0254
static var clips:Dictionary={}
static var models:Dictionary={}
var calibrations:Dictionary={}
var application_bindings:Dictionary={}
var failures:Array=[]

func model(path:String) -> Dictionary:
	if not models.has(path):
		var data:Variant=JSON.parse_string(FileAccess.get_file_as_string(path))
		models[path]=data if data is Dictionary else {}
	return models[path]

func clip(path:String) -> Dictionary:
	if not clips.has(path):
		var data:Variant=JSON.parse_string(FileAccess.get_file_as_string(path))
		if not data is Dictionary:return {}
		for variant in data.get("variants",[]):
			var bytes:=FileAccess.get_file_as_bytes(str(variant.data))
			if bytes.size()!=int(variant.frames)*variant.bones.size()*32:
				failures.append("Authored pose size mismatch: "+path);return {}
			variant["samples"]=bytes.to_float32_array()
			variant["evaluation_order"]=_evaluation_order(variant)
		clips[path]=data
	return clips[path]

func variant(path:String,kind:String) -> Dictionary:
	var data:=clip(path)
	for item in data.get("variants",[]):
		if kind=="arms" and "/characters/viewmodel" in str(item.skeleton):return item
		if kind=="body" and "/characters/worldmodel" in str(item.skeleton):return item
		if kind=="weapon" and "/weapons/" in str(item.skeleton):return item
	return {}

func _globals(locals:Dictionary,parents:Dictionary) -> Dictionary:
	var result:Dictionary={}
	var pending:Array=locals.keys()
	for iteration in range(pending.size()+1):
		var remaining:Array=[]
		for name in pending:
			var parent=parents.get(name)
			if parent==null or str(parent)=="":result[name]=locals[name]
			elif result.has(str(parent)):result[name]=result[str(parent)]*locals[name]
			else:remaining.append(name)
		if remaining.is_empty():return result
		if remaining.size()==pending.size():
			failures.append("Authored skeleton has unresolved parents.");return {}
		pending=remaining
	return result

func model_globals(data:Dictionary) -> Dictionary:
	var locals:Dictionary={};var parents:Dictionary={}
	for bone in data.get("bones",[]):
		var p:Array=bone.position;var q:Array=bone.rotation
		locals[str(bone.name)]=Transform3D(Basis(Quaternion(q[0],q[1],q[2],q[3])),Vector3(p[0],p[1],p[2])*UNIT)
		parents[str(bone.name)]=bone.parent
	return _globals(locals,parents)

func _evaluation_order(data:Dictionary) -> Array:
	var ordered:Array=[];var available:Dictionary={};var pending:Array=[]
	for index in range(data.bones.size()):pending.append(index)
	for iteration in range(pending.size()+1):
		var remaining:Array=[]
		for index in pending:
			var parent:Variant=data.hierarchy[index].parent
			if parent==null or str(parent)=="" or available.has(str(parent)):
				ordered.append(index);available[str(data.bones[index])]=true
			else:remaining.append(index)
		if remaining.is_empty():return ordered
		if remaining.size()==pending.size():return []
		pending=remaining
	return []

func sample(data:Dictionary,seconds:float,loop:bool=false) -> Dictionary:
	if data.is_empty():return {}
	var count:int=int(data.frames)
	var frame:float=maxf(0,seconds)*float(data.fps)
	frame=fmod(frame,maxi(1,count-1)) if loop else minf(frame,count-1)
	var first:int=int(floor(frame));var second:int=mini(first+1,count-1)
	var fraction:float=frame-first
	var values:PackedFloat32Array=data.samples
	var result:Dictionary={}
	# Compile hierarchy order once per immutable clip, not for every sample of
	# each directional blend on all ten actors. Arithmetic and sampling stay exact.
	if not data.has("evaluation_order"):data["evaluation_order"]=_evaluation_order(data)
	if data.evaluation_order.size()!=data.bones.size():
		failures.append("Authored skeleton has unresolved parents.");return {}
	for index in data.evaluation_order:
		var a:int=(first*data.bones.size()+index)*8;var b:int=(second*data.bones.size()+index)*8
		var position:=Vector3(values[a],values[a+1],values[a+2]).lerp(Vector3(values[b],values[b+1],values[b+2]),fraction)*UNIT
		var rotation:=Quaternion(values[a+3],values[a+4],values[a+5],values[a+6]).normalized().slerp(Quaternion(values[b+3],values[b+4],values[b+5],values[b+6]).normalized(),fraction)
		var scale:float=lerpf(values[a+7],values[b+7],fraction)
		var local:=Transform3D(Basis(rotation).scaled(Vector3.ONE*scale),position)
		var parent:Variant=data.hierarchy[index].parent
		result[str(data.bones[index])]=local if parent==null or str(parent)=="" else result[str(parent)]*local
	return result

func calibration(skeleton:Skeleton3D,metadata:Dictionary) -> Transform3D:
	var identity:int=skeleton.get_instance_id()
	if calibrations.has(identity):return calibrations[identity]
	var source:=model_globals(metadata)
	var conversion:=Transform3D.IDENTITY
	var found:=false
	for index in range(skeleton.get_bone_count()):
		var name:String=str(skeleton.get_bone_name(index))
		if source.has(name):
			conversion=skeleton.get_bone_global_rest(index)*source[name].affine_inverse();found=true;break
	if not found:failures.append("Stock rig has no source skeleton correspondence.")
	for index in range(skeleton.get_bone_count()):
		var name:String=str(skeleton.get_bone_name(index))
		if not source.has(name):continue
		var expected:Transform3D=conversion*source[name]
		if expected.origin.distance_to(skeleton.get_bone_global_rest(index).origin)>.003:
			failures.append("Source rest calibration mismatch: "+name);break
	calibrations[identity]=conversion
	return conversion

func apply_additive(skeleton:Skeleton3D,data:Dictionary,seconds:float,loop:bool=false,upper_only:bool=false) -> void:
	# Additive Source clips encode zero as neutral scale, not a hidden bone.
	# Keep their local deltas out of the absolute global-pose conversion path.
	if data.is_empty():return
	var count:int=int(data.frames);var frame:float=maxf(0,seconds)*float(data.fps)
	frame=fmod(frame,maxi(1,count-1)) if loop else minf(frame,count-1)
	var first:int=int(floor(frame));var second:int=mini(first+1,count-1);var blend:float=frame-first
	var values:PackedFloat32Array=data.samples
	for index in range(data.bones.size()):
		var bone:int=skeleton.find_bone(str(data.bones[index]));if bone<0:continue
		if upper_only:
			var parent:int=bone;var upper:bool=false
			while parent>=0:
				if "spine" in str(skeleton.get_bone_name(parent)).to_lower():upper=true;break
				parent=skeleton.get_bone_parent(parent)
			if not upper:continue
		var a:int=(first*data.bones.size()+index)*8;var b:int=(second*data.bones.size()+index)*8
		var offset:=Vector3(values[a],values[a+1],values[a+2]).lerp(Vector3(values[b],values[b+1],values[b+2]),blend)*UNIT
		var rotation:=Quaternion(values[a+3],values[a+4],values[a+5],values[a+6]).normalized().slerp(Quaternion(values[b+3],values[b+4],values[b+5],values[b+6]).normalized(),blend)
		var scale:float=lerpf(values[a+7],values[b+7],blend)
		skeleton.set_bone_pose_position(bone,skeleton.get_bone_pose_position(bone)+offset)
		skeleton.set_bone_pose_rotation(bone,(skeleton.get_bone_pose_rotation(bone)*rotation).normalized())
		skeleton.set_bone_pose_scale(bone,skeleton.get_bone_pose_scale(bone)*(1.0+scale))

func apply(skeleton:Skeleton3D,metadata:Dictionary,pose:Dictionary) -> Transform3D:
	var conversion:=calibration(skeleton,metadata)
	var identity:int=skeleton.get_instance_id()
	if not application_bindings.has(identity):
		for old in application_bindings.keys():
			if application_bindings[old].owner.get_ref()==null:application_bindings.erase(old)
		var names:PackedStringArray=[];var parents:PackedInt32Array=[];var rest:Array[Transform3D]=[]
		for index in range(skeleton.get_bone_count()):
			names.append(str(skeleton.get_bone_name(index)));parents.append(skeleton.get_bone_parent(index));rest.append(skeleton.get_bone_global_rest(index))
		application_bindings[identity]={"owner":weakref(skeleton),"names":names,"parents":parents,"rest":rest}
	var binding:Dictionary=application_bindings[identity]
	var desired:Dictionary={}
	for index in range(binding.names.size()):
		var name:String=binding.names[index]
		if pose.has(name):desired[index]=conversion*pose[name]
		else:skeleton.reset_bone_pose(index)
	for index in desired:
		var parent:int=binding.parents[index]
		var transform:Transform3D=desired[index]
		if parent>=0:
			var parent_transform:Transform3D=desired.get(parent,binding.rest[parent])
			if absf(parent_transform.basis.determinant())>.000001:transform=parent_transform.affine_inverse()*transform
		skeleton.set_bone_pose_position(index,transform.origin)
		var scale:Vector3=transform.basis.get_scale()
		# Some authored weapon clips hide magazine/accessory bones with zero
		# scale. That is valid visibility data, not a basis to decompose.
		if absf(transform.basis.determinant())<.00000001:
			skeleton.set_bone_pose_rotation(index,Quaternion.IDENTITY)
			skeleton.set_bone_pose_scale(index,Vector3.ZERO)
		else:
			skeleton.set_bone_pose_rotation(index,transform.basis.get_rotation_quaternion().normalized())
			skeleton.set_bone_pose_scale(index,scale)
	return conversion
