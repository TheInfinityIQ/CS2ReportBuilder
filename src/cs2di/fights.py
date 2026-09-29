"""Fight episodes: every gunfight between two opposing players, not only the ones that end in a death.

A fight starts at the first gun damage between two opposing players (either direction) and
continues while they keep damaging each other with gaps of at most ``GAP_S`` seconds. It ends
when one kills the other or the gap passes. Grenade and fire damage never start a fight (it is
not a duel), but a grenade kill still ends one.

Each fight yields two rows, one per participant, with the situation as it was at the first
damage from that participant's point of view. Everything is taken from event-time state the
extractor already recorded; nothing is re-parsed.

Outcome per row: ``win`` (killed the opponent), ``loss`` (killed by the opponent) or ``none``
(nobody died to the other: disengaged, or one of them was finished by someone else).

Limits (carried into every finding):
- Fights with no damage at all (a missed peek, a shot that never landed) are invisible.
- "Initiative" means dealing the first damage, not seeing or shooting first.
- Man advantage counts deaths so far and assumes five a side.
"""

from __future__ import annotations

import json
import re
import math
from pathlib import Path

import pandas as pd

TICKRATE = 64
GAP_S = 3.0
NON_DUEL = ("hegrenade", "inferno", "molotov", "incgrenade", "smokegrenade", "flashbang", "decoy", "world")

RIFLES = {"ak47", "m4a1", "m4a1_silencer", "m4a4", "galilar", "famas", "aug", "sg556"}
SNIPERS = {"awp", "ssg08", "g3sg1", "scar20"}
SMGS = {"mac10", "mp9", "mp7", "mp5sd", "ump45", "p90", "bizon"}
PISTOLS = {"glock", "hkp2000", "usp_silencer", "p250", "fiveseven", "tec9", "cz75a", "deagle", "elite", "revolver"}
HEAVY = {"nova", "xm1014", "mag7", "sawedoff", "m249", "negev"}


ALIASES = {  # event names (ak47) and display names (AK-47) both occur: pitfall 24
    "m4a1s": "m4a1_silencer", "usps": "usp_silencer", "uspsilencer": "usp_silencer", "p2000": "hkp2000",
    "glock18": "glock", "deserteagle": "deagle", "tec9": "tec9", "dualberettas": "elite", "cz75auto": "cz75a",
    "r8revolver": "revolver", "sg553": "sg556", "ppbizon": "bizon", "mac10": "mac10", "zeusx27": "taser",
    "m4a4": "m4a4", "sawedoff": "sawedoff", "highexplosivegrenade": "hegrenade", "incendiarygrenade": "incgrenade",
    "c4explosive": "c4",
}
UTILITY = {"hegrenade", "incgrenade", "molotov", "smokegrenade", "flashbang", "decoy", "c4", "taser"}


def _norm_weapon(w) -> str:
    s = re.sub(r"[\s\-_]", "", str(w or "").lower().replace("weapon_", ""))
    s = {"m4a1silencer": "m4a1_silencer", "uspsilencer": "usp_silencer"}.get(s, s)
    return ALIASES.get(s, s)


def weapon_class(w) -> str:
    s = _norm_weapon(w)
    for name, group in (("rifle", RIFLES), ("sniper", SNIPERS), ("smg", SMGS), ("pistol", PISTOLS),
                        ("heavy", HEAVY), ("utility", UTILITY)):
        if s in group:
            return name
    if any(k in s for k in ("knife", "bayonet", "karambit", "dagger")):
        return "knife"
    return "unknown" if not s or s == "nan" else "other"


def _speed(r, p):
    x, y = r.get(f"{p}_velocity_X"), r.get(f"{p}_velocity_Y")
    if x is None or y is None or pd.isna(x) or pd.isna(y):
        return None
    return math.hypot(x, y)


def _dist(r):
    try:
        v = [r[f"attacker_{a}"] - r[f"user_{a}"] for a in "XYZ"]
    except KeyError:
        return None
    return None if any(pd.isna(x) for x in v) else math.sqrt(sum(x * x for x in v))


def _side(team_num):
    return {2: "T", 3: "CT"}.get(int(team_num)) if not pd.isna(team_num) else None


def demo_fights(demo_dir: Path) -> pd.DataFrame:
    """Two rows per fight for one analyzed demo."""
    demo_dir = Path(demo_dir)
    ms = json.loads((demo_dir / "match_summary.json").read_text(encoding="utf-8"))
    rounds = pd.read_csv(demo_dir / "rounds.csv")
    rinfo = rounds.set_index("parser_round")[["round", "freeze_end_tick", "end_tick", "bomb_plant_tick"]].to_dict("index")
    sid = {"attacker_steamid": "Int64", "user_steamid": "Int64"}
    h = pd.read_csv(demo_dir / "events" / "player_hurt.csv.gz", dtype=sid)
    d = pd.read_csv(demo_dir / "events" / "player_death.csv.gz", dtype=sid)
    dmg = "dmg_health_effective" if "dmg_health_effective" in h.columns else "dmg_health_capped"
    ok = (h.attacker_steamid.notna() & h.user_steamid.notna() & (h.attacker_steamid != h.user_steamid)
          & (h.attacker_team_num != h.user_team_num) & h.total_rounds_played.isin(rinfo.keys()))
    h = h[ok].copy()
    h["duel"] = ~h.weapon.astype(str).str.lower().isin(NON_DUEL)
    h["kind"] = 0  # hurt sorts before a death on the same tick
    d = d[d.user_steamid.notna()].copy()
    d["kind"] = 1
    d["duel"] = False
    ev = pd.concat([h, d], ignore_index=True, sort=False).sort_values(["tick", "kind"], kind="mergesort")
    deaths_by_tick = d[["tick", "user_team_num"]].sort_values("tick")

    open_: dict[tuple, dict] = {}
    done: list[dict] = []
    gap = GAP_S * TICKRATE

    def close(key):
        f = open_.pop(key, None)
        if f:
            done.append(f)

    for r in ev.to_dict("records"):
        t = r["tick"]
        if r["kind"] == 1:
            v, a = r["user_steamid"], r.get("attacker_steamid")
            for key in [k for k in open_ if v in k[1:]]:
                f = open_[key]
                if t - f["last"] > gap:
                    close(key)
                    continue
                if not pd.isna(a) and a in key[1:] and a != v:
                    f["winner"] = int(a)
                else:
                    f["ended_by_other"] = True
                close(key)
            continue
        a, v = int(r["attacker_steamid"]), int(r["user_steamid"])
        key = (int(r["total_rounds_played"]), min(a, v), max(a, v))
        f = open_.get(key)
        if f and t - f["last"] > gap:
            close(key)
            f = None
        if f is None:
            if not r["duel"]:
                continue
            f = {"key": key, "start": t, "last": t, "first": r, "hits": {a: 0, v: 0}, "dmg": {a: 0.0, v: 0.0},
                 "winner": None, "ended_by_other": False}
            open_[key] = f
        f["last"] = t
        f["hits"][a] += 1
        f["dmg"][a] += float(r.get(dmg) or 0)
    for key in list(open_):
        close(key)

    rows = []
    for f in done:
        r, (rnd, _, _) = f["first"], f["key"]
        ri = rinfo[rnd]
        init, targ = int(r["attacker_steamid"]), int(r["user_steamid"])
        t = f["start"]
        before = deaths_by_tick[deaths_by_tick.tick < t]
        dead = before[(before.tick >= ri["freeze_end_tick"])].user_team_num.value_counts().to_dict()
        plant = ri["bomb_plant_tick"]
        for me, opp, mp, op in ((init, targ, "attacker", "user"), (targ, init, "user", "attacker")):
            my_team, opp_team = r.get(f"{mp}_team_num"), r.get(f"{op}_team_num")
            alive_me = 5 - dead.get(my_team, 0)
            alive_opp = 5 - dead.get(opp_team, 0)
            outcome = "win" if f["winner"] == me else "loss" if f["winner"] == opp else "none"
            rows.append({
                "demo_id": demo_dir.name, "map": ms.get("map_name"), "source": ms.get("demo_source_family"),
                "parser_round": rnd, "round": ri["round"], "start_tick": t, "end_tick": f["last"],
                "steamid": me, "opponent": opp, "side": _side(my_team),
                "outcome": outcome, "ended_by_other": f["ended_by_other"] and f["winner"] is None,
                "initiative": me == init,
                "my_speed": _speed(r, mp), "opp_speed": _speed(r, op), "distance": _dist(r),
                "my_hp": r.get(f"{mp}_health") if me == init else r.get("user_health"),
                "opp_hp": r.get("user_health") if me == init else r.get(f"{op}_health"),
                "my_weapon": weapon_class(r.get(f"{mp}_active_weapon_name")),
                "opp_weapon": weapon_class(r.get(f"{op}_active_weapon_name")),
                "my_scoped": r.get(f"{mp}_is_scoped"), "my_ducking": r.get(f"{mp}_ducking"),
                "my_equip": r.get(f"{mp}_current_equip_value"), "opp_equip": r.get(f"{op}_current_equip_value"),
                "place": r.get(f"{mp}_last_place_name"), "opp_place": r.get(f"{op}_last_place_name"),
                "alive_me": alive_me, "alive_opp": alive_opp,
                "round_time_s": (t - ri["freeze_end_tick"]) / TICKRATE,
                "post_plant": bool(not pd.isna(plant) and t >= plant),
                "my_hits": f["hits"][me], "opp_hits": f["hits"][opp],
                "my_damage": f["dmg"][me], "opp_damage": f["dmg"][opp],
                "duration_s": (f["last"] - t) / TICKRATE,
            })
    out = pd.DataFrame(rows)
    return out


def batch_fights(batch_dir: Path) -> pd.DataFrame:
    dirs = sorted(p for p in Path(batch_dir).iterdir() if (p / "match_summary.json").exists())
    frames = []
    for p in dirs:
        ms = json.loads((p / "match_summary.json").read_text(encoding="utf-8"))
        if ms.get("valid") is False:
            continue
        frames.append(demo_fights(p))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def match_fingerprint(g: pd.DataFrame) -> tuple:
    """Same match extracted twice (e.g. into two batches) gives the same fingerprint."""
    g = g.sort_values(["start_tick", "steamid"])
    return (g["map"].iloc[0], tuple(zip(g.start_tick.head(8), g.steamid.head(8))))


def load_fights(paths) -> pd.DataFrame:
    """Load per-batch fight files and keep ONE copy of every match (pitfall 28)."""
    frames = []
    for p in paths:
        f = pd.read_csv(p)
        f["batch"] = Path(p).name.replace("fights_", "").replace(".csv.gz", "")
        frames.append(f)
    f = pd.concat(frames, ignore_index=True)
    fp = f.groupby(["batch", "demo_id"], sort=True).apply(match_fingerprint, include_groups=False)
    keep = set(fp[~fp.duplicated(keep="first")].index)
    return f[[k in keep for k in zip(f.batch, f.demo_id)]].reset_index(drop=True)


__all__ = ["demo_fights", "batch_fights", "weapon_class", "load_fights", "match_fingerprint"]
