"""Resolve a (demo, round) reference into a plain event timeline, from analyzed files only."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import fmt


def load_situation(batch_dir: Path, demo_id: str, round_no: int, steamid: int) -> dict:
    d = Path(batch_dir) / demo_id
    if not d.is_dir():
        raise KeyError(f"demo not found: {demo_id}")
    ms = json.loads((d / "match_summary.json").read_text(encoding="utf-8"))
    tick = float(ms.get("tickrate") or 64)
    rounds = pd.read_csv(d / "rounds.csv").sort_values("round").reset_index(drop=True)
    hit = rounds[rounds["round"] == round_no]
    if hit.empty:
        raise KeyError(f"round {round_no} not found in {demo_id}")
    i = int(hit.index[0])
    r = hit.iloc[0]
    lo = float(r["freeze_end_tick"])
    hi = float(rounds.iloc[i + 1]["start_tick"]) if i + 1 < len(rounds) else float("inf")
    pr = pd.read_csv(d / "player_rounds.csv", dtype={"steamid": "int64"})
    pr = pr[pr["round"] == round_no]
    side_of = {int(s): fmt.side_name(x) for s, x in zip(pr.steamid, pr.side)}
    players = pd.read_csv(d / "players.csv", dtype={"steamid": "int64"})
    name_of = {int(s): str(n) for s, n in zip(players.steamid, players.name)}
    me = pr[pr.steamid == steamid]
    if me.empty:
        raise KeyError(f"player not in round {round_no} of {demo_id}")
    death_cols = ["tick", "attacker_steamid", "user_steamid", "attacker_team_num", "user_team_num",
                  "headshot", "weapon", "attacker_last_place_name", "user_last_place_name"]
    ev = pd.read_csv(d / "events" / "player_death.csv.gz", usecols=lambda c: c in death_cols,
                     dtype={"attacker_steamid": "Int64", "user_steamid": "Int64"})
    ev = ev[(ev.tick >= lo) & (ev.tick < hi)].sort_values("tick")
    out = []
    for _, e in ev.iterrows():
        a = int(e.attacker_steamid) if pd.notna(e.attacker_steamid) else None
        v = int(e.user_steamid) if pd.notna(e.user_steamid) else None
        role = "kill" if a == steamid and v != steamid else "death" if v == steamid else None
        out.append({
            "t": (float(e.tick) - lo) / tick,
            "killer": name_of.get(a) if a else None, "killer_side": side_of.get(a),
            "victim": name_of.get(v) if v else None, "victim_side": side_of.get(v),
            "weapon": None if pd.isna(e.weapon) else str(e.weapon),
            "headshot": bool(e.headshot) if pd.notna(e.headshot) else False,
            "place": fmt.place(e.user_last_place_name),
            "self_or_world": a is None or a == v,
            "role": role,
        })
    bomb = None
    if pd.notna(r.get("bomb_plant_tick")) and lo <= float(r["bomb_plant_tick"]) < hi:
        bomb = {"t": (float(r["bomb_plant_tick"]) - lo) / tick,
                "site": str(r.get("bomb_plant_site") or "").replace("Bombsite", "")}
    return {
        "demo_id": demo_id, "round": round_no, "map": ms.get("map_name"),
        "side": fmt.side_name(me.iloc[0]["side"]), "win": str(me.iloc[0]["result"]) == "WIN",
        "events": out, "bomb": bomb, "duration_s": float(r.get("duration_s") or 0),
        "player_name": name_of.get(steamid),
    }
