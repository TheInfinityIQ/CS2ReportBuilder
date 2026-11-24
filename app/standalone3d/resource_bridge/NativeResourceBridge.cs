using System.Security.Cryptography;
using System.Text.Json;
using SteamDatabase.ValvePak;
using ValveResourceFormat;
using ValveResourceFormat.ResourceTypes;
using ValveResourceFormat.Serialization.KeyValues;

// Read one selected resource with the same pinned offline reader. Texture data
// stays in the game's original GPU format; no PNG expansion or recompression.
static class NativeResourceBridge {
    public static void Run(string archive,string name,string output,bool metadataOnly=false) {
        if(!name.EndsWith(".vmat_c") && !name.EndsWith(".vtex_c") && !name.EndsWith(".vents_c"))throw new ArgumentException("Expected one material, texture or entity lump");
        Directory.CreateDirectory(output);
        using var package=new Package();package.Read(archive);
        var entry=package.FindEntry(name)??throw new FileNotFoundException(name);
        if(entry.TotalLength>128*1024*1024)throw new InvalidDataException("Selected resource exceeds bound");
        package.ReadEntry(entry,out var bytes);
        using var resource=new Resource();resource.Read(new MemoryStream(bytes));
        object result;
        if(resource.DataBlock is Material material) {
            result=new{schema=1,resource=name,crc=entry.CRC32,shader=material.ShaderName,ints=material.IntParams,floats=material.FloatParams,
                vectors=material.VectorParams.ToDictionary(p=>p.Key,p=>new[]{p.Value.X,p.Value.Y,p.Value.Z,p.Value.W}),textures=material.TextureParams};
        } else if(resource.DataBlock is EntityLump entities) {
            var skies=entities.GetEntities().Where(e=>e.GetStringProperty("classname")=="env_sky").Select(e=>new{
                material=e.GetStringProperty("skyname"),target=e.GetStringProperty("targetname"),brightness=e.GetFloatProperty("brightnessscale",1),
                angles=Components(e.GetVector3Property("angles",System.Numerics.Vector3.Zero)),tint=Components(e.ContainsKey("tint_color")?e.GetColor32Property("tint_color"):System.Numerics.Vector3.One)}).ToArray();
            var suns=entities.GetEntities().Where(e=>e.GetStringProperty("classname")=="light_environment").Select(e=>new{
                angles=Components(e.GetVector3Property("angles",System.Numerics.Vector3.Zero)),color=Components(e.GetColor32Property("color")),
                properties=e.Children.ToDictionary(p=>p.Key,p=>p.Value.ToString())}).ToArray();
            var probes=entities.GetEntities().Where(e=>e.GetStringProperty("classname")=="env_combined_light_probe_volume").Select(e=>new{
                properties=e.Children.ToDictionary(p=>p.Key,p=>p.Value.ToString())}).ToArray();
            var objects=entities.GetEntities().Where(e=>e.GetStringProperty("classname") is "func_breakable" or "prop_door_rotating").Select(e=>new{
                kind=e.GetStringProperty("classname")=="func_breakable"?"CBreakable":"CPropDoorRotating",
                model=e.GetStringProperty("model"),
                origin=Components(e.GetVector3Property("origin",System.Numerics.Vector3.Zero)),
                angles=Components(e.GetVector3Property("angles",System.Numerics.Vector3.Zero))}).ToArray();
            var soundscapes=entities.GetEntities().Where(e=>e.GetStringProperty("classname")=="env_soundscape").Select(e=>new{
                name=e.GetStringProperty("soundscape"),
                origin=Components(e.GetVector3Property("origin",System.Numerics.Vector3.Zero)),
                radius=e.GetFloatProperty("radius",128)}).ToArray();
            result=new{schema=1,resource=name,crc=entry.CRC32,skies,suns,probes,objects,soundscapes};
        } else if(resource.DataBlock is Texture texture) {
            if(texture.Width>8192 || texture.Height>8192 || texture.NumMipLevels is <1 or >14)throw new InvalidDataException("Unsupported texture dimensions");
            if(metadataOnly) {
                File.WriteAllText(Path.Combine(output,"resource.json"),JsonSerializer.Serialize(new{schema=1,resource=name,crc=entry.CRC32,width=texture.Width,height=texture.Height,
                    depth=texture.Depth,format=texture.Format.ToString(),radiance_coefficients=texture.RadianceCoefficients}));return;
            }
            var levels=new List<object>();long total=0;
            using(var file=File.Create(Path.Combine(output,"texture.blocks")))for(uint mip=0;mip<texture.NumMipLevels;mip++) {
                var data=new byte[texture.CalculateBufferSizeForMipLevel(mip)];texture.ReadTextureMipLevel(data,mip);
                if(total+data.Length>128*1024*1024)throw new InvalidDataException("Texture data exceeds bound");
                levels.Add(new{level=mip,offset=total,bytes=data.Length,width=Math.Max(1,texture.Width>>(int)mip),height=Math.Max(1,texture.Height>>(int)mip)});
                file.Write(data);total+=data.Length;
            }
            result=new{schema=1,resource=name,crc=entry.CRC32,format=texture.Format.ToString(),width=texture.Width,height=texture.Height,depth=texture.Depth,levels,
                bytes=total,sha256=Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Path.Combine(output,"texture.blocks")))).ToLowerInvariant()};
        } else throw new InvalidDataException("Unexpected resource type");
        File.WriteAllText(Path.Combine(output,"resource.json"),JsonSerializer.Serialize(result));
    }
    static float[] Components(System.Numerics.Vector3 v)=>[v.X,v.Y,v.Z];
}
