using DemoFile;
using Google.Protobuf;
using System.Text.Json;
using System.Reflection;
if(args.Length!=4)throw new ArgumentException("demo startTick endTick report.json");
var parser=new CsDemoParser();
int start=int.Parse(args[1]),end=int.Parse(args[2]);
var counts=new Dictionary<string,int>();var selected=new Dictionary<string,int>();
var rows=new List<object>();
object Snapshot(object value){
    if(value is IMessage message)return JsonSerializer.Deserialize<JsonElement>(JsonFormatter.Default.Format(message));
    var fields=new Dictionary<string,object?>();
    foreach(var p in value.GetType().GetProperties()){
        if(p.GetIndexParameters().Length!=0)continue;
        var v=p.GetValue(value);
        if(v==null||v is string||v.GetType().IsPrimitive||v.GetType().IsEnum)fields[p.Name]=v;
        else if(v is System.Numerics.Vector3 vector)fields[p.Name]=new[]{vector.X,vector.Y,vector.Z};
        else if(p.Name is "Player" or "Attacker" or "Victim"){
            fields[p.Name]=new {steamid=v.GetType().GetProperty("SteamID")?.GetValue(v)?.ToString(),name=v.GetType().GetProperty("PlayerName")?.GetValue(v)};
        }
    }
    return fields;
}
void Record(string kind,object value){
    counts[kind]=counts.GetValueOrDefault(kind)+1;
    var tick=parser.CurrentDemoTick.Value;
    if(tick<start||tick>end)return;
    selected[kind]=selected.GetValueOrDefault(kind)+1;
    rows.Add(new {tick,kind,data=Snapshot(value)});
}
parser.Source1GameEvents.BulletImpact += e=>Record("bullet_impact",e);
parser.Source1GameEvents.BulletDamage += e=>Record("bullet_damage",e);
parser.Source1GameEvents.PlayerShoot += e=>Record("player_shoot",e);
parser.Source1GameEvents.AddBulletHitMarker += e=>Record("add_bullet_hit_marker",e);
parser.GameEvents.FireBullets += e=>Record("fire_bullets",e);
parser.TempEntityEvents.Impact += e=>Record("temporary_entity_impact",e);
parser.UserMessageEvents.ShootInfo += e=>Record("shoot_info",e);
using(var stream=File.OpenRead(args[0]))await DemoFileReader.Create(parser,stream).ReadAllAsync();
var output=Path.GetFullPath(args[3]);Directory.CreateDirectory(Path.GetDirectoryName(output)!);
File.WriteAllText(output,JsonSerializer.Serialize(new {demo=Path.GetFileName(args[0]),start,end,counts,selected,rows},new JsonSerializerOptions{WriteIndented=true}));
Console.WriteLine(JsonSerializer.Serialize(new {counts,selected,output}));
