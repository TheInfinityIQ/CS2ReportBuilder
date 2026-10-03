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

from . import fmt, weapons as wmap

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


SIDECAR_HZ_STEP = 8  # ticks between sidecar samples (8 Hz)


def _sidecar_tracks(d: Path, round_no: int, lo: int, hi: int):
    """Continuous facing + position from extractor/extract_viewer_tracks.py (8 Hz), or None when not present."""
    f = d / "viewer_tracks.csv.gz"
    if not f.exists():
        return None
    t = pd.read_csv(f, dtype={"steamid": "int64"})
    t = t[(t["round"] == round_no) & (t.tick >= lo) & (t.tick <= hi)]
    if t.empty:
        return None
    return t


def _sidecar_throws(d: Path, round_no: int):
    """Real projectile paths (simplified to +-12 units) per throw, or (None, None) when not present."""
    ft, fp = d / "grenade_throws.csv.gz", d / "grenade_paths.csv.gz"
    if not (ft.exists() and fp.exists()):
        return None, None
    th = pd.read_csv(ft, dtype={"steamid": "int64"})
    th = th[th["round"] == round_no]
    if th.empty:
        return None, None
    pa = pd.read_csv(fp)
    pa = pa[pa.throw_id.isin(th.throw_id)]
    return th, {int(k): g.sort_values("tick") for k, g in pa.groupby("throw_id")}


def _nades(d: Path, lo: int, hi: int, side_of: dict, round_no: int | None = None) -> list[dict]:
    """Grenade detonations, each tied to the real throw (spot + time) recorded in weapon_fire.

    With the viewer-tracks sidecar the real flight path is attached (`pa`, points every ~12 units of deviation).
    Without it only the throw spot, landing spot and both times are known, and the viewer draws a plain straight
    line and says so.
    """
    sc_th, sc_pa = _sidecar_throws(d, round_no) if round_no is not None else (None, None)
    sc_used: set[int] = set()
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
            if sc_th is not None and sid is not None:
                m = sc_th[(sc_th.steamid == sid) & (sc_th.kind == kind) & (sc_th.detonated == 1)
                          & ((sc_th.det_tick - row.tick).abs() <= 3)]
                m = m[~m.throw_id.isin(sc_used)]
                if len(m):
                    th = m.iloc[(m.det_tick - row.tick).abs().argsort().iloc[0]]
                    tid = int(th.throw_id)
                    sc_used.add(tid)
                    pts = sc_pa.get(tid)
                    if pts is not None and len(pts) >= 2:
                        n["pa"] = [[round((int(a) - lo) / TICK, 2), int(b), int(c)]
                                   for a, b, c in zip(pts.tick, pts.x, pts.y)]
                        n["tt"] = round((int(th.throw_tick) - lo) / TICK, 2)
                        n["tx"], n["ty"] = int(th.throw_x), int(th.throw_y)
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
                hp.append(0)
                ar.append(0)
                wp.append(-1)
                fl.append(0)
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
    # State (health, armour, active item, flash) stays on the 2 Hz grid; position and facing move to 8 Hz when the
    # viewer-tracks sidecar exists. Facing is then a recorded value at every sample (circular interpolation in the
    # browser), not an inference from events.
    sdt = (ticks[1] - ticks[0]) / TICK if len(ticks) > 1 else 0.5
    st0 = (ticks[0] - lo) / TICK if ticks else 0.0
    sn = len(ticks)
    grid = dict(dt=sdt, t0=st0, n=sn)
    sc = _sidecar_tracks(d, round_no, lo, hi)
    facing = False
    if sc is not None and sid_index and set(sid_index) <= set(int(x) for x in sc.steamid.unique()):
        gt = list(range(lo, min(hi, int(sc.tick.max())) + 1, SIDECAR_HZ_STEP))
        for sid_, ix in sid_index.items():
            g = sc[sc.steamid == sid_].drop_duplicates("tick").set_index("tick").reindex(gt)
            ok = g["x"].notna().to_numpy()
            xs, ys, ws, fs = g["x"].to_numpy(), g["y"].to_numpy(), g["yaw"].to_numpy(), g["flags"].to_numpy()
            xy8, yw8, fg8 = [], [], []
            for k in range(len(gt)):
                if ok[k]:
                    xy8 += [int(xs[k]), int(ys[k])]
                    yw8.append(None if np.isnan(ws[k]) else int(round(float(ws[k]))))
                    fg8.append(0 if np.isnan(fs[k]) else int(fs[k]))
                else:
                    xy8 += [None, None]
                    yw8.append(None)
                    fg8.append(0)
            players[ix].update({"xy": xy8, "yw": yw8, "fg": fg8})
        grid = dict(dt=SIDECAR_HZ_STEP / TICK, t0=0.0, n=len(gt))
        facing = True
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
                      "wi": wmap.icon_id(e.weapon) if isinstance(e.weapon, str) else "",
                      "hs": bool(getattr(e, "headshot", False)) if not pd.isna(getattr(e, "headshot", float("nan"))) else False})
    nades = _nades(d, lo, hi, side_of, round_no)
    bomb = None
    bp = d / "events" / "bomb_planted.csv.gz"
    if bp.exists():
        b = pd.read_csv(bp, usecols=lambda c: c in {"tick", "user_X", "user_Y", "site"})
        b = b[(b.tick >= lo) & (b.tick <= hi)]
        if len(b):
            bomb = {"t": (int(b.tick.iloc[0]) - lo) / TICK, "x": int(b.user_X.iloc[0]), "y": int(b.user_Y.iloc[0])}
    return {"map": ms.get("map_name"), "dt": grid["dt"], "t0": grid["t0"], "n": grid["n"],
            "sdt": float(sdt), "st0": float(st0), "sn": sn, "facing": facing,
            "players": players, "weapons": weapons, "wi": [wmap.icon_id(w) for w in weapons], "kills": kills,
            "nades": nades, "bomb": bomb, "focus": None if focus_tick is None else (focus_tick - lo) / TICK,
            "end": (int(r.end_tick) - lo) / TICK}


def _view_offsets(d: Path, round_no: int, tick: int, me: int, other: int):
    """How far (degrees) the player's recorded view was from the other player, 1.0 s and 0.5 s before `tick`.
    Needs the viewer-tracks sidecar (8 Hz view angle); returns None without it."""
    f = d / "viewer_tracks.csv.gz"
    if not f.exists():
        return None
    t = pd.read_csv(f, dtype={"steamid": "int64"})
    t = t[(t["round"] == round_no) & (t.tick >= tick - 2 * TICK) & (t.tick <= tick + 8)]
    out = {}
    for label, back in (("1.0", 64), ("0.5", 32)):
        want = tick - back
        rows = {}
        for who in (me, other):
            g = t[t.steamid == who]
            if g.empty:
                break
            g = g.iloc[(g.tick - want).abs().argsort()[:1]]
            if abs(int(g.tick.iloc[0]) - want) > 8:
                break
            rows[who] = g.iloc[0]
        if len(rows) < 2:
            return None
        dx, dy = float(rows[other]["x"] - rows[me]["x"]), float(rows[other]["y"] - rows[me]["y"])
        dist = float(np.hypot(dx, dy))
        if dist < 1:
            return None
        bearing = float(np.degrees(np.arctan2(dy, dx)))
        off = abs(((float(rows[me]["yaw"]) - bearing + 540) % 360) - 180)
        out[label] = (int(round(off)), int(round(dist)))
    return out


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
    # Where the player was looking just before a kill or death in this moment (recorded view angle, 8 Hz sidecar)
    for e in near.itertuples():
        if abs(e.tick - focus_tick) > TICK or pd.isna(e.attacker_steamid) or pd.isna(e.user_steamid):
            continue
        a, v = int(e.attacker_steamid), int(e.user_steamid)
        if a == v or steamid not in (a, v):
            continue
        other = a if v == steamid else v
        vo = _view_offsets(d, round_no, int(e.tick), steamid, other)
        if not vo:
            continue
        name = e.attacker_name if v == steamid else e.user_name
        (o1, dist), (o5, _) = vo["1.0"], vo["0.5"]
        verb = f"died to {name}" if v == steamid else f"killed {name}"
        facts.append(f"When you {verb} from {dist} units away, your view was {o5}° away from them half a second earlier "
                     f"and {o1}° away one second earlier (recorded view angle).")
    return facts


VIEWER_JS = (Path(__file__).with_name("viewer.js")).read_text(encoding="utf-8")


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
    real = data["facing"]
    face_note = ("Each pin points where that player was actually looking (view angle recorded 8 times a second)."
                 if real else
                 "Each pin points where that player last aimed, but only right after a shot, hit or kill (held 1.5 s); "
                 "between those moments the demo has no view angle here, so a moving player gets a short trail and a "
                 "still player a plain dot.")
    paths = any("pa" in n for n in data["nades"])
    nade_note = ("Grenades follow their recorded flight path, bounces included." if paths else
                 "A dashed line joins where a grenade was thrown to where it landed (a straight line: the flight path "
                 "is not recorded for this game).")
    how = (f'<details class="disc v-how"><summary>How to read this replay</summary><div class="disc-body">'
           f'<p>{note} You are the white-outlined pin. {face_note} The icon by each name is the kind of item the player '
           f'is holding (rifle, pistol, grenade, knife, bomb); the exact item is in the list under the map. '
           f'Smoke and fire are drawn at their in-game size. {nade_note} Crosses mark deaths and a thin line flashes from '
           f'killer to victim. A white ring means flashed; a green dashed ring means defusing. Coloured ticks on the timeline '
           f'are kills, the bomb plant, the moment being discussed (yellow) and the round end.</p></div></details>')
    return (f'<div class="viewer"><script type="application/json">{payload}</script>'
            f'<div class="v-stage"><canvas role="img" aria-label="Top-down replay of the round"></canvas>'
            f'<button class="v-expand" aria-pressed="false">Expand replay</button></div>'
            f'<div class="v-feed" aria-live="polite"></div>'
            f'<div class="v-ctl"><button class="v-prev" title="Previous event">◀ Event</button>'
            f'<button class="v-play" aria-pressed="false">Play</button>'
            f'<button class="v-next" title="Next event">Event ▶</button>'
            f'<button data-step="-0.5" title="Back half a second" aria-label="Back half a second">−½</button>'
            f'<button data-step="0.5" title="Forward half a second" aria-label="Forward half a second">+½</button>'
            f'<button class="v-jump" title="Jump to 5 seconds before the moment">Lead-in</button></div>'
            f'<div class="v-ctl v-scrub"><div class="v-track"><input type="range" min="0" step="0.05" aria-label="Round time">'
            f'<div class="v-marks"></div></div>'
            f'<span class="v-time"></span><select aria-label="Speed"><option value="0.5">0.5×</option>'
            f'<option value="1" selected>1×</option><option value="2">2×</option><option value="4">4×</option></select></div>'
            f'<div class="v-ctl v-layers"><span class="v-lbl">Show</span>'
            f'<button data-layer="names" aria-pressed="true">Names</button>'
            f'<button data-layer="facing" aria-pressed="true">Facing</button>'
            f'<button data-layer="util" aria-pressed="true">Utility</button>'
            f'<button data-layer="feed" aria-pressed="true">Feed</button></div>'
            f'<div class="v-roster"></div>{how}</div>')


def maps_script(maps: dict) -> str:
    if not maps:
        return ""
    return "<script>window.__MAPS=" + json.dumps(maps, separators=(",", ":")) + ";</script><script>" + VIEWER_JS + "</script>"
