"""Evidence digest: the software computes every number, the AI only interprets.

``build_digest`` reads gate-passing analyzed demos for ONE player and returns plain
metrics (with numerator, denominator and a plain definition) plus per-map and per-side
splits. Reports reference these metric ids; they never carry numbers of their own.

Conventions
- A round's events run from freeze end up to (not including) the next round's start, so
  kills that land just after the round-end tick still count (scoreboard-consistent).
- Only PvP (different team, real attacker) counts as a kill. Deaths count every death of
  the player (including a bomb/world death); ``deaths_pvp`` is the PvP-only figure.
- Values that cannot be known are ``None``, never zero.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import pandas as pd

from .damage import effective_damage
from .evidence import scan_batch
from .ids import parse_steamid

RIFLES = frozenset({"ak47", "m4a1_silencer", "m4a1", "galilar", "famas"})


def _read_events(path: Path, cols: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(path, usecols=lambda c: c in cols, dtype={"attacker_steamid": "Int64", "user_steamid": "Int64"})
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    return df


def _damage(hurt: pd.DataFrame) -> pd.Series:
    """Effective damage: repaired/v7.8 column if present, else computed (pitfall 27)."""
    if hurt["dmg_health_effective"].notna().any():
        return hurt["dmg_health_effective"]
    if hurt["user_health"].notna().any():
        return effective_damage(hurt)[0]
    return hurt["dmg_health_capped"]


def demo_round_facts(demo_dir: Path, steamid: int) -> tuple[list[dict], str | None]:
    """Per-round facts for one demo. Returns (facts, map_name)."""
    ms = json.loads((demo_dir / "match_summary.json").read_text(encoding="utf-8"))
    map_name = ms.get("map_name")
    rounds = pd.read_csv(demo_dir / "rounds.csv").sort_values("round").reset_index(drop=True)
    pr = pd.read_csv(demo_dir / "player_rounds.csv", dtype={"steamid": "int64"})
    mine = pr[pr.steamid == steamid].drop_duplicates("round").set_index("round")
    deaths = _read_events(
        demo_dir / "events" / "player_death.csv.gz",
        ["tick", "attacker_steamid", "user_steamid", "attacker_team_num", "user_team_num", "headshot", "weapon"],
    )
    hurt = _read_events(
        demo_dir / "events" / "player_hurt.csv.gz",
        ["tick", "attacker_steamid", "user_steamid", "attacker_team_num", "user_team_num", "dmg_health_capped",
         "dmg_health_effective", "user_health", "health"],
    )
    hurt["dmg"] = _damage(hurt)
    facts: list[dict] = []
    starts = rounds["start_tick"].tolist()
    for i, r in rounds.iterrows():
        n = int(r["round"])
        if n not in mine.index:
            continue
        lo = r["freeze_end_tick"]
        hi = starts[i + 1] if i + 1 < len(starts) else float("inf")
        ev = deaths[(deaths.tick >= lo) & (deaths.tick < hi)].sort_values("tick")
        pvp = ev[
            ev.attacker_steamid.notna()
            & (ev.attacker_steamid != ev.user_steamid)
            & (ev.attacker_team_num != ev.user_team_num)
        ]
        my_kills = pvp[pvp.attacker_steamid == steamid]
        my_deaths = ev[ev.user_steamid == steamid]
        my_pvp_deaths = pvp[pvp.user_steamid == steamid]
        h = hurt[
            (hurt.tick >= lo) & (hurt.tick < hi)
            & (hurt.attacker_steamid == steamid)
            & (hurt.attacker_team_num != hurt.user_team_num)
        ]
        opening = None
        if len(pvp):
            first = pvp.iloc[0]
            if first.attacker_steamid == steamid:
                opening = "KILL"
            elif first.user_steamid == steamid:
                opening = "DEATH"
        facts.append({
            "round": n,
            "side": str(mine.loc[n, "side"]),
            "win": str(mine.loc[n, "result"]) == "WIN",
            "kills": len(my_kills),
            "headshots": int((my_kills.headshot == True).sum()),  # noqa: E712
            "deaths": len(my_deaths),
            "deaths_pvp": len(my_pvp_deaths),
            "damage": float(h.dmg.sum()),
            "opening": opening,
            "died": len(my_deaths) > 0,
        })
    return facts, map_name


def _metric(label, value, num=None, den=None, unit="count", definition="", scope="all included rounds"):
    return {"label": label, "value": value, "numerator": num, "denominator": den,
            "unit": unit, "definition": definition, "scope": scope}


def _ratio(n, d):
    return None if not d else n / d


def _median(xs):
    xs = [x for x in xs if x is not None and not pd.isna(x)]
    return (statistics.median(xs), len(xs)) if xs else (None, 0)


def build_digest(batch_dir: Path, steamid, *, demo_ids: list[str] | None = None) -> dict:
    """Digest for one player across the gate-passing demos of a batch."""
    sid = parse_steamid(steamid)
    gates = [g for g in scan_batch(Path(batch_dir)) if g.passed]
    if demo_ids is not None:
        keep = set(demo_ids)
        gates = [g for g in gates if g.demo_id in keep]
    rows: list[dict] = []
    demos: list[dict] = []
    rifle_kill_speed: list[float | None] = []
    rifle_death_speed: list[float | None] = []
    util_by_map: dict[str, float] = {}
    name = None
    for g in gates:
        facts, mp = demo_round_facts(g.path, sid)
        if not facts:
            continue
        for f in facts:
            f["demo_id"], f["map"] = g.demo_id, mp
        rows += facts
        demos.append({"demo_id": g.demo_id, "map": mp, "rounds": len(facts)})
        players = pd.read_csv(g.path / "players.csv", dtype={"steamid": "int64"})
        hit = players[players.steamid == sid]
        if len(hit):
            name = name or str(hit.iloc[0]["name"])
        eng_path = g.path / "coaching" / "engagements.csv"
        if eng_path.exists():
            e = pd.read_csv(eng_path, dtype={"attacker_steamid": "int64", "victim_steamid": "int64"})
            k = e[(e.attacker_steamid == sid) & e.weapon.isin(RIFLES)]
            d = e[(e.victim_steamid == sid) & e.weapon.isin(RIFLES)]
            rifle_kill_speed += k.attacker_speed_2d.tolist()
            rifle_death_speed += d.victim_speed_2d.tolist()
        up = g.path / "coaching" / "utility_effectiveness.csv"
        if up.exists():
            u = pd.read_csv(up, dtype={"steamid": "int64"})
            u = u[u.steamid == sid]
            util_by_map[mp] = util_by_map.get(mp, 0.0) + float((u.he_enemy_damage + u.fire_enemy_damage).sum())
    df = pd.DataFrame(rows)
    n = len(df)
    if not n:
        return {"subject": {"steamid64": str(sid), "name": name}, "scope": {"demos": 0, "rounds": 0},
                "metrics": {}, "per_map": [], "per_side": [], "demos": []}

    kills, deaths = int(df.kills.sum()), int(df.deaths.sum())
    hs, dmg = int(df.headshots.sum()), float(df.damage.sum())
    ok, od = int((df.opening == "KILL").sum()), int((df.opening == "DEATH").sum())
    okr = df[df.opening == "KILL"]
    died_after = okr[okr.died]
    survived = okr[~okr.died]
    ks_med, ks_n = _median(rifle_kill_speed)
    ds_med, ds_n = _median(rifle_death_speed)
    util_total = sum(util_by_map.values())

    m = {
        "rounds": _metric("Rounds", n, n, n, "rounds", "Rounds this player was in, across the included demos."),
        "kills": _metric("Kills", kills, kills, None, "kills", "Enemy kills, counting any kill in the round including just after the round-end tick."),
        "deaths": _metric("Deaths", deaths, deaths, None, "deaths", "Every death of the player, including a bomb or world death."),
        "kd": _metric("Kill/death ratio", _ratio(kills, deaths), kills, deaths, "kd_ratio", "Kills divided by deaths."),
        "adr": _metric("Damage per round", dmg / n, round(dmg), n, "damage_per_round", "Damage dealt to enemies (health only, capped at 100 per hit) divided by rounds."),
        "headshot_kills": _metric("Headshot kills", hs, hs, kills, "kills", "Kills that were headshots."),
        "headshot_rate": _metric("Headshot share of kills", _ratio(hs, kills), hs, kills, "share", "Headshot kills divided by kills."),
        "opening_kills": _metric("Opening kills", ok, ok, n, "rounds", "Rounds where this player got the first kill of the round."),
        "opening_deaths": _metric("Opening deaths", od, od, n, "rounds", "Rounds where this player was the first to die."),
        "opening_involvement": _metric("Rounds with an opening fight", ok + od, ok + od, n, "rounds", "Rounds where this player took part in the first kill of the round, as killer or victim."),
        "opening_win_rate": _metric("Opening fights won", _ratio(ok, ok + od), ok, ok + od, "share", "Opening kills divided by all opening fights this player was in."),
        "opening_kill_rounds": _metric("Rounds with an opening kill", len(okr), len(okr), n, "rounds", "Rounds where this player got the first kill."),
        "opening_kill_died_later": _metric("Died later after an opening kill", len(died_after), len(died_after), len(okr), "rounds", "Of the opening-kill rounds, how many the player then died in before the round ended."),
        "opening_kill_died_later_won": _metric("Team won after opening kill and later death", int(died_after.win.sum()), int(died_after.win.sum()), len(died_after), "rounds", "Of the rounds where the player got the opening kill and later died, how many the team won."),
        "opening_kill_survived": _metric("Survived after an opening kill", len(survived), len(survived), len(okr), "rounds", "Of the opening-kill rounds, how many the player survived to round end."),
        "opening_kill_survived_won": _metric("Team won after opening kill and surviving", int(survived.win.sum()), int(survived.win.sum()), len(survived), "rounds", "Of the rounds where the player got the opening kill and survived, how many the team won."),
        "rifle_kill_speed": _metric("Typical speed when winning a rifle fight", ks_med, None, ks_n, "units_per_second", "Median movement speed at the moment the player first fired in rifle kills (game units per second).", "rifle kills"),
        "rifle_death_speed": _metric("Typical speed when losing a rifle fight", ds_med, None, ds_n, "units_per_second", "Median movement speed at the moment the enemy first fired in rifle deaths (game units per second). Measured at a different moment from the kill figure.", "rifle deaths"),
        "enemy_utility_damage": _metric("Grenade damage to enemies", util_total, round(util_total), n, "damage", "Damage to enemies from HE grenades and fire (molotov/incendiary)."),
    }

    per_map = []
    for mp, g in df.groupby("map"):
        k, d_ = int(g.kills.sum()), int(g.deaths.sum())
        rn = len(g)
        per_map.append({
            "map": mp, "rounds": rn, "kills": k, "deaths": d_, "kd": _ratio(k, d_),
            "adr": float(g.damage.sum()) / rn,
            "opening_kills": int((g.opening == "KILL").sum()), "opening_deaths": int((g.opening == "DEATH").sum()),
            "wins": int(g.win.sum()),
            "enemy_utility_damage": util_by_map.get(mp),
            "enemy_utility_damage_per_round": (util_by_map[mp] / rn) if mp in util_by_map else None,
        })
    per_side = []
    for sd, g in df.groupby("side"):
        per_side.append({"side": sd, "rounds": len(g), "wins": int(g.win.sum()),
                         "kills": int(g.kills.sum()), "deaths": int(g.deaths.sum())})
    return {
        "subject": {"steamid64": str(sid), "name": name},
        "scope": {"demos": len(demos), "rounds": n, "maps": sorted(df["map"].unique().tolist())},
        "metrics": m,
        "per_map": sorted(per_map, key=lambda x: -x["rounds"]),
        "per_side": per_side,
        "demos": demos,
    }
