from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

M3_VERSION = "3.0-v0.1.2"
CANONICAL_SCHEMA_VERSION = "1.0.0-alpha1"

PLAYER_STATE_SCHEMA = pa.schema([
    pa.field("demo_id", pa.string(), nullable=False),
    pa.field("tick", pa.int64(), nullable=False),
    pa.field("steamid", pa.string(), nullable=False),
    pa.field("round", pa.int32()),
    pa.field("parser_round", pa.int32()),
    pa.field("side", pa.string()),
    pa.field("team_name", pa.string()),
    pa.field("name", pa.string()),
    pa.field("X", pa.float64()), pa.field("Y", pa.float64()), pa.field("Z", pa.float64()),
    pa.field("yaw", pa.float64()), pa.field("pitch", pa.float64()),
    pa.field("health", pa.int16()), pa.field("armor_value", pa.int16()),
    pa.field("is_alive", pa.bool_()),
    pa.field("active_weapon_name", pa.string()),
    pa.field("inventory_json", pa.large_string()),
    pa.field("is_scoped", pa.bool_()), pa.field("is_walking", pa.bool_()), pa.field("is_airborne", pa.bool_()),
    pa.field("flash_duration", pa.float64()),
    pa.field("has_helmet", pa.bool_()), pa.field("has_defuser", pa.bool_()),
    pa.field("balance", pa.int32()), pa.field("current_equip_value", pa.int32()),
    pa.field("last_place_name", pa.string()), pa.field("spotted", pa.bool_()),
    pa.field("approximate_spotted_by_json", pa.large_string()),
    pa.field("parser_velocity_x", pa.float64()), pa.field("parser_velocity_y", pa.float64()), pa.field("parser_velocity_z", pa.float64()),
    pa.field("parser_velocity_magnitude", pa.float64()),
    pa.field("previous_observation_tick", pa.int64()),
    pa.field("observation_delta_ticks", pa.int32()),
    pa.field("observation_delta_s", pa.float64()),
    pa.field("sample_displacement_units", pa.float64()),
    pa.field("sample_displacement_speed_units_s", pa.float64()),
    pa.field("sample_event_tick", pa.bool_(), nullable=False),
    pa.field("sample_stride_tick", pa.bool_(), nullable=False),
    pa.field("truth_class", pa.string(), nullable=False),
])

WORLD_TICK_SCHEMA = pa.schema([
    pa.field("demo_id", pa.string(), nullable=False),
    pa.field("tick", pa.int64(), nullable=False),
    pa.field("round", pa.int32()),
    pa.field("t_alive", pa.int16()), pa.field("ct_alive", pa.int16()),
    pa.field("t_observed_players", pa.int16()), pa.field("ct_observed_players", pa.int16()),
    pa.field("t_equipment_value_sum", pa.int32()), pa.field("ct_equipment_value_sum", pa.int32()),
    pa.field("bomb_planted_observed", pa.bool_()),
    pa.field("sample_event_tick", pa.bool_(), nullable=False),
    pa.field("sample_stride_tick", pa.bool_(), nullable=False),
])

ROUND_STATE_SCHEMA = pa.schema([
    pa.field("demo_id", pa.string(), nullable=False),
    pa.field("round", pa.int32(), nullable=False),
    pa.field("start_tick", pa.int64()), pa.field("freeze_end_tick", pa.int64()), pa.field("end_tick", pa.int64(), nullable=False),
    pa.field("winner", pa.string()), pa.field("reason", pa.string()),
    pa.field("bomb_plant_tick", pa.int64()), pa.field("bomb_plant_site", pa.string()),
    pa.field("ct_score_before", pa.int16()), pa.field("t_score_before", pa.int16()),
    pa.field("ct_score_after", pa.int16()), pa.field("t_score_after", pa.int16()),
    pa.field("start_t_alive", pa.int16()), pa.field("start_ct_alive", pa.int16()),
    pa.field("freeze_t_alive", pa.int16()), pa.field("freeze_ct_alive", pa.int16()),
    pa.field("end_t_alive", pa.int16()), pa.field("end_ct_alive", pa.int16()),
    pa.field("start_t_equipment_value_sum", pa.int32()), pa.field("start_ct_equipment_value_sum", pa.int32()),
    pa.field("freeze_t_equipment_value_sum", pa.int32()), pa.field("freeze_ct_equipment_value_sum", pa.int32()),
    pa.field("end_t_equipment_value_sum", pa.int32()), pa.field("end_ct_equipment_value_sum", pa.int32()),
    pa.field("observation_complete", pa.bool_(), nullable=False),
])

LIFE_INTERVAL_SCHEMA = pa.schema([
    pa.field("demo_id", pa.string(), nullable=False),
    pa.field("round", pa.int32()),
    pa.field("steamid", pa.string(), nullable=False),
    pa.field("is_alive", pa.bool_()),
    pa.field("start_observed_tick", pa.int64(), nullable=False),
    pa.field("end_observed_tick", pa.int64(), nullable=False),
    pa.field("next_change_tick", pa.int64()),
    pa.field("start_boundary_source", pa.string(), nullable=False),
    pa.field("end_boundary_source", pa.string(), nullable=False),
    pa.field("truth_class", pa.string(), nullable=False),
])

DISCRETE_INTERVAL_SCHEMA = pa.schema([
    pa.field("demo_id", pa.string(), nullable=False),
    pa.field("round", pa.int32()),
    pa.field("steamid", pa.string(), nullable=False),
    pa.field("start_observed_tick", pa.int64(), nullable=False),
    pa.field("end_observed_tick", pa.int64(), nullable=False),
    pa.field("next_change_tick", pa.int64()),
    pa.field("side", pa.string()),
    pa.field("active_weapon_name", pa.string()),
    pa.field("is_scoped", pa.bool_()), pa.field("is_walking", pa.bool_()), pa.field("is_airborne", pa.bool_()),
    pa.field("flash_active", pa.bool_()),
    pa.field("has_helmet", pa.bool_()), pa.field("has_defuser", pa.bool_()),
    pa.field("last_place_name", pa.string()),
    pa.field("truth_class", pa.string(), nullable=False),
])

BOMB_INTERVAL_SCHEMA = pa.schema([
    pa.field("demo_id", pa.string(), nullable=False),
    pa.field("round", pa.int32(), nullable=False),
    pa.field("start_tick", pa.int64(), nullable=False),
    pa.field("end_tick_exclusive", pa.int64(), nullable=False),
    pa.field("bomb_state", pa.string(), nullable=False),
    pa.field("carrier_steamid", pa.string()),
    pa.field("site", pa.string()),
    pa.field("source_event", pa.string(), nullable=False),
    pa.field("truth_class", pa.string(), nullable=False),
])

UTILITY_INTERVAL_SCHEMA = pa.schema([
    pa.field("demo_id", pa.string(), nullable=False),
    pa.field("round", pa.int32()),
    pa.field("utility_type", pa.string(), nullable=False),
    pa.field("start_tick", pa.int64(), nullable=False),
    pa.field("end_tick", pa.int64()),
    pa.field("owner_steamid", pa.string()),
    pa.field("x", pa.float64()), pa.field("y", pa.float64()), pa.field("z", pa.float64()),
    pa.field("pairing_method", pa.string(), nullable=False),
    pa.field("end_known", pa.bool_(), nullable=False),
    pa.field("truth_class", pa.string(), nullable=False),
])


def write_json(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def table_from_df(df: pd.DataFrame, schema: pa.Schema) -> pa.Table:
    arrays = []
    for field in schema:
        if field.name in df.columns:
            vals = df[field.name].tolist()
        else:
            vals = [None] * len(df)
        arrays.append(pa.array(vals, type=field.type, from_pandas=True))
    return pa.Table.from_arrays(arrays, schema=schema)


def write_parquet(df: pd.DataFrame, schema: pa.Schema, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = table_from_df(df, schema)
    tmp = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(path)
    return {"rows": table.num_rows, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dataset_from_path(path: str) -> str:
    s = path.replace("/", "\\")
    parts = [p for p in s.split("\\") if p]
    lower = [p.lower() for p in parts]
    for key in ("austinmajor_2025", "faceit", "iemcolognemajor2026", "premier_batch1", "starladder_2025"):
        if key in lower:
            return parts[lower.index(key)]
    return "unknown"


def discover_evidence(output_folder: Path) -> list[dict]:
    parent = output_folder.resolve().parent
    roots = [parent / "Stage3_M211", parent / "Stage3_M21", parent / "Stage3_M2", parent / "Stage3_M1"]
    seen: dict[str, dict] = {}
    priority = {"Stage3_M211": 0, "Stage3_M21": 1, "Stage3_M2": 2, "Stage3_M1": 3}
    for root in roots:
        ev = root / "evidence"
        if not ev.exists():
            ev = root / "golden"
        if not ev.exists():
            continue
        for d in ev.iterdir():
            if not d.is_dir() or d.name.startswith("."):
                continue
            manifest = d / "manifest.json"
            required = [d / "players.parquet", d / "rounds.parquet", d / "events.parquet", d / "state_samples.parquet", manifest]
            if not all(p.exists() for p in required):
                continue
            try:
                m = read_json(manifest)
            except Exception:
                continue
            demo_id = m.get("demo_id", d.name)
            item = {
                "demo_id": demo_id,
                "evidence_dir": d,
                "root": root.name,
                "priority": priority.get(root.name, 99),
                "manifest": m,
                "dataset": dataset_from_path(str(m.get("source_path", ""))),
                "source_family": m.get("source_family", "unknown"),
                "segmented_hint": bool(m.get("segmented_hint", False)),
                "map_name": (m.get("header") or {}).get("map_name"),
            }
            old = seen.get(demo_id)
            if old is None or item["priority"] < old["priority"]:
                seen[demo_id] = item
    return list(seen.values())


def choose_sample(items: list[dict]) -> list[dict]:
    if not items:
        return []
    chosen: list[dict] = []
    used: set[str] = set()

    def add_best(cands: list[dict]) -> None:
        cands = [x for x in cands if x["demo_id"] not in used]
        if not cands:
            return
        # Prefer the newest/most optimized evidence root when that source class
        # is represented there. Fall back to older exact-equivalent evidence
        # only when needed (for example, segmented SourceTV coverage).
        best_priority = min(x["priority"] for x in cands)
        cands = [x for x in cands if x["priority"] == best_priority]
        cands.sort(key=lambda x: x["demo_id"])
        x = cands[len(cands)//2]
        chosen.append(x); used.add(x["demo_id"])

    add_best([x for x in items if "faceit" in x["source_family"].lower() or x["dataset"].lower() == "faceit"])
    add_best([x for x in items if "premier" in x["source_family"].lower() or x["dataset"].lower() == "premier_batch1"])
    add_best([x for x in items if x["segmented_hint"]])
    for ds in ("AustinMajor_2025", "IEMCologneMajor2026", "Starladder_2025"):
        add_best([x for x in items if x["dataset"].lower() == ds.lower() and not x["segmented_hint"]])
    if len(chosen) < 6:
        for x in sorted(items, key=lambda z: (z["priority"], z["demo_id"])):
            if x["demo_id"] not in used:
                chosen.append(x); used.add(x["demo_id"])
            if len(chosen) >= 6:
                break
    return chosen[:6]


def side_from_team_num(v: Any) -> str | None:
    try:
        if pd.isna(v): return None
        i = int(v)
    except Exception:
        return None
    if i == 2: return "T"
    if i == 3: return "CT"
    return None


def canonical_player_state(state: pd.DataFrame, tickrate: float) -> pd.DataFrame:
    q = state.copy()
    q["steamid"] = q["steamid"].astype("string")
    q["tick"] = pd.to_numeric(q["tick"], errors="coerce").astype("Int64")
    q = q[q["tick"].notna() & q["steamid"].notna()].copy()
    q["side"] = q.get("team_num", pd.Series(index=q.index, dtype="Float64")).map(side_from_team_num).astype("string")
    q["round"] = pd.to_numeric(q.get("segment_round"), errors="coerce").astype("Int32")
    q.sort_values(["steamid", "tick"], kind="stable", inplace=True)
    grp = q.groupby("steamid", sort=False, observed=True)
    q["previous_observation_tick"] = grp["tick"].shift(1).astype("Int64")
    q["observation_delta_ticks"] = (q["tick"] - q["previous_observation_tick"]).astype("Int32")
    q["observation_delta_s"] = pd.to_numeric(q["observation_delta_ticks"], errors="coerce") / float(tickrate or 64.0)
    for c in ("X", "Y", "Z"):
        q[c] = pd.to_numeric(q.get(c), errors="coerce")
        q[f"_prev_{c}"] = grp[c].shift(1)
    dx = q["X"] - q["_prev_X"]; dy = q["Y"] - q["_prev_Y"]; dz = q["Z"] - q["_prev_Z"]
    q["sample_displacement_units"] = np.sqrt(dx*dx + dy*dy + dz*dz)
    q["sample_displacement_speed_units_s"] = q["sample_displacement_units"] / q["observation_delta_s"].replace(0, np.nan)
    vx = pd.to_numeric(q.get("velocity_X"), errors="coerce")
    vy = pd.to_numeric(q.get("velocity_Y"), errors="coerce")
    vz = pd.to_numeric(q.get("velocity_Z"), errors="coerce")
    q["parser_velocity_x"] = vx; q["parser_velocity_y"] = vy; q["parser_velocity_z"] = vz
    q["parser_velocity_magnitude"] = np.sqrt(vx*vx + vy*vy + vz*vz)
    q["truth_class"] = "observed_sample_or_parser_property"
    rename = {}
    q.rename(columns=rename, inplace=True)
    wanted = [f.name for f in PLAYER_STATE_SCHEMA]
    for c in wanted:
        if c not in q.columns:
            q[c] = pd.NA
    return q[wanted].sort_values(["tick", "steamid"], kind="stable").reset_index(drop=True)


def _aggregate_raw_bomb_planted(raw_state: pd.DataFrame | None) -> dict[int, bool | None]:
    """Return tri-state bomb-planted observations by tick from raw evidence.

    is_bomb_planted is a global game property repeated on player rows. It does
    not belong in canonical PLAYER_STATE_SCHEMA, so aggregate it before that
    global property is intentionally dropped from player state.
    """
    if raw_state is None or raw_state.empty or "is_bomb_planted" not in raw_state.columns or "tick" not in raw_state.columns:
        return {}
    q = raw_state[["tick", "is_bomb_planted"]].copy()
    q["tick"] = pd.to_numeric(q["tick"], errors="coerce").astype("Int64")
    q = q[q["tick"].notna()].copy()
    out: dict[int, bool | None] = {}
    for tick, g in q.groupby("tick", sort=False):
        vals = g["is_bomb_planted"].astype("boolean").dropna()
        if len(vals) == 0:
            out[int(tick)] = None
        elif bool(vals.any()):
            out[int(tick)] = True
        elif bool((~vals).any()):
            out[int(tick)] = False
        else:
            out[int(tick)] = None
    return out


def _bomb_interval_observation(bomb: pd.DataFrame | None, round_no: int | None, tick: int) -> bool | None:
    if bomb is None or bomb.empty or round_no is None:
        return None
    g = bomb[(bomb["round"] == int(round_no)) & (bomb["start_tick"] <= int(tick)) & (bomb["end_tick_exclusive"] > int(tick))]
    if g.empty:
        return None
    state = str(g.iloc[-1]["bomb_state"])
    if state == "planted":
        return True
    if state in {"carried", "dropped", "defused", "exploded"}:
        return False
    return None


def world_ticks(player_state: pd.DataFrame, raw_state: pd.DataFrame | None = None, bomb: pd.DataFrame | None = None) -> pd.DataFrame:
    q = player_state.copy()
    q["equip"] = pd.to_numeric(q["current_equip_value"], errors="coerce").fillna(0)
    q["alive_i"] = q["is_alive"].astype("boolean").fillna(False).astype("int16")
    raw_bomb = _aggregate_raw_bomb_planted(raw_state)
    rows = []
    for tick, g in q.groupby("tick", sort=True):
        t = g[g["side"] == "T"]; ct = g[g["side"] == "CT"]
        round_vals = g["round"].dropna()
        round_no = int(round_vals.iloc[0]) if len(round_vals) else None
        bomb_obs = raw_bomb.get(int(tick))
        if bomb_obs is None:
            bomb_obs = _bomb_interval_observation(bomb, round_no, int(tick))
        rows.append({
            "demo_id": str(g["demo_id"].iloc[0]), "tick": int(tick),
            "round": round_no,
            "t_alive": int(t["alive_i"].sum()), "ct_alive": int(ct["alive_i"].sum()),
            "t_observed_players": int(len(t)), "ct_observed_players": int(len(ct)),
            "t_equipment_value_sum": int(t["equip"].sum()), "ct_equipment_value_sum": int(ct["equip"].sum()),
            "bomb_planted_observed": bomb_obs,
            "sample_event_tick": bool(g["sample_event_tick"].fillna(False).any()),
            "sample_stride_tick": bool(g["sample_stride_tick"].fillna(False).any()),
        })
    return pd.DataFrame(rows)


def nearest_world_row(w: pd.DataFrame, tick: int | None, mode: str = "nearest") -> pd.Series | None:
    if tick is None or w.empty:
        return None
    ticks = w["tick"].to_numpy(dtype=np.int64)
    pos = int(np.searchsorted(ticks, int(tick)))
    candidates = []
    if pos < len(ticks): candidates.append(pos)
    if pos > 0: candidates.append(pos-1)
    if not candidates: return None
    if mode == "at_or_after":
        candidates = [i for i in candidates if ticks[i] >= int(tick)] or candidates
    elif mode == "at_or_before":
        candidates = [i for i in candidates if ticks[i] <= int(tick)] or candidates
    i = min(candidates, key=lambda j: abs(int(ticks[j]) - int(tick)))
    return w.iloc[i]


def round_state(rounds: pd.DataFrame, w: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in rounds.iterrows():
        rd = int(r["round"])
        ww = w[w["round"] == rd]
        s = nearest_world_row(ww, int(r["start_tick"]) if pd.notna(r.get("start_tick")) else None, "at_or_after")
        f = nearest_world_row(ww, int(r["freeze_end_tick"]) if pd.notna(r.get("freeze_end_tick")) else None, "nearest")
        e = nearest_world_row(ww, int(r["end_tick"]), "at_or_before")
        def val(row, key):
            if row is None: return None
            v = row.get(key)
            return None if pd.isna(v) else int(v)
        rows.append({
            "demo_id": str(r["demo_id"]), "round": rd,
            "start_tick": None if pd.isna(r.get("start_tick")) else int(r["start_tick"]),
            "freeze_end_tick": None if pd.isna(r.get("freeze_end_tick")) else int(r["freeze_end_tick"]),
            "end_tick": int(r["end_tick"]),
            "winner": None if pd.isna(r.get("winner")) else str(r.get("winner")),
            "reason": None if pd.isna(r.get("reason")) else str(r.get("reason")),
            "bomb_plant_tick": None if pd.isna(r.get("bomb_plant_tick")) else int(r.get("bomb_plant_tick")),
            "bomb_plant_site": None if pd.isna(r.get("bomb_plant_site")) else str(r.get("bomb_plant_site")),
            "ct_score_before": None if pd.isna(r.get("ct_score_before")) else int(r.get("ct_score_before")),
            "t_score_before": None if pd.isna(r.get("t_score_before")) else int(r.get("t_score_before")),
            "ct_score_after": None if pd.isna(r.get("ct_score_after")) else int(r.get("ct_score_after")),
            "t_score_after": None if pd.isna(r.get("t_score_after")) else int(r.get("t_score_after")),
            "start_t_alive": val(s,"t_alive"), "start_ct_alive": val(s,"ct_alive"),
            "freeze_t_alive": val(f,"t_alive"), "freeze_ct_alive": val(f,"ct_alive"),
            "end_t_alive": val(e,"t_alive"), "end_ct_alive": val(e,"ct_alive"),
            "start_t_equipment_value_sum": val(s,"t_equipment_value_sum"), "start_ct_equipment_value_sum": val(s,"ct_equipment_value_sum"),
            "freeze_t_equipment_value_sum": val(f,"t_equipment_value_sum"), "freeze_ct_equipment_value_sum": val(f,"ct_equipment_value_sum"),
            "end_t_equipment_value_sum": val(e,"t_equipment_value_sum"), "end_ct_equipment_value_sum": val(e,"ct_equipment_value_sum"),
            "observation_complete": bool(s is not None and e is not None),
        })
    return pd.DataFrame(rows)


def event_tick_map(events: pd.DataFrame, names: set[str], actor_col: str = "user_steamid") -> set[tuple[str,int]]:
    if events.empty: return set()
    e = events[events["event_name"].isin(names)]
    out = set()
    for _, r in e.iterrows():
        sid = r.get(actor_col); tick = r.get("tick")
        if pd.notna(sid) and pd.notna(tick): out.add((str(sid), int(tick)))
    return out


def _interval_runs(g: pd.DataFrame, keys: list[str]) -> list[pd.DataFrame]:
    """Split a sorted frame into consecutive runs with identical key values.

    M2.1.1 Parquet files can round-trip pandas columns as Arrow extension
    dtypes (for example bool[pyarrow]). Pandas does not support cumsum()
    directly on an Arrow boolean array. Keep the comparison semantics in
    pandas, but materialize only the tiny run-boundary mask as NumPy bool
    before the cumulative sum. This is dtype-agnostic and preserves NA==NA
    for interval segmentation.
    """
    if g.empty:
        return []
    change = np.zeros(len(g), dtype=np.bool_)
    for k in keys:
        s = g[k]
        prev = s.shift(1)
        eq = (s.eq(prev) | (s.isna() & prev.isna())).fillna(False)
        eq_np = eq.to_numpy(dtype=bool, na_value=False)
        change |= ~eq_np
    change[0] = True
    run_id = np.cumsum(change.astype(np.int64))
    # Group by a plain NumPy-backed Series so Arrow extension dtypes in the
    # evidence columns never control the run-id operation.
    run_series = pd.Series(run_id, index=g.index, dtype="int64")
    return [x for _, x in g.groupby(run_series, sort=False)]


def life_intervals(player_state: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    deaths = event_tick_map(events, {"player_death"}, "user_steamid")
    spawns = event_tick_map(events, {"player_spawn"}, "user_steamid")
    rows = []
    q = player_state.sort_values(["steamid","round","tick"], kind="stable")
    for (sid, rd), g in q.groupby(["steamid","round"], dropna=False, sort=False):
        if pd.isna(rd): continue
        for run in _interval_runs(g, ["is_alive"]):
            st = int(run["tick"].iloc[0]); en = int(run["tick"].iloc[-1])
            next_rows = g[g["tick"] > en]
            nxt = int(next_rows["tick"].iloc[0]) if len(next_rows) else None
            alive = run["is_alive"].iloc[0]
            alive = None if pd.isna(alive) else bool(alive)
            start_source = "player_spawn_event" if (str(sid),st) in spawns else ("player_death_event" if (str(sid),st) in deaths else "sample_observation")
            end_source = "next_sample_change" if nxt is not None else "round_last_observation"
            rows.append({
                "demo_id": str(run["demo_id"].iloc[0]), "round": int(rd), "steamid": str(sid), "is_alive": alive,
                "start_observed_tick": st, "end_observed_tick": en, "next_change_tick": nxt,
                "start_boundary_source": start_source, "end_boundary_source": end_source,
                "truth_class": "event_refined_sample_interval" if start_source.endswith("event") else "sampled_interval",
            })
    return pd.DataFrame(rows)


def discrete_intervals(player_state: pd.DataFrame) -> pd.DataFrame:
    q = player_state.copy()
    q["flash_active"] = pd.to_numeric(q["flash_duration"], errors="coerce") > 0
    keys = ["side","active_weapon_name","is_scoped","is_walking","is_airborne","flash_active","has_helmet","has_defuser","last_place_name"]
    rows = []
    q.sort_values(["steamid","round","tick"], kind="stable", inplace=True)
    for (sid, rd), g in q.groupby(["steamid","round"], dropna=False, sort=False):
        if pd.isna(rd): continue
        for run in _interval_runs(g, keys):
            st = int(run["tick"].iloc[0]); en = int(run["tick"].iloc[-1])
            next_rows = g[g["tick"] > en]
            nxt = int(next_rows["tick"].iloc[0]) if len(next_rows) else None
            first = run.iloc[0]
            row = {"demo_id": str(first["demo_id"]), "round": int(rd), "steamid": str(sid),
                   "start_observed_tick": st, "end_observed_tick": en, "next_change_tick": nxt,
                   "truth_class": "sampled_discrete_interval"}
            for k in keys:
                v = first[k]
                row[k] = None if pd.isna(v) else (bool(v) if k in {"is_scoped","is_walking","is_airborne","flash_active","has_helmet","has_defuser"} else str(v))
            rows.append(row)
    return pd.DataFrame(rows)


def payload_dict(v: Any) -> dict:
    if v is None or (isinstance(v,float) and math.isnan(v)): return {}
    try:
        return json.loads(str(v))
    except Exception:
        return {}


def payload_xyz(payload: dict) -> tuple[float|None,float|None,float|None]:
    def num(keys):
        for k in keys:
            if k in payload and payload[k] is not None:
                try:
                    x=float(payload[k]);
                    if math.isfinite(x): return x
                except Exception: pass
        return None
    return num(["x","X","pos_x","origin_x"]), num(["y","Y","pos_y","origin_y"]), num(["z","Z","pos_z","origin_z"])


def payload_entity(payload: dict) -> str | None:
    for k,v in payload.items():
        lk=str(k).lower()
        if lk in {"entityid","entity_id","entindex","entity_index","projectile_entity_id"} or ("entity" in lk and "id" in lk):
            if v is not None and str(v).strip() not in {"","0","None","nan"}: return str(v)
    return None


def bomb_intervals(rounds: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    trans = {"bomb_pickup":"carried","bomb_dropped":"dropped","bomb_planted":"planted","bomb_defused":"defused","bomb_exploded":"exploded"}
    rows=[]
    for _, rr in rounds.iterrows():
        rd=int(rr["round"]); st=int(rr["start_tick"]) if pd.notna(rr.get("start_tick")) else int(rr["end_tick"]); end=int(rr["end_tick"])+1
        ev=events[(events["segment_round"]==rd) & events["event_name"].isin(trans.keys())].sort_values(["tick","event_name"])
        points=[{"tick":st,"state":"unknown","carrier":None,"site":None,"event":"round_start_unknown"}]
        for _,e in ev.iterrows():
            name=str(e["event_name"]); tick=int(e["tick"]); carrier=None; site=None
            if name=="bomb_pickup" and pd.notna(e.get("user_steamid")): carrier=str(e.get("user_steamid"))
            if name=="bomb_planted" and pd.notna(e.get("site")): site=str(e.get("site"))
            points.append({"tick":tick,"state":trans[name],"carrier":carrier,"site":site,"event":name})
        points.sort(key=lambda x:(x["tick"],x["event"]))
        # if first real transition is exactly at round start, it supersedes unknown at that tick
        ded=[]
        for p in points:
            if ded and p["tick"]==ded[-1]["tick"]: ded[-1]=p
            else: ded.append(p)
        for i,p in enumerate(ded):
            nxt=ded[i+1]["tick"] if i+1<len(ded) else end
            if nxt<=p["tick"]: continue
            rows.append({"demo_id":str(rr["demo_id"]),"round":rd,"start_tick":int(p["tick"]),"end_tick_exclusive":int(nxt),
                         "bomb_state":p["state"],"carrier_steamid":p["carrier"],"site":p["site"],"source_event":p["event"],
                         "truth_class":"observed_event_state" if p["event"]!="round_start_unknown" else "unknown_until_observed"})
    return pd.DataFrame(rows)


def utility_intervals(events: pd.DataFrame, tickrate: float) -> pd.DataFrame:
    tr = float(tickrate or 64.0)
    specs=[("smoke","smokegrenade_detonate","smokegrenade_expired",int(40*tr)),("inferno","inferno_startburn","inferno_expire",int(20*tr))]
    rows=[]
    for util,start_name,end_name,max_dt in specs:
        starts=events[events["event_name"]==start_name].copy(); ends=events[events["event_name"]==end_name].copy()
        if starts.empty: continue
        end_used=set()
        end_records=[]
        for idx,e in ends.iterrows():
            p=payload_dict(e.get("payload_json")); x,y,z=payload_xyz(p); ent=payload_entity(p)
            end_records.append((idx,e,p,x,y,z,ent))
        for _,s in starts.iterrows():
            sp=payload_dict(s.get("payload_json")); sx,sy,sz=payload_xyz(sp); sent=payload_entity(sp)
            rd=None if pd.isna(s.get("segment_round")) else int(s.get("segment_round")); st=int(s["tick"])
            cand=[]
            for idx,e,p,x,y,z,ent in end_records:
                if idx in end_used: continue
                erd=None if pd.isna(e.get("segment_round")) else int(e.get("segment_round"))
                if rd is not None and erd is not None and rd!=erd: continue
                et=int(e["tick"])
                if et<st or et-st>max_dt: continue
                if sent and ent and sent==ent:
                    cand.append((0.0,0,idx,e,x,y,z,"exact_entity")); continue
                if None not in (sx,sy,sz,x,y,z):
                    dist=math.sqrt((sx-x)**2+(sy-y)**2+(sz-z)**2)
                    if dist<=96:
                        cand.append((dist,1,idx,e,x,y,z,"spatial_nearest"))
            chosen=min(cand,key=lambda z:(z[1],z[0],int(z[3]["tick"]))) if cand else None
            if chosen:
                _,_,idx,e,_,_,_,method=chosen; end_used.add(idx); et=int(e["tick"]); known=True
            else:
                et=None; method="unpaired"; known=False
            rows.append({"demo_id":str(s["demo_id"]),"round":rd,"utility_type":util,"start_tick":st,"end_tick":et,
                         "owner_steamid":None if pd.isna(s.get("user_steamid")) else str(s.get("user_steamid")),
                         "x":sx,"y":sy,"z":sz,"pairing_method":method,"end_known":known,
                         "truth_class":"event_paired_interval" if known else "event_start_end_unknown"})
    return pd.DataFrame(rows)


def validate_intervals(rounds: pd.DataFrame, player_state: pd.DataFrame, life: pd.DataFrame, bomb: pd.DataFrame) -> list[str]:
    errors=[]
    if len(player_state)==0: errors.append("no canonical player state")
    if player_state[["demo_id","tick","steamid"]].duplicated().any(): errors.append("duplicate canonical player tick identity")
    # Bomb intervals must be ordered and non-overlapping within every round.
    for rd,g in bomb.groupby("round", sort=False):
        gg=g.sort_values("start_tick")
        prev=None
        for _,r in gg.iterrows():
            st=int(r["start_tick"]); en=int(r["end_tick_exclusive"])
            if en<=st: errors.append(f"bomb nonpositive interval r{rd}")
            if prev is not None and st<prev: errors.append(f"bomb overlap r{rd}")
            prev=en
    # Life sampled intervals must be ordered, non-overlapping per player/round.
    for (sid,rd),g in life.groupby(["steamid","round"], sort=False):
        gg=g.sort_values("start_observed_tick")
        prev=None
        for _,r in gg.iterrows():
            st=int(r["start_observed_tick"]); en=int(r["end_observed_tick"])
            if en<st: errors.append(f"life negative interval {sid} r{rd}")
            if prev is not None and st<=prev: errors.append(f"life overlap {sid} r{rd}")
            prev=en
    return errors


def process_evidence(item: dict, output_root: Path) -> dict:
    t0=time.perf_counter(); d=item["evidence_dir"]; m=item["manifest"]; demo_id=item["demo_id"]
    out=output_root/"canonical"/demo_id; tmp=output_root/"canonical"/f".{demo_id}.tmp"
    shutil.rmtree(tmp,ignore_errors=True); tmp.mkdir(parents=True,exist_ok=True)
    result={"demo_id":demo_id,"source_evidence_root":item["root"],"dataset":item["dataset"],"source_family":item["source_family"],"segmented_hint":item["segmented_hint"],"map_name":item["map_name"],"success":False,"errors":[],"timings":{}}
    try:
        p=time.perf_counter(); players=pq.read_table(d/"players.parquet").to_pandas(); rounds=pq.read_table(d/"rounds.parquet").to_pandas(); events=pq.read_table(d/"events.parquet").to_pandas(); state=pq.read_table(d/"state_samples.parquet").to_pandas(); result["timings"]["read_evidence_s"]=time.perf_counter()-p
        tickrate=float((m.get("sampling") or {}).get("estimated_tickrate") or 64.0)
        p=time.perf_counter(); ps=canonical_player_state(state,tickrate); result["timings"]["player_state_s"]=time.perf_counter()-p
        # Build persistent objective state from literal events before world ticks.
        # The raw is_bomb_planted property is global evidence, not player state.
        p=time.perf_counter(); bi=bomb_intervals(rounds,events); li=life_intervals(ps,events); di=discrete_intervals(ps); ui=utility_intervals(events,tickrate); result["timings"]["intervals_s"]=time.perf_counter()-p
        p=time.perf_counter(); wt=world_ticks(ps, state, bi); result["timings"]["world_ticks_s"]=time.perf_counter()-p
        p=time.perf_counter(); rs=round_state(rounds,wt); result["timings"]["round_state_s"]=time.perf_counter()-p
        errs=validate_intervals(rounds,ps,li,bi)
        if errs: raise RuntimeError("; ".join(errs[:20]))
        p=time.perf_counter(); outputs={}
        outputs["player_state"]=write_parquet(ps,PLAYER_STATE_SCHEMA,tmp/"player_state.parquet")
        outputs["world_state_ticks"]=write_parquet(wt,WORLD_TICK_SCHEMA,tmp/"world_state_ticks.parquet")
        outputs["round_state"]=write_parquet(rs,ROUND_STATE_SCHEMA,tmp/"round_state.parquet")
        outputs["player_life_intervals"]=write_parquet(li,LIFE_INTERVAL_SCHEMA,tmp/"player_life_intervals.parquet")
        outputs["player_discrete_intervals"]=write_parquet(di,DISCRETE_INTERVAL_SCHEMA,tmp/"player_discrete_intervals.parquet")
        outputs["bomb_intervals"]=write_parquet(bi,BOMB_INTERVAL_SCHEMA,tmp/"bomb_intervals.parquet")
        outputs["utility_intervals"]=write_parquet(ui,UTILITY_INTERVAL_SCHEMA,tmp/"utility_intervals.parquet")
        result["timings"]["write_s"]=time.perf_counter()-p
        known_util=int(ui["end_known"].fillna(False).sum()) if len(ui) else 0
        manifest={
            "m3_version":M3_VERSION,"canonical_schema_version":CANONICAL_SCHEMA_VERSION,"demo_id":demo_id,
            "source_evidence":{"root":item["root"],"path":str(d),"evidence_schema_version":m.get("schema_version"),"source_demo_sha256":m.get("source_sha256")},
            "map_name":item["map_name"],"source_family":item["source_family"],"dataset":item["dataset"],"segmented_hint":item["segmented_hint"],
            "tickrate":tickrate,"outputs":outputs,
            "counts":{"players":len(players),"rounds":len(rounds),"player_state_rows":len(ps),"world_ticks":len(wt),"life_intervals":len(li),"discrete_intervals":len(di),"bomb_intervals":len(bi),"utility_intervals":len(ui),"utility_intervals_end_known":known_util},
            "truth_semantics":{"observed":"literal/parser sample or event","deterministic_derived":"repeatable transformation of typed evidence","unknown":"preserved as null/unknown; never coerced to false/zero","sampled_boundaries":"player state interval boundaries are observation boundaries unless refined by an event"},
            "awpy_used":False,"coaching_generated":False,"candidate_detection":False,
        }
        write_json(manifest,tmp/"manifest.json")
        if out.exists(): shutil.rmtree(out)
        tmp.replace(out)
        result.update({"success":True,"counts":manifest["counts"],"output_dir":str(out),"utility_pair_rate": (known_util/len(ui) if len(ui) else None)})
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}"); shutil.rmtree(tmp,ignore_errors=True)
    result["wall_seconds"]=time.perf_counter()-t0
    return result


def main() -> int:
    ap=argparse.ArgumentParser(description="CS2 Coaching Stage 3 Milestone 3 canonical state/interval reconstruction")
    ap.add_argument("--input-folder",required=True)
    ap.add_argument("--output-folder",required=True)
    args=ap.parse_args()
    input_folder=Path(args.input_folder); output_folder=Path(args.output_folder); output_folder.mkdir(parents=True,exist_ok=True)
    t0=time.perf_counter(); items=discover_evidence(output_folder); selected=choose_sample(items)
    if len(selected)<3:
        raise SystemExit("M3 could not find enough prior Stage3_M211/M2/M1 evidence next to the requested output folder. Keep those Stage3 output folders in place.")
    results=[process_evidence(x,output_folder) for x in selected]
    success=[r for r in results if r["success"]]
    segmented_ok=any(r.get("segmented_hint") and r.get("success") for r in results)
    sources={r.get("source_family") for r in success}
    utility_rates=[r["utility_pair_rate"] for r in success if r.get("utility_pair_rate") is not None]
    decision="M3_PASS: canonical state/interval reconstruction is reproducible from typed evidence with UNKNOWN preserved. Proceed to spatial sidecar integration." if len(success)==len(results) and segmented_ok and len(sources)>=3 else "M3_FAIL: canonical-state promotion gates not met."
    report={
        "m3_version":M3_VERSION,"canonical_schema_version":CANONICAL_SCHEMA_VERSION,"generated_at_local":time.strftime("%Y-%m-%d %H:%M:%S"),
        "input_folder":str(input_folder),"output_folder":str(output_folder),"discovered_evidence_demos":len(items),"selected_count":len(selected),
        "success_count":len(success),"failure_count":len(results)-len(success),"segmented_source_included":segmented_ok,
        "source_families":sorted(x for x in sources if x),"utility_pair_rate_mean":float(np.mean(utility_rates)) if utility_rates else None,
        "results":results,"wall_seconds":time.perf_counter()-t0,"decision":decision,
        "next_stage":"M4 spatial sidecar: NAV/Valve-place where trustworthy; static collision LOS; smoke relation; explicit dynamic-world uncertainty. No coaching semantics."
    }
    write_json(report,output_folder/"M3_report.json")
    print(json.dumps({"decision":decision,"success":f"{len(success)}/{len(results)}","wall_seconds":report["wall_seconds"]},indent=2))
    return 0 if decision.startswith("M3_PASS") else 2

if __name__=="__main__":
    raise SystemExit(main())
