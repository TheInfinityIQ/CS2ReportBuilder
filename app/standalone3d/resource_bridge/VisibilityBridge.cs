using System.Numerics;
using System.Runtime.CompilerServices;
using System.Text.Json;
using SteamDatabase.ValvePak;
using ValveResourceFormat;
using ValveResourceFormat.Blocks;

// Reuse the pinned MIT VRF octree/box query, including its conservative large
// box rules. This accesses our resource-reader library, never a game DLL.
static class VisibilityBridge {
    [UnsafeAccessor(UnsafeAccessorKind.Method,Name="QueryOctreeBox")]
    static extern void QueryBox(VoxelVisibility visibility,uint index,Vector3 min,Vector3 max,Vector3 queryMin,Vector3 queryMax,Span<uint> result,bool enclosed);
    static Vector3 Vector(JsonElement e)=>new(e[0].GetSingle(),e[1].GetSingle(),e[2].GetSingle());
    public static void Run(string archive,string resourceName,string boundsFile,string output) {
        Directory.CreateDirectory(output);
        using var package=new Package();package.Read(archive);
        var entry=package.FindEntry(resourceName)??throw new InvalidDataException("Missing compiled map visibility");
        package.ReadEntry(entry,out var sourceBytes);
        var compiled=Path.Combine(output,"source.vvis_c");File.WriteAllBytes(compiled,sourceBytes);
        using var resource=new Resource();resource.Read(compiled);
        var visibility=resource.Blocks.OfType<VoxelVisibility>().Single();
        if(visibility.BaseClusterCount is <1 or >4096 || visibility.PVSBytesPerCluster!=512 || visibility.Nodes.Length==0)throw new InvalidDataException("Unsupported visibility layout");
        using var document=JsonDocument.Parse(File.ReadAllText(boundsFile));
        var objects=document.RootElement.EnumerateArray().ToArray();
        var membership=new uint[objects.Length][];var paths=new List<string>();
        for(int i=0;i<objects.Length;i++) {
            var item=objects[i];paths.Add(item.GetProperty("path").GetString()!);
            // Visibility cells describe free space, not solid wall interiors.
            // Include neighbouring cells for thin surfaces/ropes on a boundary.
            var padding=new Vector3(Math.Max(16f,visibility.GridSize*2f)+.03125f);
            var min=Vector(item.GetProperty("min"))-padding;var max=Vector(item.GetProperty("max"))+padding;
            var bits=new uint[128];
            QueryBox(visibility,0,visibility.MinBounds,visibility.MaxBounds,min,max,bits,false);
            var tight=new uint[128];
            QueryBox(visibility,0,visibility.MinBounds,visibility.MaxBounds,Vector(item.GetProperty("min"))-new Vector3(.03125f),Vector(item.GetProperty("max"))+new Vector3(.03125f),tight,false);
            // Unknown/outside/solid-only bounds remain visible. They may include
            // skybox meshes or surfaces that straddle the edge of free space.
            if(!tight.Any(x=>x!=0) || min.X<visibility.MinBounds.X || min.Y<visibility.MinBounds.Y || min.Z<visibility.MinBounds.Z || max.X>visibility.MaxBounds.X || max.Y>visibility.MaxBounds.Y || max.Z>visibility.MaxBounds.Z)bits[0]|=1;
            membership[i]=bits;
        }
        int rowBytes=(objects.Length+7)/8;var rows=new byte[visibility.BaseClusterCount*rowBytes];
        for(int cluster=0;cluster<visibility.BaseClusterCount;cluster++) {
            var pvs=visibility.VisBlocks.AsSpan(cluster*512,512);
            for(int i=0;i<objects.Length;i++) {
                bool seen=(membership[i][0]&1)!=0;
                for(int word=0;!seen && word<128;word++)seen=(BitConverter.ToUInt32(pvs.Slice(word*4,4))&membership[i][word])!=0;
                if(seen)rows[cluster*rowBytes+i/8]|=(byte)(1<<(i%8));
            }
        }
        File.WriteAllBytes(Path.Combine(output,"object-visibility.bin"),rows);
        using(var writer=new BinaryWriter(File.Create(Path.Combine(output,"nodes.bin"))))foreach(var node in visibility.Nodes){writer.Write(node.IsLeaf?1u:0u);writer.Write(node.Offset);writer.Write((uint)node.RegionCount);}
        using(var writer=new BinaryWriter(File.Create(Path.Combine(output,"regions.bin"))))foreach(var region in visibility.Regions){writer.Write((uint)region.ClusterId);writer.Write((uint)region.MaskIndex);}
        using(var writer=new BinaryWriter(File.Create(Path.Combine(output,"masks.bin"))))foreach(var mask in visibility.Masks)writer.Write(mask);
        var probes=new List<object>();
        foreach(var item in objects.Take(64)) {
            var point=(Vector(item.GetProperty("min"))+Vector(item.GetProperty("max")))*.5f;
            var pvs=visibility.GetPVSForPoint(point);probes.Add(new{point=new[]{point.X,point.Y,point.Z},cluster=visibility.GetClusterForPosition(point),pvs=pvs==null?null:Convert.ToBase64String(pvs)});
        }
        File.WriteAllBytes(Path.Combine(output,"pvs.bin"),visibility.VisBlocks);
        File.WriteAllText(Path.Combine(output,"manifest.json"),JsonSerializer.Serialize(new{schema=1,reader="ValveResourceFormat/20.1.7467",source_crc=entry.CRC32,
            min=new[]{visibility.MinBounds.X,visibility.MinBounds.Y,visibility.MinBounds.Z},max=new[]{visibility.MaxBounds.X,visibility.MaxBounds.Y,visibility.MaxBounds.Z},
            clusters=visibility.BaseClusterCount,row_bytes=rowBytes,objects=paths,nodes=visibility.Nodes.Length,regions=visibility.Regions.Length,masks=visibility.Masks.Length,probes}));
        Console.WriteLine(JsonSerializer.Serialize(new{objects=objects.Length,clusters=visibility.BaseClusterCount,bytes=rows.Length}));
    }
}
