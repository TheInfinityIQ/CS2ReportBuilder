using System.Text.Json;
using ValveResourceFormat;
using ValveResourceFormat.ResourceTypes;

static class UvContracts {
    public static void Export(string glb,string map,string output,Func<string,Resource> load) {
        using var input=new BinaryReader(File.OpenRead(glb));input.BaseStream.Position=12;
        var length=input.ReadInt32();input.ReadUInt32();
        if(length<1 || length>64*1024*1024)throw new InvalidDataException("GLB metadata exceeds bounds");
        using var document=JsonDocument.Parse(input.ReadBytes(length));
        var wanted=document.RootElement.GetProperty("meshes").EnumerateArray().Where(m=>m.GetProperty("primitives").EnumerateArray().Any(p=>p.GetProperty("attributes").TryGetProperty("TEXCOORD_2",out _))).ToArray();
        string Base(string name) {var at=name.IndexOf(".meshset_");if(at<0)at=name.LastIndexOf("_fragment");return at<0?name:name[..at];}
        var result=new Dictionary<string,string[]>();
        foreach(var group in wanted.GroupBy(m=>Base(m.GetProperty("name").GetString()!))) {
            using var resource=load($"maps/{map}/worldnodes/{group.Key}.vmdl_c");var model=(Model)resource.DataBlock!;
            var ordinals=new HashSet<int>();
            void Inspect(Mesh mesh) {
                var semantics=mesh.VBIB.VertexBuffers.SelectMany(b=>b.InputLayoutFields)
                    .Where(f=>f.SemanticName.Equals("TEXCOORD",StringComparison.OrdinalIgnoreCase) && f.SemanticIndex<=3)
                    .Select(f=>(int)f.SemanticIndex).Distinct().Order().ToList();
                if(semantics.Contains(3))ordinals.Add(semantics.IndexOf(3));
            }
            foreach(var embedded in model.GetEmbeddedMeshes())Inspect(embedded.Mesh);
            foreach(var reference in model.GetReferenceMeshNamesForLod(0)){using var mesh=load(reference+"_c");Inspect((Mesh)mesh.DataBlock!);}
            if(ordinals.Count!=1)throw new InvalidDataException("Ambiguous source lightmap UV layout: "+group.Key);
            var channel="TEXCOORD_"+ordinals.Single();
            foreach(var mesh in group) {
                // A meshset may mix draw layouts. Only remap primitives that
                // actually carry the extra exported channel; two-channel draws
                // already occupy Godot's UV2 and must keep that input.
                result[mesh.GetProperty("name").GetString()!]=mesh.GetProperty("primitives").EnumerateArray()
                    .Select(p=>p.GetProperty("attributes").TryGetProperty(channel,out _)?channel:"TEXCOORD_1").ToArray();
            }
        }
        File.WriteAllText(Path.Combine(output,"uv-channels.json"),JsonSerializer.Serialize(new{schema=1,map,channels=result}));
        Console.WriteLine($"UV contracts: {result.Count}");
    }
}
