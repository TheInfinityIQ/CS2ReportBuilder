from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

M5_VERSION = "5.0-v0.1.1"
RELATIONSHIP_SCHEMA_VERSION = "1.0.0-alpha1"

PLAYER_REL_SCHEMA = pa.schema([
    pa.field("demo_id", pa.string(), nullable=False),
    pa.field("tick", pa.int64(), nullable=False),
    pa.field("round", pa.int32()),
    pa.field("steamid", pa.string(), nullable=False),
    pa.field("side", pa.string()),
    pa.field("is_alive", pa.bool_()),
    pa.field("health", pa.int16()),
    pa.field("armor_value", pa.int16()),
    pa.field("active_weapon_name", pa.string()),
    pa.field("is_scoped", pa.bool_()),
    pa.field("is_walking", pa.bool_()),
    pa.field("is_airborne", pa.bool_()),
    pa.field("flash_active", pa.bool_()),
    pa.field("balance", pa.int32()),
    pa.field("current_equip_value", pa.int32()),
    pa.field("team_alive", pa.int16()),
    pa.field("enemy_alive", pa.int16()),
    pa.field("alive_diff_team_minus_enemy", pa.int16()),
    pa.field("team_equipment_value_sum", pa.int32()),
    pa.field("enemy_equipment_value_sum", pa.int32()),
    pa.field("equipment_value_diff_team_minus_enemy", pa.int32()),
    pa.field("nearest_enemy_distance", pa.float64()),
    pa.field("static_clear_enemy_count", pa.int16()),
    pa.field("static_exposed_to_enemy_count", pa.int16()),
    pa.field("static_unresolved_enemy_count", pa.int16()),
    pa.field("static_unresolved_exposed_by_enemy_count", pa.int16()),
    pa.field("nearest_static_clear_enemy_distance", pa.float64()),
    pa.field("nearest_known_active_smoke_segment_distance", pa.float64()),
    pa.field("known_active_smoke_count", pa.int16(), nullable=False),
    pa.field("unknown_end_smoke_count", pa.int16(), nullable=False),
    pa.field("dynamic_world_uncertainty", pa.bool_(), nullable=False),
    pa.field("static_collision_status", pa.string(), nullable=False),
    pa.field("truth_class", pa.string(), nullable=False),
])

PAIR_REL_SCHEMA = pa.schema([
    pa.field("demo_id", pa.string(), nullable=False),
    pa.field("tick", pa.int64(), nullable=False),
    pa.field("round", pa.int32()),
    pa.field("t_steamid", pa.string(), nullable=False),
    pa.field("ct_steamid", pa.string(), nullable=False),
    pa.field("distance_units", pa.float64()),
    pa.field("previous_sample_tick", pa.int64()),
    pa.field("sample_delta_ticks", pa.int64()),
    pa.field("previous_distance_units", pa.float64()),
    pa.field("distance_delta_units", pa.float64()),
    pa.field("t_to_ct_static_relation", pa.string(), nullable=False),
    pa.field("ct_to_t_static_relation", pa.string(), nullable=False),
    pa.field("t_to_ct_head_static_relation", pa.string(), nullable=False),
    pa.field("ct_to_t_head_static_relation", pa.string(), nullable=False),
    pa.field("t_to_ct_relation_status", pa.string()),
    pa.field("ct_to_t_relation_status", pa.string()),
    pa.field("deep_event_tick", pa.bool_(), nullable=False),
    pa.field("nearest_known_active_smoke_segment_distance", pa.float64()),
    pa.field("known_active_smoke_count", pa.int16(), nullable=False),
    pa.field("unknown_end_smoke_count", pa.int16(), nullable=False),
    pa.field("dynamic_world_uncertainty", pa.bool_(), nullable=False),
    pa.field("collision_status", pa.string(), nullable=False),
    pa.field("truth_class", pa.string(), nullable=False),
])

WORLD_REL_SCHEMA = pa.schema([
    pa.field("demo_id", pa.string(), nullable=False),
    pa.field("tick", pa.int64(), nullable=False),
    pa.field("round", pa.int32()),
    pa.field("t_alive", pa.int16()),
    pa.field("ct_alive", pa.int16()),
    pa.field("alive_diff_t_minus_ct", pa.int16()),
    pa.field("t_equipment_value_sum", pa.int32()),
    pa.field("ct_equipment_value_sum", pa.int32()),
    pa.field("equipment_value_diff_t_minus_ct", pa.int32()),
    pa.field("bomb_planted_observed", pa.bool_()),
    pa.field("t_to_ct_static_true_count", pa.int32(), nullable=False),
    pa.field("t_to_ct_static_false_count", pa.int32(), nullable=False),
    pa.field("t_to_ct_static_unknown_count", pa.int32(), nullable=False),
    pa.field("ct_to_t_static_true_count", pa.int32(), nullable=False),
    pa.field("ct_to_t_static_false_count", pa.int32(), nullable=False),
    pa.field("ct_to_t_static_unknown_count", pa.int32(), nullable=False),
    pa.field("t_to_ct_head_clear_count", pa.int32(), nullable=False),
    pa.field("ct_to_t_head_clear_count", pa.int32(), nullable=False),
    pa.field("known_active_smoke_count", pa.int16(), nullable=False),
    pa.field("unknown_end_smoke_count", pa.int16(), nullable=False),
    pa.field("dynamic_world_uncertainty", pa.bool_(), nullable=False),
    pa.field("truth_class", pa.string(), nullable=False),
])

TRANSITION_SCHEMA = pa.schema([
    pa.field("demo_id", pa.string(), nullable=False),
    pa.field("round", pa.int32()),
    pa.field("tick", pa.int64(), nullable=False),
    pa.field("previous_tick", pa.int64()),
    pa.field("scope", pa.string(), nullable=False),
    pa.field("subject_steamid", pa.string()),
    pa.field("other_steamid", pa.string()),
    pa.field("side", pa.string()),
    pa.field("transition_type", pa.string(), nullable=False),
    pa.field("from_bool", pa.bool_()),
    pa.field("to_bool", pa.bool_()),
    pa.field("from_int", pa.int64()),
    pa.field("to_int", pa.int64()),
    pa.field("delta_int", pa.int64()),
    pa.field("from_float", pa.float64()),
    pa.field("to_float", pa.float64()),
    pa.field("delta_float", pa.float64()),
    pa.field("from_text", pa.string()),
    pa.field("to_text", pa.string()),
    pa.field("observation_basis", pa.string(), nullable=False),
    pa.field("truth_class", pa.string(), nullable=False),
])

FORBIDDEN_SEMANTIC_TOKENS = {
    "bad", "good", "mistake", "correct", "incorrect", "peek", "rotation", "rotate",
    "tradeable", "untradeable", "throw", "misplay", "smart", "poor", "optimal", "suboptimal",
    "aggressive", "passive", "overextend", "overextended", "coach", "coaching",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


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
            s = df[field.name]
        else:
            s = pd.Series([pd.NA] * len(df))
        if pa.types.is_integer(field.type):
            vals = pd.to_numeric(s, errors="coerce").astype("Int64")
        elif pa.types.is_floating(field.type):
            vals = pd.to_numeric(s, errors="coerce").astype("Float64")
        elif pa.types.is_boolean(field.type):
            vals = s.astype("boolean")
        elif pa.types.is_string(field.type) or pa.types.is_large_string(field.type):
            vals = s.astype("string")
        else:
            vals = s
        arrays.append(pa.array(vals, type=field.type, from_pandas=True))
    return pa.Table.from_arrays(arrays, schema=schema)


def write_parquet(df: pd.DataFrame, schema: pa.Schema, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = table_from_df(df, schema)
    tmp = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(path)
    return {"rows": table.num_rows, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def to_python(v: Any) -> Any:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if isinstance(v, np.generic):
        return v.item()
    return v


def same_value(a: Any, b: Any) -> bool:
    a = to_python(a); b = to_python(b)
    if a is None and b is None:
        return True
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-12)
        except Exception:
            return False
    return a == b


def tri(v: Any) -> str:
    v = to_python(v)
    if v is True:
        return "TRUE"
    if v is False:
        return "FALSE"
    return "UNKNOWN"


def head_tri(v: Any) -> str:
    return tri(v)


def discover_pairs(output_folder: Path) -> list[dict]:
    parent = output_folder.resolve().parent
    spatial_root = parent / "Stage3_M42" / "spatial"
    canonical_root = parent / "Stage3_M31" / "canonical"
    if not spatial_root.exists():
        raise FileNotFoundError(f"Passing M4.2 spatial root not found: {spatial_root}")
    if not canonical_root.exists():
        raise FileNotFoundError(f"Passing M3.1 canonical root not found: {canonical_root}")
    out = []
    for sdir in sorted(spatial_root.iterdir()):
        if not sdir.is_dir() or sdir.name.startswith("."):
            continue
        sm_path = sdir / "manifest.json"
        pair_p = sdir / "pair_spatial_relations.parquet"
        player_p = sdir / "player_spatial_samples.parquet"
        cdir = canonical_root / sdir.name
        cm_path = cdir / "manifest.json"
        required_c = [
            cdir / "player_state.parquet", cdir / "world_state_ticks.parquet",
            cdir / "bomb_intervals.parquet", cdir / "utility_intervals.parquet", cm_path,
        ]
        if not (sm_path.exists() and pair_p.exists() and player_p.exists() and all(p.exists() for p in required_c)):
            continue
        sm = read_json(sm_path); cm = read_json(cm_path)
        out.append({"demo_id": sdir.name, "sdir": sdir, "cdir": cdir, "sm": sm, "cm": cm})
    return out


def coerce_steamid(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = df[c].astype("string")
    return df


def build_player_relationships(ps: pd.DataFrame, state: pd.DataFrame, world: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    ps = coerce_steamid(ps.copy(), ["steamid"])
    state = coerce_steamid(state.copy(), ["steamid"])
    keep = [
        "tick", "steamid", "is_alive", "health", "armor_value", "active_weapon_name",
        "is_scoped", "is_walking", "is_airborne", "flash_duration", "balance", "current_equip_value",
    ]
    st = state[[c for c in keep if c in state.columns]].copy()
    merged = ps.merge(st, on=["tick", "steamid"], how="left", validate="one_to_one", indicator=True)
    missing_state = int((merged["_merge"] != "both").sum())
    merged = merged.drop(columns=["_merge"])
    wcols = ["tick", "t_alive", "ct_alive", "t_equipment_value_sum", "ct_equipment_value_sum"]
    w = world[[c for c in wcols if c in world.columns]].drop_duplicates("tick")
    merged = merged.merge(w, on="tick", how="left", validate="many_to_one", indicator=True)
    missing_world = int((merged["_merge"] != "both").sum())
    merged = merged.drop(columns=["_merge"])

    flash = pd.to_numeric(merged.get("flash_duration"), errors="coerce")
    merged["flash_active"] = flash.gt(0).where(flash.notna(), pd.NA)
    is_t = merged["side"].astype("string").str.upper().eq("T")
    is_ct = merged["side"].astype("string").str.upper().eq("CT")
    merged["team_alive"] = np.where(is_t, merged["t_alive"], np.where(is_ct, merged["ct_alive"], np.nan))
    merged["enemy_alive"] = np.where(is_t, merged["ct_alive"], np.where(is_ct, merged["t_alive"], np.nan))
    merged["alive_diff_team_minus_enemy"] = merged["team_alive"] - merged["enemy_alive"]
    merged["team_equipment_value_sum"] = np.where(is_t, merged["t_equipment_value_sum"], np.where(is_ct, merged["ct_equipment_value_sum"], np.nan))
    merged["enemy_equipment_value_sum"] = np.where(is_t, merged["ct_equipment_value_sum"], np.where(is_ct, merged["t_equipment_value_sum"], np.nan))
    merged["equipment_value_diff_team_minus_enemy"] = merged["team_equipment_value_sum"] - merged["enemy_equipment_value_sum"]
    merged["truth_class"] = "deterministic_joined_canonical_and_spatial_relationship"
    return merged, {"missing_player_state_joins": missing_state, "missing_world_state_joins": missing_world}


def build_pair_relationships(pair: pd.DataFrame) -> pd.DataFrame:
    pair = coerce_steamid(pair.copy(), ["t_steamid", "ct_steamid"])
    pair["t_to_ct_static_relation"] = pair["t_to_ct_any_static_ray_clear"].map(tri)
    pair["ct_to_t_static_relation"] = pair["ct_to_t_any_static_ray_clear"].map(tri)
    pair["t_to_ct_head_static_relation"] = pair["t_to_ct_head_static_ray_clear"].map(head_tri)
    pair["ct_to_t_head_static_relation"] = pair["ct_to_t_head_static_ray_clear"].map(head_tri)
    pair = pair.sort_values(["t_steamid", "ct_steamid", "tick"], kind="stable").reset_index(drop=True)
    g = pair.groupby(["t_steamid", "ct_steamid"], sort=False, dropna=False)
    pair["previous_sample_tick"] = g["tick"].shift(1)
    pair["sample_delta_ticks"] = pair["tick"] - pair["previous_sample_tick"]
    pair["previous_distance_units"] = g["distance_units"].shift(1)
    pair["distance_delta_units"] = pair["distance_units"] - pair["previous_distance_units"]
    pair["truth_class"] = "deterministic_spatial_relationship_tri_state"
    return pair


def build_world_relationships(world: pd.DataFrame, pair_rel: pd.DataFrame, player_rel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    # The union of pair and player spatial ticks is authoritative. Pair rows can
    # legitimately disappear after one side has no observed living players.
    spatial_ticks = set(pair_rel["tick"].dropna().astype("int64").tolist())
    spatial_ticks.update(player_rel["tick"].dropna().astype("int64").tolist())
    ticks = pd.DataFrame({"tick": sorted(spatial_ticks)})
    w = world.drop_duplicates("tick").copy()
    base = ticks.merge(w, on="tick", how="left", validate="one_to_one", indicator=True)
    missing_world = int((base["_merge"] != "both").sum())
    base = base.drop(columns=["_merge"])
    base["alive_diff_t_minus_ct"] = base["t_alive"] - base["ct_alive"]
    base["equipment_value_diff_t_minus_ct"] = base["t_equipment_value_sum"] - base["ct_equipment_value_sum"]

    def counts_for(col: str, prefix: str) -> pd.DataFrame:
        x = pair_rel[["tick", col]].copy()
        x["state"] = x[col].astype("string")
        ct = x.groupby(["tick", "state"], dropna=False).size().unstack(fill_value=0)
        for s in ("TRUE", "FALSE", "UNKNOWN"):
            if s not in ct.columns:
                ct[s] = 0
        ct = ct[["TRUE", "FALSE", "UNKNOWN"]].rename(columns={
            "TRUE": f"{prefix}_static_true_count",
            "FALSE": f"{prefix}_static_false_count",
            "UNKNOWN": f"{prefix}_static_unknown_count",
        })
        return ct.reset_index()

    base = base.merge(counts_for("t_to_ct_static_relation", "t_to_ct"), on="tick", how="left")
    base = base.merge(counts_for("ct_to_t_static_relation", "ct_to_t"), on="tick", how="left")

    heads = pair_rel.groupby("tick", dropna=False).agg(
        t_to_ct_head_clear_count=("t_to_ct_head_static_relation", lambda s: int((s == "TRUE").sum())),
        ct_to_t_head_clear_count=("ct_to_t_head_static_relation", lambda s: int((s == "TRUE").sum())),
        known_active_smoke_count=("known_active_smoke_count", "max"),
        unknown_end_smoke_count=("unknown_end_smoke_count", "max"),
        dynamic_world_uncertainty=("dynamic_world_uncertainty", "max"),
    ).reset_index()
    base = base.merge(heads, on="tick", how="left", validate="one_to_one")
    count_cols = [c for c in base.columns if c.endswith("_count") and c not in {"known_active_smoke_count", "unknown_end_smoke_count"}]
    for c in count_cols:
        base[c] = base[c].fillna(0)
    base["known_active_smoke_count"] = base["known_active_smoke_count"].fillna(0)
    base["unknown_end_smoke_count"] = base["unknown_end_smoke_count"].fillna(0)
    base["dynamic_world_uncertainty"] = base["dynamic_world_uncertainty"].fillna(True)
    base["truth_class"] = "deterministic_world_and_spatial_relationship_summary"
    return base, {"missing_world_relationship_joins": missing_world}


def add_transition(rows: list[dict], *, demo_id: str, round_v: Any, tick: Any, previous_tick: Any, scope: str,
                   transition_type: str, subject: Any = None, other: Any = None, side: Any = None,
                   from_v: Any = None, to_v: Any = None, basis: str, truth_class: str) -> None:
    a = to_python(from_v); b = to_python(to_v)
    row = {
        "demo_id": demo_id, "round": to_python(round_v), "tick": int(tick), "previous_tick": to_python(previous_tick),
        "scope": scope, "subject_steamid": None if subject is None else str(subject),
        "other_steamid": None if other is None else str(other), "side": to_python(side),
        "transition_type": transition_type,
        "from_bool": None, "to_bool": None,
        "from_int": None, "to_int": None, "delta_int": None,
        "from_float": None, "to_float": None, "delta_float": None,
        "from_text": None, "to_text": None,
        "observation_basis": basis, "truth_class": truth_class,
    }
    if isinstance(a, (bool, np.bool_)) or isinstance(b, (bool, np.bool_)):
        row["from_bool"] = a if isinstance(a, (bool, np.bool_)) else None
        row["to_bool"] = b if isinstance(b, (bool, np.bool_)) else None
    elif isinstance(a, (int, np.integer)) or isinstance(b, (int, np.integer)):
        row["from_int"] = int(a) if isinstance(a, (int, np.integer)) else None
        row["to_int"] = int(b) if isinstance(b, (int, np.integer)) else None
        if row["from_int"] is not None and row["to_int"] is not None:
            row["delta_int"] = row["to_int"] - row["from_int"]
    elif isinstance(a, (float, np.floating)) or isinstance(b, (float, np.floating)):
        row["from_float"] = float(a) if isinstance(a, (float, np.floating)) and math.isfinite(float(a)) else None
        row["to_float"] = float(b) if isinstance(b, (float, np.floating)) and math.isfinite(float(b)) else None
        if row["from_float"] is not None and row["to_float"] is not None:
            row["delta_float"] = row["to_float"] - row["from_float"]
    else:
        row["from_text"] = None if a is None else str(a)
        row["to_text"] = None if b is None else str(b)
    rows.append(row)


def _changed_mask(cur: pd.Series, prev: pd.Series) -> pd.Series:
    """Return a plain-bool change mask without nullable-Arrow comparisons.

    pandas/pyarrow extension arrays can raise ``TypeError: boolean value of NA is
    ambiguous`` inside Series.eq() before fillna() gets a chance to run.  Keep
    missingness handling explicit, compare only positions where both values are
    known, and return an ordinary numpy-backed boolean Series.
    """
    cur_na = cur.isna().to_numpy(dtype=bool)
    prev_na = prev.isna().to_numpy(dtype=bool)

    changed = np.logical_xor(cur_na, prev_na)
    both_known = ~(cur_na | prev_na)
    if bool(both_known.any()):
        left = cur.loc[both_known].astype(object).to_numpy()
        right = prev.loc[both_known].astype(object).to_numpy()
        changed[both_known] = np.not_equal(left, right)

    return pd.Series(changed, index=cur.index, dtype=bool)


def transitions_from_player_state(demo_id: str, state: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    state = coerce_steamid(state.copy(), ["steamid"])
    state = state.sort_values(["steamid", "tick"], kind="stable").reset_index(drop=True)
    flash = pd.to_numeric(state.get("flash_duration"), errors="coerce")
    state["flash_active"] = flash.gt(0).where(flash.notna(), pd.NA)
    fields = [
        "is_alive", "health", "armor_value", "active_weapon_name", "is_scoped", "is_walking",
        "is_airborne", "side", "balance", "current_equip_value", "flash_active",
    ]
    grouped = state.groupby("steamid", sort=False, dropna=False)
    prev_tick = grouped["tick"].shift(1)
    first = prev_tick.isna()
    for f in fields:
        if f not in state.columns:
            continue
        prev = grouped[f].shift(1)
        changed = _changed_mask(state[f], prev) & ~first
        if not bool(changed.any()):
            continue
        sub = state.loc[changed, ["tick", "round", "steamid", "side", f]].copy()
        sub["previous_tick"] = prev_tick.loc[changed].to_numpy()
        sub["from_value"] = prev.loc[changed].to_numpy()
        for rec in sub.to_dict("records"):
            add_transition(
                rows, demo_id=demo_id, round_v=rec.get("round"), tick=rec["tick"], previous_tick=rec.get("previous_tick"),
                scope="player", transition_type=f, subject=rec.get("steamid"), side=rec.get("side"),
                from_v=rec.get("from_value"), to_v=rec.get(f), basis="successive_canonical_player_samples",
                truth_class="observed_sampled_state_change",
            )
    return rows

def transitions_from_world(demo_id: str, world_rel: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    g = world_rel.sort_values("tick", kind="stable")
    fields = [
        "t_alive", "ct_alive", "alive_diff_t_minus_ct", "t_equipment_value_sum", "ct_equipment_value_sum",
        "equipment_value_diff_t_minus_ct", "bomb_planted_observed",
        "t_to_ct_static_true_count", "t_to_ct_static_false_count", "t_to_ct_static_unknown_count",
        "ct_to_t_static_true_count", "ct_to_t_static_false_count", "ct_to_t_static_unknown_count",
        "known_active_smoke_count", "unknown_end_smoke_count",
    ]
    prev = None
    for rec in g.to_dict("records"):
        if prev is not None:
            for f in fields:
                a, b = prev.get(f), rec.get(f)
                if not same_value(a, b):
                    add_transition(
                        rows, demo_id=demo_id, round_v=rec.get("round"), tick=rec["tick"], previous_tick=prev.get("tick"),
                        scope="world", transition_type=f, from_v=a, to_v=b,
                        basis="successive_spatial_sample_ticks", truth_class="deterministic_relationship_summary_change",
                    )
        prev = rec
    return rows


def transitions_from_pairs(demo_id: str, pair_rel: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    pair_rel = pair_rel.sort_values(["t_steamid", "ct_steamid", "tick"], kind="stable").reset_index(drop=True)
    grouped = pair_rel.groupby(["t_steamid", "ct_steamid"], sort=False, dropna=False)
    prev_tick = grouped["tick"].shift(1)
    first = prev_tick.isna()
    fields = [
        ("t_to_ct_static_relation", "T", "t_steamid", "ct_steamid"),
        ("ct_to_t_static_relation", "CT", "ct_steamid", "t_steamid"),
        ("t_to_ct_head_static_relation", "T", "t_steamid", "ct_steamid"),
        ("ct_to_t_head_static_relation", "CT", "ct_steamid", "t_steamid"),
    ]
    for f, side, subj_col, other_col in fields:
        prev = grouped[f].shift(1)
        changed = _changed_mask(pair_rel[f], prev) & ~first
        if not bool(changed.any()):
            continue
        sub = pair_rel.loc[changed, ["tick", "round", subj_col, other_col, f]].copy()
        sub["previous_tick"] = prev_tick.loc[changed].to_numpy()
        sub["from_value"] = prev.loc[changed].to_numpy()
        for rec in sub.to_dict("records"):
            add_transition(
                rows, demo_id=demo_id, round_v=rec.get("round"), tick=rec["tick"], previous_tick=rec.get("previous_tick"),
                scope="pair", transition_type=f, subject=rec.get(subj_col), other=rec.get(other_col), side=side,
                from_v=rec.get("from_value"), to_v=rec.get(f), basis="successive_spatial_pair_samples",
                truth_class="deterministic_tri_state_spatial_relation_change",
            )
    return rows

def transitions_from_bomb_utility(demo_id: str, bomb: pd.DataFrame, util: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    if not bomb.empty:
        for rd, g in bomb.sort_values(["round", "start_tick"], kind="stable").groupby("round", sort=False, dropna=False):
            prev_state = None; prev_tick = None
            for rec in g.to_dict("records"):
                add_transition(
                    rows, demo_id=demo_id, round_v=rd, tick=rec["start_tick"], previous_tick=prev_tick,
                    scope="bomb", transition_type="bomb_state", subject=rec.get("carrier_steamid"),
                    from_v=prev_state, to_v=rec.get("bomb_state"), basis="canonical_bomb_interval_start",
                    truth_class=str(rec.get("truth_class") or "deterministic_bomb_interval_transition"),
                )
                prev_state = rec.get("bomb_state"); prev_tick = rec.get("start_tick")
    if not util.empty:
        for rec in util.to_dict("records"):
            utype = str(rec.get("utility_type") or "unknown")
            add_transition(
                rows, demo_id=demo_id, round_v=rec.get("round"), tick=rec["start_tick"], previous_tick=None,
                scope="utility", transition_type=f"utility_active::{utype}", subject=rec.get("owner_steamid"),
                from_v=False, to_v=True, basis="canonical_utility_interval_start",
                truth_class=str(rec.get("truth_class") or "deterministic_utility_interval_transition"),
            )
            end_tick = to_python(rec.get("end_tick"))
            end_known = bool(to_python(rec.get("end_known"))) if to_python(rec.get("end_known")) is not None else False
            if end_known and end_tick is not None:
                add_transition(
                    rows, demo_id=demo_id, round_v=rec.get("round"), tick=end_tick, previous_tick=rec.get("start_tick"),
                    scope="utility", transition_type=f"utility_active::{utype}", subject=rec.get("owner_steamid"),
                    from_v=True, to_v=False, basis="canonical_utility_interval_end",
                    truth_class=str(rec.get("truth_class") or "deterministic_utility_interval_transition"),
                )
    return rows


def forbidden_semantics(transitions: pd.DataFrame) -> list[str]:
    bad = set()
    if "transition_type" not in transitions.columns:
        return []
    for v in transitions["transition_type"].dropna().astype(str):
        toks = set(v.lower().replace("::", "_").split("_"))
        bad.update(toks.intersection(FORBIDDEN_SEMANTIC_TOKENS))
    return sorted(bad)


def process_demo(item: dict, output_root: Path) -> dict:
    t0 = time.perf_counter()
    demo_id = item["demo_id"]
    sdir: Path = item["sdir"]; cdir: Path = item["cdir"]
    sm = item["sm"]; cm = item["cm"]
    res = {
        "demo_id": demo_id,
        "dataset": sm.get("dataset"), "source_family": sm.get("source_family"),
        "segmented_hint": bool(sm.get("segmented_hint")), "map_name": sm.get("map_name"),
        "success": False, "errors": [], "warnings": [], "timings": {},
    }
    out = output_root / "relationships" / demo_id
    tmp = output_root / "relationships" / f".{demo_id}.tmp"
    shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir(parents=True, exist_ok=True)
    try:
        p = time.perf_counter()
        ps = pq.read_table(sdir / "player_spatial_samples.parquet").to_pandas()
        pair = pq.read_table(sdir / "pair_spatial_relations.parquet").to_pandas()
        state = pq.read_table(cdir / "player_state.parquet").to_pandas()
        world = pq.read_table(cdir / "world_state_ticks.parquet").to_pandas()
        bomb = pq.read_table(cdir / "bomb_intervals.parquet").to_pandas()
        util = pq.read_table(cdir / "utility_intervals.parquet").to_pandas()
        res["timings"]["read_inputs_s"] = time.perf_counter() - p

        p = time.perf_counter()
        player_rel, player_join = build_player_relationships(ps, state, world)
        pair_rel = build_pair_relationships(pair)
        world_rel, world_join = build_world_relationships(world, pair_rel, player_rel)
        res["timings"]["relationships_s"] = time.perf_counter() - p

        p = time.perf_counter()
        tr_rows = []
        tr_rows.extend(transitions_from_player_state(demo_id, state))
        tr_rows.extend(transitions_from_world(demo_id, world_rel))
        tr_rows.extend(transitions_from_pairs(demo_id, pair_rel))
        tr_rows.extend(transitions_from_bomb_utility(demo_id, bomb, util))
        transitions = pd.DataFrame(tr_rows)
        if not transitions.empty:
            transitions = transitions.sort_values(["tick", "scope", "transition_type", "subject_steamid", "other_steamid"], kind="stable", na_position="last").reset_index(drop=True)
        res["timings"]["transitions_s"] = time.perf_counter() - p

        input_unknown_t = int(pair["t_to_ct_any_static_ray_clear"].isna().sum())
        input_unknown_ct = int(pair["ct_to_t_any_static_ray_clear"].isna().sum())
        output_unknown_t = int((pair_rel["t_to_ct_static_relation"] == "UNKNOWN").sum())
        output_unknown_ct = int((pair_rel["ct_to_t_static_relation"] == "UNKNOWN").sum())
        collision_ready = str((sm.get("geometry_profile") or {}).get("collision_status") or "") == "ready"
        deep = pair_rel[pair_rel["deep_event_tick"] == True]  # noqa: E712
        deep_unresolved = int(((deep["t_to_ct_static_relation"] == "UNKNOWN") | (deep["ct_to_t_static_relation"] == "UNKNOWN")).sum()) if collision_ready else 0
        forbidden = forbidden_semantics(transitions)
        gates = {
            "player_rows_preserved": len(player_rel) == len(ps),
            "pair_rows_preserved": len(pair_rel) == len(pair),
            "canonical_player_join_complete": player_join["missing_player_state_joins"] == 0,
            "canonical_world_join_complete": player_join["missing_world_state_joins"] == 0 and world_join["missing_world_relationship_joins"] == 0,
            "tri_state_unknown_preserved": input_unknown_t == output_unknown_t and input_unknown_ct == output_unknown_ct,
            "deep_event_collision_ready_rows_resolved": deep_unresolved == 0,
            "transitions_nonzero": len(transitions) > 0,
            "forbidden_coaching_semantics_absent": len(forbidden) == 0,
        }
        res["gates"] = gates
        if not all(gates.values()):
            raise RuntimeError(f"M5 gates failed: {gates}")

        p = time.perf_counter()
        outputs = {
            "player_relationship_samples": write_parquet(player_rel, PLAYER_REL_SCHEMA, tmp / "player_relationship_samples.parquet"),
            "pair_relationship_samples": write_parquet(pair_rel, PAIR_REL_SCHEMA, tmp / "pair_relationship_samples.parquet"),
            "world_relationship_samples": write_parquet(world_rel, WORLD_REL_SCHEMA, tmp / "world_relationship_samples.parquet"),
            "state_transitions": write_parquet(transitions, TRANSITION_SCHEMA, tmp / "state_transitions.parquet"),
        }
        transition_counts = Counter(transitions["scope"].astype(str).tolist()) if not transitions.empty else Counter()
        manifest = {
            "m5_version": M5_VERSION, "relationship_schema_version": RELATIONSHIP_SCHEMA_VERSION,
            "demo_id": demo_id, "dataset": sm.get("dataset"), "source_family": sm.get("source_family"),
            "segmented_hint": bool(sm.get("segmented_hint")), "map_name": sm.get("map_name"),
            "source_canonical": {"path": str(cdir), "canonical_schema_version": cm.get("canonical_schema_version")},
            "source_spatial": {"path": str(sdir), "spatial_schema_version": sm.get("spatial_schema_version")},
            "semantics": {
                "relationship_layer": "Deterministic joins, numeric differences, sampled deltas, and tri-state spatial relationships only.",
                "unknown": "M4.2 UNKNOWN remains UNKNOWN. It is never rewritten as FALSE or zero.",
                "transition": "A transition means the observed value differs between successive canonical/spatial samples or begins/ends a canonical interval. It is not a tactical judgment.",
                "distance_delta": "Signed change in pair distance between successive sampled spatial observations; no tactical meaning is assigned.",
                "alive_and_equipment_diffs": "Signed arithmetic differences only; no advantage/win-probability label is emitted.",
            },
            "counts": {
                "player_relationship_rows": len(player_rel), "pair_relationship_rows": len(pair_rel),
                "world_relationship_rows": len(world_rel), "transition_rows": len(transitions),
                "transition_scope_counts": dict(transition_counts),
                "t_to_ct_unknown_rows": output_unknown_t, "ct_to_t_unknown_rows": output_unknown_ct,
            },
            "join_diagnostics": {**player_join, **world_join},
            "gates": gates, "forbidden_semantic_tokens_found": forbidden,
            "outputs": outputs,
            "demo_reparsed": False, "awpy_invoked": False, "new_raycasting": False,
            "candidate_detection": False, "coaching_generated": False,
        }
        write_json(manifest, tmp / "manifest.json")
        res["timings"]["write_s"] = time.perf_counter() - p

        if out.exists():
            shutil.rmtree(out)
        tmp.replace(out)
        res.update({
            "success": True, "output_dir": str(out), "counts": manifest["counts"],
            "join_diagnostics": manifest["join_diagnostics"], "gates": gates,
        })
    except Exception as exc:
        res["errors"].append(f"{type(exc).__name__}: {exc}")
        res["traceback"] = traceback.format_exc()
        shutil.rmtree(tmp, ignore_errors=True)
    res["wall_seconds"] = time.perf_counter() - t0
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-folder", required=True)
    ap.add_argument("--output-folder", required=True)
    args = ap.parse_args()
    output = Path(args.output_folder)
    output.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    report = {
        "m5_version": M5_VERSION, "relationship_schema_version": RELATIONSHIP_SCHEMA_VERSION,
        "generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S"),
        "input_folder": args.input_folder, "output_folder": str(output),
        "results": [],
    }
    try:
        items = discover_pairs(output)
    except Exception as exc:
        report.update({"discovered_demo_count": 0, "success_count": 0, "failure_count": 1, "fatal_error": f"{type(exc).__name__}: {exc}", "decision": "M5_FAIL: required passing M3.1/M4.2 inputs were not found."})
        report["wall_seconds"] = time.perf_counter() - t0
        write_json(report, output / "M5_report.json")
        print(json.dumps({"decision": report["decision"], "success": "0/0", "wall_seconds": report["wall_seconds"]}, indent=2))
        return 1

    report["discovered_demo_count"] = len(items)
    for item in items:
        report["results"].append(process_demo(item, output))

    success = [r for r in report["results"] if r.get("success")]
    failure = [r for r in report["results"] if not r.get("success")]
    report["success_count"] = len(success); report["failure_count"] = len(failure)
    report["segmented_source_included"] = any(bool(r.get("segmented_hint")) for r in success)
    report["source_families"] = sorted({str(r.get("source_family")) for r in success})
    report["total_transition_rows"] = sum(int((r.get("counts") or {}).get("transition_rows", 0)) for r in success)
    report["total_pair_relationship_rows"] = sum(int((r.get("counts") or {}).get("pair_relationship_rows", 0)) for r in success)
    report["total_unknown_direction_rows"] = sum(
        int((r.get("counts") or {}).get("t_to_ct_unknown_rows", 0)) + int((r.get("counts") or {}).get("ct_to_t_unknown_rows", 0)) for r in success
    )
    all_gates = all(all((r.get("gates") or {}).values()) for r in success) if success else False
    expected_all = len(items) > 0 and len(success) == len(items)
    report["promotion_gates"] = {
        "all_discovered_spatial_demos_succeeded": expected_all,
        "all_per_demo_relationship_gates_passed": all_gates,
        "segmented_source_included": report["segmented_source_included"],
        "transitions_nonzero": report["total_transition_rows"] > 0,
    }
    passed = not failure and all(report["promotion_gates"].values())
    report["wall_seconds"] = time.perf_counter() - t0
    if passed:
        report["decision"] = "M5_PASS: deterministic relationship samples and neutral state transitions are reproducible from canonical plus tri-state spatial evidence with UNKNOWN preserved. Proceed to neutral candidate-situation generation."
        report["next_stage"] = "M6 neutral candidate situations and evidence references; no coaching semantics."
    else:
        report["decision"] = "M5_FAIL: relationship/state-transition promotion gates not met."
        report["next_stage"] = "Repair M5 only; retain passing M3.1 and M4.2 outputs."
    write_json(report, output / "M5_report.json")
    print(json.dumps({"decision": report["decision"], "success": f"{len(success)}/{len(items)}", "transitions": report["total_transition_rows"], "wall_seconds": report["wall_seconds"]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
