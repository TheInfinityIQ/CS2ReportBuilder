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


THROW_KIND = {"weapon_smokegrenade": "smoke", "weapon_hegrenade": "he", "weapon_flashbang": "flash",
              "weapon_molotov": "fire", "weapon_incgrenade": "fire"}
EXPIRE = {"smokegrenade_detonate": "smokegrenade_expired", "inferno_startburn": "inferno_expire"}


def _nades(d: Path, lo: int, hi: int, side_of: dict) -> list[dict]:
    """Grenade detonations, each tied to the real throw (spot + time) recorded in weapon_fire.

    Only the throw spot, landing spot and both times are recorded. The flight path itself (arc, bounces) is
    not in the demo, so the viewer draws a plain straight line and says so.
    """
    throws = []
    wf = d / "events" / "weapon_fire.csv.gz"
    if wf.exists():
        g = pd.read_csv(wf, usecols=lambda c: c in {"tick", "weapon", "user_steamid", "user_name", "user_X", "user_Y"},
                        dtype={"user_steamid": "Int64"})
        g = g[g.weapon.isin(THROW_KIND) & (g.tick >= lo - 10 * TICK) & (g.tick <= hi)]
        throws = [dict(tick=int(r.tick), kind=THROW_KIND[r.weapon], sid=int(r.user_steamid), x=r.user_X, y=r.user_Y,
                       used=False) for r in g.itertuples() if not pd.isna(r.user_steamid)]
    out = []
    for ev, (kind, dur) in NADES.items():
        f = d / "events" / f"{ev}.csv.gz"
        if not f.exists():
            continue
        g = pd.read_csv(f, usecols=lambda c: c in {"tick", "x", "y", "entityid", "user_steamid", "user_name"},
                        dtype={"user_steamid": "Int64"})
        g = g[(g.tick >= lo) & (g.tick <= hi)]
        ends = {}
        ex = d / "events" / f"{EXPIRE.get(ev, '')}.csv.gz"
        if ev in EXPIRE and ex.exists() and "entityid" in g:
            e = pd.read_csv(ex, usecols=lambda c: c in {"tick", "entityid"})
            for a_, b_ in zip(e.entityid, e.tick):
                ends.setdefault(int(a_), []).append(int(b_))
        for row in g.itertuples():
            sid = None if pd.isna(row.user_steamid) else int(row.user_steamid)
            d_s = dur
            if ev in EXPIRE and getattr(row, "entityid", None) in ends:
                later = [x for x in ends[int(row.entityid)] if x >= row.tick]
                if later and (min(later) - row.tick) / TICK <= 30:  # entity ids get reused; ignore later rounds
                    d_s = max(0.5, (min(later) - row.tick) / TICK)
            n = {"t": (row.tick - lo) / TICK, "k": kind, "d": round(d_s, 2), "x": int(row.x), "y": int(row.y),
                 "s": side_of.get(sid) if sid is not None else None,
                 "by": None if pd.isna(row.user_name) else str(row.user_name)}
            # match the nearest earlier unused throw of the same kind by the same player (flight < ~7 s)
            best = None
            for th in throws:
                if th["used"] or th["kind"] != kind or th["sid"] != sid or th["tick"] > row.tick:
                    continue
                if row.tick - th["tick"] > 7 * TICK or pd.isna(th["x"]):
                    continue
                if best is None or th["tick"] > best["tick"]:
                    best = th
            if best is not None:
                best["used"] = True
                n.update({"tt": (best["tick"] - lo) / TICK, "tx": int(best["x"]), "ty": int(best["y"])})
            out.append(n)
    return out


def round_payload(batch_dir, demo_id: str, round_no: int, steamid: int, focus_tick: int | None = None) -> dict:
    d = Path(batch_dir) / demo_id
    ms = json.loads((d / "match_summary.json").read_text(encoding="utf-8"))
    rounds = pd.read_csv(d / "rounds.csv").sort_values("round").reset_index(drop=True)
    i = int(rounds.index[rounds["round"] == round_no][0])
    r = rounds.iloc[i]
    lo = int(r.freeze_end_tick)
    nxt = int(rounds.iloc[i + 1].start_tick) if i + 1 < len(rounds) else int(r.end_tick) + 5 * TICK
    hi = min(int(r.end_tick) + 4 * TICK, nxt)
    pos = pd.read_csv(d / "player_positions.csv.gz",
                      usecols=["tick", "steamid", "name", "team_name", "is_alive", "X", "Y", "health", "armor_value",
                               "active_weapon_name", "flash_duration"],
                      dtype={"steamid": "int64"}, low_memory=False)
    pos = pos[(pos.tick >= lo) & (pos.tick <= hi)].sort_values("tick")
    ticks = sorted(pos.tick.unique())
    pr = pd.read_csv(d / "player_rounds.csv", dtype={"steamid": "int64"})
    side_of = {int(a): _side(b) for a, b in zip(pr[pr["round"] == round_no].steamid, pr[pr["round"] == round_no].side)}
    weapons: list[str] = []
    players, sid_index = [], {}
    for sid, g in pos.groupby("steamid"):
        side = side_of.get(int(sid)) or _side(g.team_name.iloc[0])
        if side is None:
            continue
        g = g.set_index("tick").reindex(ticks)
        alive = g.is_alive.isin([True, "True", 1]) & g.X.notna()
        xy, hp, ar, wp, fl = [], [], [], [], []
        for t in ticks:
            row = g.loc[t]
            if not alive[t]:
                xy += [None, None]
                hp.append(0); ar.append(0); wp.append(-1); fl.append(0)
                continue
            xy += [int(row.X), int(row.Y)]
            hp.append(int(row.health) if not pd.isna(row.health) else 0)
            ar.append(1 if not pd.isna(row.armor_value) and row.armor_value > 0 else 0)
            wn = row.active_weapon_name
            if isinstance(wn, str) and wn:
                if wn not in weapons:
                    weapons.append(wn)
                wp.append(weapons.index(wn))
            else:
                wp.append(-1)
            fl.append(1 if not pd.isna(row.flash_duration) and row.flash_duration > 0.3 else 0)
        sid_index[int(sid)] = len(players)
        players.append({"name": str(g.name.dropna().iloc[0]) if g.name.notna().any() else "?", "side": side,
                        "me": int(sid) == int(steamid), "xy": xy, "hp": hp, "ar": ar, "wp": wp, "fl": fl, "aim": []})
    # Recorded view angles (yaw). The demo stores them only at events (shots, hits, kills), never continuously,
    # so these are the only moments a facing direction is a fact rather than a guess.
    def _aim(fname, sid_col, yaw_col):
        f = d / "events" / fname
        if not f.exists():
            return
        try:
            g = pd.read_csv(f, usecols=lambda c: c in {"tick", sid_col, yaw_col}, dtype={sid_col: "Int64"})
        except ValueError:
            return
        if sid_col not in g or yaw_col not in g:
            return
        g = g[(g.tick >= lo) & (g.tick <= hi)].dropna(subset=[sid_col, yaw_col])
        for tk, sd, yw in zip(g.tick, g[sid_col], g[yaw_col]):
            ix = sid_index.get(int(sd))
            if ix is not None:
                players[ix]["aim"].append([round((int(tk) - lo) / TICK, 2), round(float(yw), 1)])
    _aim("weapon_fire.csv.gz", "user_steamid", "user_yaw")
    _aim("player_hurt.csv.gz", "attacker_steamid", "attacker_yaw")
    _aim("player_hurt.csv.gz", "user_steamid", "user_yaw")
    _aim("player_death.csv.gz", "attacker_steamid", "attacker_yaw")
    _aim("player_death.csv.gz", "user_steamid", "user_yaw")
    for pl in players:
        pl["aim"] = sorted({(a, b) for a, b in pl["aim"]})
        pl["aim"] = [list(x) for x in pl["aim"]]
    dth = pd.read_csv(d / "events" / "player_death.csv.gz", dtype={"attacker_steamid": "Int64", "user_steamid": "Int64"},
                      usecols=lambda c: c in {"tick", "attacker_steamid", "user_steamid", "attacker_X", "attacker_Y",
                                              "user_X", "user_Y", "weapon", "attacker_name", "user_name", "headshot"})
    dth = dth[(dth.tick >= lo) & (dth.tick <= hi)].sort_values("tick")
    kills = []
    for e in dth.itertuples():
        kills.append({"t": (e.tick - lo) / TICK, "a": None if pd.isna(e.attacker_name) else str(e.attacker_name),
                      "v": str(e.user_name), "ax": None if pd.isna(e.attacker_X) else int(e.attacker_X),
                      "ay": None if pd.isna(e.attacker_Y) else int(e.attacker_Y),
                      "vx": None if pd.isna(e.user_X) else int(e.user_X), "vy": None if pd.isna(e.user_Y) else int(e.user_Y),
                      "as": side_of.get(int(e.attacker_steamid)) if not pd.isna(e.attacker_steamid) else None,
                      "vs": side_of.get(int(e.user_steamid)) if not pd.isna(e.user_steamid) else None,
                      "w": fmt.weapon(e.weapon) if isinstance(e.weapon, str) else "",
                      "wr": e.weapon if isinstance(e.weapon, str) else "",
                      "hs": bool(getattr(e, "headshot", False)) if not pd.isna(getattr(e, "headshot", float("nan"))) else False})
    nades = _nades(d, lo, hi, side_of)
    bomb = None
    bp = d / "events" / "bomb_planted.csv.gz"
    if bp.exists():
        b = pd.read_csv(bp, usecols=lambda c: c in {"tick", "user_X", "user_Y", "site"})
        b = b[(b.tick >= lo) & (b.tick <= hi)]
        if len(b):
            bomb = {"t": (int(b.tick.iloc[0]) - lo) / TICK, "x": int(b.user_X.iloc[0]), "y": int(b.user_Y.iloc[0])}
    return {"map": ms.get("map_name"), "dt": (ticks[1] - ticks[0]) / TICK if len(ticks) > 1 else 0.5,
            "t0": (ticks[0] - lo) / TICK if ticks else 0.0, "n": len(ticks), "players": players, "weapons": weapons, "kills": kills,
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
const COL={CT:'#3f8fe0',T:'#e39a35'}, EDGE={CT:'#173f73',T:'#7a4a0c'};
const PILL={CT:'rgba(24,52,92,.90)',T:'rgba(96,58,10,.90)'};
const TXT={CT:'#8fc3f5',T:'#f5c27a'};
function fmt(t){t=Math.max(0,t);return Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0');}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}

/* weapon name -> icon category (names come from the demo's active_weapon_name / kill weapon) */
function wcat(n){n=(n||'').toLowerCase();
 if(!n) return 'none';
 if(/awp|ssg|scout|scar|g3sg1/.test(n)) return 'sniper';
 if(/knife|bayonet|karambit|butterfly|flip|gut|falchion|shadow|bowie|huntsman|navaja|stiletto|talon|ursus|skeleton|paracord|survival|nomad|classic/.test(n)) return 'knife';
 if(/smoke/.test(n)) return 'smoke'; if(/flash/.test(n)) return 'flash';
 if(/he grenade|hegrenade/.test(n)) return 'he'; if(/molotov|incendiary|incgrenade/.test(n)) return 'fire';
 if(/decoy/.test(n)) return 'decoy'; if(/c4|bomb/.test(n)) return 'c4'; if(/zeus|taser/.test(n)) return 'zeus';
 if(/nova|xm1014|sawed|mag-?7/.test(n)) return 'shotgun';
 if(/mp[0-9]|p90|ump|mac-?10|bizon/.test(n)) return 'smg';
 if(/glock|usp|p2000|p250|five|tec|cz75|desert|deagle|dual|r8|revolver/.test(n)) return 'pistol';
 return 'rifle';}

function initViewer(root){
  const data=JSON.parse(root.querySelector('script[type="application/json"]').textContent);
  const bg=window.__MAPS[data.map]; const cv=root.querySelector('canvas'); const ctx=cv.getContext('2d');
  const img=new Image(); img.src=bg.img; cv.width=bg.w; cv.height=bg.h;
  const P=(x,y)=>[(x-bg.x0)/bg.s,(bg.y0-y)/bg.s];
  const range=root.querySelector('input[type=range]'), btn=root.querySelector('.v-play'), lab=root.querySelector('.v-time'), spd=root.querySelector('select');
  const rosterEl=root.querySelector('.v-roster'), feed=root.querySelector('.v-feed');
  const T=data.t0+(data.n-1)*data.dt; range.max=T; let t=Math.max(0,(data.focus==null?0:data.focus-8)); let playing=false, last=0;
  const R=Math.max(5,bg.w/110), W=cv.width, H=cv.height;
  let rosterHtml='';

  const clampT=x=>Math.max(data.t0,Math.min(T,x));
  function frameIx(tt){return Math.max(0,Math.min(data.n-1,Math.round((tt-data.t0)/data.dt)));}
  function posAt(p,tt){const f=(clampT(tt)-data.t0)/data.dt, i=Math.floor(f), j=Math.min(i+1,data.n-1);
    const a=[p.xy[2*i],p.xy[2*i+1]], b=[p.xy[2*j],p.xy[2*j+1]];
    if(a[0]==null) return null; if(b[0]==null) return a; const k=f-i; return [a[0]+(b[0]-a[0])*k,a[1]+(b[1]-a[1])*k];}

  /* facing: 1) a recorded aim angle from the last 1.5 s (shot / hit / kill), else 2) direction of travel, else 3) last known */
  function lastAim(p,tt){let r=null; for(const a of p.aim){ if(a[0]<=tt) r=a; else break; } return r;}
  function heading(p,tt){
    const a=lastAim(p,tt);
    if(a && tt-a[0]<=1.5){ p._th=-a[1]*Math.PI/180; return p._th; }
    const w=data.dt*2, ta=clampT(tt-w), tb=clampT(tt+w);
    if(tb>ta){const A=posAt(p,ta), B=posAt(p,tb);
      if(A&&B){const [ax,ay]=P(A[0],A[1]),[bx,by]=P(B[0],B[1]); if(Math.hypot(bx-ax,by-ay)>1.2){p._th=Math.atan2(by-ay,bx-ax); return p._th;}}}
    return p._th==null?null:p._th;
  }

  /* ---- small drawing helpers ---- */
  function rr(x,y,w,h,r){ctx.beginPath();ctx.moveTo(x+r,y);ctx.arcTo(x+w,y,x+w,y+h,r);ctx.arcTo(x+w,y+h,x,y+h,r);ctx.arcTo(x,y+h,x,y,r);ctx.arcTo(x,y,x+w,y,r);ctx.closePath();}
  function glyph(c,x,y,w,h,col){ /* icon drawn in box left=x, vertical centre=y */
    ctx.fillStyle=col; ctx.strokeStyle=col; ctx.lineWidth=Math.max(1,h*.13);
    const F=(a,b,cw,ch)=>ctx.fillRect(x+w*a,y+h*b,w*cw,h*ch);
    const poly=pts=>{ctx.beginPath();pts.forEach((q,i)=>i?ctx.lineTo(x+w*q[0],y+h*q[1]):ctx.moveTo(x+w*q[0],y+h*q[1]));ctx.closePath();ctx.fill();};
    const ball=(cx,cy,r)=>{ctx.beginPath();ctx.arc(x+w*cx,y+h*cy,h*r,0,7);ctx.fill();};
    if(c==='rifle'){F(0,-.05,.22,.32);F(.14,-.2,.42,.34);F(.5,-.13,.5,.16);poly([[.36,.12],[.5,.12],[.44,.5],[.32,.5]]);}
    else if(c==='sniper'){F(0,-.05,.2,.3);F(.14,-.16,.4,.3);F(.5,-.1,.5,.13);F(.3,-.36,.3,.14);poly([[.36,.1],[.48,.1],[.44,.42],[.34,.42]]);}
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
  }
  function cloud(x,y,r,a){ctx.fillStyle='rgba(255,255,255,'+a+')';
    [[-.5,.1,.42],[.1,-.15,.55],[.6,.1,.4]].forEach(function(c){ctx.beginPath();ctx.arc(x+r*c[0],y+r*c[1],r*c[2],0,7);ctx.fill();});}
  function flame(x,y,r,a){ctx.beginPath();ctx.moveTo(x,y-r);ctx.bezierCurveTo(x+r*.95,y-r*.15,x+r*.7,y+r*.9,x,y+r*.9);
    ctx.bezierCurveTo(x-r*.7,y+r*.9,x-r*.95,y-r*.15,x,y-r);ctx.fillStyle='rgba(255,240,180,'+a+')';ctx.fill();}
  function star(x,y,r1,r2,n,a,col){ctx.beginPath();for(let i=0;i<n*2;i++){const r=i%2?r2:r1,th=i*Math.PI/n;ctx.lineTo(x+Math.cos(th)*r,y+Math.sin(th)*r);}ctx.closePath();ctx.fillStyle=col+a+')';ctx.fill();}
  function pin(x,y,th,fill,edge,me){
    const D=R*2.7, al=Math.acos(R/D); ctx.beginPath();
    if(th==null){ctx.arc(x,y,R,0,7);}
    else{ctx.moveTo(x+Math.cos(th)*D,y+Math.sin(th)*D);ctx.lineTo(x+Math.cos(th+al)*R,y+Math.sin(th+al)*R);
      ctx.arc(x,y,R,th+al,th-al+Math.PI*2,false);ctx.closePath();}
    ctx.fillStyle=fill;ctx.fill();ctx.lineJoin='round';ctx.lineWidth=me?R*.42:R*.24;ctx.strokeStyle=me?'#fff':edge;ctx.stroke();
    ctx.beginPath();ctx.arc(x,y,R*.4,0,7);ctx.fillStyle='rgba(255,255,255,.95)';ctx.fill();
  }

  function drawNade(n){
    const age=t-n.t; if(age<0||age>n.d) return; const [x,y]=P(n.x,n.y), col=n.s==='CT'?'63,143,224':n.s==='T'?'227,154,53':'200,200,200';
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
  function drawThrow(n){ /* real throw spot + landing spot + both times; the path between is not recorded, so it is a straight line */
    if(n.tt==null||t<n.tt||t>n.t+1.2) return; const [tx,ty]=P(n.tx,n.ty),[nx,ny]=P(n.x,n.y);
    const a=t<=n.t?.85:Math.max(0,1-(t-n.t)/1.2)*.6;
    ctx.save();ctx.strokeStyle='rgba(235,240,250,'+a+')';ctx.lineWidth=Math.max(1.2,R*.16);ctx.setLineDash([R*.5,R*.45]);
    ctx.beginPath();ctx.moveTo(tx,ty);ctx.lineTo(nx,ny);ctx.stroke();ctx.setLineDash([]);
    ctx.beginPath();ctx.arc(tx,ty,R*.35,0,7);ctx.fillStyle='rgba(235,240,250,'+a+')';ctx.fill();
    if(t<=n.t){const f=(t-n.tt)/Math.max(.1,n.t-n.tt); ctx.beginPath();ctx.arc(tx+(nx-tx)*f,ty+(ny-ty)*f,R*.5,0,7);
      ctx.fillStyle=n.k==='smoke'?'#d5d9e0':n.k==='fire'?'#ff9a3c':n.k==='he'?'#9fb35f':'#ffffff';ctx.fill();ctx.lineWidth=1;ctx.strokeStyle='rgba(0,0,0,.6)';ctx.stroke();}
    ctx.restore();
  }

  function draw(){
    ctx.clearRect(0,0,W,H);ctx.fillStyle='#141a22';ctx.fillRect(0,0,W,H);
    if(img.complete){ctx.drawImage(img,0,0,W,H);ctx.fillStyle='rgba(8,12,18,.34)';ctx.fillRect(0,0,W,H);} /* dim radar so units stand out */
    for(const n of data.nades) drawNade(n);
    for(const n of data.nades) drawThrow(n);
    if(data.bomb&&t>=data.bomb.t){const [x,y]=P(data.bomb.x,data.bomb.y),ph=((t-data.bomb.t)*1.2)%1;
      ctx.beginPath();ctx.arc(x,y,R*(1+ph*2),0,7);ctx.strokeStyle='rgba(255,70,70,'+(.7*(1-ph))+')';ctx.lineWidth=R*.3;ctx.stroke();
      ctx.beginPath();ctx.arc(x,y,R*.9,0,7);ctx.fillStyle='#e03434';ctx.fill();ctx.lineWidth=R*.25;ctx.strokeStyle='#ffb0b0';ctx.stroke();
      glyph('c4',x-R*.55,y,R*1.1,R*1.1,'#fff');}
    const vis=[], fi=frameIx(t);
    for(const p of data.players){const q=posAt(p,t); if(!q) continue; const [x,y]=P(q[0],q[1]); vis.push({p,x,y,th:heading(p,t)});}
    /* recorded aim cones (only at moments the demo logged a view angle) */
    for(const v of vis){const a=lastAim(v.p,t); if(!a||t-a[0]>1.2) continue; const age=t-a[0], th=-a[1]*Math.PI/180, L=650/bg.s, k=1-age/1.2;
      const g=ctx.createRadialGradient(v.x,v.y,R,v.x,v.y,L);g.addColorStop(0,'rgba('+(v.p.side==='CT'?'63,143,224':'227,154,53')+','+(.38*k)+')');g.addColorStop(1,'rgba(255,255,255,0)');
      ctx.beginPath();ctx.moveTo(v.x,v.y);ctx.arc(v.x,v.y,L,th-.42,th+.42);ctx.closePath();ctx.fillStyle=g;ctx.fill();}
    for(const k of data.kills){ if(t<k.t) continue;
      if(t-k.t<1.5&&k.ax!=null&&k.vx!=null){const [a,b]=P(k.ax,k.ay),[c,d]=P(k.vx,k.vy);ctx.strokeStyle=k.as==='CT'?'rgba(120,180,240,'+(1-(t-k.t)/1.5)+')':'rgba(245,190,110,'+(1-(t-k.t)/1.5)+')';
        ctx.lineWidth=Math.max(1.5,R*.25);ctx.beginPath();ctx.moveTo(a,b);ctx.lineTo(c,d);ctx.stroke();}
      if(k.vx!=null){const [x,y]=P(k.vx,k.vy);ctx.strokeStyle=k.vs?COL[k.vs]:'#999';ctx.lineWidth=R*.4;ctx.beginPath();
        ctx.moveTo(x-R*.6,y-R*.6);ctx.lineTo(x+R*.6,y+R*.6);ctx.moveTo(x+R*.6,y-R*.6);ctx.lineTo(x-R*.6,y+R*.6);ctx.stroke();}}
    for(const v of vis){ if(v.p.fl[fi]){ctx.beginPath();ctx.arc(v.x,v.y,R*1.9,0,7);ctx.strokeStyle='rgba(255,255,255,.9)';ctx.lineWidth=R*.3;ctx.stroke();}
      pin(v.x,v.y,v.th,COL[v.p.side],EDGE[v.p.side],v.p.me);}
    /* name pills with the equipped weapon icon; nudged apart so they don't stack */
    const placed=[]; vis.sort((a,b)=>(b.p.me-a.p.me)||(a.y-b.y));
    for(const v of vis){const p=v.p, wn=data.weapons[p.wp[fi]]||'', cat=wcat(wn), gw=cat==='none'?0:R*4.0;
      const fs=Math.round(R*(p.me?2.25:1.95));ctx.font=(p.me?'700 ':'600 ')+fs+'px system-ui,sans-serif';ctx.textBaseline='middle';
      const tw=ctx.measureText(p.name).width, pw=tw+gw+R*1.7+(gw?R*.5:0), ph=R*3.0;
      let px=Math.max(3,Math.min(W-pw-3,v.x-pw/2)), py=v.y-R*3.5-ph, dir=-1;
      if(py<3){py=v.y+R*2.6;dir=1;}
      for(let i=0;i<6;i++){const hit=placed.some(o=>px<o[0]+o[2]+2&&px+pw+2>o[0]&&py<o[1]+o[3]+2&&py+ph+2>o[1]); if(!hit) break; py+=dir*(ph+2);}
      py=Math.max(3,Math.min(H-ph-3,py)); placed.push([px,py,pw,ph]);
      rr(px,py,pw,ph,ph/2.6);ctx.fillStyle=PILL[p.side];ctx.fill();if(p.me){ctx.lineWidth=R*.2;ctx.strokeStyle='#fff';ctx.stroke();}
      if(gw) glyph(cat,px+R*.8,py+ph/2,gw,ph*.8,'#e9edf3');
      ctx.fillStyle=p.me?'#fff':TXT[p.side];ctx.fillText(p.name,px+R*.8+gw+(gw?R*.5:0),py+ph/2+1);}
    /* kill feed, top right */
    const recent=data.kills.filter(k=>k.t<=t&&t-k.t<6).slice(-4);
    ctx.font='600 '+Math.round(R*1.9)+'px system-ui,sans-serif';
    recent.forEach(function(k,i){const an=k.a||'', vn=k.v, cat=wcat(k.wr), gw=R*4.0, sp=R*.7;
      const w1=an?ctx.measureText(an).width:0, w2=ctx.measureText(vn).width, hs=k.hs?R*1.4:0, tot=w1+(an?sp:0)+gw+hs+sp+w2+R*1.6, h=R*3.0;
      const x0=W-tot-6, y0=6+i*(h+3); rr(x0,y0,tot,h,h/2.6);ctx.fillStyle='rgba(10,14,20,.82)';ctx.fill();
      let cx=x0+R*.8; ctx.textBaseline='middle';
      if(an){ctx.fillStyle=TXT[k.as]||'#ddd';ctx.fillText(an,cx,y0+h/2+1);cx+=w1+sp;}
      glyph(cat==='none'?'rifle':cat,cx,y0+h/2,gw,h*.78,'#e9edf3');cx+=gw;
      if(k.hs){ctx.beginPath();ctx.arc(cx+R*.6,y0+h/2,R*.5,0,7);ctx.strokeStyle='#ff6b6b';ctx.lineWidth=R*.2;ctx.stroke();ctx.beginPath();ctx.arc(cx+R*.6,y0+h/2,R*.14,0,7);ctx.fillStyle='#ff6b6b';ctx.fill();cx+=hs;}
      cx+=sp;ctx.fillStyle=TXT[k.vs]||'#ddd';ctx.fillText(vn,cx,y0+h/2+1);});
    if(data.focus!=null&&Math.abs(t-data.focus)<1.2){ctx.strokeStyle='#ffd400';ctx.lineWidth=R/2;ctx.strokeRect(2,2,W-4,H-4);}
    range.value=t;lab.textContent=fmt(t)+' / '+fmt(T);
    const nextHtml=recent.map(k=>'<span><b class="'+(k.as||'')+'">'+esc(k.a||'World')+'</b> '+(k.w?'['+esc(k.w)+'] ':'')+'<b class="'+(k.vs||'')+'">'+esc(k.v)+'</b></span>').join('');
    if(feed.innerHTML!==nextHtml) feed.innerHTML=nextHtml;
    /* roster: health, armour and equipped weapon for both teams */
    let h='';
    for(const side of ['CT','T']){const ps=data.players.filter(p=>p.side===side); const alive=ps.filter(p=>p.xy[2*fi]!=null).length;
      h+='<div class="rt '+side+'"><div class="rh"><b>'+side+'</b><span>'+alive+' alive</span></div>';
      for(const p of ps){const up=p.xy[2*fi]!=null, hp=p.hp[fi], wn=data.weapons[p.wp[fi]]||'';
        h+='<div class="rr'+(up?'':' dead')+(p.me?' me':'')+'"><div class="l1"><span class="nm">'+esc(p.name)+'</span><span class="hpb"><i class="'+(hp<=30?'lo':'')+'" style="width:'+(up?Math.max(3,hp):0)+'%"></i></span><span class="hpn">'+(up?hp:'dead')+'</span></div>'
          +'<div class="wn">'+(up?esc(wn)+(p.ar[fi]?' · armor':''):'&nbsp;')+'</div></div>';}
      h+='</div>';}
    if(h!==rosterHtml){rosterHtml=h;rosterEl.innerHTML=h;}
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
            f'<div class="v-roster"></div>'
            f'<p class="muted small">{note} You are the white-outlined pin. Pins point where a player last aimed '
            f'(recorded on shots, hits and kills, held 1.5 s) or, otherwise, where they were moving; the shaded cone is that '
            f'recorded aim. The icon by each name is the equipped weapon. Smoke and fire are drawn at their in-game size. '
            f'A dashed line joins where a grenade was thrown to where it landed (straight line: the demo does not record the '
            f'flight path). Crosses mark deaths; a thin line flashes from killer to victim.</p></div>')


def maps_script(maps: dict) -> str:
    if not maps:
        return ""
    return "<script>window.__MAPS=" + json.dumps(maps, separators=(",", ":")) + ";</script><script>" + VIEWER_JS + "</script>"
