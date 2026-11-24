using System.Text.Json;
using SteamDatabase.ValvePak;
using ValveResourceFormat;
using ValveResourceFormat.ResourceTypes;
using ValveResourceFormat.ResourceTypes.ModelAnimation;
using ValveResourceFormat.ResourceTypes.ModelAnimation2;
using ValveResourceFormat.Serialization.KeyValues;

// Offline preparation only; no game integration, process launch or installed writes.
if(args.Length==4 && args[0]=="--native-resource") {
    NativeResourceBridge.Run(args[1],args[2],args[3]);return;
}
if(args.Length==4 && args[0]=="--texture-metadata" && args[2].EndsWith(".vtex_c")) {
    NativeResourceBridge.Run(args[1],args[2],args[3],true);return;
}
if(args.Length==5 && args[0]=="--visibility") {
    VisibilityBridge.Run(args[1],args[2],args[3],args[4]);return;
}
if(args.Length is 4 or 5 && args[0]=="--shader-profile") {
    ShaderProbe.Run(args[1],args[2],args[3],args.Length==5?args[4]:null);return;
}
if (args.Length<3) throw new ArgumentException("Expected VPK, clip path and private output directory.");
using var package=new Package();package.Read(args[0]);
var output=Path.GetFullPath(args[2]);Directory.CreateDirectory(output);
var resourceCache=args.Length>3?Path.GetFullPath(args[3]):output;Directory.CreateDirectory(resourceCache);
Resource Load(string path) {
    path=path.Replace('\\','/');if(!path.EndsWith("_c"))path+="_c";
    var entry=package.FindEntry(path)??throw new FileNotFoundException("Resource not found",path);
    var file=Path.Combine(resourceCache,Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(path)))+Path.GetExtension(path));
    if(!File.Exists(file)){package.ReadEntry(entry,out var bytes);File.WriteAllBytes(file,bytes);}
    var resource=new Resource();resource.Read(file);return resource;
}
using var clipResource=Load(args[1]);
object SkeletonInfo(Skeleton skeleton) => skeleton.Bones.Select(b=>new {name=b.Name,parent=b.Parent?.Name,
    position=new[]{b.Position.X,b.Position.Y,b.Position.Z},rotation=new[]{b.Angle.X,b.Angle.Y,b.Angle.Z,b.Angle.W}}).ToArray();
if(clipResource.DataBlock is Model model) {
    if(args.Length>4 && args[4]=="materials") {
        var materials=new List<object>();
        var names=new HashSet<string>();
        void References(Resource resource){foreach(var reference in resource.ExternalReferences.ResourceRefInfoList)if(reference.Name.EndsWith(".vmat"))names.Add(reference.Name);}
        References(clipResource);
        foreach(var meshName in model.GetReferenceMeshNamesForLod(0)){using var resource=Load(meshName.MeshName);References(resource);}
        foreach(var name in names) {
            using var resource=Load(name);var material=(Material)resource.DataBlock!;
            materials.Add(new {resource=name,shader=material.ShaderName,ints=material.IntParams,floats=material.FloatParams});
        }
        File.WriteAllText(Path.Combine(output,"materials.json"),JsonSerializer.Serialize(materials));return;
    }
    File.WriteAllText(Path.Combine(output,"model.json"),JsonSerializer.Serialize(new{schema=1,resource=args[1],bones=SkeletonInfo(model.Skeleton)}));
    Console.WriteLine("Model skeleton prepared");return;
}
var primary=(AnimationClip)clipResource.DataBlock!;
var variants=new[]{primary}.Concat(primary.SecondaryAnimations).ToArray();
var reports=new List<object>();
foreach(var clip in variants) {
    using var skeletonResource=Load(clip.SkeletonName);
    var skeleton=Skeleton.FromSkeletonData(((BinaryKV3)skeletonResource.DataBlock!).Data);
    var animation=new ClipAnimation(clip);var cache=new AnimationFrameCache(skeleton,[]);
    if(animation.FrameCount<1||animation.FrameCount>4096||skeleton.Bones.Length>256)throw new InvalidDataException("Animation exceeds preparation bounds.");
    var path=Path.Combine(output,$"variant_{reports.Count}.bin");
    using(var writer=new BinaryWriter(File.Create(path))) {
        for(var frameIndex=0;frameIndex<animation.FrameCount;frameIndex++) {
            var frame=cache.GetFrame(animation,frameIndex);
            foreach(var bone in frame.Bones) {
                writer.Write(bone.Position.X);writer.Write(bone.Position.Y);writer.Write(bone.Position.Z);
                writer.Write(bone.Angle.X);writer.Write(bone.Angle.Y);writer.Write(bone.Angle.Z);writer.Write(bone.Angle.W);writer.Write(bone.Scale);
            }
        }
    }
    reports.Add(new {skeleton=clip.SkeletonName,name=args[1],frames=animation.FrameCount,fps=animation.Fps,additive=animation.IsAdditive,
        bones=skeleton.Bones.Select(b=>b.Name).ToArray(),hierarchy=SkeletonInfo(skeleton),data=path});
}
File.WriteAllText(Path.Combine(output,"clip.json"),JsonSerializer.Serialize(new{schema=1,reader="ValveResourceFormat/20.1.7467",variants=reports}));
Console.WriteLine(JsonSerializer.Serialize(new {variants=reports.Count,output}));
