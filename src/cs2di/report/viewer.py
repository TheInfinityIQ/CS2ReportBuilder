"""2D round viewer: software-built playback of a round on the map, plus observed facts.

Background: a radar image when verified map assets are installed (assets/maps: awpy's
map-data.json + de_<map>.png), otherwise a map outline drawn from where players actually stood in
the batch's games (accurate by construction, no downloads). Both use the same world->pixel
transform: px = (x - x0) / s, py = (y0 - y) / s.

Nothing here is written by the AI: the coach picks a round and writes a note; the software draws.
"""

from __future__ import annotations

import base64
import io
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import fmt

TICK = 64
NADES = {"smokegrenade_detonate": ("smoke", 18.0), "inferno_startburn": ("fire", 7.0),
         "hegrenade_detonate": ("he", 0.8), "flashbang_detonate": ("flash", 0.8)}
REASONS = {"bomb_defused": "CT defused the bomb", "bomb_exploded": "the bomb exploded",
           "t_killed": "all T players died", "ct_killed": "all CT players died",
           "target_saved": "time ran out (CT win)"}
ASSETS = Path(__file__).resolve().parents[3] / "assets" / "maps"


def _side(x):
    return {"CT": "CT", "TERRORIST": "T", "T": "T"}.get(str(x))


@lru_cache(maxsize=16)
def _radar(map_name: str):
    """Verified radar + calibration if installed, else None."""
    md = ASSETS / "map-data.json"
    img = ASSETS / f"{map_name}.png"
    if not (md.exists() and img.exists()):
        return None
    cal = json.loads(md.read_text()).get(map_name)
    if not cal:
        return None
    b64 = base64.b64encode(img.read_bytes()).decode()
    return {"img": f"data:image/png;base64,{b64}", "x0": cal["pos_x"], "y0": cal["pos_y"], "s": cal["scale"],
            "w": 1024, "h": 1024, "kind": "radar"}


@lru_cache(maxsize=16)
def _outline(batch_dir: str, map_name: str):
    """Map outline from every position sample on this map in the batch."""
    from PIL import Image, ImageFilter

    xs, ys = [], []
    for d in Path(batch_dir).iterdir():
        ms = d / "match_summary.json"
        if not ms.exists() or json.loads(ms.read_text(encoding="utf-8")).get("map_name") != map_name:
            continue
        p = pd.read_csv(d / "player_positions.csv.gz", usecols=["X", "Y", "is_alive"])
        p = p[p.is_alive == True]  # noqa: E712
        xs.append(p.X.to_numpy())
        ys.append(p.Y.to_numpy())
    if not xs:
        return None
    x, y = np.concatenate(xs), np.concatenate(ys)
    x0, x1 = np.percentile(x, [0.05, 99.95])
    y0, y1 = np.percentile(y, [0.05, 99.95])
    pad = 0.04 * max(x1 - x0, y1 - y0)
    x0, x1, y0, y1 = x0 - pad, x1 + pad, y0 - pad, y1 + pad
    size = 640
    s = max(x1 - x0, y1 - y0) / size
    w, h = int((x1 - x0) / s), int((y1 - y0) / s)
    H, _, _ = np.histogram2d((y1 - y) / s, (x - x0) / s, bins=[h, w], range=[[0, h], [0, w]])
    m = (H > 0).astype(np.uint8) * 255
    im = Image.fromarray(m, "L").filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(1.2))
    a = np.asarray(im)
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., :3] = (206, 212, 220)
    rgba[..., 3] = a
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG", optimize=True)
    return {"img": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
            "x0": float(x0), "y0": float(y1), "s": float(s), "w": w, "h": h, "kind": "outline"}


def background(batch_dir, map_name: str) -> dict | None:
    return _radar(map_name) or _outline(str(batch_dir), map_name)


def round_payload(batch_dir, demo_id: str, round_no: int, steamid: int, focus_tick: int | None = None) -> dict:
    d = Path(batch_dir) / demo_id
    ms = json.loads((d / "match_summary.json").read_text(encoding="utf-8"))
    rounds = pd.read_csv(d / "rounds.csv").sort_values("round").reset_index(drop=True)
    i = int(rounds.index[rounds["round"] == round_no][0])
    r = rounds.iloc[i]
    lo = int(r.freeze_end_tick)
    nxt = int(rounds.iloc[i + 1].start_tick) if i + 1 < len(rounds) else int(r.end_tick) + 5 * TICK
    hi = min(int(r.end_tick) + 4 * TICK, nxt)
    pos = pd.read_csv(d / "player_positions.csv.gz", usecols=["tick", "steamid", "name", "team_name", "is_alive", "X", "Y"],
                      dtype={"steamid": "int64"})
    pos = pos[(pos.tick >= lo) & (pos.tick <= hi)].sort_values("tick")
    ticks = sorted(pos.tick.unique())
    pr = pd.read_csv(d / "player_rounds.csv", dtype={"steamid": "int64"})
    side_of = {int(a): _side(b) for a, b in zip(pr[pr["round"] == round_no].steamid, pr[pr["round"] == round_no].side)}
    players = []
    for sid, g in pos.groupby("steamid"):
        side = side_of.get(int(sid)) or _side(g.team_name.iloc[0])
        if side is None:
            continue
        g = g.set_index("tick").reindex(ticks)
        xy = []
        for t in ticks:
            row = g.loc[t]
            if pd.isna(row.X) or row.is_alive not in (True, "True", 1):
                xy += [None, None]
            else:
                xy += [int(row.X), int(row.Y)]
        players.append({"name": str(g.name.dropna().iloc[0]) if g.name.notna().any() else "?", "side": side,
                        "me": int(sid) == int(steamid), "xy": xy})
    dth = pd.read_csv(d / "events" / "player_death.csv.gz", dtype={"attacker_steamid": "Int64", "user_steamid": "Int64"},
                      usecols=lambda c: c in {"tick", "attacker_steamid", "user_steamid", "attacker_X", "attacker_Y",
                                              "user_X", "user_Y", "weapon", "attacker_name", "user_name"})
    dth = dth[(dth.tick >= lo) & (dth.tick <= hi)].sort_values("tick")
    kills = []
    for e in dth.itertuples():
        kills.append({"t": (e.tick - lo) / TICK, "a": None if pd.isna(e.attacker_name) else str(e.attacker_name),
                      "v": str(e.user_name), "ax": None if pd.isna(e.attacker_X) else int(e.attacker_X),
                      "ay": None if pd.isna(e.attacker_Y) else int(e.attacker_Y),
                      "vx": None if pd.isna(e.user_X) else int(e.user_X), "vy": None if pd.isna(e.user_Y) else int(e.user_Y),
                      "as": side_of.get(int(e.attacker_steamid)) if not pd.isna(e.attacker_steamid) else None,
                      "vs": side_of.get(int(e.user_steamid)) if not pd.isna(e.user_steamid) else None,
                      "w": fmt.weapon(e.weapon) if isinstance(e.weapon, str) else ""})
    nades = []
    for ev, (kind, dur) in NADES.items():
        f = d / "events" / f"{ev}.csv.gz"
        if not f.exists():
            continue
        g = pd.read_csv(f, usecols=lambda c: c in {"tick", "x", "y", "user_X", "user_Y"})
        g = g[(g.tick >= lo) & (g.tick <= hi)]
        for row in g.itertuples():
            tx = int(row.user_X) if hasattr(row, "user_X") and not pd.isna(row.user_X) else None
            ty = int(row.user_Y) if hasattr(row, "user_Y") and not pd.isna(row.user_Y) else None
            nades.append({"t": (row.tick - lo) / TICK, "k": kind, "d": dur,
                          "x": int(row.x), "y": int(row.y), "tx": tx, "ty": ty})
    bomb = None
    bp = d / "events" / "bomb_planted.csv.gz"
    if bp.exists():
        b = pd.read_csv(bp, usecols=lambda c: c in {"tick", "user_X", "user_Y", "site"})
        b = b[(b.tick >= lo) & (b.tick <= hi)]
        if len(b):
            bomb = {"t": (int(b.tick.iloc[0]) - lo) / TICK, "x": int(b.user_X.iloc[0]), "y": int(b.user_Y.iloc[0])}
    return {"map": ms.get("map_name"), "dt": (ticks[1] - ticks[0]) / TICK if len(ticks) > 1 else 0.5,
            "t0": (ticks[0] - lo) / TICK if ticks else 0.0, "n": len(ticks), "players": players, "kills": kills,
            "nades": nades, "bomb": bomb, "focus": None if focus_tick is None else (focus_tick - lo) / TICK,
            "end": (int(r.end_tick) - lo) / TICK}


def observed_facts(batch_dir, demo_id: str, round_no: int, steamid: int, focus_tick: int | None) -> list[str]:
    """Plain facts about the moment, computed from the files (coach notes must agree with them)."""
    d = Path(batch_dir) / demo_id
    rounds = pd.read_csv(d / "rounds.csv")
    r = rounds[rounds["round"] == round_no].iloc[0]
    lo = r.freeze_end_tick
    pr = pd.read_csv(d / "player_rounds.csv", dtype={"steamid": "int64"})
    pr = pr[pr["round"] == round_no]
    me_side = _side(pr[pr.steamid == steamid].side.iloc[0]) if (pr.steamid == steamid).any() else None
    facts = []
    winner = _side(r.get("winner"))
    reason = r.get("reason")
    if winner and me_side:
        how = REASONS.get(str(reason), str(reason).replace("_", " ")) if isinstance(reason, str) else "reason not recorded"
        facts.append(f"You were {me_side}. The round was {'won' if winner == me_side else 'lost'}: {how}.")
    elif me_side:
        facts.append(f"You were {me_side}. Round result not recorded.")
    if focus_tick is None:
        return facts
    plant = r.get("bomb_plant_tick", float("nan"))
    if not pd.isna(plant):
        when = fmt.clock((plant - lo) / TICK)
        facts.append(f"Bomb planted at {when}" + (" (before this moment)." if plant <= focus_tick else " (after this moment)."))
    else:
        facts.append("The bomb was not planted this round.")
    if "end_tick" in r and focus_tick > r.end_tick:
        facts.append("This moment came after the round was already decided.")
    dth = pd.read_csv(d / "events" / "player_death.csv.gz", dtype={"attacker_steamid": "Int64", "user_steamid": "Int64"},
                      usecols=lambda c: c in {"tick", "attacker_steamid", "user_steamid", "attacker_name", "user_name"})
    near = dth[(dth.tick >= focus_tick - 5 * TICK) & (dth.tick <= focus_tick + 5 * TICK)].sort_values("tick")
    side_of = {int(a): _side(b) for a, b in zip(pr.steamid, pr.side)}
    before = dth[(dth.tick >= lo) & (dth.tick < focus_tick)]
    alive = {"CT": int((pr.side.map(_side) == "CT").sum()), "T": int((pr.side.map(_side) == "T").sum())}
    for v in before.user_steamid.dropna():
        s = side_of.get(int(v))
        if s:
            alive[s] -= 1
    if me_side:
        opp = "T" if me_side == "CT" else "CT"
        facts.append(f"Just before it: {alive[me_side]} of your team alive against {alive[opp]}.")
    lines = []
    for e in near.itertuples():
        dt = (e.tick - focus_tick) / TICK
        a = "the bomb / world" if pd.isna(e.attacker_name) else e.attacker_name
        lines.append(f"{dt:+.1f} s: {a} killed {e.user_name}")
    if lines:
        facts.append("Kills within 5 seconds of the moment:")
        facts += ["  " + x for x in lines]
    return facts


VIEWER_JS = r"""
(function(){
const COL={CT:'#2f6db5',T:'#a8600f'};
const NCOL={smoke:'rgba(200,205,215,',fire:'rgba(240,80,20,',he:'rgba(255,210,30,',flash:'rgba(240,240,255,'};
function fmt(t){t=Math.max(0,t);return Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0');}

/* draw a filled arrowhead at (x,y) pointing in direction (dx,dy) */
function arrowHead(ctx,x,y,dx,dy,size){
  const len=Math.hypot(dx,dy); if(len<0.5) return;
  const ux=dx/len, uy=dy/len;
  const lx=x-ux*size, ly=y-uy*size;
  const px=-uy*size*0.45, py=ux*size*0.45;
  ctx.beginPath(); ctx.moveTo(x,y); ctx.lineTo(lx+px,ly+py); ctx.lineTo(lx-px,ly-py); ctx.closePath(); ctx.fill();
}

/* draw a quadratic bezier arc from thrower to nade landing */
function drawNadeArc(ctx,tx,ty,nx,ny,col,alpha,progress){
  const mx=(tx+nx)/2, my=(ty+ny)/2;
  const dx=nx-tx, dy=ny-ty;
  const cpx=mx+dy*0.35, cpy=my-dx*0.35; /* control point lifted perpendicularly */
  ctx.save();
  ctx.strokeStyle=col+(alpha*0.7)+')';
  ctx.lineWidth=1.5; ctx.setLineDash([4,4]); ctx.lineDashOffset=-(progress*12);
  ctx.beginPath(); ctx.moveTo(tx,ty);
  ctx.quadraticCurveTo(cpx,cpy,nx,ny);
  ctx.stroke(); ctx.setLineDash([]); ctx.restore();
}

/* draw a styled nade splash */
function drawNade(ctx,kind,x,y,R,age,dur){
  const life=Math.min(age/dur,1);
  if(kind==='smoke'){
    /* pulsing grey cloud that grows then fades */
    const r=R*(2.8+life*0.6);
    const a=0.55*(1-Math.max(0,(life-0.8)/0.2));
    const g=ctx.createRadialGradient(x,y,r*0.1,x,y,r);
    g.addColorStop(0,'rgba(220,222,226,'+a+')');
    g.addColorStop(0.6,'rgba(180,184,192,'+(a*0.7)+')');
    g.addColorStop(1,'rgba(140,145,155,0)');
    ctx.beginPath(); ctx.arc(x,y,r,0,7); ctx.fillStyle=g; ctx.fill();
    /* small "S" label */
    ctx.fillStyle='rgba(255,255,255,0.7)'; ctx.font='bold '+Math.round(R*1.3)+'px system-ui';
    ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.fillText('SMOKE',x,y); ctx.textAlign='left';
  } else if(kind==='fire'){
    /* fire blob: inner bright, outer dark; flickers */
    const r=R*(2.1+Math.sin(age*8)*0.12);
    const g=ctx.createRadialGradient(x,y,r*0.05,x,y,r);
    g.addColorStop(0,'rgba(255,240,60,0.9)');
    g.addColorStop(0.35,'rgba(240,100,10,0.75)');
    g.addColorStop(0.7,'rgba(180,40,0,0.5)');
    g.addColorStop(1,'rgba(80,0,0,0)');
    ctx.beginPath(); ctx.arc(x,y,r,0,7); ctx.fillStyle=g; ctx.fill();
    ctx.fillStyle='rgba(255,255,255,0.65)'; ctx.font='bold '+Math.round(R*1.1)+'px system-ui';
    ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.fillText('FIRE',x,y); ctx.textAlign='left';
  } else if(kind==='he'){
    /* sharp burst ring + bright center flash that fades fast */
    const flash=Math.max(0,1-life*3);
    const r=R*(1.4+life*1.0);
    ctx.beginPath(); ctx.arc(x,y,r,0,7);
    ctx.strokeStyle='rgba(255,210,30,'+(0.9*(1-life))+')'; ctx.lineWidth=R*0.4; ctx.stroke();
    if(flash>0){
      ctx.beginPath(); ctx.arc(x,y,R*1.2*flash,0,7);
      ctx.fillStyle='rgba(255,240,120,'+flash+')'; ctx.fill();
    }
    ctx.fillStyle='rgba(255,255,255,0.75)'; ctx.font='bold '+Math.round(R*1.1)+'px system-ui';
    ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.fillText('HE',x,y); ctx.textAlign='left';
  } else { /* flash */
    const r=R*(1.6+life*0.6);
    const a=0.85*(1-life);
    const g=ctx.createRadialGradient(x,y,0,x,y,r);
    g.addColorStop(0,'rgba(255,255,255,'+a+')');
    g.addColorStop(0.5,'rgba(220,230,255,'+(a*0.6)+')');
    g.addColorStop(1,'rgba(200,220,255,0)');
    ctx.beginPath(); ctx.arc(x,y,r,0,7); ctx.fillStyle=g; ctx.fill();
    ctx.fillStyle='rgba(255,255,255,0.75)'; ctx.font='bold '+Math.round(R*1.0)+'px system-ui';
    ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.fillText('FLASH',x,y); ctx.textAlign='left';
  }
}

function initViewer(root){
  const data=JSON.parse(root.querySelector('script[type="application/json"]').textContent);
  const bg=window.__MAPS[data.map]; const cv=root.querySelector('canvas'); const ctx=cv.getContext('2d');
  const img=new Image(); img.src=bg.img; cv.width=bg.w; cv.height=bg.h;
  const P=(x,y)=>[(x-bg.x0)/bg.s,(bg.y0-y)/bg.s];
  const range=root.querySelector('input[type=range]'), btn=root.querySelector('.v-play'), lab=root.querySelector('.v-time'), spd=root.querySelector('select');
  const T=data.t0+(data.n-1)*data.dt; range.max=T; let t=Math.max(0,(data.focus==null?0:data.focus-8)); let playing=false, last=0;
  const R=Math.max(5,bg.w/110);

  function posAt(p,tt){const f=(tt-data.t0)/data.dt, i=Math.floor(f), j=Math.min(i+1,data.n-1);
    if(i<0) return null; const a=[p.xy[2*i],p.xy[2*i+1]], b=[p.xy[2*j],p.xy[2*j+1]];
    if(a[0]==null) return null; if(b[0]==null) return a; const k=f-i; return [a[0]+(b[0]-a[0])*k,a[1]+(b[1]-a[1])*k];}

  /* compute movement direction from adjacent position samples */
  function dirAt(p,tt){
    const dt=data.dt*1.5;
    const a=posAt(p,tt-dt), b=posAt(p,tt+dt);
    if(!a||!b) return null;
    const dx=(b[0]-a[0]), dy=(b[1]-a[1]);
    return Math.hypot(dx,dy)>8 ? [dx,dy] : null;
  }

  function draw(){
    ctx.clearRect(0,0,cv.width,cv.height); ctx.fillStyle='#1d232b'; ctx.fillRect(0,0,cv.width,cv.height);
    if(img.complete) ctx.drawImage(img,0,0,bg.w,bg.h);

    /* nade arcs (drawn before splash so arc is behind the circle) */
    for(const n of data.nades){
      if(n.tx==null||n.t>t||t>n.t+0.5) continue; /* only show arc briefly before detonation */
      const [nx,ny]=P(n.x,n.y), [tx2,ty2]=P(n.tx,n.ty);
      const progress=(t-n.t+4)%1; /* animate dash offset */
      drawNadeArc(ctx,tx2,ty2,nx,ny,NCOL[n.k]||'rgba(200,200,200,',0.7,progress);
    }

    /* nade splashes */
    for(const n of data.nades){
      if(t<n.t||t>n.t+n.d) continue;
      const [x,y]=P(n.x,n.y);
      drawNade(ctx,n.k,x,y,R,t-n.t,n.d);
    }

    /* bomb */
    if(data.bomb && t>=data.bomb.t){
      const [x,y]=P(data.bomb.x,data.bomb.y);
      ctx.fillStyle='#e03030'; ctx.strokeStyle='#ff8888'; ctx.lineWidth=R/3;
      ctx.beginPath(); ctx.arc(x,y,R*0.9,0,7); ctx.fill(); ctx.stroke();
      ctx.fillStyle='#fff'; ctx.font='bold '+Math.round(R*1.1)+'px system-ui';
      ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.fillText('B',x,y); ctx.textAlign='left';
    }

    /* kill markers */
    for(const k of data.kills){
      if(t<k.t) continue;
      if(k.vx!=null){const [x,y]=P(k.vx,k.vy); ctx.strokeStyle=k.vs?COL[k.vs]:'#999'; ctx.lineWidth=R/2.2;
        ctx.beginPath(); ctx.moveTo(x-R*.7,y-R*.7); ctx.lineTo(x+R*.7,y+R*.7); ctx.moveTo(x+R*.7,y-R*.7); ctx.lineTo(x-R*.7,y+R*.7); ctx.stroke();}
      if(t-k.t<2 && k.ax!=null && k.vx!=null){const [a,b]=P(k.ax,k.ay),[c,d]=P(k.vx,k.vy); ctx.strokeStyle='rgba(255,255,255,.9)'; ctx.lineWidth=R/3; ctx.beginPath(); ctx.moveTo(a,b); ctx.lineTo(c,d); ctx.stroke();}
    }

    /* players: dot + movement pointer + name */
    ctx.textBaseline='middle';
    for(const p of data.players){
      const q=posAt(p,t); if(!q) continue; const [x,y]=P(q[0],q[1]);
      ctx.beginPath(); ctx.arc(x,y,R,0,7); ctx.fillStyle=COL[p.side]; ctx.fill();
      ctx.lineWidth=p.me?R/2:R/5; ctx.strokeStyle=p.me?'#fff':'rgba(0,0,0,.6)'; ctx.stroke();

      /* movement pointer */
      const dir=dirAt(p,t);
      if(dir){
        const [dx,dy]=P(q[0]+dir[0],q[1]+dir[1]);
        const [ox,oy]=P(q[0],q[1]);
        const vx=dx-ox, vy=dy-oy; const vlen=Math.hypot(vx,vy);
        if(vlen>0.5){
          const nx2=vx/vlen*R*1.6, ny2=vy/vlen*R*1.6;
          ctx.fillStyle=p.me?'rgba(255,255,255,0.95)':'rgba(255,255,255,0.65)';
          arrowHead(ctx,x+nx2,y+ny2,nx2,ny2,R*0.85);
        }
      }

      /* name label */
      const fs=p.me?Math.round(R*2.1):Math.round(R*1.7); ctx.font=(p.me?'700 ':'500 ')+fs+'px system-ui,sans-serif';
      ctx.fillStyle=p.me?'#fff':'rgba(255,255,255,.85)'; ctx.strokeStyle='#000'; ctx.lineWidth=p.me?3:2;
      ctx.strokeText(p.name,x+R*1.4,y); ctx.fillText(p.name,x+R*1.4,y);
    }

    /* focus flash border */
    if(data.focus!=null && Math.abs(t-data.focus)<1.2){ctx.strokeStyle='#ffd400'; ctx.lineWidth=R/2; ctx.strokeRect(2,2,cv.width-4,cv.height-4);}
    range.value=t; lab.textContent=fmt(t)+' / '+fmt(T);
    const feed=root.querySelector('.v-feed'); const recent=data.kills.filter(k=>k.t<=t&&t-k.t<4).slice(-3);
    const nextHtml=recent.map(k=>'<span><b class="'+(k.as||'')+'">'+(k.a||'World')+'</b> '+(k.w?'['+k.w+'] ':'')+'<b class="'+(k.vs||'')+'">'+k.v+'</b></span>').join('');
    if(feed.innerHTML!==nextHtml) feed.innerHTML=nextHtml;
  }

  function loop(ts){ if(!playing) return; if(last) t+=(ts-last)/1000*parseFloat(spd.value); last=ts;
    if(t>=T){t=T; playing=false; btn.textContent='Play'; btn.setAttribute('aria-pressed','false');} draw(); if(playing) requestAnimationFrame(loop);}
  btn.addEventListener('click',()=>{playing=!playing; btn.textContent=playing?'Pause':'Play'; btn.setAttribute('aria-pressed',String(playing)); last=0; if(playing){ if(t>=T) t=0; requestAnimationFrame(loop);} });
  range.addEventListener('input',()=>{t=parseFloat(range.value); draw();});
  root.querySelector('.v-jump').addEventListener('click',()=>{t=Math.max(0,(data.focus||0)-5); draw(); playing=false; btn.textContent='Play'; btn.setAttribute('aria-pressed','false');});
  img.onload=draw; draw();
}
document.querySelectorAll('.viewer').forEach(initViewer);
})();
"""


def viewer_html(batch_dir, demo_id: str, round_no: int, steamid: int, focus_tick: int | None, maps: dict) -> str:
    if not (Path(batch_dir) / demo_id / "player_positions.csv.gz").exists():
        return '<p class="muted small">No position data for this game, so the map replay is not available.</p>'
    data = round_payload(batch_dir, demo_id, round_no, steamid, focus_tick)
    if data["map"] not in maps:
        bg = background(batch_dir, data["map"])
        if bg is None:
            return ""
        maps[data["map"]] = bg
    kind = maps[data["map"]]["kind"]
    note = ("Map: radar image." if kind == "radar" else
            "Map outline drawn from where players stood in these games; radar images not installed yet.")
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return (f'<div class="viewer"><script type="application/json">{payload}</script>'
            f'<canvas role="img" aria-label="Top-down replay of the round"></canvas>'
            f'<div class="v-feed" aria-live="polite"></div>'
            f'<div class="v-ctl"><button class="v-play" aria-pressed="false">Play</button>'
            f'<button class="v-jump">Lead-in (−5 s)</button>'
            f'<input type="range" min="0" step="0.1" aria-label="Round time">'
            f'<span class="v-time"></span><select aria-label="Speed"><option value="0.5">0.5×</option>'
            f'<option value="1" selected>1×</option><option value="2">2×</option><option value="4">4×</option></select></div>'
            f'<p class="muted small">{note} You are the ringed dot. Blue CT, orange T; crosses mark deaths; '
            f'a white line flashes from killer to victim.</p></div>')


def maps_script(maps: dict) -> str:
    if not maps:
        return ""
    return "<script>window.__MAPS=" + json.dumps(maps, separators=(",", ":")) + ";</script><script>" + VIEWER_JS + "</script>"
