from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import time
import traceback
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from awpy.nav import Nav
from awpy.visibility import VisibilityChecker

M41_VERSION = "4.1-v0.1"
SPATIAL_SCHEMA_VERSION = "1.1.0-alpha1"
DEFAULT_ROUNDS = 4
DEFAULT_GRID_STEP_TICKS = 64
RAY_CACHE_SIZE = 100_000
COMBAT_EVENT_NAMES = {
    "player_death", "player_hurt", "weapon_fire",
    "smokegrenade_detonate", "smokegrenade_expired",
    "inferno_startburn", "inferno_expire",
    "bomb_planted", "bomb_defused", "bomb_exploded",
}

PLAYER_SPATIAL_SCHEMA = pa.schema([
    pa.field("demo_id", pa.string(), nullable=False),
    pa.field("tick", pa.int64(), nullable=False),
    pa.field("round", pa.int32()),
    pa.field("steamid", pa.string(), nullable=False),
    pa.field("side", pa.string()),
    pa.field("x", pa.float64()), pa.field("y", pa.float64()), pa.field("z", pa.float64()),
    pa.field("place_name_literal", pa.string()),
    pa.field("nav_area_id", pa.int64()),
    pa.field("nav_assignment_mode", pa.string()),
    pa.field("nav_assignment_distance", pa.float64()),
    pa.field("static_collision_status", pa.string(), nullable=False),
    pa.field("static_clear_enemy_count", pa.int16()),
    pa.field("static_exposed_to_enemy_count", pa.int16()),
    pa.field("nearest_enemy_distance", pa.float64()),
    pa.field("nearest_static_clear_enemy_distance", pa.float64()),
    pa.field("nearest_known_active_smoke_segment_distance", pa.float64()),
    pa.field("known_active_smoke_count", pa.int16(), nullable=False),
    pa.field("unknown_end_smoke_count", pa.int16(), nullable=False),
    pa.field("dynamic_world_uncertainty", pa.bool_(), nullable=False),
])

# Preserve the M4 pair columns for downstream stability. Fractions are deliberately
# null in the fast path: exact any-clear and head-clear are computed, while full
# 12-point fractions become deep evidence only.
PAIR_SCHEMA = pa.schema([
    pa.field("demo_id", pa.string(), nullable=False),
    pa.field("tick", pa.int64(), nullable=False),
    pa.field("round", pa.int32()),
    pa.field("t_steamid", pa.string(), nullable=False),
    pa.field("ct_steamid", pa.string(), nullable=False),
    pa.field("distance_units", pa.float64()),
    pa.field("collision_evaluated", pa.bool_(), nullable=False),
    pa.field("collision_status", pa.string(), nullable=False),
    pa.field("t_to_ct_any_static_ray_clear", pa.bool_()),
    pa.field("t_to_ct_static_clear_fraction", pa.float64()),
    pa.field("t_to_ct_head_static_ray_clear", pa.bool_()),
    pa.field("ct_to_t_any_static_ray_clear", pa.bool_()),
    pa.field("ct_to_t_static_clear_fraction", pa.float64()),
    pa.field("ct_to_t_head_static_ray_clear", pa.bool_()),
    pa.field("nearest_known_active_smoke_segment_distance", pa.float64()),
    pa.field("known_active_smoke_count", pa.int16(), nullable=False),
    pa.field("unknown_end_smoke_count", pa.int16(), nullable=False),
    pa.field("dynamic_world_uncertainty", pa.bool_(), nullable=False),
    pa.field("truth_class", pa.string(), nullable=False),
])


def write_json(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def table_from_rows(rows: list[dict], schema: pa.Schema) -> pa.Table:
    arrays = []
    for field in schema:
        vals = [r.get(field.name) for r in rows]
        arrays.append(pa.array(vals, type=field.type, from_pandas=True))
    return pa.Table.from_arrays(arrays, schema=schema)


def write_rows(rows: list[dict], schema: pa.Schema, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = table_from_rows(rows, schema)
    tmp = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(path)
    return {"rows": table.num_rows, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def safe_int(v: Any) -> int | None:
    try:
        if pd.isna(v):
            return None
        return int(v)
    except Exception:
        return None


def safe_float(v: Any) -> float | None:
    try:
        if pd.isna(v):
            return None
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def side_value(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v).upper()
    return s if s in {"T", "CT"} else None


def resolve_existing_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    p = Path(raw)
    if p.exists():
        return p
    s = str(raw).replace("/", "\\")
    marker = "\\AppData\\Local\\CS2Coach\\"
    idx = s.lower().find(marker.lower())
    local = os.environ.get("LOCALAPPDATA")
    if idx >= 0 and local:
        q = Path(local + "\\CS2Coach\\" + s[idx + len(marker):])
        if q.exists():
            return q
    return p


def profile_for_dataset(dataset: str) -> str:
    k = (dataset or "").lower()
    if k == "austinmajor_2025":
        return "austin_major_2025"
    if k == "starladder_2025":
        return "starladder_major_2025"
    if k == "iemcolognemajor2026":
        return "live_current_iem_proxy"
    if k in {"faceit", "premier_batch1"}:
        return "live_current"
    return "unknown"


def point_in_poly(x: float, y: float, poly: list[tuple[float, float, float]]) -> bool:
    inside = False
    n = len(poly)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        den = (yj - yi) if (yj - yi) != 0 else 1e-12
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / den + xi):
            inside = not inside
        j = i
    return inside


def vxyz(v: Any) -> tuple[float, float, float]:
    if all(hasattr(v, k) for k in ("x", "y", "z")):
        return float(v.x), float(v.y), float(v.z)
    a = list(v)
    return float(a[0]), float(a[1]), float(a[2])


class NavLocator:
    def __init__(self, nav: Nav, cell: float = 512.0):
        self.recs = []
        self.grid = defaultdict(list)
        self.cell = cell
        for aid, a in nav.areas.items():
            pts = [vxyz(c) for c in a.corners]
            if len(pts) < 3:
                continue
            cx, cy, cz = vxyz(a.centroid)
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            rec = {"id": int(aid), "poly": pts, "centroid": (cx, cy, cz), "minx": min(xs), "maxx": max(xs), "miny": min(ys), "maxy": max(ys)}
            idx = len(self.recs)
            self.recs.append(rec)
            for gx in range(math.floor(rec["minx"] / cell), math.floor(rec["maxx"] / cell) + 1):
                for gy in range(math.floor(rec["miny"] / cell), math.floor(rec["maxy"] / cell) + 1):
                    self.grid[(gx, gy)].append(idx)

    def locate(self, p: tuple[float, float, float]):
        x, y, z = p
        gx = math.floor(x / self.cell)
        gy = math.floor(y / self.cell)
        cand = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                cand.update(self.grid.get((gx + dx, gy + dy), []))
        if not cand:
            cand = range(len(self.recs))
        containing = []
        for i in cand:
            r = self.recs[i]
            if r["minx"] - 2 <= x <= r["maxx"] + 2 and r["miny"] - 2 <= y <= r["maxy"] + 2 and point_in_poly(x, y, r["poly"]):
                containing.append(r)
        if containing:
            r = min(containing, key=lambda q: abs(q["centroid"][2] - z))
            return r["id"], "contains_xy", abs(r["centroid"][2] - z)
        recs = [self.recs[i] for i in cand]
        if not recs:
            return None, "unavailable", None
        r = min(recs, key=lambda q: (q["centroid"][0] - x) ** 2 + (q["centroid"][1] - y) ** 2 + (q["centroid"][2] - z) ** 2)
        return r["id"], "nearest_centroid", math.dist(r["centroid"], p)


class CachedVisibility:
    """Exact-coordinate bounded memoization around AWPy's static collision query."""

    def __init__(self, checker: VisibilityChecker, maxsize: int = RAY_CACHE_SIZE):
        self.checker = checker

        @lru_cache(maxsize=maxsize)
        def _cached(ax: float, ay: float, az: float, bx: float, by: float, bz: float) -> bool:
            return bool(self.checker.is_visible((ax, ay, az), (bx, by, bz)))

        self._cached = _cached

    def is_visible(self, a: tuple[float, float, float], b: tuple[float, float, float]) -> bool:
        return self._cached(a[0], a[1], a[2], b[0], b[1], b[2])

    def cache_info(self) -> dict:
        c = self._cached.cache_info()
        return {"hits": c.hits, "misses": c.misses, "maxsize": c.maxsize, "currsize": c.currsize}


def static_any_shortcircuit(checker: CachedVisibility, src: tuple[float, float, float], dst: tuple[float, float, float]) -> dict:
    """Exact M4 any-clear semantics without computing the 12-ray fraction.

    The original M4 evaluated 12 unique target-body rays, then repeated the head-center
    ray a 13th time. Here head-center is evaluated once, then the remaining 11 unique
    rays are tested only until the first clear ray is found. If none clear, all 12 have
    been evaluated, so any-clear is exactly equivalent to M4.
    """
    ax, ay, az = src
    bx, by, bz = dst
    dx = bx - ax
    dy = by - ay
    L = math.hypot(dx, dy)
    px, py = (1.0, 0.0) if L < 1e-9 else (-dy / L, dx / L)
    eye = (ax, ay, az + 64.0)
    head_target = (bx, by, bz + 64.0)
    rays = 1
    head = checker.is_visible(eye, head_target)
    if head:
        return {"any": True, "head": True, "rays": rays}

    # Priority order favors central upper-body probes, then side/lower points.
    ordered_targets = [
        (bx, by, bz + 53.0),
        (bx, by, bz + 41.0),
        (bx, by, bz + 28.0),
        (bx - px * 8.0, by - py * 8.0, bz + 64.0),
        (bx + px * 8.0, by + py * 8.0, bz + 64.0),
        (bx - px * 8.0, by - py * 8.0, bz + 53.0),
        (bx + px * 8.0, by + py * 8.0, bz + 53.0),
        (bx - px * 8.0, by - py * 8.0, bz + 41.0),
        (bx + px * 8.0, by + py * 8.0, bz + 41.0),
        (bx - px * 8.0, by - py * 8.0, bz + 28.0),
        (bx + px * 8.0, by + py * 8.0, bz + 28.0),
    ]
    for target in ordered_targets:
        rays += 1
        if checker.is_visible(eye, target):
            return {"any": True, "head": False, "rays": rays}
    return {"any": False, "head": False, "rays": rays}


def point_segment_distance(p: tuple[float, float, float], a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    px, py, pz = p
    ax, ay, az = a
    bx, by, bz = b
    ab = (bx - ax, by - ay, bz - az)
    ap = (px - ax, py - ay, pz - az)
    den = sum(v * v for v in ab)
    if den <= 1e-12:
        return math.dist(p, a)
    t = max(0.0, min(1.0, sum(ap[i] * ab[i] for i in range(3)) / den))
    q = (ax + t * ab[0], ay + t * ab[1], az + t * ab[2])
    return math.dist(p, q)


def smoke_state_at_tick(ui: pd.DataFrame, tick: int, rd: int | None):
    if ui.empty:
        return [], 0
    s = ui[ui["utility_type"].astype(str) == "smoke"]
    if rd is not None and "round" in s.columns:
        rr = pd.to_numeric(s["round"], errors="coerce")
        s = s[(rr.isna()) | (rr == rd)]
    known = []
    unknown = 0
    for _, r in s.iterrows():
        st = safe_int(r.get("start_tick"))
        en = safe_int(r.get("end_tick"))
        end_known = bool(r.get("end_known")) if not pd.isna(r.get("end_known")) else False
        if st is None or tick < st:
            continue
        if end_known and en is not None:
            if tick <= en:
                xyz = tuple(safe_float(r.get(k)) for k in ("x", "y", "z"))
                if None not in xyz:
                    known.append(xyz)
        else:
            unknown += 1
    return known, unknown


def source_event_ticks(cmanifest: dict, round_bounds: list[tuple[int, int, int]], fallback_player: pd.DataFrame) -> set[int]:
    evidence_path = Path(str((cmanifest.get("source_evidence") or {}).get("path") or ""))
    ep = evidence_path / "events.parquet"
    if not ep.exists():
        return set(int(x) for x in fallback_player.loc[fallback_player["sample_event_tick"].fillna(False), "tick"].tolist())
    try:
        ev = pq.read_table(ep, columns=["event_name", "tick", "segment_round"]).to_pandas()
    except Exception:
        ev = pq.read_table(ep).to_pandas()
    if "event_name" not in ev or "tick" not in ev:
        return set()
    ev = ev[ev["event_name"].astype(str).isin(COMBAT_EVENT_NAMES)]
    out = set()
    for _, r in ev.iterrows():
        t = safe_int(r.get("tick"))
        rd = safe_int(r.get("segment_round"))
        if t is None:
            continue
        if any(a <= t <= b and (rd is None or rd == rno) for rno, a, b in round_bounds):
            out.add(t)
    return out


def choose_ticks(ps: pd.DataFrame, rs: pd.DataFrame, cmanifest: dict, rounds_n: int, step_ticks: int):
    rsort = rs.sort_values("round").head(rounds_n)
    bounds = []
    for _, r in rsort.iterrows():
        rd = safe_int(r.get("round"))
        a = safe_int(r.get("freeze_end_tick")) or safe_int(r.get("start_tick"))
        b = safe_int(r.get("end_tick"))
        if rd is not None and a is not None and b is not None and b >= a:
            bounds.append((rd, a, b))
    ticks = set()
    uniq = sorted(set(int(x) for x in ps["tick"].tolist()))
    for rd, a, b in bounds:
        inr = [t for t in uniq if a <= t <= b]
        if not inr:
            continue
        last = None
        for t in inr:
            if last is None or t - last >= step_ticks:
                ticks.add(t)
                last = t
        ticks.add(inr[-1])
    ticks |= source_event_ticks(cmanifest, bounds, ps)
    return sorted(ticks), bounds


def discover_canonical(output_folder: Path) -> list[Path]:
    parent = output_folder.resolve().parent
    root = parent / "Stage3_M31" / "canonical"
    if not root.exists():
        root = parent / "Stage3_M3" / "canonical"
    if not root.exists():
        return []
    return sorted([p for p in root.iterdir() if p.is_dir() and (p / "manifest.json").exists()])


def _bool_series_equal(a: pd.Series, b: pd.Series) -> bool:
    return a.astype("boolean").reset_index(drop=True).equals(b.astype("boolean").reset_index(drop=True))


def compare_with_m4(demo_id: str, new_pair: Path, new_player: Path, prior_m4_root: Path) -> dict:
    ref_dir = prior_m4_root / "spatial" / demo_id
    ref_pair = ref_dir / "pair_spatial_relations.parquet"
    ref_player = ref_dir / "player_spatial_samples.parquet"
    if not ref_pair.exists() or not ref_player.exists():
        return {"available": False, "equal_core": False, "reason": "prior_m4_artifacts_missing"}
    oldp = pq.read_table(ref_pair).to_pandas()
    newp = pq.read_table(new_pair).to_pandas()
    keys = ["tick", "round", "t_steamid", "ct_steamid"]
    cols = [
        "t_to_ct_any_static_ray_clear", "t_to_ct_head_static_ray_clear",
        "ct_to_t_any_static_ray_clear", "ct_to_t_head_static_ray_clear",
    ]
    oldp = oldp.sort_values(keys, na_position="last").reset_index(drop=True)
    newp = newp.sort_values(keys, na_position="last").reset_index(drop=True)
    pair_keys_equal = len(oldp) == len(newp) and oldp[keys].astype(str).equals(newp[keys].astype(str))
    col_equal = {c: (pair_keys_equal and _bool_series_equal(oldp[c], newp[c])) for c in cols}

    oldpl = pq.read_table(ref_player).to_pandas()
    newpl = pq.read_table(new_player).to_pandas()
    pkeys = ["tick", "round", "steamid"]
    pcols = ["static_clear_enemy_count", "static_exposed_to_enemy_count"]
    oldpl = oldpl.sort_values(pkeys, na_position="last").reset_index(drop=True)
    newpl = newpl.sort_values(pkeys, na_position="last").reset_index(drop=True)
    player_keys_equal = len(oldpl) == len(newpl) and oldpl[pkeys].astype(str).equals(newpl[pkeys].astype(str))
    player_col_equal = {c: (player_keys_equal and oldpl[c].astype("Int64").equals(newpl[c].astype("Int64"))) for c in pcols}

    # Existing M4 head-head rays are the same geometric segment in reverse. Report
    # empirical symmetry, but do not depend on it for the optimized implementation.
    ready = oldp[oldp["collision_evaluated"].fillna(False)]
    head_symmetry_rate = None
    if len(ready):
        x = ready["t_to_ct_head_static_ray_clear"].astype("boolean")
        y = ready["ct_to_t_head_static_ray_clear"].astype("boolean")
        both = x.notna() & y.notna()
        if both.any():
            head_symmetry_rate = float((x[both] == y[both]).mean())

    return {
        "available": True,
        "old_pair_rows": len(oldp),
        "new_pair_rows": len(newp),
        "pair_keys_equal": pair_keys_equal,
        "collision_boolean_equal": col_equal,
        "player_keys_equal": player_keys_equal,
        "player_aggregate_equal": player_col_equal,
        "head_ray_symmetry_rate_in_prior_m4": head_symmetry_rate,
        "equal_core": pair_keys_equal and player_keys_equal and all(col_equal.values()) and all(player_col_equal.values()),
        "fractions_intentionally_not_compared": True,
    }


def process_demo(cdir: Path, registry: dict, output_root: Path, checker_cache: dict, nav_cache: dict, rounds_n: int, step_ticks: int, prior_m4_root: Path) -> dict:
    t0 = time.perf_counter()
    cm = read_json(cdir / "manifest.json")
    demo_id = str(cm.get("demo_id") or cdir.name)
    dataset = str(cm.get("dataset") or "unknown")
    map_name = str(cm.get("map_name") or "unknown")
    profile = profile_for_dataset(dataset)
    key = f"{profile}::{map_name}"
    entry = (registry.get("profiles") or {}).get(key)
    res = {"demo_id": demo_id, "dataset": dataset, "map_name": map_name, "profile": profile, "registry_key": key, "success": False, "errors": [], "warnings": [], "timings": {}}
    out = output_root / "spatial" / demo_id
    tmp = output_root / "spatial" / f".{demo_id}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        p = time.perf_counter()
        ps = pq.read_table(cdir / "player_state.parquet").to_pandas()
        rs = pq.read_table(cdir / "round_state.parquet").to_pandas()
        ui = pq.read_table(cdir / "utility_intervals.parquet").to_pandas()
        res["timings"]["read_canonical_s"] = time.perf_counter() - p
        ticks, bounds = choose_ticks(ps, rs, cm, rounds_n, step_ticks)
        ps = ps[ps["tick"].isin(ticks)].copy()
        ps = ps[ps["is_alive"].fillna(False)].copy()

        tri = None
        checker = None
        locator = None
        if entry is None:
            collision_status = "registry_missing"
            nav_status = "registry_missing"
        else:
            tri = resolve_existing_path(entry.get("tri_path"))
            navp = resolve_existing_path(entry.get("nav_path"))
            if entry.get("known_quarantine") or (entry.get("exposure_ready") is False):
                collision_status = "quarantined" if entry.get("known_quarantine") else ("deferred" if entry.get("known_deferred") else "not_ready")
            elif tri is None or not tri.exists():
                collision_status = "asset_missing"
            else:
                collision_status = "ready"
                ckey = str(tri)
                if ckey not in checker_cache:
                    checker_cache[ckey] = CachedVisibility(VisibilityChecker(path=tri))
                checker = checker_cache[ckey]
            if entry.get("nav_backend_ready") and navp is not None and navp.exists():
                try:
                    nkey = str(navp)
                    if nkey not in nav_cache:
                        nav_cache[nkey] = Nav.from_path(navp)
                    locator = NavLocator(nav_cache[nkey])
                    nav_status = "ready"
                except Exception as exc:
                    nav_status = f"load_error:{type(exc).__name__}"
                    locator = None
            else:
                nav_status = "backend_unavailable" if entry.get("nav_backend_ready") is False else "asset_missing"

        p = time.perf_counter()
        player_rows = []
        pair_rows = []
        ray_count = 0
        collision_pairs = 0
        nav_assigned = 0
        nav_fallback = 0
        smoke_known_tick_count = 0
        smoke_unknown_tick_count = 0
        for tick, g in ps.groupby("tick", sort=True):
            tick = int(tick)
            players = []
            for _, r in g.iterrows():
                x, y, z = safe_float(r.get("X")), safe_float(r.get("Y")), safe_float(r.get("Z"))
                sid = str(r.get("steamid")) if not pd.isna(r.get("steamid")) else None
                side = side_value(r.get("side"))
                rd = safe_int(r.get("round"))
                if sid is None or side not in {"T", "CT"} or None in (x, y, z):
                    continue
                nav_id = nav_dist = None
                nav_mode = nav_status
                if locator is not None:
                    nav_id, nav_mode, nav_dist = locator.locate((x, y, z))
                    nav_assigned += 1
                    if nav_mode == "nearest_centroid":
                        nav_fallback += 1
                players.append({"steamid": sid, "side": side, "round": rd, "pos": (x, y, z), "row": r, "nav_id": nav_id, "nav_mode": nav_mode, "nav_dist": nav_dist})
            if not players:
                continue
            rd = next((pp["round"] for pp in players if pp["round"] is not None), None)
            smokes, unknown_smokes = smoke_state_at_tick(ui, tick, rd)
            if smokes:
                smoke_known_tick_count += 1
            if unknown_smokes:
                smoke_unknown_tick_count += 1
            accum = {pp["steamid"]: {"clear": 0, "exposed": 0, "dist": [], "clear_dist": [], "smoke_dist": []} for pp in players}
            ts = [pp for pp in players if pp["side"] == "T"]
            cts = [pp for pp in players if pp["side"] == "CT"]
            for a in ts:
                for b in cts:
                    d = math.dist(a["pos"], b["pos"])
                    accum[a["steamid"]]["dist"].append(d)
                    accum[b["steamid"]]["dist"].append(d)
                    smoke_d = min((point_segment_distance(s, a["pos"], b["pos"]) for s in smokes), default=None)
                    if smoke_d is not None:
                        accum[a["steamid"]]["smoke_dist"].append(smoke_d)
                        accum[b["steamid"]]["smoke_dist"].append(smoke_d)
                    ab = ba = None
                    if checker is not None:
                        ab = static_any_shortcircuit(checker, a["pos"], b["pos"])
                        ba = static_any_shortcircuit(checker, b["pos"], a["pos"])
                        collision_pairs += 1
                        ray_count += ab["rays"] + ba["rays"]
                        if ab["any"]:
                            accum[a["steamid"]]["clear"] += 1
                            accum[a["steamid"]]["clear_dist"].append(d)
                            accum[b["steamid"]]["exposed"] += 1
                        if ba["any"]:
                            accum[b["steamid"]]["clear"] += 1
                            accum[b["steamid"]]["clear_dist"].append(d)
                            accum[a["steamid"]]["exposed"] += 1
                    pair_rows.append({
                        "demo_id": demo_id, "tick": tick, "round": rd, "t_steamid": a["steamid"], "ct_steamid": b["steamid"], "distance_units": d,
                        "collision_evaluated": checker is not None, "collision_status": collision_status,
                        "t_to_ct_any_static_ray_clear": None if ab is None else ab["any"], "t_to_ct_static_clear_fraction": None, "t_to_ct_head_static_ray_clear": None if ab is None else ab["head"],
                        "ct_to_t_any_static_ray_clear": None if ba is None else ba["any"], "ct_to_t_static_clear_fraction": None, "ct_to_t_head_static_ray_clear": None if ba is None else ba["head"],
                        "nearest_known_active_smoke_segment_distance": smoke_d, "known_active_smoke_count": len(smokes), "unknown_end_smoke_count": unknown_smokes,
                        "dynamic_world_uncertainty": True,
                        "truth_class": "deterministic_static_geometry_relation_fast_any" if checker is not None else "spatial_relation_unavailable",
                    })
            for p0 in players:
                a = accum[p0["steamid"]]
                r = p0["row"]
                player_rows.append({
                    "demo_id": demo_id, "tick": tick, "round": p0["round"], "steamid": p0["steamid"], "side": p0["side"], "x": p0["pos"][0], "y": p0["pos"][1], "z": p0["pos"][2],
                    "place_name_literal": None if pd.isna(r.get("last_place_name")) else str(r.get("last_place_name")), "nav_area_id": p0["nav_id"], "nav_assignment_mode": p0["nav_mode"], "nav_assignment_distance": p0["nav_dist"],
                    "static_collision_status": collision_status, "static_clear_enemy_count": a["clear"] if checker is not None else None, "static_exposed_to_enemy_count": a["exposed"] if checker is not None else None,
                    "nearest_enemy_distance": min(a["dist"]) if a["dist"] else None, "nearest_static_clear_enemy_distance": min(a["clear_dist"]) if a["clear_dist"] else None,
                    "nearest_known_active_smoke_segment_distance": min(a["smoke_dist"]) if a["smoke_dist"] else None, "known_active_smoke_count": len(smokes), "unknown_end_smoke_count": unknown_smokes, "dynamic_world_uncertainty": True,
                })
        res["timings"]["spatial_compute_s"] = time.perf_counter() - p

        p = time.perf_counter()
        outputs = {}
        outputs["player_spatial_samples"] = write_rows(player_rows, PLAYER_SPATIAL_SCHEMA, tmp / "player_spatial_samples.parquet")
        outputs["pair_spatial_relations"] = write_rows(pair_rows, PAIR_SCHEMA, tmp / "pair_spatial_relations.parquet")
        cache_info = checker.cache_info() if checker is not None else None
        manifest = {
            "m41_version": M41_VERSION, "spatial_schema_version": SPATIAL_SCHEMA_VERSION, "demo_id": demo_id, "map_name": map_name, "dataset": dataset,
            "source_family": cm.get("source_family"), "segmented_hint": bool(cm.get("segmented_hint")),
            "source_canonical": {"path": str(cdir), "canonical_schema_version": cm.get("canonical_schema_version")},
            "geometry_profile": {"profile": profile, "registry_key": key, "registry_entry": entry, "resolved_tri_path": str(tri) if tri else None, "collision_status": collision_status, "nav_status": nav_status},
            "sampling": {"rounds_requested": rounds_n, "round_bounds": bounds, "grid_step_ticks": step_ticks, "sample_tick_count": len(ticks), "policy": "same M4 first-live-rounds grid plus combat/objective/smoke event ticks"},
            "model_semantics": {
                "static_collision": "Exact M4 any-static-ray-clear and head-ray semantics over the same 12 unique standing probes, but short-circuited after the first clear ray. Full clear fraction is intentionally not computed on the routine fast path.",
                "fraction": "M4 12-point static_clear_fraction is deep evidence only. Fast-path fraction columns are null by design, not zero.",
                "ray_cache": "Bounded exact-coordinate memoization only; no spatial quantization or approximation.",
                "smoke": "Same M4 deterministic distance-to-known-active-smoke-center relation; no smoke occlusion boolean.",
                "dynamic_world": "Same M4 explicit uncertainty for doors, breakables, players, dropped items and other dynamic props.",
                "nav": "Same versioned registry policy as M4; last_place_name remains separate literal parser evidence.",
            },
            "counts": {"player_rows": len(player_rows), "pair_rows": len(pair_rows), "collision_pair_evaluations": collision_pairs, "visibility_rays_executed": ray_count, "nav_assignments": nav_assigned, "nav_nearest_centroid_fallbacks": nav_fallback, "ticks_with_known_active_smoke": smoke_known_tick_count, "ticks_with_unpaired_smoke_uncertainty": smoke_unknown_tick_count},
            "ray_cache": cache_info, "outputs": outputs, "awpy_used_for_spatial_only": True, "demo_reparsed": False, "coaching_generated": False, "candidate_detection": False,
        }
        write_json(manifest, tmp / "manifest.json")
        res["timings"]["write_s"] = time.perf_counter() - p

        pair_gate = len(pair_rows) > 0 and len(player_rows) > 0
        collision_gate = (collision_pairs > 0) if collision_status == "ready" else (collision_pairs == 0)
        nav_gate = (nav_assigned > 0) if nav_status == "ready" else True
        res["gates"] = {"rows_nonzero": pair_gate, "collision_policy_respected": collision_gate, "nav_policy_respected": nav_gate}
        if not all(res["gates"].values()):
            raise RuntimeError(f"M4.1 gates failed: {res['gates']}")
        if out.exists():
            shutil.rmtree(out)
        tmp.replace(out)
        comparison = compare_with_m4(demo_id, out / "pair_spatial_relations.parquet", out / "player_spatial_samples.parquet", prior_m4_root)
        res.update({"success": True, "collision_status": collision_status, "nav_status": nav_status, "sample_tick_count": len(ticks), "round_bounds": bounds, "counts": manifest["counts"], "ray_cache": cache_info, "comparison_to_m4": comparison, "output_dir": str(out)})
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
    ap.add_argument("--registry", required=True)
    ap.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    ap.add_argument("--grid-step-ticks", type=int, default=DEFAULT_GRID_STEP_TICKS)
    args = ap.parse_args()

    started = time.perf_counter()
    output = Path(args.output_folder)
    output.mkdir(parents=True, exist_ok=True)
    parent = output.resolve().parent
    prior_m4_root = parent / "Stage3_M4"
    prior_report_path = prior_m4_root / "M4_report.json"
    prior_report = read_json(prior_report_path) if prior_report_path.exists() else {}
    prior_by_demo = {r.get("demo_id"): r for r in prior_report.get("results", [])}

    registry = read_json(Path(args.registry))
    cdirs = discover_canonical(output)
    report = {
        "m41_version": M41_VERSION, "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
        "generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S"), "input_folder": args.input_folder, "output_folder": str(output),
        "registry": str(Path(args.registry).resolve()), "prior_m4_root": str(prior_m4_root), "discovered_canonical_demos": len(cdirs), "selected_count": len(cdirs), "results": [],
    }
    checker_cache = {}
    nav_cache = {}
    for cdir in cdirs:
        r = process_demo(cdir, registry, output, checker_cache, nav_cache, args.rounds, args.grid_step_ticks, prior_m4_root)
        old = prior_by_demo.get(r.get("demo_id")) or {}
        if old:
            old_s = safe_float((old.get("timings") or {}).get("spatial_compute_s"))
            new_s = safe_float((r.get("timings") or {}).get("spatial_compute_s"))
            old_rays = safe_int((old.get("counts") or {}).get("estimated_visibility_rays"))
            new_rays = safe_int((r.get("counts") or {}).get("visibility_rays_executed"))
            r["performance_vs_m4"] = {
                "old_spatial_compute_s": old_s, "new_spatial_compute_s": new_s,
                "compute_speedup_x": (old_s / new_s) if old_s and new_s and new_s > 0 else None,
                "old_visibility_rays": old_rays, "new_visibility_rays": new_rays,
                "ray_reduction_x": (old_rays / new_rays) if old_rays and new_rays and new_rays > 0 else None,
            }
        report["results"].append(r)

    success = [r for r in report["results"] if r.get("success")]
    fail = [r for r in report["results"] if not r.get("success")]
    report["success_count"] = len(success)
    report["failure_count"] = len(fail)
    report["segmented_source_included"] = any(read_json(Path(r["output_dir"]) / "manifest.json").get("segmented_hint") for r in success if r.get("output_dir"))
    report["total_collision_pair_evaluations"] = sum((r.get("counts") or {}).get("collision_pair_evaluations", 0) for r in success)
    report["total_visibility_rays_executed"] = sum((r.get("counts") or {}).get("visibility_rays_executed", 0) for r in success)
    report["prior_m4_total_visibility_rays"] = safe_int(prior_report.get("total_visibility_rays"))
    comparisons = [r.get("comparison_to_m4") or {} for r in success]
    report["core_equivalence_count"] = sum(bool(c.get("equal_core")) for c in comparisons)
    speedups = [safe_float((r.get("performance_vs_m4") or {}).get("compute_speedup_x")) for r in success]
    speedups = [x for x in speedups if x is not None]
    ray_red = [safe_float((r.get("performance_vs_m4") or {}).get("ray_reduction_x")) for r in success]
    ray_red = [x for x in ray_red if x is not None]
    report["median_compute_speedup_x"] = float(pd.Series(speedups).median()) if speedups else None
    report["median_ray_reduction_x"] = float(pd.Series(ray_red).median()) if ray_red else None
    report["wall_seconds"] = time.perf_counter() - started

    equivalence_gate = len(success) == len(cdirs) and len(cdirs) >= 6 and report["core_equivalence_count"] == len(success)
    performance_gate = report["median_compute_speedup_x"] is not None and report["median_compute_speedup_x"] >= 1.5
    pass_gate = equivalence_gate and performance_gate and report["segmented_source_included"] and report["total_collision_pair_evaluations"] > 0
    report["gates"] = {
        "all_demos_success": len(fail) == 0 and len(cdirs) >= 6,
        "core_any_head_player_aggregates_arrow_semantically_equal_to_m4": equivalence_gate,
        "median_collision_compute_speedup_at_least_1_5x": performance_gate,
        "segmented_source_included": report["segmented_source_included"],
    }
    if pass_gate:
        report["decision"] = "M41_PASS: exact M4 any-clear/head-clear semantics preserved while removing routine full-fraction work. Promote fast spatial core; keep 12-point fraction as deep evidence. Proceed to M5 deterministic relationships/state transitions."
        report["next_stage"] = "M5 deterministic relationships and neutral state transitions over canonical state plus M4.1 fast spatial core; no coaching semantics."
    else:
        report["decision"] = "M41_FAIL: do not promote the spatial fast path until exact core equivalence and performance gates pass."
        report["next_stage"] = "Repair/retune M4.1 only; retain passing M4 outputs and do not rerun upstream decode/canonical stages."
    write_json(report, output / "M41_report.json")
    print(json.dumps({"decision": report["decision"], "success": f"{len(success)}/{len(cdirs)}", "wall_seconds": report["wall_seconds"], "core_equivalence": f"{report['core_equivalence_count']}/{len(success)}", "median_compute_speedup_x": report["median_compute_speedup_x"], "median_ray_reduction_x": report["median_ray_reduction_x"]}, indent=2))
    return 0 if pass_gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
