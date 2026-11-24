using DemoFile;
using DemoFile.Game.Cs;
using System.Text.Json;
using Google.Protobuf;

if(args.Length==1 && args[0]=="--inspect") {
    foreach(var type in new[]{typeof(CsDemoParser),typeof(CCSPlayerController),typeof(CCSPlayerPawn),typeof(CCSWeaponBase)}) {
        Console.WriteLine(type.Name);
        foreach(var property in type.GetProperties().Where(p=>new[]{"Player","Pawn","Steam","Weapon","Ammo","Clip","LookAt","Inspect","FOV"}.Any(k=>p.Name.Contains(k))))
            Console.WriteLine(property.Name+" "+property.PropertyType.Name);
    }
    return;
}
if(args.Length<3)throw new ArgumentException("demo output.json source-sha256 [end-tick]");
var demo=new CsDemoParser();var rows=new Dictionary<string,List<object[]>>();var previous=new Dictionary<string,string>();
var shots=new List<object>();var stop=args.Length>3?int.Parse(args[3]):int.MaxValue;
using var cancellation=new CancellationTokenSource();
demo.OnCommandFinishPersistent+=()=> {
    int tick=demo.CurrentDemoTick.Value;if(tick<0)return;
    if(tick>stop){cancellation.Cancel();return;}
    foreach(var controller in demo.Players) {
        if(controller.SteamID==0 || controller.PlayerPawn?.ActiveWeapon is not CCSWeaponBase weapon)continue;
        var key=controller.SteamID.ToString();var reserve=weapon.ReserveAmmo;
        var state=new object[]{weapon.EconItem.Name,weapon.Clip1,reserve.Length>0?reserve[0]:-1,reserve.Length>1?reserve[1]:-1,
            weapon.WeaponGameplayAnimState.ToString(),weapon.WeaponGameplayAnimStateTimestamp.Value,
            weapon.InspectPending,weapon.InspectShouldLoop,weapon.WeaponActionPlaybackRate,
            weapon.GetType().GetProperty("ThrowStrength")?.GetValue(weapon) ?? 1f,demo.CurrentGameTick.Value};
        // Network clock is metadata for translating animation start times; it
        // must not make an unchanged player state generate a new row every tick.
        var signature=JsonSerializer.Serialize(state.Take(state.Length-1));
        if(previous.GetValueOrDefault(key)==signature)continue;
        previous[key]=signature;if(!rows.ContainsKey(key))rows[key]=new();
        rows[key].Add(new object[]{tick}.Concat(state).ToArray());
    }
};
demo.GameEvents.FireBullets+=message=> {
    int tick=demo.CurrentDemoTick.Value;if(tick<0 || tick>stop)return;
    if(message is IMessage proto) {
        var data=JsonSerializer.Deserialize<JsonElement>(JsonFormatter.Default.Format(proto));
        ulong shooter=0;
        if(data.TryGetProperty("player",out var handle) && handle.TryGetUInt32(out var value))
            foreach(var controller in demo.Players)
                if(controller.PlayerPawn?.EntityHandle.Value==value){shooter=controller.SteamID;break;}
        shots.Add(new {tick,shooter=shooter.ToString(),data});
    }
};
using(var input=File.OpenRead(args[0])) {
    try{await DemoFileReader.Create(demo,input).ReadAllAsync(cancellation.Token);}
    catch(OperationCanceledException)when(cancellation.IsCancellationRequested){}
}
var target=Path.GetFullPath(args[1]);Directory.CreateDirectory(Path.GetDirectoryName(target)!);
File.WriteAllText(target,JsonSerializer.Serialize(new {schema=1,source=args[2],tickrate=CsDemoParser.TickRate,
    fields=new[]{"weapon","clip","reserve","secondary_reserve","anim_state","anim_start_time","inspect","inspect_loop","playback_rate","throw_strength","network_tick"},players=rows,shots}));
Console.WriteLine(JsonSerializer.Serialize(new {players=rows.Count,rows=rows.Values.Sum(x=>x.Count),shots=shots.Count}));
