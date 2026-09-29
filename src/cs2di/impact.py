"""Round impact: what each kill and death did to the team's chance of winning the round.

Everything is learned from the batch itself (ADR-013). The win-chance table comes from the rounds
in the submitted demos: for every moment a death changes the numbers (e.g. 4 vs 5, bomb down), how
often did the side in that spot go on to win? Sparse spots borrow strength from the simpler
"players-alive difference" table (shrinkage), so one odd round cannot dominate.

Per-player events produced here (one row each):
- kills: win-chance swing, opening kill, trade kill (killed the enemy who had just killed a
  teammate), low-swing kill (changed the round by under 5 points, e.g. an already-decided round).
- deaths: swing, first death of the round, traded (a teammate killed the killer within 5 s),
  nearest teammate distance at death, died while the team had more players alive.
- trade chances: a teammate died near this player (within reach) while the player was alive;
  did the player kill that enemy within 5 s?
- clutches: the player was the last one alive against one or more enemies.

Limits: 5 s and 900 units are conventions, not truths; positions are sampled twice a second;
"within reach" ignores walls. Win-chance values are estimates from 20-30 games, not a model of
CS2. Post-round-end kills are kept out of impact (the round is decided).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

TICKRATE = 64
TRADE_S = 5.0
REACH = 900.0
LOW_SWING = 0.05
SIDES = {"CT": "CT", "TERRORIST": "T", "T": "T", 3: "CT", 2: "T", "3": "CT", "2": "T"}


def _side(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return SIDES.get(int(x) if isinstance(x, float) else x)


def _round_windows(rounds: pd.DataFrame):
    r = rounds.sort_values("round").reset_index(drop=True)
    nxt = r.start_tick.shift(-1).fillna(np.inf)
    return [(int(x["round"]), x.freeze_end_tick, x.end_tick, nxt[i], _side(x.winner), x.bomb_plant_tick)
            for i, x in r.iterrows()]


def demo_states(demo_dir: Path) -> tuple[list[dict], list[dict]]:
    """Death timeline with before/after numbers for one demo. Returns (states, deaths)."""
    demo_dir = Path(demo_dir)
    ms = json.loads((demo_dir / "match_summary.json").read_text(encoding="utf-8"))
    rounds = pd.read_csv(demo_dir / "rounds.csv")
    pr = pd.read_csv(demo_dir / "player_rounds.csv", dtype={"steamid": "int64"})
    pr["s"] = pr.side.map(_side)
    d = pd.read_csv(demo_dir / "events" / "player_death.csv.gz",
                    dtype={"attacker_steamid": "Int64", "user_steamid": "Int64"})
    states, deaths = [], []
    for rnd, lo, end, hi, winner, plant in _round_windows(rounds):
        if winner is None:
            continue
        roster = pr[(pr["round"] == rnd) & pr.s.notna()]
        side_of = dict(zip(roster.steamid, roster.s))
        alive = {"T": int((roster.s == "T").sum()) or 5, "CT": int((roster.s == "CT").sum()) or 5}
        ev = d[(d.tick >= lo) & (d.tick < hi) & d.user_steamid.notna()].sort_values("tick")
        planted = False
        states.append({"side": "T", "own": alive["T"], "opp": alive["CT"], "planted": False, "win": winner == "T"})
        states.append({"side": "CT", "own": alive["CT"], "opp": alive["T"], "planted": False, "win": winner == "CT"})
        first = True
        for r in ev.to_dict("records"):
            v = int(r["user_steamid"])
            vs = side_of.get(v) or _side(r.get("user_team_num"))
            if vs is None:
                continue
            planted = bool(not pd.isna(plant) and r["tick"] >= plant)
            before = dict(alive)
            alive[vs] = max(alive[vs] - 1, 0)
            a = r.get("attacker_steamid")
            a = None if pd.isna(a) else int(a)
            as_ = side_of.get(a) or _side(r.get("attacker_team_num")) if a is not None else None
            after_end = r["tick"] > end
            deaths.append({
                "demo_id": demo_dir.name, "map": ms.get("map_name"), "round": rnd, "tick": int(r["tick"]),
                "victim": v, "victim_side": vs, "attacker": a, "attacker_side": as_,
                "pvp": a is not None and a != v and as_ is not None and as_ != vs,
                "before_T": before["T"], "before_CT": before["CT"], "after_T": alive["T"], "after_CT": alive["CT"],
                "planted": planted, "winner": winner, "first_death": first and not after_end, "after_round_end": after_end,
                "weapon": r.get("weapon"), "round_time_s": (r["tick"] - lo) / TICKRATE,
            })
            first = first and after_end
            if not after_end:
                for s in ("T", "CT"):
                    o = "CT" if s == "T" else "T"
                    states.append({"side": s, "own": alive[s], "opp": alive[o], "planted": planted, "win": winner == s})
    return states, deaths


class WinChance:
    """Empirical win chance by (side, own alive, enemy alive, bomb planted), shrunk toward the
    pooled players-alive-difference table and then toward 0.5."""

    def __init__(self, states: pd.DataFrame, k: float = 6.0):
        s = states.copy()
        s["diff"] = s.own - s.opp
        g = s.groupby("diff").win.agg(["sum", "count"])
        self.by_diff = ((g["sum"] + k * 0.5) / (g["count"] + k)).to_dict()
        self.full = s.groupby(["side", "own", "opp", "planted"]).win.agg(["sum", "count"]).to_dict("index")
        self.k = k

    def __call__(self, side, own, opp, planted) -> float:
        if own <= 0:
            return 0.0
        if opp <= 0:
            return 1.0
        prior = self.by_diff.get(own - opp, 0.5)
        c = self.full.get((side, own, opp, planted))
        if not c:
            return prior
        return (c["sum"] + self.k * prior) / (c["count"] + self.k)


def _nearest_teammate(pos: pd.DataFrame, tick: int, sid: int, team: str) -> float | None:
    """Distance to the nearest living teammate at the last position sample before ``tick``."""
    t = pos.tick[pos.tick <= tick]
    if t.empty:
        return None
    snap = pos[pos.tick == t.max()]
    me = snap[snap.steamid == sid]
    if me.empty:
        return None
    mates = snap[(snap.team_name == team) & (snap.steamid != sid) & (snap.is_alive == True)]  # noqa: E712
    if mates.empty:
        return None
    x, y, z = me.iloc[0][["X", "Y", "Z"]]
    return float(np.sqrt((mates.X - x) ** 2 + (mates.Y - y) ** 2 + (mates.Z - z) ** 2).min())


def batch_impact(batch_dir: Path) -> dict[str, pd.DataFrame]:
    """Kills, deaths, trade chances and clutches for EVERY player in the batch (peers included)."""
    dirs = sorted(p for p in Path(batch_dir).iterdir() if (p / "match_summary.json").exists())
    all_states, per_demo = [], []
    for p in dirs:
        if json.loads((p / "match_summary.json").read_text(encoding="utf-8")).get("valid") is False:
            continue
        s, d = demo_states(p)
        all_states += s
        per_demo.append((p, pd.DataFrame(d)))
    wc = WinChance(pd.DataFrame(all_states))
    kills, deaths, chances, clutches, pr_rows = [], [], [], [], []
    trade_ticks = TRADE_S * TICKRATE
    for p, d in per_demo:
        if d.empty:
            continue
        pos = pd.read_csv(p / "player_positions.csv.gz", usecols=["tick", "steamid", "team_name", "is_alive", "X", "Y", "Z"],
                          dtype={"steamid": "int64"})
        pos["team"] = pos.team_name.map(_side)
        pos["team_name"] = pos["team"]
        ros_all = pd.read_csv(p / "player_rounds.csv", dtype={"steamid": "int64"})
        pr_rows.append(ros_all[ros_all.side.notna()].assign(demo_id=p.name)[["demo_id", "round", "steamid"]])
        for rnd, g in d.groupby("round"):
            g = g.sort_values("tick")
            live = g[~g.after_round_end]
            for _, r in g.iterrows():
                vs, as_ = r.victim_side, r.attacker_side
                b_own, b_opp = (r.before_T, r.before_CT) if vs == "T" else (r.before_CT, r.before_T)
                a_own, a_opp = (r.after_T, r.after_CT) if vs == "T" else (r.after_CT, r.after_T)
                swing = 0.0 if r.after_round_end else wc(vs, a_own, a_opp, r.planted) - wc(vs, b_own, b_opp, r.planted)
                later = live[(live.tick > r.tick) & (live.tick <= r.tick + trade_ticks)]
                traded = bool(r.pvp and ((later.victim == r.attacker) & (later.attacker_side == vs)).any())
                dist = _nearest_teammate(pos, r.tick, r.victim, vs)
                base = {"demo_id": r.demo_id, "map": r["map"], "round": rnd, "tick": r.tick,
                        "round_time_s": r.round_time_s, "winner": r.winner, "after_round_end": r.after_round_end}
                deaths.append({**base, "steamid": r.victim, "side": vs, "killer": r.attacker, "pvp": r.pvp,
                               "swing": swing, "first_death": r.first_death, "traded": traded,
                               "teammate_distance": dist, "team_ahead": b_own > b_opp, "team_behind": b_own < b_opp,
                               "own_alive": b_own, "opp_alive": b_opp, "planted": r.planted,
                               "round_won": r.winner == vs})
                if r.pvp:
                    earlier = live[(live.tick < r.tick) & (live.tick >= r.tick - trade_ticks)]
                    trade_kill = bool(((earlier.attacker == r.victim) & (earlier.victim_side == as_)).any())
                    kills.append({**base, "steamid": r.attacker, "side": as_, "victim": r.victim, "swing": -swing,
                                  "opening": r.first_death, "trade_kill": trade_kill,
                                  "low_swing": (-swing) < LOW_SWING, "own_alive": b_opp, "opp_alive": b_own,
                                  "weapon": r.weapon, "round_won": r.winner == as_})
                    # trade chances for the victim's living teammates within reach
                    if not r.after_round_end:
                        snap_t = pos.tick[pos.tick <= r.tick]
                        if not snap_t.empty:
                            snap = pos[(pos.tick == snap_t.max())]
                            vpos = snap[snap.steamid == r.victim]
                            mates = snap[(snap.team == vs) & (snap.steamid != r.victim) & (snap.is_alive == True)]  # noqa: E712
                            if not vpos.empty:
                                x, y, z = vpos.iloc[0][["X", "Y", "Z"]]
                                for _, m in mates.iterrows():
                                    dd = float(np.sqrt((m.X - x) ** 2 + (m.Y - y) ** 2 + (m.Z - z) ** 2))
                                    if dd <= REACH:
                                        got = bool(((later.victim == r.attacker) & (later.attacker == m.steamid)).any())
                                        chances.append({**base, "steamid": int(m.steamid), "side": vs, "dead_teammate": r.victim,
                                                        "enemy": r.attacker, "distance": dd, "traded_by_me": got})
            # clutches: first moment a side is down to one player vs one or more
            for s in ("T", "CT"):
                o = "CT" if s == "T" else "T"
                hit = live[(live[f"after_{s}"] == 1) & (live[f"after_{o}"] >= 1)]
                if hit.empty:
                    continue
                h = hit.iloc[0]
                dead = set(live[(live.tick <= h.tick) & (live.victim_side == s)].victim)
                ros = ros_all[(ros_all["round"] == rnd) & (ros_all.side.map(_side) == s)]
                last = [x for x in ros.steamid if x not in dead]
                if len(last) == 1:
                    clutches.append({"demo_id": h.demo_id, "map": h["map"], "round": rnd, "tick": int(h.tick),
                                     "steamid": int(last[0]), "side": s, "vs": int(h[f"after_{o}"]),
                                     "planted": bool(h.planted), "won": h.winner == s})
    return {"player_rounds": pd.concat(pr_rows, ignore_index=True) if pr_rows else pd.DataFrame(columns=["demo_id", "round", "steamid"]),
            "kills": pd.DataFrame(kills), "deaths": pd.DataFrame(deaths),
            "trade_chances": pd.DataFrame(chances), "clutches": pd.DataFrame(clutches)}
