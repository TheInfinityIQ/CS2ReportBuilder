extends RefCounted

const Layered=preload("res://source_layered.gdshader")
const Water=preload("res://source_water.gdshader")
var definitions:Dictionary={}
var geometry:Dictionary={}
var root:Node
var animated:Array[ShaderMaterial]=[]
var failures:Array=[]
var applied:Dictionary={"layered":0,"decal":0,"water":0}
var detail_gaps:Array=[]

func configure(data:Dictionary) -> void:
	definitions=data.get("materials",{})
	geometry=data.get("geometry_meshes",{})

func _color(values:Array) -> Color:
	return Color(float(values[0]),float(values[1]),float(values[2]),1)

func apply_mesh(node:MeshInstance3D) -> void:
	var originals:Array=[]
	for surface in range(node.mesh.get_surface_count()):originals.append(node.mesh.surface_get_material(surface))
	var replacement:Mesh=geometry.get(str(root.get_path_to(node))) if root!=null else null
	if replacement!=null:
		var a:=node.mesh.get_aabb()
		var b:=replacement.get_aabb()
		if not a.position.is_equal_approx(b.position) or not a.size.is_equal_approx(b.size) or replacement.get_surface_count()!=originals.size():
			failures.append("Source blend geometry boundary mismatch: "+str(node.name))
		else:
			node.mesh=replacement
			for surface in range(originals.size()):node.set_surface_override_material(surface,originals[surface])
	for surface in range(node.mesh.get_surface_count()):
		var original:Material=originals[surface]
		if not original is StandardMaterial3D or not definitions.has(original.resource_name):continue
		var definition:Dictionary=definitions[original.resource_name]
		var family:String=definition.family
		if family=="layered":
			if not node.mesh is ArrayMesh or (node.mesh.surface_get_format(surface)&Mesh.ARRAY_FORMAT_COLOR)==0:
				failures.append("Source blend attributes not bound: "+str(node.name))
				continue
		if family=="decal":
			var source:Dictionary=definition.source
			if int(source.get("IntParams",{}).get("F_BLEND_MODE",0))==3:
				var overlay:=ShaderMaterial.new();overlay.shader=preload("res://source_overlay.gdshader")
				overlay.resource_name=original.resource_name
				overlay.set_shader_parameter("color_texture",original.albedo_texture)
				var grid:Array=source.get("VectorParams",{}).get("g_vAnimationGrid",[1,1])
				overlay.set_shader_parameter("animation_grid",Vector2(grid[0],grid[1]))
				overlay.set_shader_parameter("frame_count",float(source.get("IntParams",{}).get("g_nNumAnimationCells",1)))
				overlay.set_shader_parameter("frame_seconds",source.get("FloatParams",{}).get("g_flAnimationTimePerFrame",.05))
				overlay.set_shader_parameter("opacity",source.get("FloatParams",{}).get("g_flOpacityScale",1))
				var bright:=ShaderMaterial.new();bright.shader=preload("res://source_overlay_add.gdshader")
				for parameter in ["color_texture","animation_grid","frame_count","frame_seconds","opacity"]:
					bright.set_shader_parameter(parameter,overlay.get_shader_parameter(parameter))
				overlay.next_pass=bright;animated.append(bright)
				node.set_surface_override_material(surface,overlay);animated.append(overlay)
				node.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				applied.decal+=1
				continue
			var decal:=original.duplicate() as StandardMaterial3D
			decal.transparency=BaseMaterial3D.TRANSPARENCY_ALPHA
			decal.cull_mode=BaseMaterial3D.CULL_DISABLED
			decal.vertex_color_use_as_albedo=false
			node.set_surface_override_material(surface,decal)
			node.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			applied.decal+=1
			continue
		var source:Dictionary=definition.source
		var vectors:Dictionary=source.get("VectorParams",{})
		var floats:Dictionary=source.get("FloatParams",{})
		var textures:Dictionary=definition.get("loaded_textures",{})
		var material:=ShaderMaterial.new()
		material.set_shader_parameter("reflection_count",0)
		material.resource_name=original.resource_name
		if family=="water":
			material.shader=Water
			material.set_shader_parameter("waves",textures.get("g_tWavesNormalHeight"))
			material.set_shader_parameter("fog_color",_color(vectors.get("g_vWaterFogColor",[.3,.4,.3])))
			material.set_shader_parameter("decay_color",_color(vectors.get("g_vWaterDecayColor",[.4,.7,.7])))
			material.set_shader_parameter("wave_speed",floats.get("g_flWavesSpeed",.8))
			material.set_shader_parameter("wave_scale",float(vectors.get("g_vWaveScale",[15,15])[0])*.0254)
			material.set_shader_parameter("depth_scale",float(floats.get("g_flWaterMaxDepth",100))*.0254)
			animated.append(material)
			node.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		else:
			material.shader=Layered
			if not str(definition.get("detail_gap","")).is_empty() and str(definition.source.get("Name","")) not in detail_gaps:
				detail_gaps.append(str(definition.source.get("Name","")))
			material.set_shader_parameter("color1",original.albedo_texture)
			material.set_shader_parameter("color2",textures.get("g_tLayer2Color"))
			material.set_shader_parameter("normal1",textures.get("g_tLayer1NormalRoughness"))
			material.set_shader_parameter("normal2",textures.get("g_tLayer2NormalRoughness"))
			material.set_shader_parameter("modulation",textures.get("g_tBlendModulation"))
			material.set_shader_parameter("has_normals",textures.has("g_tLayer1NormalRoughness") and textures.has("g_tLayer2NormalRoughness"))
			material.set_shader_parameter("tint",original.albedo_color)
			material.set_shader_parameter("tint1",_color(vectors.get("g_vLayer1Tint",[1,1,1])))
			material.set_shader_parameter("tint2",_color(vectors.get("g_vLayer2Tint",[1,1,1])))
			material.set_shader_parameter("border_tint",_color(vectors.get("g_vLayerBorderTint",[1,1,1])))
			material.set_shader_parameter("fancy",source.get("IntParams",{}).get("F_FANCY_BLENDING",0))
			material.set_shader_parameter("softness",floats.get("g_flBlendSoftness",.1))
			material.set_shader_parameter("border_strength",floats.get("g_flLayerBorderStrength",0))
			material.set_shader_parameter("border_softness",floats.get("g_flLayerBorderSoftness",.5))
			material.set_shader_parameter("border_offset",floats.get("g_flLayerBorderOffset",0))
			material.set_shader_parameter("metalness",floats.get("g_flMetalness",0))
			var flags:Dictionary=source.get("IntParams",{})
			material.set_shader_parameter("has_detail",int(flags.get("F_DETAILTEXTURE",0))==1 and int(flags.get("F_ADDBUMPMAPS",0))==0 and textures.has("g_tLayer1Detail"))
			material.set_shader_parameter("detail1",textures.get("g_tLayer1Detail"))
			var detail_scale:Array=vectors.get("g_vLayer1DetailScale",[1,1])
			var detail_tint:Array=vectors.get("g_vLayer1DetailTintAndBlend",[1,1,1,0])
			material.set_shader_parameter("detail_scale",Vector2(detail_scale[0],detail_scale[1]))
			material.set_shader_parameter("detail_tint_blend",Vector4(detail_tint[0],detail_tint[1],detail_tint[2],detail_tint[3]))
			material.set_shader_parameter("has_material_ao",textures.has("g_tLayer1AmbientOcclusion") and textures.has("g_tLayer2AmbientOcclusion"))
			material.set_shader_parameter("material_ao1",textures.get("g_tLayer1AmbientOcclusion"))
			material.set_shader_parameter("material_ao2",textures.get("g_tLayer2AmbientOcclusion"))
			material.set_shader_parameter("texture_transforms",int(flags.get("F_TEXTURETRANSFORMS",0))==1)
			material.set_shader_parameter("specular_enabled",int(flags.get("F_SPECULAR_DIRECT",0))==1 or int(flags.get("F_SPECULAR_INDIRECT",0))==1)
			for layer in [1,2]:
				var v:Array=vectors.get("g_vLayer"+str(layer)+"TexCoordScale",[1,1])
				var o:Array=vectors.get("g_vLayer"+str(layer)+"TexCoordOffset",[0,0])
				material.set_shader_parameter("scale"+str(layer),Vector2(v[0],v[1]))
				material.set_shader_parameter("offset"+str(layer),Vector2(o[0],o[1]))
				var ns:Array=vectors.get("g_vLayer"+str(layer)+"NormalTexCoordScale",[1,1])
				var no:Array=vectors.get("g_vLayer"+str(layer)+"NormalTexCoordOffset",[0,0])
				material.set_shader_parameter("normal_scale"+str(layer),Vector2(ns[0],ns[1]))
				material.set_shader_parameter("normal_offset"+str(layer),Vector2(no[0],no[1]))
				var center:Array=vectors.get("g_vLayer"+str(layer)+"TexCoordCenter",[.5,.5])
				var normal_center:Array=vectors.get("g_vLayer"+str(layer)+"NormalTexCoordCenter",[.5,.5])
				material.set_shader_parameter("center"+str(layer),Vector2(center[0],center[1]))
				material.set_shader_parameter("normal_center"+str(layer),Vector2(normal_center[0],normal_center[1]))
				material.set_shader_parameter("rotation"+str(layer),floats.get("g_flLayer"+str(layer)+"TexCoordRotation",0))
				material.set_shader_parameter("normal_rotation"+str(layer),floats.get("g_flLayer"+str(layer)+"NormalTexCoordRotation",0))
			for pair in [["scale",[1,1]],["offset",[0,0]],["center",[.5,.5]]]:
				var v:Array=vectors.get("g_vBlendModulateTexCoord"+str(pair[0]).capitalize(),pair[1])
				material.set_shader_parameter("modulation_"+str(pair[0]),Vector2(v[0],v[1]))
			material.set_shader_parameter("modulation_rotation",floats.get("g_flBlendModulateTexCoordRotation",0))
		node.set_surface_override_material(surface,material)
		applied[family]+=1

func update_tick(seconds:float) -> void:
	for material in animated:material.set_shader_parameter("demo_time",seconds)
