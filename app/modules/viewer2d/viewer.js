import {clamp, lerp, interpolate, stateAt, upperBound, weaponKey, smokeOpacity, formatTime, entityStatesAt, jumpAnimations, jumpAmount, crouchAmount} from './engine.mjs?v=4';
import {fireMesh} from './geometry.mjs?v=1';
import {directionEndpoint, prepareShots, comparisonShot} from './shots.mjs?v=1';

const $ = id => document.getElementById(id);
const canvas = $('map'), ctx = canvas.getContext('2d');
const colors = {CT:'#58aff7', T:'#f1b34f'};
const icons = new Map();
const smokeLayers = new Map();
const voxelImages = new Map();
const firePaths = new Map();
let replay, tick = 0, playing = false, speed = 1, previousTime = 0, requestId = 0;
let mapImage = new Image(), lowerImage = new Image(), mapReady = false, lowerReady = false;
let zoom = 1, pan = [0,0], follow = null, names = true, trails = true;
let view = {size:1, x:0, y:0}, width = 1, height = 1, hitboxes = [], drag = null;
let rosterNodes = new Map(), lastUI = 0, lastFeed = '', catalog = [];
let previewEnd = null;
const nameFor = id => replay.players.find(p => p.id === id)?.name || 'World';
const sideFor = id => replay.players.find(p => p.id === id)?.side || 'CT';
const seconds = t => (t - replay.start) / replay.tickrate;
const point = (x,y) => [(x - replay.calibration.pos_x) / replay.calibration.scale,
  (replay.calibration.pos_y - y) / replay.calibration.scale];
const screen = (x,y) => {const p = point(x,y); return [view.x + p[0] * view.size/1024, view.y + p[1] * view.size/1024];};
const unit = n => n / replay.calibration.scale * view.size / 1024;

function icon(name) {
  const key = weaponKey(name);
  if (!icons.has(key)) {
    const image = new Image(); image.src = `../../assets/weapons/${key || 'knife'}.svg`;
    icons.set(key,image);
  }
  return icons.get(key);
}
function drawIcon(name,x,y,w=22,h=12,alpha=1) {
  const image = icon(name);
  if (!image.complete || !image.naturalWidth) return;
  ctx.save();ctx.globalAlpha=alpha;ctx.filter='brightness(0) invert(.93)';
  const ratio = Math.min(w/image.naturalWidth,h/image.naturalHeight);
  ctx.drawImage(image,x-image.naturalWidth*ratio/2,y-image.naturalHeight*ratio/2,image.naturalWidth*ratio,image.naturalHeight*ratio);ctx.restore();
}
function circle(x,y,r,fill,stroke=null,line=1) {
  ctx.beginPath();ctx.arc(x,y,Math.max(.1,r),0,Math.PI*2);
  if(fill){ctx.fillStyle=fill;ctx.fill();}if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=line;ctx.stroke();}
}
function setPlaying(value) {
  if(!value)previewEnd=null;
  playing=value;$('play').textContent=playing?'Ⅱ':'▶';$('play').setAttribute('aria-label',playing?'Pause':'Play');
}
function seek(value) { previewEnd=null;tick=clamp(value,replay.start,replay.end);lastUI=0;renderUI(); }
function eventDescription(e) {
  if(e.kind==='player_death') return `${e.attacker_name || 'World'} → ${e.user_name || nameFor(e.user_steamid)}`;
  if(e.kind==='bomb_planted') return 'Bomb planted';
  if(e.kind==='bomb_defused') return 'Bomb defused';
  if(e.kind==='bomb_exploded') return 'Bomb exploded';
  return e.kind.replaceAll('_',' ');
}
function makeRoster() {
  rosterNodes.clear();
  for(const side of ['CT','T']) {
    const team=$(side==='CT'?'ct-team':'t-team');team.replaceChildren();
    const head=document.createElement('div');head.className='team-head';
    const title=document.createElement('span');title.textContent=side==='CT'?'COUNTER-TERRORISTS':'TERRORISTS';
    const count=document.createElement('strong');head.append(title,count);team.append(head);
    for(const player of replay.players.filter(p=>p.side===side)) {
      const row=document.createElement('div');row.className='roster';row.tabIndex=0;row.setAttribute('role','button');row.setAttribute('aria-label',`Follow ${player.name}`);
      const top=document.createElement('div');top.className='roster-top';const name=document.createElement('b');name.textContent=player.name;
      const money=document.createElement('span');top.append(name,money);
      const hp=document.createElement('div');hp.className='hp';const fill=document.createElement('i');hp.append(fill);
      const loadout=document.createElement('div');loadout.className='loadout';const weapon=document.createElement('img');weapon.alt='';
      const status=document.createElement('small');const util=document.createElement('span');loadout.append(weapon,util,status);row.append(top,hp,loadout);
      const select=()=>{follow=follow===player.id?null:player.id;lastUI=0;};row.onclick=select;
      row.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select();}};
      team.append(row);rosterNodes.set(player.id,{row,money,fill,weapon,status,util,count});
    }
  }
}
async function loadReplay(data) {
  replay=data;tick=data.start;setPlaying(false);zoom=1;pan=[0,0];follow=null;lastFeed='';smokeLayers.clear();voxelImages.clear();firePaths.clear();
  data.shots=prepareShots(data.shots || [],data.events);
  $('replay-shots').disabled=!data.shots.length;
  updateShotStatus();
  for(const player of data.players){
    const jumpTicks=data.events.filter(e=>e.kind==='player_jump'&&e.user_steamid===player.id).map(e=>e.tick);
    player.jumpAnimations=jumpAnimations(player.track,data.tickrate,jumpTicks);
  }
  mapReady=false;lowerReady=false;mapImage=new Image();lowerImage=new Image();
  mapImage.onload=()=>{mapReady=true;};mapImage.onerror=()=>{$('loading').textContent=`Map asset missing: ${data.map}`;$('loading').hidden=false;};
  mapImage.src=`../../assets/maps/${data.map}.png`;
  if(['de_nuke','de_vertigo','de_train'].includes(data.map)) {
    lowerImage.onload=()=>{lowerReady=true;};lowerImage.src=`../../assets/maps/${data.map}_lower.png`;
  }
  $('map-title').textContent=data.map.replace('de_','').replace(/^./,s=>s.toUpperCase());
  $('match-name').textContent=`${data.roundInfo.ct_team_clan_name || 'Counter-Terrorists'} vs ${data.roundInfo.t_team_clan_name || 'Terrorists'}`;
  $('source-name').textContent=data.source.split('/').at(-1);
  $('quality').textContent=data.entities?.smokeDecoded?'V8 smoke & fire preview':`${data.sampleHz} Hz · Recorded replay`;
  $('utility-presets').replaceChildren(...(data.utilityChecks || []).map(check=>{
    const button=document.createElement('button');button.textContent=check.label;button.onclick=()=>{setPlaying(false);seek(check.tick);};return button;
  }));
  const jumpExamples=data.players.flatMap(p=>p.jumpAnimations.map(j=>({...j,player:p}))).sort((a,b)=>a.start-b.start);
  const jumpExample=jumpExamples.find(j=>j.start>data.start+data.tickrate*10)||jumpExamples[0];
  if(jumpExample){
    const button=document.createElement('button');button.textContent='Replay jump';button.title='Follow one jump at half speed';
    button.onclick=()=>{seek(jumpExample.start-data.tickrate*.15);follow=jumpExample.player.id;zoom=2;
      speed=.5;$('speed').value='0.5';previewEnd=jumpExample.end+data.tickrate*.3;setPlaying(true);};
    $('utility-presets').append(button);
  }
  const note=document.querySelector('.data-note');
  note.replaceChildren(document.createTextNode(data.entities?.smokeDecoded?'Recorded fire · decoded smoke':'Recorded player movement'),document.createElement('br'));
  const detail=document.createElement('span');detail.textContent=data.entities?.smokeDecoded?'HE smoke clearing is not reproduced. See ? for limits.':'Utility shapes & ground loot are approximations.';note.append(detail);
  const shotNote=document.createElement('span');shotNote.textContent='Choose flashes or approximate directional tracers with Shot Display. Reconstructed rays are unavailable.';note.append(document.createElement('br'),shotNote);
  if(data.shotAudit){const audit=document.createElement('span');audit.textContent=`Impact check: ${data.shotAudit.firingMessages} firing messages · ${data.shotAudit.impactMessages} impact-channel messages`;note.append(document.createElement('br'),audit);}
  $('round-label').textContent=`ROUND ${String(data.round).padStart(2,'0')}`;
  $('ct-score').textContent=data.roundInfo.ct_score_before;$('t-score').textContent=data.roundInfo.t_score_before;
  $('duration').textContent=formatTime(seconds(data.end));
  const notes=data.notes.filter(n=>!n.startsWith('Shot lines require'))
    .map(n=>n.replace('No substitute hit links or direction rays have been added.',''));
  $('notes').replaceChildren(...[...notes,'Shot comparison: flashes show recorded firing. Directional tracers use recorded angles with a fixed 350-unit visual length; they omit spread and collisions and may cross walls. Reconstructed rays are unavailable until verified spread and collision data exist.','Jump scaling uses a smooth takeoff/landing animation, independent of world elevation. When recorded jump events are absent, takeoffs are conservatively inferred from an airborne ballistic rise.'].map(note=>{const li=document.createElement('li');li.textContent=note;return li;}));
  $('rounds').replaceChildren(...data.rounds.map(r=>{
    const b=document.createElement('button');b.textContent=r.round;b.dataset.side=r.winner;b.className=r.round===data.round?'selected':'';
    b.setAttribute('aria-label',`Round ${r.round}, ${r.winner} win`);b.setAttribute('aria-current',r.round===data.round?'true':'false');
    if(r.round===13)b.dataset.half='true';b.onclick=()=>{if(r.round!==data.round)loadRound(data.source,r.round);};return b;
  }));
  const keyEvents=data.events.filter(e=>['player_death','bomb_planted','bomb_defused','bomb_exploded'].includes(e.kind));
  $('event-count').textContent=keyEvents.length;
  $('event-list').replaceChildren(...keyEvents.map(e=>{const b=document.createElement('button');b.className='event';
    const time=document.createElement('time');time.textContent=formatTime(seconds(e.tick));const label=document.createElement('span');label.textContent=eventDescription(e);b.append(time,label);b.onclick=()=>seek(e.tick-replay.tickrate);return b;}));
  $('markers').replaceChildren(...keyEvents.map(e=>{const marker=document.createElement('i');marker.className=e.kind==='player_death'?'kill':'bomb';marker.style.left=`${100*(e.tick-data.start)/(data.end-data.start)}%`;return marker;}));
  makeRoster();renderUI();$('loading').hidden=true;
  // Preload unique held weapons and utility icons; no network dependencies.
  data.players.flatMap(p=>p.states).forEach(s=>{icon(s.weapon);s.inventory.forEach(icon);});
  ['he','fire','smoke','flash','decoy','c4'].forEach(icon);
  const option=[...$('match-select').options].find(o=>o.value===data.source);
  if(option)$('match-select').value=data.source;
}
async function loadRound(source,round) {
  const id=++requestId;setPlaying(false);$('loading').textContent=`Loading round ${round}…`;$('loading').hidden=false;
  try{const response=await fetch(`/api/replay?source=${encodeURIComponent(source)}&round=${round}`);
    if(!response.ok)throw new Error('Run server.py to browse other rounds in your analysis library.');
    const data=await response.json();if(id!==requestId)return;await loadReplay(data);
  }catch(e){if(id!==requestId)return;$('loading').hidden=true;alert(e.message);}
}
function deathFor(id){return replay.events.find(e=>e.kind==='player_death'&&e.user_steamid===id&&e.tick<=tick);}
function playerAt(player) {
  const location=interpolate(player.track,tick);if(!location)return null;
  const state=stateAt(player,tick), death=deathFor(player.id);
  let flash=0;
  for(const e of replay.events){if(e.kind!=='player_blind'||e.user_steamid!==player.id||e.tick>tick)continue;
    flash=Math.max(flash,clamp((e.blind_duration-(tick-e.tick)/replay.tickrate)/1.5,0,1));}
  return {...location,...state,health:death?0:state.health,dead:!!death,flash};
}
function renderUI() {
  if(!replay)return;
  const age=seconds(tick), plant=replay.events.find(e=>e.kind==='bomb_planted'&&e.tick<=tick);
  const resolved=replay.events.find(e=>['bomb_defused','bomb_exploded'].includes(e.kind)&&e.tick<=tick);
  $('clock').textContent=formatTime(plant?40-(tick-plant.tick)/replay.tickrate:115-age);
  $('clock').style.color=plant?'#efb95c':'';
  $('phase').textContent=resolved?(resolved.kind==='bomb_defused'?'BOMB DEFUSED':'BOMB EXPLODED'):tick>=replay.end?'ROUND COMPLETE':plant?'BOMB PLANTED':'LIVE ROUND';
  $('elapsed').textContent=formatTime(age);$('tick-label').textContent=`TICK ${Math.floor(tick)}`;
  const percent=100*(tick-replay.start)/(replay.end-replay.start);$('timeline').value=percent*10;$('timeline').style.setProperty('--progress',`${percent}%`);
  const alive={CT:0,T:0};
  for(const player of replay.players){const p=playerAt(player);if(!p)continue;
    if(p.health>0)alive[player.side]++;
    const n=rosterNodes.get(player.id);n.row.classList.toggle('dead',p.health<=0);n.row.classList.toggle('followed',follow===player.id);
    n.fill.style.width=`${clamp(p.health,0,100)}%`;n.money.textContent=p.money===null?'—':`$${p.money}`;
    const path=`../../assets/weapons/${weaponKey(p.weapon)}.svg`;if(n.weapon.getAttribute('src')!==path)n.weapon.src=path;
    n.weapon.title=p.weapon;n.weapon.alt=p.weapon;
    n.status.textContent=p.dead?'ELIMINATED':p.flash>.1?'BLINDED':p.flags&16?'DEFUSING':p.flags&32?'RELOAD':`${Math.round(p.health)} HP`;
    const utility=p.inventory.filter(w=>['smokegrenade','flashbang','hegrenade','molotov','incgrenade','c4','decoy'].includes(weaponKey(w)));
    const signature=utility.join('|');if(n.util.dataset.items!==signature){n.util.dataset.items=signature;n.util.replaceChildren(...utility.map(w=>{const im=document.createElement('img');im.src=`../../assets/weapons/${weaponKey(w)}.svg`;im.className='utility';im.alt=w;im.title=w;return im;}));}
  }
  for(const side of ['CT','T']){const p=replay.players.find(p=>p.side===side);if(p)rosterNodes.get(p.id).count.textContent=`${alive[side]} / 5`;}
  const feed=replay.events.filter(e=>e.kind==='player_death'&&e.tick<=tick&&tick-e.tick<replay.tickrate*8).slice(-4);
  const signature=feed.map(e=>e.tick).join();
  if(signature!==lastFeed){lastFeed=signature;$('killfeed').replaceChildren(...feed.map(e=>{const row=document.createElement('div');row.className='kill-row';
    const a=document.createElement('span');a.textContent=e.attacker_name||'World';a.style.color=colors[sideFor(e.attacker_steamid)];
    const im=document.createElement('img');im.src=`../../assets/weapons/${weaponKey(e.weapon)}.svg`;im.alt=e.weapon;
    const b=document.createElement('span');b.textContent=e.user_name||'Player';b.style.color=colors[sideFor(e.user_steamid)];
    row.append(a,im,b);if(e.headshot==='True'){const hs=document.createElement('span');hs.textContent='⊕';row.append(hs);}
    return row;}));}
}
function drawGrenades() {
  const rate=replay.tickrate;
  for(const g of replay.grenades){
    if(tick<g.throw_tick)continue;
    const color={smoke:'#b5c3bd',fire:'#f0a53c',he:'#b3c87e',flash:'#f6f0c5',decoy:'#9c93ca'}[g.kind];
    const det=g.det_tick||g.path.at(-1)?.[0]||g.throw_tick;
    const age=(tick-det)/rate;
    if(tick<=det&&g.path.length){
      const pts=g.path.filter(p=>p[0]<=tick),j=Math.max(0,upperBound(g.path,tick)-1),a=g.path[j],b=g.path[j+1]||a;
      const f=a===b?0:clamp((tick-a[0])/(b[0]-a[0]),0,1);const current=[tick,lerp(a[1],b[1],f),lerp(a[2],b[2],f),lerp(a[3],b[3],f)];
      if(trails&&pts.length){ctx.beginPath();[...pts,current].forEach((p,i)=>{const s=screen(p[1],p[2]);if(i)ctx.lineTo(...s);else ctx.moveTo(...s);});ctx.strokeStyle=color+'aa';ctx.lineWidth=1.3;ctx.stroke();}
      const [x,y]=screen(current[1],current[2]);circle(x,y,5,'#18232a',color,1.5);drawIcon(g.kind,x,y,9,9);continue;
    }
    if(!g.detonated||age<0)continue;
    if(g.kind==='fire'&&replay.entities)continue;
    if(g.kind==='smoke'&&replay.entities?.smokeDecoded)continue;
    const [x,y]=screen(g.land_x,g.land_y);
    const expireKind=g.kind==='smoke'?'smokegrenade_expired':'inferno_expire';
    const expiry=replay.events.find(e=>e.kind===expireKind&&e.tick>=det&&Math.hypot((e.x??1e9)-g.land_x,(e.y??1e9)-g.land_y)<180);
    const lifetime=expiry?(expiry.tick-det)/rate:g.kind==='smoke'?20:g.kind==='fire'?7:1;
    if(age>lifetime)continue;
    if(g.kind==='smoke'){
      const {envelope}=smokeOpacity(age,lifetime,0,false);const radius=unit(145)*Math.min(1,age/.8);
      // Composite smoke in its own layer so an HE hole reveals the map, not a black patch.
      if(!smokeLayers.has(g.throw_id))smokeLayers.set(g.throw_id,document.createElement('canvas'));
      const layer=smokeLayers.get(g.throw_id),dimension=Math.max(1,Math.ceil(radius*2+12));
      if(layer.width!==dimension){layer.width=layer.height=dimension;}
      const c=layer.getContext('2d'),cx=layer.width/2;c.clearRect(0,0,dimension,dimension);c.globalCompositeOperation='source-over';
      for(let i=0;i<10;i++){const angle=i*2.39996,r=radius*.45*Math.sqrt(i/10),px=cx+Math.cos(angle)*r,py=cx+Math.sin(angle)*r;
        const gradient=c.createRadialGradient(px,py,0,px,py,radius*.65);gradient.addColorStop(0,`rgba(180,191,183,${.22*envelope})`);gradient.addColorStop(.6,`rgba(151,164,154,${.17*envelope})`);gradient.addColorStop(1,'rgba(141,156,149,0)');c.fillStyle=gradient;c.fillRect(0,0,layer.width,layer.height);}
      for(const he of replay.grenades.filter(h=>h.kind==='he'&&h.detonated)){
        const heAge=(tick-he.det_tick)/rate;if(heAge<0||heAge>3.2)continue;
        const distance=Math.hypot(he.land_x-g.land_x,he.land_y-g.land_y);if(distance>350)continue;
        const {hole}=smokeOpacity(age,lifetime,heAge,true),[hx,hy]=screen(he.land_x,he.land_y);c.globalCompositeOperation='destination-out';
        const hr=unit(170)*Math.min(1,heAge/.15),grad=c.createRadialGradient(cx+hx-x,cx+hy-y,0,cx+hx-x,cx+hy-y,Math.max(.1,hr));
        grad.addColorStop(0,`rgba(0,0,0,${Math.min(1,hole*3)})`);grad.addColorStop(.65,`rgba(0,0,0,${hole})`);grad.addColorStop(1,'transparent');c.fillStyle=grad;c.fillRect(0,0,layer.width,layer.height);
      }
      ctx.drawImage(layer,x-cx,y-cx);
    }else if(g.kind==='fire'){
      const grow=clamp(age/.9,0,1),fade=clamp((lifetime-age)/1.4,0,1),radius=unit(130)*grow;
      for(let i=0;i<19;i++){const angle=i*2.39996,r=radius*.8*Math.sqrt(i/19),px=x+Math.cos(angle)*r,py=y+Math.sin(angle)*r;
        const rr=radius*(.20+.035*Math.sin(age*9+i));const grad=ctx.createRadialGradient(px,py,0,px,py,Math.max(.1,rr));
        grad.addColorStop(0,`rgba(255,203,86,${.7*fade})`);grad.addColorStop(.55,`rgba(239,109,26,${.48*fade})`);grad.addColorStop(1,'rgba(239,74,15,0)');ctx.fillStyle=grad;ctx.fillRect(px-rr,py-rr,rr*2,rr*2);}
    }else if(age<.65){ctx.save();ctx.globalAlpha=1-age/.65;circle(x,y,unit(g.kind==='he'?100:85)*Math.min(1,age*5),g.kind==='he'?'#efb96536':'#fffbdc26',color,1);ctx.restore();}
  }
}
function drawShots() {
  const lifetime=.20;
  for(const shot of replay.shots||[]){
    const age=(tick-shot.tick)/replay.tickrate;if(age<0||age>=lifetime)continue;
    const [x,y]=screen(shot.origin[0],shot.origin[1]);
    const brightness=Math.pow(1-age/lifetime,2.6);
    const light=(r,g,b)=>`rgb(${Math.round(r*brightness)},${Math.round(g*brightness)},${Math.round(b*brightness)})`;
    // Add emitted light to the map. RGB intensity decays; opacity stays fixed.
    ctx.save();ctx.globalAlpha=1;ctx.globalCompositeOperation='lighter';ctx.lineCap='round';
    const endpoint=$('shot-style').value==='direction'?directionEndpoint(shot):null;
    if(endpoint){
      const [ex,ey]=screen(endpoint[0],endpoint[1]);
      ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(ex,ey);
      // A diffuse halo surrounds the narrower, nearly white hot core.
      ctx.filter='blur(8px)';ctx.strokeStyle=light(140,92,30);ctx.lineWidth=6;ctx.stroke();
      ctx.filter='blur(3px)';ctx.strokeStyle=light(220,174,85);ctx.lineWidth=3;ctx.stroke();
      ctx.filter='blur(1px)';ctx.strokeStyle=light(240,226,185);ctx.lineWidth=1.4;ctx.stroke();
    }
    ctx.filter='blur(7px)';circle(x,y,7,light(125,85,30));
    ctx.filter='blur(1.5px)';circle(x,y,3,light(235,220,180));ctx.restore();
  }
}
function updateShotStatus(){
  const directional=$('shot-style').value==='direction';
  const missing=(replay.shots||[]).filter(s=>!directionEndpoint(s)).length;
  $('shot-status').textContent=directional
    ? `Approximate direction · fixed 350-unit length · no impact or spread correction.${missing?` ${missing} shots lack angles and show flashes only.`:''}`
    : 'Recorded firing time and origin · no bullet path shown.';
}
$('shot-style').onchange=()=>{if(replay)updateShotStatus();};
$('replay-shots').onclick=()=>{
  const shot=comparisonShot(replay.shots,replay.tickrate);if(!shot)return;
  seek(shot.tick-replay.tickrate*.5);follow=shot.shooter;zoom=2;
  speed=.5;$('speed').value='0.5';previewEnd=Math.min(replay.end,shot.tick+replay.tickrate*4.5);setPlaying(true);
};
function drawGround() {
  if(replay.entities){for(const state of entityStatesAt(replay.entities.loot,tick).values()){
    const [x,y]=screen(state.x,state.y);drawIcon(state.item,x,y,21,13,.8);
  }}
  if(!replay.entities)for(const e of replay.events){if(e.tick>tick)break;
    if(e.kind==='player_death'){
      const p=replay.players.find(p=>p.id===e.user_steamid);if(!p)continue;const s=stateAt(p,e.tick-1);
      const items=[s.weapon,...s.inventory].map(weaponKey).filter((v,i,a)=>a.indexOf(v)===i&&v!=='knife'&&v!=='c4');
      items.slice(0,5).forEach((item,i)=>{
        const picked=replay.events.some(p=>p.kind==='item_pickup'&&p.tick>e.tick&&p.tick<=tick&&weaponKey(p.item)===item&&Math.hypot((p.user_X??1e9)-e.user_X,(p.user_Y??1e9)-e.user_Y)<160);
        if(!picked){const [x,y]=screen(e.user_X,e.user_Y);drawIcon(item,x+((i%3)-1)*15,y+15+Math.floor(i/3)*12,18,10,.55);}
      });
    }
  }
  const bombEvents=replay.events.filter(e=>e.kind.startsWith('bomb_')&&e.tick<=tick&&['bomb_dropped','bomb_pickup','bomb_planted','bomb_defused','bomb_exploded'].includes(e.kind));
  const bomb=bombEvents.at(-1);
  if(bomb&&(bomb.kind==='bomb_planted'||bomb.kind==='bomb_dropped'&&!replay.entities)&&bomb.user_X!==undefined){const [x,y]=screen(bomb.user_X,bomb.user_Y);if(bomb.kind==='bomb_planted')circle(x,y,15+Math.sin(seconds(tick)*7)*3,'#eeb34d15','#efbc6866');drawIcon('c4',x,y,20,20);}
}

function drawRecordedUtilities(){
  if(!replay.entities)return;
  for(const fire of entityStatesAt(replay.entities.fire,tick).values()){
    const key=`${fire.id}:${fire.tick}`;
    if(!firePaths.has(key)){
      const mesh=fireMesh(fire.patches),path=new Path2D();
      for(const patch of mesh.points){path.moveTo(patch.x+22,patch.y);path.arc(patch.x,patch.y,22,0,Math.PI*2);path.closePath();}
      for(const face of mesh.triangles){
        face.forEach((i,k)=>{const p=mesh.points[i];if(k)path.lineTo(p.x,p.y);else path.moveTo(p.x,p.y);});path.closePath();
      }
      for(const [a,b] of mesh.links){
        const p=mesh.points[a],q=mesh.points[b],length=Math.hypot(q.x-p.x,q.y-p.y);
        const dx=-(q.y-p.y)/length*16,dy=(q.x-p.x)/length*16;
        path.moveTo(p.x+dx,p.y+dy);path.lineTo(p.x-dx,p.y-dy);path.lineTo(q.x-dx,q.y-dy);path.lineTo(q.x+dx,q.y+dy);path.closePath();
      }
      if(firePaths.size>512)firePaths.clear();firePaths.set(key,{path,points:mesh.points});
    }
    const {path,points}=firePaths.get(key),[ox,oy]=screen(0,0),scale=unit(1);
    ctx.save();ctx.translate(ox,oy);ctx.scale(scale,-scale);
    // One nonzero fill composites the union once, avoiding bright overlap seams.
    ctx.shadowColor='#ff7211';ctx.shadowBlur=8;ctx.fillStyle='#ef7e22cc';ctx.fill(path);ctx.shadowBlur=0;
    ctx.clip(path);
    for(const p of points){
      const radius=36+4*Math.sin(seconds(tick)*5+(p.index||0)),gradient=ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,radius);
      gradient.addColorStop(0,'#ffe7a566');gradient.addColorStop(.55,'#ffbd4c40');gradient.addColorStop(1,'#ff871000');
      ctx.fillStyle=gradient;ctx.fillRect(p.x-radius,p.y-radius,radius*2,radius*2);
    }
    ctx.restore();
  }
  for(const smoke of entityStatesAt(replay.entities.smoke,tick).values()){
    const opacity=smoke.fading?clamp(1-(tick-smoke.tick)/replay.tickrate/2,0,1):1;
    if(!opacity)continue;
    const key=`${smoke.id}:${smoke.tick}`;
    if(!voxelImages.has(key)){
      const image=document.createElement('canvas');image.width=image.height=256;
      const c=image.getContext('2d'),pixels=c.createImageData(32,32),depth=new Uint8Array(1024);
      for(let i=0;i<smoke.occupied.length;i+=2){
        const start=smoke.occupied[i],end=start+smoke.occupied[i+1];
        for(let index=start;index<end;index++)depth[index&1023]++;
      }
      for(let y=0;y<32;y++)for(let x=0;x<32;x++){
        const count=depth[x+y*32],offset=(x+(31-y)*32)*4;
        pixels.data[offset]=174;pixels.data[offset+1]=188;pixels.data[offset+2]=191;
        pixels.data[offset+3]=count?Math.round(Math.min(.98,.65+Math.sqrt(count)*.075)*255):0;
      }
      const mask=document.createElement('canvas');mask.width=mask.height=32;mask.getContext('2d').putImageData(pixels,0,0);
      c.filter='blur(6px)';c.drawImage(mask,0,0,256,256);c.filter='none';
      // Deterministic billow shading preserves the recorded silhouette and seeking.
      const texture=document.createElement('canvas');texture.width=texture.height=256;
      const tc=texture.getContext('2d'),shade=tc.createImageData(256,256);
      const layers=[4,8,16].map((n,octave)=>{
        const values=Array.from({length:(n+1)**2},(_,i)=>{const v=Math.sin(i*127.1+octave*311.7+43)*43758.5453;return v-Math.floor(v);});
        return (x,y)=>{const gx=x/256*n,gy=y/256*n,ix=Math.floor(gx),iy=Math.floor(gy),fx=gx-ix,fy=gy-iy;
          const sx=fx*fx*(3-2*fx),sy=fy*fy*(3-2*fy),offset=ix+iy*(n+1);
          return lerp(lerp(values[offset],values[offset+1],sx),lerp(values[offset+n+1],values[offset+n+2],sx),sy);};
      });
      for(let y=0;y<256;y++)for(let x=0;x<256;x++){
        const density=.55*layers[0](x,y)+.30*layers[1](x,y)+.15*layers[2](x,y);
        const value=125+108*Math.pow(density,.8);
        const offset=(x+y*256)*4;shade.data[offset]=value;shade.data[offset+1]=value+7;shade.data[offset+2]=value+12;shade.data[offset+3]=255;
      }
      tc.putImageData(shade,0,0);c.globalCompositeOperation='source-atop';c.drawImage(texture,0,0);
      c.globalCompositeOperation='source-over';
      if(voxelImages.size>256)voxelImages.clear();voxelImages.set(key,image);
    }
    const [x,y]=screen(smoke.x-192,smoke.y+192),extent=unit(384);
    ctx.save();ctx.globalAlpha=opacity;ctx.imageSmoothingEnabled=true;ctx.shadowColor='#c6d8e066';ctx.shadowBlur=5;
    ctx.drawImage(voxelImages.get(key),x,y,extent,extent);ctx.restore();
  }
}
function drawPlayer(player,p) {
  const [x,y]=screen(p.x,p.y),base=colors[player.side]||colors.CT;
  if(p.dead){ctx.strokeStyle=base+'77';ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(x-4,y-4);ctx.lineTo(x+4,y+4);ctx.moveTo(x-4,y+4);ctx.lineTo(x+4,y-4);ctx.stroke();return;}
  const jump=jumpAmount(player.jumpAnimations,tick);
  const radius=lerp(8.3,7,crouchAmount(player.track,tick))*(1+jump*.32);
  circle(x+1,y+3+6*jump,radius+2,'#00000065');
  if(follow===player.id){circle(x,y,radius+8,null,base+'77');}
  const angle=-p.yaw*Math.PI/180;
  ctx.save();ctx.translate(x,y);ctx.rotate(angle);ctx.beginPath();ctx.moveTo(radius+8,0);ctx.lineTo(radius*.4,-radius*.72);ctx.lineTo(radius*.4,radius*.72);ctx.closePath();ctx.fillStyle=base;ctx.fill();ctx.restore();
  circle(x,y,radius,base,'#071018',2);
  if(p.flash){circle(x,y,radius-1,`rgba(255,255,255,${p.flash*.95})`);}
  drawIcon(p.weapon,x,y,Math.max(13,radius*1.9),radius*1.15);
  if((p.flags&1)&&['awp','ssg08','scar20','g3sg1'].includes(weaponKey(p.weapon))){
    circle(x+radius+4,y-radius-3,5,'#101c28','#d9efff',1);ctx.strokeStyle='#e0f4ff';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x+radius+1,y-radius-3);ctx.lineTo(x+radius+7,y-radius-3);ctx.moveTo(x+radius+4,y-radius-6);ctx.lineTo(x+radius+4,y-radius);ctx.stroke();
  }
  if(p.flags&16){circle(x,y,radius+4,null,'#a8e9d3',2);}
  if(names){ctx.font='500 10px "Segoe UI",sans-serif';const label=player.name,w=ctx.measureText(label).width+13,h=17,lx=x-w/2,ly=y-radius-25;
    ctx.save();ctx.beginPath();ctx.roundRect(lx,ly,w,h,5);ctx.clip();ctx.fillStyle='#13202ee8';ctx.fillRect(lx,ly,w,h);ctx.fillStyle=base+'88';ctx.fillRect(lx,ly,w*clamp(p.health/100,0,1),h);ctx.fillStyle='#f0f6fb';ctx.textAlign='center';ctx.fillText(label,x,ly+12);ctx.restore();}
  hitboxes.push({id:player.id,x,y,r:radius+8});
}
function render() {
  ctx.clearRect(0,0,width,height);if(!replay)return;
  const size=Math.min(width-100,height-40)*zoom;let x=(width-size)/2+pan[0],y=(height-size)/2+pan[1]+14;
  if(follow){const player=replay.players.find(p=>p.id===follow),p=player&&playerAt(player);if(p){const pos=point(p.x,p.y);x=width/2-pos[0]*size/1024;y=height/2-pos[1]*size/1024;}}
  view={size,x,y};
  if(mapReady){ctx.save();ctx.globalAlpha=.85;ctx.filter='grayscale(1) brightness(.86)';ctx.drawImage(mapImage,x,y,size,size);ctx.restore();}
  // Multiple floors can be selected from the map toolbar on maps with a lower radar.
  if(lowerReady&&$('reset').dataset.floor==='lower'){ctx.save();ctx.globalAlpha=.88;ctx.drawImage(lowerImage,x,y,size,size);ctx.restore();}
  hitboxes=[];drawGrenades();drawRecordedUtilities();drawGround();
  for(const player of replay.players){const p=playerAt(player);if(p)drawPlayer(player,p);}
  drawShots();
}
function animate(now) {
  const delta=previousTime?Math.min((now-previousTime)/1000,.15):0;previousTime=now;
  if(replay&&playing){tick=clamp(tick+delta*speed*replay.tickrate,replay.start,replay.end);
    if(previewEnd!==null&&tick>=previewEnd){tick=previewEnd;setPlaying(false);}
    if(tick===replay.end)setPlaying(false);}
  render();if(now-lastUI>75){renderUI();lastUI=now;}requestAnimationFrame(animate);
}
new ResizeObserver(()=>{const rect=canvas.getBoundingClientRect();width=rect.width;height=rect.height;const dpr=window.devicePixelRatio||1;canvas.width=width*dpr;canvas.height=height*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);}).observe(canvas);
$('play').onclick=()=>{if(!replay)return;if(tick>=replay.end)seek(replay.start);setPlaying(!playing);};
$('back').onclick=()=>replay&&seek(tick-replay.tickrate*5);
$('speed').onchange=e=>speed=Number(e.target.value);
$('timeline').oninput=e=>replay&&seek(replay.start+Number(e.target.value)/1000*(replay.end-replay.start));
$('timeline').onpointermove=e=>{if(!replay)return;const rect=e.target.getBoundingClientRect(),f=clamp((e.clientX-rect.left)/rect.width,0,1);$('hover-time').style.display='block';$('hover-time').style.left=`${f*100}%`;$('hover-time').textContent=formatTime(f*seconds(replay.end));};
$('timeline').onpointerleave=()=>$('hover-time').style.display='none';
$('names').onclick=()=>{names=!names;$('names').classList.toggle('active',names);$('names').setAttribute('aria-pressed',names);};
$('trails').onclick=()=>{trails=!trails;$('trails').classList.toggle('active',trails);$('trails').setAttribute('aria-pressed',trails);};
$('zoom-in').onclick=()=>zoom=clamp(zoom*1.2,.65,4);$('zoom-out').onclick=()=>zoom=clamp(zoom/1.2,.65,4);
$('reset').onclick=e=>{zoom=1;pan=[0,0];follow=null;if(e.shiftKey&&lowerReady){const b=$('reset');b.dataset.floor=b.dataset.floor==='lower'?'upper':'lower';b.title=`${b.dataset.floor} floor · Shift-click to switch`;}};
$('fullscreen').onclick=()=>{if(document.fullscreenElement)document.exitFullscreen();else document.documentElement.requestFullscreen?.();};
$('help').onclick=()=>$('help-dialog').showModal();$('close-help').onclick=()=>$('help-dialog').close();
canvas.addEventListener('wheel',e=>{e.preventDefault();const old=zoom;zoom=clamp(zoom*Math.exp(-e.deltaY*.001),.65,4);if(!follow){const rect=canvas.getBoundingClientRect(),mx=e.clientX-rect.left-width/2,my=e.clientY-rect.top-height/2;pan=[mx-(mx-pan[0])*zoom/old,my-(my-pan[1])*zoom/old];}},{passive:false});
canvas.onpointerdown=e=>{drag={x:e.clientX,y:e.clientY,pan:[...pan],moved:false};canvas.setPointerCapture(e.pointerId);};
canvas.onpointermove=e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.hypot(dx,dy)>4){drag.moved=true;follow=null;pan=[drag.pan[0]+dx,drag.pan[1]+dy];}};
canvas.onpointerup=e=>{if(drag&&!drag.moved){const rect=canvas.getBoundingClientRect(),x=e.clientX-rect.left,y=e.clientY-rect.top;const p=hitboxes.find(p=>Math.hypot(p.x-x,p.y-y)<p.r);if(p)follow=follow===p.id?null:p.id;}drag=null;};canvas.onpointercancel=()=>drag=null;
window.onkeydown=e=>{if(['INPUT','SELECT','BUTTON'].includes(document.activeElement.tagName)||$('help-dialog').open||!replay)return;
  if(e.code==='Space'){e.preventDefault();$('play').click();}if(e.key==='ArrowLeft'){e.preventDefault();seek(tick-replay.tickrate*5);}if(e.key==='ArrowRight'){e.preventDefault();seek(tick+replay.tickrate*5);}if(e.key==='Home'){e.preventDefault();seek(replay.start);}if(e.key==='End'){e.preventDefault();seek(replay.end);}
};
$('match-select').onchange=e=>loadRound(e.target.value,1);
async function boot(){
  try{const requested=new URLSearchParams(location.search).get('sample');
    const sample=requested&&/^[a-zA-Z0-9_-]+\.json$/.test(requested)?requested:'example-round.json';
    const response=await fetch(`./${sample}`);if(!response.ok)throw new Error('Export a round with replay.py before opening the viewer.');await loadReplay(await response.json());
    const option=document.createElement('option');option.value=replay.source;option.textContent=replay.source.split('/').at(-1);$('match-select').replaceChildren(option);
    $('match-select').disabled=!!replay.previewOnly;if(replay.previewOnly)return;
    try{const r=await fetch('/api/matches');if(r.ok){catalog=await r.json();$('match-select').replaceChildren(...catalog.map(m=>{const o=document.createElement('option');o.value=m.source;o.textContent=m.name;return o;}));$('match-select').value=replay.source;}}catch{/* Exported round still works on a static server. */}
  }catch(e){$('loading').textContent=e.message;}
}
requestAnimationFrame(animate);boot();
