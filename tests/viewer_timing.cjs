/* Drive the actual viewer with a deterministic DOM/canvas and animation clock. */
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const jobs=new Map();let next=1;
const labels=[];
const ctx=new Proxy({measureText:s=>({width:s.length*8}),createRadialGradient:()=>({addColorStop(){}}),
  fillText:s=>labels.push(s)}, {get:(o,k)=>k in o?o[k]:(()=>{})});
function el(extra={}){return Object.assign({listeners:{},innerHTML:'',textContent:'',dataset:{},
  addEventListener(k,f){this.listeners[k]=f},setAttribute(){},classList:{contains:()=>false,add(){},remove(){}}},extra)}
const range=el({value:0}),play=el(),roster=el(),time=el(),utility=el();
const player={sid:'1',side:'CT',me:true,name:'Player',xy:Array.from({length:34},()=>0),
  hp:[100,50,0],ar:[1,1,0],wp:[0,1,-1],fl:[0,0,0],aim:[]};
const data={map:'map',t0:0,dt:1/16,n:17,st0:0,sdt:.5,sn:3,facing:false,players:[player],
  weapons:['AK-47','M4A1-S'],wi:['rifle','rifle'],wa:['ak47','m4a1_silencer'],
  kills:[{t:.4,vsid:'1',a:'Other',v:'Player',vs:'CT'}],
  nades:[{t:0,d:1,k:'smoke',x:0,y:0,duration_recorded:false}],end:1,focus:null};
const parts={'script[type="application/json"]':el({textContent:JSON.stringify(data)}),
  canvas:el({width:640,height:640,clientWidth:640,getContext:()=>ctx}),
  'input[type=range]':range,'.v-play':play,'.v-time':time,select:el({value:'1'}),
  '.v-roster':roster,'.v-utility':utility,'.v-feed':el(),'.v-marks':null,'.v-jump':null,'.v-next':null,'.v-prev':null,'.v-expand':null};
const root=el({querySelector:s=>parts[s],querySelectorAll:()=>[],closest:()=>null});
class Image{constructor(){this.complete=true;this.naturalWidth=100;this.naturalHeight=30}set src(x){}}
const document=el({hidden:false,querySelectorAll:()=>[root]});
const sandbox={window:{__MAPS:{map:{img:'image',w:640,h:640,x0:0,y0:0,s:1}},__WEAPONS:{}},
  document,Image,requestAnimationFrame:f=>{const id=next++;jobs.set(id,f);return id},
  cancelAnimationFrame:id=>jobs.delete(id)};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/cs2di/report/viewer.js'),'utf8'),sandbox);
const click=()=>play.listeners.click();
click();click();click();assert.equal(jobs.size,1,'rapid pause/resume must leave one animation loop');
function frame(ts){const pending=[...jobs.values()];jobs.clear();pending.forEach(f=>f(ts))}
frame(1000);frame(1100);assert(Math.abs(Number(range.value)-.1)<1e-8,'playback must advance once per frame');
range.value=.3;range.listeners.input();assert.equal(jobs.size,0,'scrubbing pauses and cancels playback');
assert(roster.innerHTML.includes('AK-47')&&!roster.innerHTML.includes('M4A1-S'),'future weapon state must not appear early');
assert(utility.innerHTML.includes('Smoke ~0.7s'),'estimated utility countdown must be explicit');
range.value=.4;range.listeners.input();assert(roster.innerHTML.includes('0 alive'),'death must occur at event time');
click();document.hidden=true;document.listeners.visibilitychange();assert.equal(jobs.size,0,'hidden pages pause');
data.st0=.2;parts['script[type="application/json"]'].textContent=JSON.stringify(data);delete root._init;
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/cs2di/report/viewer.js'),'utf8'),sandbox);
assert(!roster.innerHTML.includes('AK-47')&&roster.innerHTML.includes('hpn">?</span>'),'state before first measurement must be unknown');
console.log('PASS: one animation loop, elapsed time, past-only state, exact death, countdown, hidden-page pause');
