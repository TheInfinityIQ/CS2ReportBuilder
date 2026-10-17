using System.IO.Compression;
using System.Text.Json;
using DemoFile;
using DemoFile.Game.Cs;

// Networked entity samples, not death-position/inventory inference.
if (args.Length < 2) { Console.Error.WriteLine("Usage: EntityExtractor <demo.dem> <output-folder> [sample-hz] [start-tick] [end-tick]"); return 2; }
var demoPath = Path.GetFullPath(args[0]);
var output = Path.GetFullPath(args[1]);
var sampleHz = args.Length > 2 ? int.Parse(args[2]) : 16;
var startTick = args.Length > 3 ? int.Parse(args[3]) : 0;
var endTick = args.Length > 4 ? int.Parse(args[4]) : int.MaxValue;
if (sampleHz < 1 || sampleHz > 64 || 64 % sampleHz != 0 || startTick > endTick) throw new ArgumentException("Sample Hz must divide 64; start must not exceed end.");
Directory.CreateDirectory(output);
using var loot = new JsonLines(Path.Combine(output,"loot_tracks.jsonl.gz"));
using var fire = new JsonLines(Path.Combine(output,"inferno_patches.jsonl.gz"));
using var smoke = new JsonLines(Path.Combine(output,"smoke_frames.jsonl.gz"));
var oldLoot = new Dictionary<string,string>();
var oldFire = new Dictionary<string,string>();
var oldSmoke = new Dictionary<string,string>();
long commands = 0, maxTick = 0, voxelFrames = 0, activePatches = 0;
var networkOffsets = new HashSet<long>();
var observedWeapons = new HashSet<string>();
var observedInfernos = new HashSet<string>();
var observedSmokes = new HashSet<string>();
var demo = new CsDemoParser();
var actualRate = 64;
demo.OnCommandFinishPersistent += () => {
    int tick = demo.CurrentDemoTick.Value;
    if (tick < startTick || tick > endTick || tick < 0) return;
    commands++; maxTick = Math.Max(maxTick,tick);
    networkOffsets.Add((long)demo.CurrentGameTick.Value-tick);
    if(CsDemoParser.TickRate > 0)actualRate=CsDemoParser.TickRate;
    int step = Math.Max(1,actualRate/sampleHz);
    bool sampled = tick % step == 0;
    var aliveLoot = new HashSet<string>();
    var aliveFire = new HashSet<string>();
    var aliveSmoke = new HashSet<string>();
    foreach (var entity in demo.Entities) {
        if (!entity.IsActive) continue;
        string id = entity.EntityHandle.Value.ToString(); // Includes serial: recycled indices stay distinct.
        if (entity is CCSWeaponBase w) {
            observedWeapons.Add(id);
            // A valid owner handle must not be interpreted as ground loot, even if its pawn is temporarily unresolved.
            if(w.OwnerEntityHandle.IsValid) {
                if(oldLoot.Remove(id)) { loot.Write(new {tick,id,action="pickup",owner=w.OwnerEntityHandle.Value.ToString()}); }
                continue;
            }
            aliveLoot.Add(id);
            var p=w.Origin;
            if(!Finite(p))continue;
            var state=new {id,entityIndex=w.EntityIndex.Value,serial=w.SerialNumber,item=w.EconItem.Name,
                definitionIndex=w.EconItem.ItemDefinitionIndex,x=p.X,y=p.Y,z=p.Z,
                owner=w.OwnerEntityHandle.Value.ToString(),previousOwner=w.PrevOwnerHandle.Value.ToString(),
                dropNetworkTick=w.DropTick.Value,clip=w.Clip1};
            string signature=JsonSerializer.Serialize(state);
            if(!oldLoot.TryGetValue(id,out var previous) || (sampled && signature!=previous)) {
                loot.Write(new {tick,id,action="upsert",state});oldLoot[id]=signature;
            }
        }
        if(entity is CInferno inf) {
            observedInfernos.Add(id);aliveFire.Add(id);
            if(!sampled && oldFire.ContainsKey(id))continue;
            int count=Math.Min(Math.Max(inf.FireCount,0),Math.Min(inf.FirePositions.Length,inf.FireIsBurning.Length));
            var patches=new List<object>();
            for(int i=0;i<count;i++) {
                var p=inf.FirePositions[i];if(!Finite(p))continue;
                patches.Add(new {index=i,x=p.X,y=p.Y,z=p.Z,burning=inf.FireIsBurning[i]});
                if(inf.FireIsBurning[i])activePatches++;
            }
            var o=inf.Origin;
            var state=new {id,entityIndex=inf.EntityIndex.Value,serial=inf.SerialNumber,
                x=o.X,y=o.Y,z=o.Z,fireCount=inf.FireCount,patches,
                effectNetworkTick=inf.FireEffectTickBegin,postEffect=inf.InPostEffectTime,owner=inf.OwnerEntityHandle.Value.ToString()};
            string signature=JsonSerializer.Serialize(state);
            if(!oldFire.TryGetValue(id,out var previous)||signature!=previous){fire.Write(new {tick,id,action="upsert",state});oldFire[id]=signature;}
        }
        if(entity is CSmokeGrenadeProjectile sm && sm.DidSmokeEffect) {
            observedSmokes.Add(id);aliveSmoke.Add(id);
            // Capture raw voxel updates at every packet, independent of geometry sampling.
            var bytes=sm.VoxelFrameData.ToArray();var p=sm.SmokeDetonationPos;
            var state=new {id,entityIndex=sm.EntityIndex.Value,serial=sm.SerialNumber,
                x=p.X,y=p.Y,z=p.Z,effectNetworkTick=sm.SmokeEffectTickBegin,seed=sm.RandomSeed,
                voxelUpdate=sm.VoxelUpdate,declaredBytes=sm.VoxelFrameDataSize,payloadBytes=bytes.Length,
                voxelBase64=Convert.ToBase64String(bytes)};
            string signature=JsonSerializer.Serialize(state);
            if(!oldSmoke.TryGetValue(id,out var previous)||signature!=previous) {
                smoke.Write(new {tick,id,action="upsert",state});oldSmoke[id]=signature;
                if(bytes.Length>0)voxelFrames++;
            }
        }
    }
    RemoveMissing(oldLoot,aliveLoot,loot,tick,"removed");
    RemoveMissing(oldFire,aliveFire,fire,tick,"removed");
    RemoveMissing(oldSmoke,aliveSmoke,smoke,tick,"removed");
};
using (var stream=File.OpenRead(demoPath)) {
    var reader=DemoFileReader.Create(demo,stream);
    await reader.ReadAllAsync();
}
loot.Close();fire.Close();smoke.Close();
var metadata=new {
    schema=1,extractor="CS2ReportBuilder-v8",backend="DemoFile.Game.Cs",backendVersion="0.44.1",
    demo=Path.GetFileName(demoPath),tickDomain="demo_tick",networkTickOffsets=networkOffsets.Order().ToArray(),
    tickrate=actualRate,sampleHz,startTick,endTick=endTick==int.MaxValue?(long?)null:endTick,lastObservedTick=maxTick,
    commands,counts=new {loot=loot.Count,fire=fire.Count,smoke=smoke.Count,weaponEntities=observedWeapons.Count,
        infernoEntities=observedInfernos.Count,smokeEntities=observedSmokes.Count,voxelFrames,activePatchObservations=activePatches},
    capabilities=new {
        lootPositions=loot.Count>0?"recorded_entity_positions":"not_observed",
        firePatchPositions=activePatches>0?"recorded_burning_patch_centers":"not_observed",
        smokeVoxels=voxelFrames>0?"raw_network_payload_captured_not_decoded":"not_available_in_this_demo",
        smokeGeometry="not_decoded",exactSmokeRendering=false,exactFireBoundary=false},
    semantics=new[]{"Loot is a live weapon entity with an invalid owner handle; pickup is an observed owner transition.",
        "removed means the entity left the current networked entity set; it does not assert a pickup or destruction reason.",
        "Fire patch centers and burning flags are recorded; flame artwork/patch boundaries are not engine-rendered geometry.",
        "Smoke voxelBase64 preserves raw bytes without claiming a decoded occupancy volume or HE-hole geometry.",
        "Entity handles include serial numbers. Files contain changes; last state persists until removed or pickup.",
        "Positions sample at requested Hz; initial observations, ownership changes, removals, and smoke updates are packet-driven.",
        "No synthetic removals are emitted at the end of a selected window."},
    files=new[]{"loot_tracks.jsonl.gz","inferno_patches.jsonl.gz","smoke_frames.jsonl.gz"}
};
File.WriteAllText(Path.Combine(output,"entity_meta.json"),JsonSerializer.Serialize(metadata,new JsonSerializerOptions{WriteIndented=true}));
Console.WriteLine($"Entity pass: loot {loot.Count}, fire {fire.Count}, smoke {smoke.Count}, raw voxel frames {voxelFrames}");
return 0;

static bool Finite(Vector p)=>float.IsFinite(p.X)&&float.IsFinite(p.Y)&&float.IsFinite(p.Z);
static void RemoveMissing(Dictionary<string,string> old,HashSet<string> alive,JsonLines writer,int tick,string action) {
    foreach(var id in old.Keys.Where(id=>!alive.Contains(id)).ToArray()){writer.Write(new {tick,id,action});old.Remove(id);}
}
sealed class JsonLines : IDisposable {
    private readonly StreamWriter writer;private bool closed;
    public long Count{get;private set;}
    public JsonLines(string path){writer=new StreamWriter(new GZipStream(File.Create(path),CompressionLevel.Optimal));}
    public void Write<T>(T row){writer.WriteLine(JsonSerializer.Serialize(row));Count++;}
    public void Close(){if(!closed){writer.Dispose();closed=true;}}
    public void Dispose()=>Close();
}
