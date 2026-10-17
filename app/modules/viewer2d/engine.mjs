// Pure replay calculations. All effects derive from time, so seeking is reversible.
export const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
export const lerp = (a, b, t) => a + (b - a) * t;
export function upperBound(rows, tick, key = r => r[0]) {
  let lo = 0, hi = rows.length;
  while (lo < hi) { const m = (lo + hi) >>> 1; if (key(rows[m]) <= tick) lo = m + 1; else hi = m; }
  return lo;
}
export function interpolate(track, tick) {
  if (!track.length || tick < track[0][0]) return null;
  const i = upperBound(track, tick) - 1, a = track[i], b = track[i + 1] || a;
  const f = a === b || b[0] - a[0] > 64 ? 0 : clamp((tick - a[0]) / (b[0] - a[0]), 0, 1);
  const angle = ((b[4] - a[4] + 540) % 360) - 180;
  return {x: lerp(a[1], b[1], f), y: lerp(a[2], b[2], f), z: lerp(a[3], b[3], f),
    yaw: a[4] + angle * f, pitch: lerp(a[5], b[5], f), flags: a[6], sampleTick: a[0]};
}

export function jumpAnimations(track, tickrate=64, jumpTicks=[]) {
  const animations=[];
  for(let i=1;i<track.length;i++){
    if(!(track[i][6]&8)||(track[i-1][6]&8))continue;
    const first=i,ground=track[i-1];
    while(i+1<track.length&&(track[i+1][6]&8))i++;
    const last=i,land=track[i+1];
    if(!land)continue;
    const samples=track.slice(first,last+1),early=samples.filter(p=>p[0]-samples[0][0]<=tickrate*.22);
    if(samples.some((p,j)=>p[0]-(j?samples[j-1]:ground)[0]>tickrate*.15)
      ||land[0]-samples.at(-1)[0]>tickrate*.15)continue;
    const confirmed=jumpTicks.some(t=>t>=ground[0]-tickrate*.1&&t<=samples[0][0]+tickrate*.1);
    const slopes=early.slice(1).map((p,j)=>(p[3]-early[j][3])*tickrate/(p[0]-early[j][0]));
    // Grounded ramps, short step-ups, constant-speed climbs and ledge drops
    // are not jumps. Older exports lack jump events: require a ballistic rise.
    const inferred=early.length>=3&&samples.length>=3
      &&Math.max(...early.map(p=>p[3]))-ground[3]>=20
      &&Math.max(...slopes)>=120&&slopes[0]-slopes.at(-1)>=45;
    if(!confirmed&&!inferred)continue;
    const start=(ground[0]+samples[0][0])/2;
    animations.push({start,end:Math.min(land[0],start+tickrate*.85),
      source:confirmed?'recorded_jump':'inferred_ballistic_takeoff'});
  }
  return animations;
}

export function jumpAmount(animations,tick){
  const index=upperBound(animations,tick,a=>a.start)-1;
  if(index<0)return 0;
  const {start,end}=animations[index];
  if(tick>=end)return 0;
  const phase=clamp((tick-start)/(end-start),0,1);
  // Zero slope at takeoff and landing; deterministic during scrubbing as well.
  return Math.sin(Math.PI*phase)**2;
}

export function crouchAmount(track,tick){
  const i=upperBound(track,tick)-1;if(i<0)return 0;
  const a=track[i],b=track[i+1]||a;
  const f=a===b||b[0]-a[0]>16?0:clamp((tick-a[0])/(b[0]-a[0]),0,1);
  return lerp(a[6]&4?1:0,b[6]&4?1:0,f*f*(3-2*f));
}
export function weaponKey(name = '') {
  const key = name.toLowerCase().replace(/^weapon_/, '');
  const aliases = {'ak-47':'ak47','m4a4':'m4a1','m4a1-s':'m4a1_silencer','usp-s':'usp_silencer',
    'glock-18':'glock','p2000':'hkp2000','desert eagle':'deagle','dual berettas':'elite',
    'five-seven':'fiveseven','tec-9':'tec9','cz75-auto':'cz75a','r8 revolver':'revolver',
    'ssg 08':'ssg08','sg 553':'sg556','galil ar':'galilar','pp-bizon':'bizon',
    'mac-10':'mac10','ump-45':'ump45','mp5-sd':'mp5sd','mag-7':'mag7','sawed-off':'sawedoff',
    'smoke grenade':'smokegrenade','smoke':'smokegrenade','he grenade':'hegrenade','he':'hegrenade',
    'fire':'molotov','incendiary grenade':'incgrenade','flash':'flashbang','decoy grenade':'decoy',
    'c4 explosive':'c4','zeus x27':'taser'};
  if (key.includes('knife') || key.includes('bayonet')) return 'knife';
  return aliases[key] || key.replace(/[^a-z0-9_]/g, '');
}

export function stateAt(player, tick) {
  const i = upperBound(player.states, tick, r => r.tick) - 1;
  return i < 0 ? {health:100, weapon:'knife', armor:0, money:null, inventory:[]} : player.states[i];
}
export function smokeOpacity(age, lifetime, heAge, nearHE) {
  const envelope = Math.min(clamp(age / .85, 0, 1), clamp((lifetime - age) / 2, 0, 1));
  // HE disperses a local hole briefly; it does not permanently delete the smoke.
  const hole = nearHE && heAge >= 0 && heAge < 3.2 ? Math.sin(Math.PI * clamp(heAge / 3.2, 0, 1)) : 0;
  return {envelope, hole};
}
export function formatTime(seconds) {
  seconds = Math.max(0, Math.floor(seconds));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

export function entityStatesAt(rows, tick) {
  const active = new Map();
  for(const row of rows || []) {
    if(row.tick > tick)break;
    if(row.action === 'upsert')active.set(row.id, {...row.state,tick:row.tick});
    else active.delete(row.id);
  }
  return active;
}
