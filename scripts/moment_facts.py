"""Print the software's facts about the example rounds of a finding, so a coach can check a claim before writing it.

Usage:  python <this file> <batch_dir> <steamid> <analysis.json> <finding_id> [example_index ...]

For each example it prints: map, round, side, result, the observed-facts lines the report itself shows
(numbers alive, bomb, kills within 5 s, recorded view angle before the kill/death when available) and a few
extra context lines (place names, active items, health, distance to the nearest teammate, kill weapon).
Anything you write in a Coach's read must agree with these lines. Extra context is sampled twice a second,
so treat places, items and health as approximate.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cs2di.report import viewer  # noqa: E402


def context(b: Path, demo: str, rnd: int, tick: int, sid: int) -> list[str]:
    d = b / demo
    pos = pd.read_csv(d / "player_positions.csv.gz", dtype={"steamid": "int64"}, low_memory=False)
    pr = pd.read_csv(d / "player_rounds.csv", dtype={"steamid": "int64"})
    pr = pr[pr["round"] == rnd]
    side = {int(a): str(c) for a, c in zip(pr.steamid, pr.side)}
    p = pos[(pos.tick <= tick) & (pos.tick >= tick - 64) & (pos.is_alive == True)]  # noqa: E712
    if p.empty:
        return []
    q = p[p.tick == p.tick.max()]
    me = q[q.steamid == sid]
    if me.empty:
        return []
    me = me.iloc[0]
    mates = q[(q.steamid != sid) & (q.steamid.map(side) == side.get(sid))]
    out = [f"(approx) you: at {me.last_place_name}, holding {me.active_weapon_name}, {int(me.health)} health"]
    if len(mates):
        dm = np.hypot(mates.X - me.X, mates.Y - me.Y)
        out.append(f"(approx) {len(mates)} teammates alive; nearest about {int(dm.min())} units away")
    dth = pd.read_csv(d / "events" / "player_death.csv.gz", dtype={"attacker_steamid": "Int64", "user_steamid": "Int64"})
    k = dth[(dth.tick >= tick - 2) & (dth.tick <= tick + 2) & ((dth.user_steamid == sid) | (dth.attacker_steamid == sid))]
    if len(k):
        k = k.iloc[0]
        other = k.attacker_steamid if k.user_steamid == sid else k.user_steamid
        o = q[q.steamid == other]
        if len(o):
            o = o.iloc[0]
            out.append(f"(approx) other player: at {o.last_place_name}, holding {o.active_weapon_name}; kill weapon {k.weapon}"
                       + (", headshot" if k.get("headshot") is True else ""))
    return out


def main() -> None:
    if len(sys.argv) < 5:
        print(__doc__)
        raise SystemExit(2)
    b, sid, an, fid = Path(sys.argv[1]), int(sys.argv[2]), json.load(open(sys.argv[3])), sys.argv[4]
    f = next((x for x in an["findings"] if x["id"] == fid), None)
    if f is None:
        raise SystemExit(f"unknown finding id: {fid}")
    idx = [int(x) for x in sys.argv[5:]] or range(len(f["examples"]))
    print(f"{fid}: {len(f['examples'])} examples (selected because: {f['examples'][0].get('why') if f['examples'] else '-'})")
    for i in idx:
        e = f["examples"][i]
        ms = json.load(open(b / e["demo_id"] / "match_summary.json")).get("map_name")
        print(f"\n== example {i}: {ms} round {e['round']}")
        for line in viewer.observed_facts(b, e["demo_id"], int(e["round"]), sid, e.get("tick")):
            print("  " + line)
        if e.get("tick") is not None:
            for line in context(b, e["demo_id"], int(e["round"]), int(e["tick"]), sid):
                print("  " + line)


if __name__ == "__main__":
    main()
