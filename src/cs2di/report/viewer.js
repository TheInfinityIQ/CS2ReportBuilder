/* 2D round viewer (v3.4). Everything drawn comes from the demo:
   - facing: recorded 8 Hz view angle when data.facing, else recorded aim events (held AIM_HOLD s), else movement tail, else a plain dot
   - grenades: real projectile path when n.pa exists, else a straight line between the recorded throw and landing spots
   Heading is stateless: it depends only on the data at time t, never on how the viewer got there. */
(function(){
const COL={CT:'#3f8fe0',T:'#e39a35'}, EDGE={CT:'#173f73',T:'#7a4a0c'}, RGB={CT:'63,143,224',T:'227,154,53'};
const PILL={CT:'rgba(24,52,92,.92)',T:'rgba(96,58,10,.92)'};
const TXT={CT:'#8fc3f5',T:'#f5c27a'};
const AIM_HOLD=1.5;            /* one constant for the recorded-aim cone and the recorded-aim pin */
const NARROW=460;              /* below this displayed width (css px) no weapon glyphs are drawn */
function fmt(t){t=Math.max(0,t);return Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0');}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}

function initViewer(root){
  if(root._init) return; root._init=true;
  const data=JSON.parse(root.querySelector('script[type="application/json"]').textContent);
  const bg=window.__MAPS[data.map]; const cv=root.querySelector('canvas'); const ctx=cv.getContext('2d');
  const img=new Image(); img.src=bg.img; cv.width=bg.w; cv.height=bg.h;
  const P=(x,y)=>[(x-bg.x0)/bg.s,(bg.y0-y)/bg.s];
  const range=root.querySelector('input[type=range]'), btn=root.querySelector('.v-play'), lab=root.querySelector('.v-time'), spd=root.querySelector('select');
  const rosterEl=root.querySelector('.v-roster'), feed=root.querySelector('.v-feed'), marks=root.querySelector('.v-marks');
  const T=data.t0+(data.n-1)*data.dt; range.max=T;
  let t=Math.max(0,(data.focus==null?0:data.focus-8)); let playing=false, last=0;
  const R=Math.max(5,bg.w/110), W=cv.width, H=cv.height;
  const layer={names:true,facing:true,util:true,feed:true};
  let rosterHtml='';

  const clampT=x=>Math.max(data.t0,Math.min(T,x));
  const clampS=x=>Math.max(data.st0,Math.min(data.st0+(data.sn-1)*data.sdt,x));
  function fIx(tt){return Math.max(0,Math.min(data.n-1,Math.round((tt-data.t0)/data.dt)));}      /* position / facing grid */
  function sIx(tt){return Math.max(0,Math.min(data.sn-1,Math.round((tt-data.st0)/data.sdt)));}   /* health / item grid */
  function posAt(p,tt){const f=(clampT(tt)-data.t0)/data.dt, i=Math.floor(f), j=Math.min(i+1,data.n-1);
    const a=[p.xy[2*i],p.xy[2*i+1]], b=[p.xy[2*j],p.xy[2*j+1]];
    if(a[0]==null) return null; if(b[0]==null) return a; const k=f-i; return [a[0]+(b[0]-a[0])*k,a[1]+(b[1]-a[1])*k];}
  function scale(){return Math.min(2.4,cv.width/Math.max(1,cv.clientWidth||cv.width));}   /* canvas px per css px: keeps labels a fixed on-screen size */

  /* ---- facing (stateless) ---- */
  function lastAim(p,tt){let r=null; for(const a of p.aim){ if(a[0]<=tt) r=a; else break; } return r;}
  function yawAt(p,tt){ /* recorded 8 Hz yaw, circular interpolation */
    const f=(clampT(tt)-data.t0)/data.dt, i=Math.floor(f), j=Math.min(i+1,data.n-1), a=p.yw[i], b=p.yw[j];
    if(a==null&&b==null) return null; if(a==null) return b; if(b==null||i===j) return a;
    let d=((b-a+540)%360)-180; return a+d*(f-i);}
  function facing(p,tt){
    if(data.facing&&p.yw){const y=yawAt(p,tt); return y==null?null:{th:-y*Math.PI/180,src:'real'};}
    const a=lastAim(p,tt);
    if(a&&tt-a[0]<=AIM_HOLD) return {th:-a[1]*Math.PI/180,src:'aim',age:tt-a[0]};
    const A=posAt(p,tt-data.dt), B=posAt(p,tt+data.dt);
    if(A&&B){const [ax,ay]=P(A[0],A[1]),[bx,by]=P(B[0],B[1]); if(Math.hypot(bx-ax,by-ay)>1.2) return {th:Math.atan2(by-ay,bx-ax),src:'move'};}
    return null;
  }

  /* ---- drawing helpers ---- */
  function rr(x,y,w,h,r){ctx.beginPath();ctx.moveTo(x+r,y);ctx.arcTo(x+w,y,x+w,y+h,r);ctx.arcTo(x+w,y+h,x,y+h,r);ctx.arcTo(x,y+h,x,y,r);ctx.arcTo(x,y,x+w,y,r);ctx.closePath();}
  function glyph(c,x,y,w,h,col){ /* category icon (the kind of item, not the exact model) in box left=x, centre=y */
    ctx.fillStyle=col; ctx.strokeStyle=col; ctx.lineWidth=Math.max(1,h*.13);
    const F=(a,b,cw,ch)=>ctx.fillRect(x+w*a,y+h*b,w*cw,h*ch);
    const poly=pts=>{ctx.beginPath();pts.forEach((q,i)=>i?ctx.lineTo(x+w*q[0],y+h*q[1]):ctx.moveTo(x+w*q[0],y+h*q[1]));ctx.closePath();ctx.fill();};
    const ball=(cx,cy,r)=>{ctx.beginPath();ctx.arc(x+w*cx,y+h*cy,h*r,0,7);ctx.fill();};
    if(c==='rifle'){F(0,-.05,.22,.32);F(.14,-.2,.42,.34);F(.5,-.13,.5,.16);poly([[.36,.12],[.5,.12],[.44,.5],[.32,.5]]);}
    else if(c==='sniper'){F(0,-.05,.2,.3);F(.14,-.16,.4,.3);F(.5,-.1,.5,.13);F(.3,-.36,.3,.14);poly([[.36,.1],[.48,.1],[.44,.42],[.34,.42]]);}
    else if(c==='lmg'){F(0,-.05,.2,.3);F(.14,-.2,.44,.36);F(.5,-.13,.5,.15);F(.3,.12,.26,.34);}
    else if(c==='smg'){F(.1,-.18,.5,.34);F(.55,-.1,.32,.14);poly([[.3,.14],[.44,.14],[.4,.5],[.28,.5]]);F(0,-.02,.14,.2);}
    else if(c==='shotgun'){F(0,-.05,.2,.3);F(.15,-.16,.3,.28);F(.4,-.16,.6,.11);F(.4,-.02,.5,.1);}
    else if(c==='pistol'){F(.2,-.3,.6,.26);poly([[.22,-.05],[.42,-.05],[.36,.5],[.2,.5]]);}
    else if(c==='knife'){poly([[.05,.35],[.62,-.4],[.95,-.42],[.5,.05],[.2,.42]]);}
    else if(c==='smoke'){ctx.fillStyle='#c9ced6';ball(.5,.05,.42);ctx.fillStyle='#8a919c';F(.4,-.62,.2,.2);}
    else if(c==='flash'){ctx.fillStyle='#f4f6fb';ball(.5,.08,.4);ctx.fillStyle='#9aa3b2';F(.42,-.58,.16,.22);}
    else if(c==='he'){ctx.fillStyle='#8ea05a';ball(.5,.08,.4);ctx.fillStyle='#d9d9c8';F(.42,-.58,.16,.22);}
    else if(c==='fire'){ctx.fillStyle='#ff9a3c';poly([[.5,-.5],[.85,.1],[.7,.5],[.3,.5],[.15,.1]]);}
    else if(c==='decoy'){ctx.fillStyle='#b8b8b8';ball(.5,.08,.36);}
    else if(c==='zeus'){ctx.fillStyle='#ffe066';poly([[.55,-.5],[.2,.1],[.48,.1],[.4,.5],[.8,-.1],[.5,-.1]]);}
    else if(c==='c4'){ctx.fillStyle='#ff5c5c';F(.15,-.3,.7,.6);ctx.fillStyle='#fff';F(.25,-.15,.5,.1);}
    else { /* gear / unknown: plain rounded box, never a guess at a weapon */
      ctx.globalAlpha=.85;rr(x+w*.2,y-h*.32,w*.6,h*.64,h*.12);ctx.stroke();ctx.globalAlpha=1;}
  }
  function cloud(x,y,r,a){ctx.fillStyle='rgba(255,255,255,'+a+')';
    [[-.5,.1,.42],[.1,-.15,.55],[.6,.1,.4]].forEach(function(c){ctx.beginPath();ctx.arc(x+r*c[0],y+r*c[1],r*c[2],0,7);ctx.fill();});}
  function flame(x,y,r,a){ctx.beginPath();ctx.moveTo(x,y-r);ctx.bezierCurveTo(x+r*.95,y-r*.15,x+r*.7,y+r*.9,x,y+r*.9);
    ctx.bezierCurveTo(x-r*.7,y+r*.9,x-r*.95,y-r*.15,x,y-r);ctx.fillStyle='rgba(255,240,180,'+a+')';ctx.fill();}
  function star(x,y,r1,r2,n,a,col){ctx.beginPath();for(let i=0;i<n*2;i++){const r=i%2?r2:r1,th=i*Math.PI/n;ctx.lineTo(x+Math.cos(th)*r,y+Math.sin(th)*r);}ctx.closePath();ctx.fillStyle=col+a+')';ctx.fill();}
  function pin(x,y,th,fill,edge,me){ /* th==null: plain dot (facing unknown) */
    const D=R*2.7, al=Math.acos(R/D); ctx.beginPath();
    if(th==null){ctx.arc(x,y,R,0,7);}
    else{ctx.moveTo(x+Math.cos(th)*D,y+Math.sin(th)*D);ctx.lineTo(x+Math.cos(th+al)*R,y+Math.sin(th+al)*R);
      ctx.arc(x,y,R,th+al,th-al+Math.PI*2,false);ctx.closePath();}
    ctx.fillStyle=fill;ctx.fill();ctx.lineJoin='round';ctx.lineWidth=me?R*.42:R*.24;ctx.strokeStyle=me?'#fff':edge;ctx.stroke();
    ctx.beginPath();ctx.arc(x,y,R*.4,0,7);ctx.fillStyle='rgba(255,255,255,.95)';ctx.fill();
  }
  function tail(x,y,th,col){ /* movement only: a short trail behind the dot, not a facing claim */
    ctx.beginPath();ctx.moveTo(x-Math.cos(th)*R*1.1,y-Math.sin(th)*R*1.1);ctx.lineTo(x-Math.cos(th)*R*2.6,y-Math.sin(th)*R*2.6);
    ctx.lineCap='round';ctx.lineWidth=R*.5;ctx.strokeStyle=col;ctx.globalAlpha=.55;ctx.stroke();ctx.globalAlpha=1;ctx.lineCap='butt';}

  function drawNade(n){
    const age=t-n.t; if(age<0||age>n.d) return; const [x,y]=P(n.x,n.y), col=n.s?RGB[n.s]:'200,200,200';
    if(n.k==='smoke'){ /* real in-game radius (~144 units), pops out then fades in its last 1.5 s */
      const r=144/bg.s*Math.min(1,.55+age/.5*.45), a=Math.min(1,(n.d-age)/1.5);
      ctx.beginPath();ctx.arc(x,y,r,0,7);ctx.fillStyle='rgba(196,201,210,'+(.42*a)+')';ctx.fill();
      ctx.setLineDash([R*.7,R*.5]);ctx.lineWidth=R*.28;ctx.strokeStyle='rgba('+col+','+(.9*a)+')';ctx.stroke();ctx.setLineDash([]);
      cloud(x,y,R*1.1,.75*a);
    }else if(n.k==='fire'){ /* ~110 unit burn area */
      const r=110/bg.s, a=Math.min(1,(n.d-age)/1.0), fk=1+Math.sin(age*9)*.04;
      const g=ctx.createRadialGradient(x,y,r*.1,x,y,r*fk);g.addColorStop(0,'rgba(255,200,60,'+(.75*a)+')');g.addColorStop(.6,'rgba(235,95,20,'+(.55*a)+')');g.addColorStop(1,'rgba(160,30,0,'+(.15*a)+')');
      ctx.beginPath();ctx.arc(x,y,r*fk,0,7);ctx.fillStyle=g;ctx.fill();
      ctx.setLineDash([R*.6,R*.45]);ctx.lineWidth=R*.25;ctx.strokeStyle='rgba(255,150,40,'+(.9*a)+')';ctx.stroke();ctx.setLineDash([]);
      flame(x,y,R*1.0,.9*a);
    }else if(n.k==='he'){
      const life=age/n.d, r=R*(1.3+life*2.6);
      ctx.beginPath();ctx.arc(x,y,r,0,7);ctx.strokeStyle='rgba(255,205,60,'+(.95*(1-life))+')';ctx.lineWidth=R*.5*(1-life)+1;ctx.stroke();
      star(x,y,R*(2.2-life),R*.8,8,.95*(1-life),'rgba(255,225,110,');
    }else{
      const life=age/n.d, r=R*(1.6+life*1.8);
      const g=ctx.createRadialGradient(x,y,0,x,y,r);g.addColorStop(0,'rgba(255,255,255,'+(.95*(1-life))+')');g.addColorStop(1,'rgba(210,225,255,0)');
      ctx.beginPath();ctx.arc(x,y,r,0,7);ctx.fillStyle=g;ctx.fill();
    }
  }
  const NCOL={smoke:'#d5d9e0',fire:'#ff9a3c',he:'#9fb35f',flash:'#ffffff',decoy:'#b8b8b8'};
  function pathPos(pa,tt){ /* position on the recorded path at time tt (linear between the simplified points) */
    if(tt<=pa[0][0]) return [pa[0][1],pa[0][2],0];
    for(let i=0;i<pa.length-1;i++){ if(tt<=pa[i+1][0]){const k=(tt-pa[i][0])/Math.max(1e-6,pa[i+1][0]-pa[i][0]);return [pa[i][1]+(pa[i+1][1]-pa[i][1])*k,pa[i][2]+(pa[i+1][2]-pa[i][2])*k,i];} }
    const q=pa[pa.length-1]; return [q[1],q[2],pa.length-1];}
  function drawThrow(n){
    if(n.tt==null||t<n.tt||t>n.t+1.2) return; const [tx,ty]=P(n.tx,n.ty),[nx,ny]=P(n.x,n.y);
    const flying=t<=n.t, a=flying?.9:Math.max(0,1-(t-n.t)/1.2)*.6, colr=NCOL[n.k]||'#fff';
    ctx.save();ctx.lineJoin='round';ctx.lineCap='round';
    if(n.pa){ /* the real flight path: bounces and all */
      const pts=n.pa.map(q=>P(q[1],q[2]));
      ctx.beginPath();pts.forEach((q,i)=>i?ctx.lineTo(q[0],q[1]):ctx.moveTo(q[0],q[1]));
      ctx.strokeStyle='rgba(235,240,250,'+(a*.35)+')';ctx.lineWidth=Math.max(1.2,R*.16);ctx.setLineDash([R*.5,R*.45]);ctx.stroke();ctx.setLineDash([]);
      const cur=pathPos(n.pa,Math.min(t,n.t)), cp=P(cur[0],cur[1]);
      ctx.beginPath();ctx.moveTo(pts[0][0],pts[0][1]);for(let i=1;i<=cur[2]&&i<pts.length;i++) ctx.lineTo(pts[i][0],pts[i][1]);ctx.lineTo(cp[0],cp[1]);
      ctx.strokeStyle='rgba(255,255,255,'+a+')';ctx.lineWidth=Math.max(1.8,R*.26);ctx.stroke();
      ctx.beginPath();ctx.arc(tx,ty,R*.35,0,7);ctx.fillStyle='rgba(235,240,250,'+a+')';ctx.fill();
      if(flying){ctx.beginPath();ctx.arc(cp[0],cp[1],R*.55,0,7);ctx.fillStyle=colr;ctx.fill();ctx.lineWidth=1;ctx.strokeStyle='rgba(0,0,0,.65)';ctx.stroke();}
    }else{ /* no recorded path: throw spot and landing spot are real, the line between them is not */
      ctx.strokeStyle='rgba(235,240,250,'+a+')';ctx.lineWidth=Math.max(1.2,R*.16);ctx.setLineDash([R*.5,R*.45]);
      ctx.beginPath();ctx.moveTo(tx,ty);ctx.lineTo(nx,ny);ctx.stroke();ctx.setLineDash([]);
      ctx.beginPath();ctx.arc(tx,ty,R*.35,0,7);ctx.fillStyle='rgba(235,240,250,'+a+')';ctx.fill();
      if(flying){const f=(t-n.tt)/Math.max(.1,n.t-n.tt); ctx.beginPath();ctx.arc(tx+(nx-tx)*f,ty+(ny-ty)*f,R*.5,0,7);
        ctx.fillStyle=colr;ctx.fill();ctx.lineWidth=1;ctx.strokeStyle='rgba(0,0,0,.6)';ctx.stroke();}
    }
    ctx.restore();
  }

  function draw(){
    const S=scale(), narrow=(cv.clientWidth||W)<NARROW;
    ctx.clearRect(0,0,W,H);ctx.fillStyle='#141a22';ctx.fillRect(0,0,W,H);
    if(img.complete){ctx.drawImage(img,0,0,W,H);ctx.fillStyle='rgba(8,12,18,.34)';ctx.fillRect(0,0,W,H);} /* dim radar so units stand out */
    if(layer.util){for(const n of data.nades) drawNade(n); for(const n of data.nades) drawThrow(n);}
    if(data.bomb&&t>=data.bomb.t){const [x,y]=P(data.bomb.x,data.bomb.y),ph=((t-data.bomb.t)*1.2)%1;
      ctx.beginPath();ctx.arc(x,y,R*(1+ph*2),0,7);ctx.strokeStyle='rgba(255,70,70,'+(.7*(1-ph))+')';ctx.lineWidth=R*.3;ctx.stroke();
      ctx.beginPath();ctx.arc(x,y,R*.9,0,7);ctx.fillStyle='#e03434';ctx.fill();ctx.lineWidth=R*.25;ctx.strokeStyle='#ffb0b0';ctx.stroke();
      glyph('c4',x-R*.55,y,R*1.1,R*1.1,'#fff');}
    const vis=[], fi=fIx(t), si=sIx(t);
    for(const p of data.players){const q=posAt(p,t); if(!q) continue; const [x,y]=P(q[0],q[1]); vis.push({p,x,y,f:facing(p,t),fg:p.fg?p.fg[fi]:0});}
    /* view wedges: real facing for everyone (subtle, brighter for you), or the recorded-aim cone that fades over AIM_HOLD */
    if(layer.facing) for(const v of vis){ if(!v.f) continue;
      let k, half, L;
      if(v.f.src==='real'){k=v.p.me?.34:.17; half=(v.fg&1)?.22:.62; L=((v.fg&1)?900:520)/bg.s;}
      else if(v.f.src==='aim'){k=.38*(1-v.f.age/AIM_HOLD); half=.42; L=650/bg.s;}
      else continue;
      const g=ctx.createRadialGradient(v.x,v.y,R,v.x,v.y,L);g.addColorStop(0,'rgba('+RGB[v.p.side]+','+k+')');g.addColorStop(1,'rgba(255,255,255,0)');
      ctx.beginPath();ctx.moveTo(v.x,v.y);ctx.arc(v.x,v.y,L,v.f.th-half,v.f.th+half);ctx.closePath();ctx.fillStyle=g;ctx.fill();}
    for(const k of data.kills){ if(t<k.t) continue;
      if(t-k.t<1.5&&k.ax!=null&&k.vx!=null){const [a,b]=P(k.ax,k.ay),[c,d]=P(k.vx,k.vy);ctx.strokeStyle=k.as==='CT'?'rgba(120,180,240,'+(1-(t-k.t)/1.5)+')':'rgba(245,190,110,'+(1-(t-k.t)/1.5)+')';
        ctx.lineWidth=Math.max(1.5,R*.25);ctx.beginPath();ctx.moveTo(a,b);ctx.lineTo(c,d);ctx.stroke();}
      if(k.vx!=null){const [x,y]=P(k.vx,k.vy);ctx.strokeStyle=k.vs?COL[k.vs]:'#999';ctx.lineWidth=R*.4;ctx.beginPath();
        ctx.moveTo(x-R*.6,y-R*.6);ctx.lineTo(x+R*.6,y+R*.6);ctx.moveTo(x+R*.6,y-R*.6);ctx.lineTo(x-R*.6,y+R*.6);ctx.stroke();}}
    for(const v of vis){ if(v.p.fl[si]){ctx.beginPath();ctx.arc(v.x,v.y,R*1.9,0,7);ctx.strokeStyle='rgba(255,255,255,.9)';ctx.lineWidth=R*.3;ctx.stroke();}
      if(v.fg&16){ctx.beginPath();ctx.arc(v.x,v.y,R*2.3,0,7);ctx.strokeStyle='rgba(120,255,160,.95)';ctx.setLineDash([R*.5,R*.4]);ctx.lineWidth=R*.3;ctx.stroke();ctx.setLineDash([]);}
      const th=v.f&&v.f.src!=='move'?v.f.th:null;
      if(v.f&&v.f.src==='move') tail(v.x,v.y,v.f.th,COL[v.p.side]);
      pin(v.x,v.y,th,COL[v.p.side],EDGE[v.p.side],v.p.me);}
    /* name pills (fixed on-screen size); the icon is the kind of active item, exact names are in the roster */
    if(layer.names){const placed=[]; vis.sort((a,b)=>(b.p.me-a.p.me)||(a.y-b.y));
      for(const v of vis){const p=v.p, cat=data.wi[p.wp[si]]||'', showG=!narrow&&cat, fs=(p.me?13:12)*S, gw=showG?fs*2.1:0;
        ctx.font=(p.me?'700 ':'600 ')+fs+'px system-ui,sans-serif';ctx.textBaseline='middle';
        const tw=ctx.measureText(p.name).width, pad=fs*.55, pw=tw+gw+pad*2+(gw?fs*.35:0), ph=fs*1.7;
        let px=Math.max(3,Math.min(W-pw-3,v.x-pw/2)), py=v.y-R*2.2-ph-2, dir=-1;
        if(py<3){py=v.y+R*2.2+2;dir=1;}
        for(let i=0;i<8;i++){const hit=placed.some(o=>px<o[0]+o[2]+2&&px+pw+2>o[0]&&py<o[1]+o[3]+2&&py+ph+2>o[1]); if(!hit) break; py+=dir*(ph+2);}
        py=Math.max(3,Math.min(H-ph-3,py)); placed.push([px,py,pw,ph]);
        rr(px,py,pw,ph,ph/2.6);ctx.fillStyle=PILL[p.side];ctx.fill();if(p.me){ctx.lineWidth=fs*.14;ctx.strokeStyle='#fff';ctx.stroke();}
        if(gw) glyph(cat,px+pad,py+ph/2,gw,ph*.7,'#e9edf3');
        ctx.fillStyle=p.me?'#fff':TXT[p.side];ctx.fillText(p.name,px+pad+gw+(gw?fs*.35:0),py+ph/2+1);}}
    /* kill feed, top right: exact weapon name as text (an icon would say "rifle" for both AK and M4) */
    const recent=layer.feed?data.kills.filter(k=>k.t<=t&&t-k.t<6).slice(-(narrow?3:4)):[];
    const ffs=12*S; ctx.font='600 '+ffs+'px system-ui,sans-serif'; ctx.textBaseline='middle';
    recent.forEach(function(k,i){const an=k.a||'World', vn=k.v, wt=(k.w||'')+(k.hs?' ⌖':''), sp=ffs*.5;
      const w1=ctx.measureText(an).width, w2=ctx.measureText(vn).width, w3=wt?ctx.measureText(wt).width:0, h=ffs*1.7, tot=w1+sp+(wt?w3+sp:0)+w2+ffs*1.1;
      const x0=W-tot-6, y0=6+i*(h+3); rr(x0,y0,tot,h,h/2.6);ctx.fillStyle='rgba(10,14,20,.86)';ctx.fill();
      let cx=x0+ffs*.55; ctx.fillStyle=TXT[k.as]||'#ddd';ctx.fillText(an,cx,y0+h/2+1);cx+=w1+sp;
      if(wt){ctx.fillStyle='#e9edf3';ctx.fillText(wt,cx,y0+h/2+1);cx+=w3+sp;}
      ctx.fillStyle=TXT[k.vs]||'#ddd';ctx.fillText(vn,cx,y0+h/2+1);});
    if(data.focus!=null&&Math.abs(t-data.focus)<1.2){ctx.strokeStyle='#ffd400';ctx.lineWidth=R/2;ctx.strokeRect(2,2,W-4,H-4);}
    range.value=t;lab.textContent=fmt(t)+' / '+fmt(T);
    const nextHtml=data.kills.filter(k=>k.t<=t&&t-k.t<6).slice(-4).map(k=>'<span><b class="'+(k.as||'')+'">'+esc(k.a||'World')+'</b> '+(k.w?'['+esc(k.w)+'] ':'')+'<b class="'+(k.vs||'')+'">'+esc(k.v)+'</b></span>').join('');
    if(feed.innerHTML!==nextHtml) feed.innerHTML=nextHtml;
    /* roster: health, armour and the active item for both teams */
    let h='';
    for(const side of ['CT','T']){const ps=data.players.filter(p=>p.side===side); const alive=ps.filter(p=>p.xy[2*fi]!=null).length;
      h+='<div class="rt '+side+'"><div class="rh"><b>'+side+'</b><span>'+alive+' alive</span></div>';
      for(const p of ps){const up=p.xy[2*fi]!=null, hp=p.hp[si], wn=data.weapons[p.wp[si]]||'', dfz=p.fg&&(p.fg[fi]&16);
        h+='<div class="rr'+(up?'':' dead')+(p.me?' me':'')+'"><div class="l1"><span class="nm">'+esc(p.name)+'</span><span class="hpb"><i class="'+(hp<=30?'lo':hp<=60?'mid':'')+'" style="width:'+(up?Math.max(3,hp):0)+'%"></i></span><span class="hpn">'+(up?hp:'dead')+'</span></div>'
          +'<div class="wn">'+(up?esc(wn)+(p.ar[si]?' · armor':'')+(dfz?' · defusing':''):'&nbsp;')+'</div></div>';}
      h+='</div>';}
    if(h!==rosterHtml){rosterHtml=h;rosterEl.innerHTML=h;}
  }

  /* ---- controls ---- */
  function setT(x){t=clampT(x); draw();}
  function stop(){playing=false; btn.textContent='Play'; btn.setAttribute('aria-pressed','false');}
  function loop(ts){ if(!playing) return; if(last) t+=(ts-last)/1000*parseFloat(spd.value); last=ts;
    if(t>=T){t=T; stop();} draw(); if(playing) requestAnimationFrame(loop);}
  btn.addEventListener('click',()=>{playing=!playing; btn.textContent=playing?'Pause':'Play'; btn.setAttribute('aria-pressed',String(playing)); last=0; if(playing){ if(t>=T) t=0; requestAnimationFrame(loop);} });
  range.addEventListener('input',()=>{t=parseFloat(range.value); draw();});
  const j=root.querySelector('.v-jump'); if(j) j.addEventListener('click',()=>{stop(); setT(Math.max(0,(data.focus||0)-5));});
  root.querySelectorAll('[data-step]').forEach(b=>b.addEventListener('click',()=>{stop(); setT(t+parseFloat(b.dataset.step));}));
  /* events: kills, plant, focus, round end (also drawn as markers on the timeline) */
  const evs=[]; data.kills.forEach(k=>evs.push({t:k.t,c:'k '+(k.vs||''),l:'Kill: '+(k.a||'World')+' → '+k.v}));
  if(data.bomb) evs.push({t:data.bomb.t,c:'b',l:'Bomb planted'});
  if(data.focus!=null) evs.push({t:data.focus,c:'f',l:'Moment'});
  evs.push({t:data.end,c:'e',l:'Round end'}); evs.sort((a,b)=>a.t-b.t);
  const jt=e=>Math.max(data.t0,e.t-1);   /* land one second before an event so you see it happen */
  if(marks) evs.forEach(e=>{const m=document.createElement('button');m.type='button';m.className='mk '+e.c;m.style.left=(Math.min(100,Math.max(0,(e.t-data.t0)/(T-data.t0)*100)))+'%';
    m.title=fmt(e.t)+' · '+e.l;m.setAttribute('aria-label',fmt(e.t)+' '+e.l);m.addEventListener('click',()=>{stop();setT(jt(e));});marks.appendChild(m);});
  const nx=root.querySelector('.v-next'), pv=root.querySelector('.v-prev');
  if(nx) nx.addEventListener('click',()=>{stop(); const e=evs.find(e=>jt(e)>t+.05); setT(e?jt(e):T);});
  if(pv) pv.addEventListener('click',()=>{stop(); const c=evs.filter(e=>jt(e)<t-.05); setT(c.length?jt(c[c.length-1]):data.t0);});
  root.querySelectorAll('[data-layer]').forEach(b=>b.addEventListener('click',()=>{const k=b.dataset.layer; layer[k]=!layer[k]; b.setAttribute('aria-pressed',String(layer[k])); draw();}));
  const ex=root.querySelector('.v-expand');
  function fullOff(){root.classList.remove('v-full'); document.body.classList.remove('v-lock'); if(ex){ex.textContent='Expand replay'; ex.setAttribute('aria-pressed','false');} draw();}
  if(ex) ex.addEventListener('click',()=>{const on=!root.classList.contains('v-full'); if(!on){fullOff();return;}
    root.classList.add('v-full'); document.body.classList.add('v-lock'); ex.textContent='Close'; ex.setAttribute('aria-pressed','true'); draw();});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&root.classList.contains('v-full')) fullOff();});
  if(window.ResizeObserver) new ResizeObserver(()=>draw()).observe(cv);
  img.onload=draw; draw();
}
/* lazy start: a replay inside a closed drawer is set up the first time the drawer opens */
document.querySelectorAll('.viewer').forEach(function(v){
  const d=v.closest('details');
  if(d&&!d.open){const go=function(){if(d.open){initViewer(v);d.removeEventListener('toggle',go);}}; d.addEventListener('toggle',go);}
  else initViewer(v);
});
})();
