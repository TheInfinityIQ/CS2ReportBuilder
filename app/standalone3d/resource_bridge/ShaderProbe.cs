using System.Text.Json;
using SteamDatabase.ValvePak;
using ValveResourceFormat.CompiledShader;
using ValveResourceFormat.IO;

// Bounded offline proof. Never invoked by playback or asset preparation.
// Reads one explicitly named shader family, not the whole shader archive.
static class ShaderProbe {
    public static void Run(string archive,string featureFile,string output,string? materialFile) {
        output=Path.GetFullPath(output);Directory.CreateDirectory(output);
        if(!featureFile.EndsWith("_features.vcs",StringComparison.Ordinal))throw new ArgumentException("Expected one features shader path.");
        using var package=new Package();package.Read(archive);
        using var collection=ShaderCollection.GetShaderCollection(featureFile,package);
        var features=new Dictionary<string,byte>();
        if(materialFile!=null) {
            using var document=JsonDocument.Parse(File.ReadAllText(materialFile));
            foreach(var property in document.RootElement.GetProperty("IntParams").EnumerateObject())
                if(property.Name.StartsWith("F_",StringComparison.Ordinal))features[property.Name]=checked((byte)property.Value.GetInt32());
        }
        var reports=new List<object>();
        foreach(var shader in collection) {
            var binaries=new List<object>();
            // One static configuration only; bytecode presence is not proof
            // that its inputs/render passes have been reproduced in Godot.
            var keys=shader.StaticComboEntries.Keys.Take(1).ToArray();
            int[]? configuration=null;
            if(materialFile!=null && shader.StaticComboEntries.Count>0) {
                var selection=ShaderDataProvider.GetStaticConfiguration_ForFeatureState(collection.Features!,shader,features,new Dictionary<string,byte>());
                configuration=selection.StaticConfig;
                var selected=selection.StaticComboId;
                if(!shader.StaticComboEntries.ContainsKey(selected))throw new InvalidDataException("Material shader configuration is unavailable: "+selected);
                keys=[selected];
            }
            foreach(var key in keys) {
                var combo=shader.GetStaticCombo(key);
                foreach(var file in combo.ShaderFiles.Take(1)) {
                    var stem=shader.VcsProgramType.ToString()+"-"+key;
                    var path=Path.Combine(output,stem+".bin");
                    File.WriteAllBytes(path,file.Bytecode.ToArray());
                    string? decompiled=null;string? error=null;
                    try {
                        var source=file.GetDecompiledFile();
                        decompiled=Path.Combine(output,stem+".txt");File.WriteAllText(decompiled,source);
                    } catch(Exception e) when(e is not OutOfMemoryException) {error=e.GetType().Name+": "+e.Message;}
                    binaries.Add(new {static_combo=key,bytes=file.Bytecode.Length,container_bytes=file.Size,path,decompiled,error});
                }
            }
            reports.Add(new {shader=shader.ShaderName,stage=shader.VcsProgramType.ToString(),version=shader.VcsVersion,
                static_configurations=shader.StaticComboEntries.Count,selected_configuration=configuration,
                features=shader.StaticComboArray.Select(x=>new{name=x.Name,min=x.RangeMin,max=x.RangeMax}).ToArray(),
                bindings=shader.VariableDescriptions.Select(x=>new{name=x.Name,type=x.VfxType.ToString(),set=x.DescriptorSet,offset=x.RegisterOffset}).ToArray(),binaries});
        }
        File.WriteAllText(Path.Combine(output,"profile.json"),JsonSerializer.Serialize(new {schema=1,featureFile,
            scope=materialFile==null?"One static configuration per stage; not a matched-material rendering proof":"Material-selected static configuration; dynamic state and actual rendering are not validated",features,reports}));
        Console.WriteLine(JsonSerializer.Serialize(new {stages=reports.Count,output}));
    }
}
