using DemoFile;
using DemoFile.Game.Cs;
using System.Text.Json;

if (args.Length < 3) throw new ArgumentException("demo output source-sha256 [end-tick]");
var demo = new CsDemoParser();
var last = new Dictionary<ulong,string>();
var rows = new List<object>();
var worldRows = new List<object>();
var worldLast = new Dictionary<ulong,(float X,float Y,float Z,float Pitch,float Yaw,float Roll,int Life,string Door)>();
int end = args.Length > 3 ? int.Parse(args[3]) : int.MaxValue;
int maxTransforms = 0, maxPropPositions = 0;
using var cancellation = new CancellationTokenSource();
float[] VectorValues(Vector v) => [v.X,v.Y,v.Z];
float[] AngleValues(QAngle v) => [v.Pitch,v.Yaw,v.Roll];
float[] TransformValues(CTransform t) => [t.Position.X,t.Position.Y,t.Position.Z,t.Orientation.X,t.Orientation.Y,t.Orientation.Z,t.Orientation.W];
var removedBreakables = new List<CBaseEntity>();
demo.EntityEvents.CBreakable.Delete += entity => removedBreakables.Add(entity);
demo.EntityEvents.CBreakableProp.Delete += entity => {
    if(entity.GetType()==typeof(CBreakableProp)) removedBreakables.Add(entity);
};
demo.PacketEvents.SvcPacketEntities += packet => {
    // Snapshot replacement can also fire Delete. Only retain deletions from
    // delta packets. A simple leave-PVS does not fire this parser callback.
    int tick=demo.CurrentDemoTick.Value;
    if(packet.LegacyIsDelta && tick>=0 && tick<=end) foreach(var entity in removedBreakables) {
        ulong handle=entity.EntityHandle.Value;
        if(!worldLast.Remove(handle) || worldRows.Count>=60000) continue;
        worldRows.Add(new {tick,handle=handle.ToString(),kind=entity.GetType().Name,
            origin=VectorValues(entity.Origin),angles=AngleValues(entity.Rotation),life=(int)entity.LifeState,
            door="",removed=true});
    }
    removedBreakables.Clear();
};
demo.OnCommandFinishPersistent += () => {
    int tick = demo.CurrentDemoTick.Value;
    if (tick > end) { cancellation.Cancel(); return; }
    if (tick < 0) return;
    foreach (var entity in demo.Entities) {
        // Brush breakables and named prop doors supply recorded changes. A
        // missing entity is not proof of destruction: it can leave visibility.
        var type = entity.GetType();
        if (entity is CBasePropDoor || entity is CBaseDoor || type == typeof(CBreakable) || type == typeof(CBreakableProp)) {
            var world = (CBaseEntity)entity;
            var p = world.Origin;
            var a = world.Rotation;
            var door = entity is CBasePropDoor propDoor ? propDoor.DoorState.ToString() : "";
            var worldSignature = (p.X,p.Y,p.Z,a.Pitch,a.Yaw,a.Roll,(int)world.LifeState,door);
            var worldHandle = entity.EntityHandle.Value;
            if (!worldLast.TryGetValue(worldHandle,out var previous) || previous != worldSignature) {
                worldLast[worldHandle] = worldSignature;
                if (worldRows.Count < 60000) worldRows.Add(new {tick,handle=worldHandle.ToString(),
                    kind=type.Name,origin=VectorValues(p),angles=AngleValues(a),life=(int)world.LifeState,door});
            }
        }
        object? state = null;
        if (entity is CSmokeGrenadeProjectile smoke && smoke.DidSmokeEffect) {
            state = new {kind="smoke",entityIndex=smoke.EntityIndex.Value,serial=smoke.SerialNumber,
                color=VectorValues(smoke.SmokeColor),seed=smoke.RandomSeed,effectTick=smoke.SmokeEffectTickBegin};
        } else if (entity is CCSPlayerPawn pawn && pawn.Health <= 0) {
            var transforms = pawn.RagdollPose.Transforms.Select(TransformValues).ToArray();
            if (transforms.Length > 256) throw new InvalidDataException("Ragdoll transform count exceeds bound");
            maxTransforms = Math.Max(maxTransforms,transforms.Length);
            state = new { kind="player",player=pawn.OriginalController?.SteamID.ToString() ?? "0",pawn.Health,
                origin=VectorValues(pawn.Origin),serverOrigin=VectorValues(pawn.RagdollServerOrigin),
                eyeAngles=AngleValues(pawn.DeathEyeAngles),force=VectorValues(pawn.RagdollDamageForce),
                damagePosition=VectorValues(pawn.RagdollDamagePosition),bone=pawn.RagdollDamageBone,
                headshot=pawn.RagdollDamageHeadshot,weapon=pawn.RagdollDamageWeaponName,
                enabled=pawn.RagdollEnabled,clientSide=pawn.RagdollClientSide,transforms };
        } else if (entity is CRagdollProp prop) {
            var transforms = prop.RagdollPose.Transforms.Select(TransformValues).ToArray();
            var positions = prop.RagPos.Select(VectorValues).ToArray();
            if (transforms.Length > 256 || positions.Length > 256) throw new InvalidDataException("Ragdoll prop count exceeds bound");
            maxTransforms = Math.Max(maxTransforms,transforms.Length);maxPropPositions=Math.Max(maxPropPositions,positions.Length);
            state = new {kind="prop",owner=prop.RagdollPose.OwnerHandle.Value,transforms,positions,
                angles=prop.RagAngles.Select(AngleValues).ToArray(),force=VectorValues(prop.Force),bone=prop.ForceBone};
        }
        if (state == null) continue;
        string signature = JsonSerializer.Serialize(state);ulong handle=entity.EntityHandle.Value;
        if (last.GetValueOrDefault(handle)==signature) continue;
        if (rows.Count >= 10000) throw new InvalidDataException("Death-state recording exceeded its bound; no complete companion was saved");
        last[handle]=signature;rows.Add(new {tick,handle=handle.ToString(),state});
    }
};
using (var input = File.OpenRead(args[0])) {
    try { await DemoFileReader.Create(demo,input).ReadAllAsync(cancellation.Token); }
    catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
}
Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(args[1]))!);
File.WriteAllText(args[1],JsonSerializer.Serialize(new {schema=1,source=args[2],endTick=end,tickrate=CsDemoParser.TickRate,maxTransforms,maxPropPositions,rows,
    worldRows,worldTruncated=worldRows.Count==60000}));
Console.WriteLine(JsonSerializer.Serialize(new {states=rows.Count,maxTransforms,maxPropPositions,endTick=end}));
