using System.Text.Json;
using System.Numerics;
using SteamDatabase.ValvePak;
using ValveResourceFormat;
using ValveResourceFormat.ResourceTypes;
using ValveResourceFormat.Serialization.KeyValues;
using ValveKeyValue;

// Read-only lighting companion. Reuses the pinned reader, never changes maps.
if(args.Length<3)throw new ArgumentException("Expected map VPK, map name, private output directory.");
var map=args[1];
if(!System.Text.RegularExpressions.Regex.IsMatch(map,@"^de_[a-z0-9_]+$"))throw new ArgumentException("Invalid map name");
var output=Path.GetFullPath(args[2]);Directory.CreateDirectory(output);
using var package=new Package();package.Read(args[0]);
Resource Load(string path) {
    var entry=package.FindEntry(path)??throw new FileNotFoundException(path);
    if(entry.TotalLength>192*1024*1024)throw new InvalidDataException("Lighting resource exceeds bounds");
    package.ReadEntry(entry,out var bytes);
    var resource=new Resource();resource.Read(new MemoryStream(bytes));return resource;
}
float[] V(Vector3 v)=>[v.X,v.Y,v.Z];
if(args.Length>5 && args[5]=="uv_channels") {UvContracts.Export(args[4],map,output,Load);return;}
using var entities=Load($"maps/{map}/entities/default_ents.vents_c");
if(args.Length>5 && args[5]=="environment") {
    var environment=((EntityLump)entities.DataBlock!).GetEntities().Where(e=> {
        var kind=e.GetStringProperty("classname")??"";
        return kind.Contains("tonemap") || kind.Contains("post") || kind.Contains("fog") || kind is "light_environment" or "env_sky";
    }).Select(e=>e.Children.ToDictionary(p=>p.Key,p=>p.Value.ToString())).ToArray();
    File.WriteAllText(Path.Combine(output,"environment.json"),JsonSerializer.Serialize(environment));
    var profiles=new List<object>();
    using var shared=new Package();if(args.Length>6)shared.Read(args[6]);
    foreach(var entity in ((EntityLump)entities.DataBlock!).GetEntities()) {
        if(entity.GetStringProperty("classname")!="post_processing_volume" || entity.GetBooleanProperty("startdisabled"))continue;
        var profilePath=entity.GetStringProperty("postprocessing");if(string.IsNullOrEmpty(profilePath))continue;
        var compiled=profilePath+"_c";var owner=package;var entry=package.FindEntry(compiled);
        if(entry==null && args.Length>6){owner=shared;entry=shared.FindEntry(compiled);}
        if(entry==null)continue;
        if(entry.TotalLength>4*1024*1024)throw new InvalidDataException("Post-processing profile exceeds bounds");
        owner.ReadEntry(entry,out var bytes);using var profile=new Resource();profile.Read(new MemoryStream(bytes));
        var post=(PostProcessing)profile.DataBlock!;var tone=post.GetTonemapParams();
        var index=profiles.Count;var dimension=post.GetColorCorrectionLUTDimension();var lut=post.GetColorCorrectionLUT();
        if(dimension>0 && dimension<=64 && lut.Length==dimension*dimension*dimension*4)File.WriteAllBytes(Path.Combine(output,$"post-{index}.rgba"),lut);
        profiles.Add(new{resource=profilePath,master=entity.GetBooleanProperty("master"),min_exposure=entity.GetFloatProperty("minexposure",1),max_exposure=entity.GetFloatProperty("maxexposure",1),
            exposure_enabled=entity.GetBooleanProperty("enableexposure"),tone=tone?.Children.ToDictionary(p=>p.Key,p=>p.Value.ToString()),
            color_correction=post.HasColorCorrection(),lut_dimension=dimension,lut=$"post-{index}.rgba"});
    }
    File.WriteAllText(Path.Combine(output,"postprocessing.json"),JsonSerializer.Serialize(profiles));
    Console.WriteLine(JsonSerializer.Serialize(new{entities=environment.Length}));return;
}
var volumes=new List<object>();
foreach(var entity in ((EntityLump)entities.DataBlock!).GetEntities()) {
    var kind=entity.GetStringProperty("classname")??"";
    if(kind is not ("env_combined_light_probe_volume" or "env_light_probe_volume"))continue;
    var origin=entity.GetVector3Property("origin",Vector3.Zero);
    var angles=entity.GetVector3Property("angles",Vector3.Zero)*MathF.PI/180;
    var scales=entity.GetVector3Property("scales",Vector3.One);
    var mins=entity.GetVector3Property("box_mins",Vector3.Zero);var maxs=entity.GetVector3Property("box_maxs",Vector3.Zero);
    var extent=maxs-mins;
    if(extent.X<=0 || extent.Y<=0 || extent.Z<=0)throw new InvalidDataException("Degenerate probe bounds");
    var transform=Matrix4x4.CreateScale(scales)*Matrix4x4.CreateRotationX(angles.Z)*Matrix4x4.CreateRotationY(angles.X)*Matrix4x4.CreateRotationZ(angles.Y)*Matrix4x4.CreateTranslation(origin);
    if(!Matrix4x4.Invert(transform,out var inverse))throw new InvalidDataException("Singular probe transform");
    var normalized=inverse*Matrix4x4.CreateTranslation(-mins)*Matrix4x4.CreateScale(Vector3.One/(maxs-mins));
    volumes.Add(new {origin=V(entity.GetVector3Property("origin",Vector3.Zero)),
        angles=V(entity.GetVector3Property("angles",Vector3.Zero)),
        scales=V(entity.GetVector3Property("scales",Vector3.One)),
        mins=V(entity.GetVector3Property("box_mins",Vector3.Zero)),maxs=V(entity.GetVector3Property("box_maxs",Vector3.Zero)),
        fade=V(entity.GetVector3Property("edge_fade_dists",Vector3.Zero)),
        size=new[]{entity.GetInt32Property("light_probe_size_x"),entity.GetInt32Property("light_probe_size_y"),entity.GetInt32Property("light_probe_size_z")},
        offset=new[]{entity.GetInt32Property("light_probe_atlas_x"),entity.GetInt32Property("light_probe_atlas_y"),entity.GetInt32Property("light_probe_atlas_z")},
        priority=entity.GetInt32Property("indoor_outdoor_level"),
        cube_index=entity.GetInt32Property("array_index"),cube_texture=entity.GetStringProperty("cubemaptexture"),
        extent=V(extent),cube_center=V(Vector3.Transform(origin,normalized)),
        texture=entity.GetStringProperty("lightprobetexture"),
        disabled=entity.GetBooleanProperty("startdisabled"),
        world_to_local=new[]{normalized.M11,normalized.M21,normalized.M31,normalized.M41,normalized.M12,normalized.M22,normalized.M32,normalized.M42,normalized.M13,normalized.M23,normalized.M33,normalized.M43}});
}
if(args.Length>5 && args[5]=="reflections") {
    using var cubeResource=Load($"maps/{map}/cubemaps/env_cubemap_array.vtex_c");var cube=(Texture)cubeResource.DataBlock!;
    if(cube.Format.ToString()!="BC6H" || cube.Width!=cube.Height || cube.Width>512 || cube.Depth>320 || cube.NumMipLevels<1)throw new InvalidDataException("Unsupported reflection atlas layout");
    var levels=new List<object>();
    using(var file=File.Create(Path.Combine(output,"radiance.blocks"))) {
        for(uint mip=0;mip<cube.NumMipLevels;mip++) {
            var raw=new byte[cube.CalculateBufferSizeForMipLevel(mip)];cube.ReadTextureMipLevel(raw,mip);
            levels.Add(new{level=mip,width=Math.Max(1,cube.Width>>((int)mip)),height=Math.Max(1,cube.Height>>((int)mip)),offset=file.Position,bytes=raw.Length});file.Write(raw);
        }
    }
    using var input=File.OpenRead(Path.Combine(output,"radiance.blocks"));
    var receipt=new{schema=1,map,source_fingerprint=args[3],width=cube.Width,height=cube.Height,cubes=cube.Depth,format="BC6H_UFLOAT",levels,bytes=input.Length,sha256=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(input)).ToLowerInvariant(),volumes};
    File.WriteAllText(Path.Combine(output,"reflections.json"),JsonSerializer.Serialize(receipt));
    Console.WriteLine(JsonSerializer.Serialize(new{cubes=cube.Depth,bytes=input.Length}));return;
}
if(args.Length>5 && args[5]=="direct") {
    var textures=new Dictionary<string,object>();
    foreach(var name in new[]{"direct_light_shadows","env_light_probe_volume_atlas_dlshd"}) {
        using var resource=Load($"maps/{map}/lightmaps/{name}.vtex_c");var tex=(Texture)resource.DataBlock!;
        var bytes=new byte[tex.CalculateBufferSizeForMipLevel(0)];tex.ReadTextureMipLevel(bytes,0);
        if(bytes.Length>64*1024*1024)throw new InvalidDataException("Direct shadow atlas exceeds bounds");
        File.WriteAllBytes(Path.Combine(output,name+".blocks"),bytes);
        textures[name]=new{width=tex.Width,height=tex.Height,depth=tex.Depth,format=tex.Format.ToString(),bytes=bytes.Length,sha256=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes)).ToLowerInvariant()};
    }
    var lights=new List<object>();var sunChannel=-1;
    foreach(var entity in ((EntityLump)entities.DataBlock!).GetEntities()) {
        var kind=entity.GetStringProperty("classname")??"";
        if(kind=="light_environment") {sunChannel=entity.ContainsKey("bakedshadowindex")?entity.GetInt32Property("bakedshadowindex"):-1;continue;}
        if(kind is not ("light_omni2" or "light_barn" or "light_spot"))continue;
        if(entity.GetInt32Property("directlight")!=1 || (entity.ContainsKey("enabled") && !entity.GetBooleanProperty("enabled")))continue;
        lights.Add(new{kind,origin=V(entity.GetVector3Property("origin",Vector3.Zero)),angles=V(entity.GetVector3Property("angles",Vector3.Zero)),color=V(entity.GetColor32Property("color")),
            lumens=entity.GetFloatProperty("brightness_lumens"),range=entity.GetFloatProperty("range"),shape=entity.GetInt32Property("shape"),size=V(entity.GetVector3Property("size_params",Vector3.Zero)),shadow=entity.GetInt32Property("castshadows"),baked_channel=entity.GetInt32Property("bakedshadowindex")});
    }
    File.WriteAllText(Path.Combine(output,"direct.json"),JsonSerializer.Serialize(new{schema=1,map,source_fingerprint=args[3],sun_channel=sunChannel,textures,lights}));
    Console.WriteLine(JsonSerializer.Serialize(new{lights=lights.Count,sun_channel=sunChannel}));return;
}
var path=$"maps/{map}/lightmaps/env_light_probe_volume_atlas.vtex_c";
using var atlas=Load(path);var texture=(Texture)atlas.DataBlock!;
if(texture.Depth%6!=0 || texture.Width*texture.Height*(long)texture.Depth>200_000_000)throw new InvalidDataException("Unexpected ambient cube atlas");
if(texture.Format.ToString()!="BC6H")throw new InvalidDataException("Unsupported HDR probe format: "+texture.Format);
var buffer=new byte[texture.CalculateBufferSizeForMipLevel(0)];
texture.ReadTextureMipLevel(buffer,0);
File.WriteAllBytes(Path.Combine(output,"atlas.bc6h"),buffer);
var maps=new Dictionary<string,object>();
foreach(var name in new[]{"irradiance","directional_irradiance"}) {
    using var lightResource=Load($"maps/{map}/lightmaps/{name}.vtex_c");
    var light=(Texture)lightResource.DataBlock!;
    if(light.Depth!=1 || light.Width>8192 || light.Height>8192)throw new InvalidDataException("Unsupported static lightmap layout");
    var raw=new byte[light.CalculateBufferSizeForMipLevel(0)];light.ReadTextureMipLevel(raw,0);
    File.WriteAllBytes(Path.Combine(output,name+".blocks"),raw);
    maps[name]=new{width=light.Width,height=light.Height,format=light.Format.ToString(),bytes=raw.Length,sha256=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(raw)).ToLowerInvariant()};
}
using var worldResource=Load($"maps/{map}/world.vwrld_c");
var world=(World)worldResource.DataBlock!;var info=world.GetWorldLightingInfo()!;
var eligibility=new Dictionary<string,bool[]>();
string? witnessPath=null;string? witnessMesh=null;
if(args.Length>4) {
    using var reader=new BinaryReader(File.OpenRead(args[4]));
    if(reader.ReadUInt32()!=0x46546c67)throw new InvalidDataException("Not a GLB");
    reader.ReadUInt32();reader.ReadUInt32();var length=reader.ReadInt32();reader.ReadUInt32();
    if(length<1 || length>64*1024*1024)throw new InvalidDataException("GLB metadata exceeds bounds");
    using var gltf=JsonDocument.Parse(reader.ReadBytes(length));
    var gltfMeshes=gltf.RootElement.GetProperty("meshes").EnumerateArray().Select(x=>(Name:x.GetProperty("name").GetString()!,Count:x.GetProperty("primitives").GetArrayLength())).ToArray();
    string BaseName(string name) {
        var split=name.IndexOf(".meshset_");if(split<0)split=name.LastIndexOf("_fragment");
        return split<0?name:name[..split];
    }
    var names=gltfMeshes.Select(x=>BaseName(x.Name)).Distinct();
    foreach(var name in names) {
        var modelPath=$"maps/{map}/worldnodes/{name}.vmdl_c";
        if(package.FindEntry(modelPath)==null)continue;
        using var modelResource=Load(modelPath);var model=(Model)modelResource.DataBlock!;
        var index=0;
        void Inspect(Mesh mesh) {
            foreach(var sceneObject in mesh.Data.GetArray("m_sceneObjects")) {
                eligibility[name+".meshset_"+index++]=sceneObject.GetArray("m_drawCalls").Select(Mesh.HasBakedLightingFromLightMap).ToArray();
            }
        }
        foreach(var embedded in model.GetEmbeddedMeshes())Inspect(embedded.Mesh);
        foreach(var reference in model.GetReferenceMeshNamesForLod(0)) {using var res=Load(reference+"_c");Inspect((Mesh)res.DataBlock!);}
        if(witnessPath==null && !name.Contains("agg_merge") && eligibility.TryGetValue(name+".meshset_0",out var first) && first.Length==1 && first[0]) {
            witnessPath=modelPath;witnessMesh=name+".meshset_0";
        }
        var flags=eligibility.Where(x=>x.Key.StartsWith(name+".meshset_")).SelectMany(x=>x.Value).Distinct().ToArray();
        // Aggregate fragments are slices of the same authored draw data. Only
        // propagate when every draw agrees; mixed cases stay explicitly unverified.
        if(flags.Length==1)foreach(var fragment in gltfMeshes.Where(x=>x.Name.StartsWith(name+"_fragment")))eligibility[fragment.Name]=Enumerable.Repeat(flags[0],fragment.Count).ToArray();
    }
}
var result=new{schema=1,map,source_fingerprint=args.Length>3?args[3]:"",reader="ValveResourceFormat/20.1.7467",format="BC6H_UFLOAT",width=texture.Width,height=texture.Height,depth=texture.Depth,bytes=buffer.Length,atlas_sha256=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(buffer)).ToLowerInvariant(),volumes,lightmaps=maps,lightmap_eligibility=eligibility,
    lightmap_version=info.GetInt32Property("m_nLightmapVersionNumber"),lightmap_game_version=info.GetInt32Property("m_nLightmapGameVersionNumber"),uv_scale=new[]{world.GetLightmapUvScale().X,world.GetLightmapUvScale().Y}};
File.WriteAllText(Path.Combine(output,"probes.json"),JsonSerializer.Serialize(result));
Console.WriteLine(JsonSerializer.Serialize(new{volumes=volumes.Count,bytes=buffer.Length}));
// A tiny source-UV witness checks exporter scaling without re-exporting geometry.
if(witnessPath!=null) {
    using var witness=Load(witnessPath);
    var samples=new List<object>();
    var witnessModel=(Model)witness.DataBlock!;
    var meshes=witnessModel.GetEmbeddedMeshes().Select(x=>x.Mesh).ToList();
    var references=new List<Resource>();
    foreach(var name in witnessModel.GetReferenceMeshNamesForLod(0)) {
        var resource=Load(name+"_c");references.Add(resource);meshes.Add((Mesh)resource.DataBlock!);
    }
    foreach(var mesh in meshes) {
        foreach(var vb in mesh.VBIB.VertexBuffers) {
            foreach(var field in vb.InputLayoutFields.Where(f=>f.SemanticName.StartsWith("TEXCOORD"))) {
                samples.Add(new{format=field.Format.ToString(),stride=vb.ElementSizeInBytes,count=vb.ElementCount,offset=field.Offset,
                    semantic=field.SemanticName,index=field.SemanticIndex,
                    bytes=Convert.ToHexString(vb.Data.AsSpan(0,(int)Math.Min(vb.Data.Length,vb.ElementSizeInBytes*8)))});
            }
        }
    }
    foreach(var resource in references)resource.Dispose();
    File.WriteAllText(Path.Combine(output,"uv-witness.json"),JsonSerializer.Serialize(new{mesh=witnessMesh,samples}));
}
