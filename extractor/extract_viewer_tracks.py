"""
CS2 viewer-tracks sidecar  --  extract_viewer_tracks.py  (v1.1)

WHAT IT DOES
    Adds two thin data sets that the 2D viewer and several coaching measures need but the frozen v7.x
    extractor never wrote.  It is ADDITIVE: it replaces only its additive viewer files, so the
    schema-3.7/3.8 output stays byte-for-byte as it is and nothing needs re-extracting.

    For every demo folder in the analyzed batch it writes, next to rounds.csv:

      viewer_tracks.csv.gz      16 Hz player tracks, live-round windows only, alive players only
      grenade_throws.csv.gz     one row per grenade thrown (who, when, where, aim, landing)
      grenade_paths.csv.gz      the real flight path of each grenade (simplified, bounces kept)
      viewer_tracks_meta.json   provenance + self-checks for that demo
    and once per batch:
      viewer_tracks_batch_summary.json

    Windows are read from the folder's own rounds.csv, exactly as the report viewer reads them:
        start = freeze_end_tick
        end   = min(end_tick + 4 s, next round's start_tick)

REQUIREMENTS   (the same as the extractor)
    Python 3.10+, pandas, numpy, demoparser2.        No other packages.

HOW TO RUN
    1. Edit DEMO_FOLDER below (same convention as extract_demos_v7dot8.py), or pass paths on the command line.
    2. python extract_viewer_tracks.py
       python extract_viewer_tracks.py --demos "D:\\demos\\pugs" --analyzed "D:\\out\\analyzed_pugs"
    3. Send the zip it makes (see --pack).  Typical: python extract_viewer_tracks.py --pack viewer_tracks_pack.zip

    Each demo's analyzed folder must be named after the demo file (that is what the extractor does:
    pug1.dem -> analyzed_<batch>/pug1/).  Demos with no matching folder are skipped and reported.

OPTIONS
    --demos DIR       folder with the .dem files          (default: from the constants below)
    --analyzed DIR    the analyzed_<batch> output folder  (default: from the constants below)
    --hz N            track sample rate, must divide the tick rate (default 16)
    --only STEM       process only this demo (repeatable)
    --limit N         process at most N demos (for a quick trial)
    --force           overwrite existing outputs (default: skip demos already done by this version)
    --no-validate     skip the per-demo interpolation self-check (saves ~2 s per demo)
    --pack ZIP        after running, zip ONLY the new files (tracks, throws, paths, meta, summary)

OUTPUT SCHEMA  (schema 1)
    viewer_tracks.csv.gz
        round, tick, steamid, x, y, z (game units, int), yaw, pitch (degrees, 1 decimal), flags (int)
        yaw: 0 = +X (east), counter-clockwise, range -180..180.   pitch: + = looking down.
        flags bits: 1 scoped, 2 walking (shift), 4 crouched (duck_amount >= 0.5), 8 airborne,
                    16 defusing, 32 reloading.
        Interpolate linearly between rows; interpolate yaw circularly (unwrap first).
    grenade_throws.csv.gz
        round, throw_id, steamid, name, kind (smoke/he/flash/fire/decoy), throw_tick, det_tick (blank if it
        never detonated), detonated (0/1), flight_s, throw_x/y/z + aim_yaw/aim_pitch (the thrower, from the
        weapon_fire event), release_x/y/z (first projectile position), land_x/y/z, n_points
    grenade_paths.csv.gz
        throw_id, tick, x, y, z     (time-aware simplified polyline: linear interpolation by tick stays within
        PATH_TOLERANCE units of the recorded path, and bounces are kept)
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
import time
import traceback
import zipfile
from pathlib import Path
try:
    from cs2di.demo_layout import collection_dir, data_root, demo_files
except ImportError:
    from demo_layout import collection_dir, data_root, demo_files

import numpy as np
import pandas as pd
from demoparser2 import DemoParser

SCRIPT_VERSION = "1.1"
SCHEMA = 1

# ============================================================
# CONFIGURATION  (same convention as extract_demos_v7dot8.py)
# ============================================================
PROJECT_ROOT = data_root()

DEMO_FOLDER = "iTrilogy"
DEMO_DIR = collection_dir(DEMO_FOLDER)
ANALYZED_DIR = PROJECT_ROOT / "02_Analysis" / f"analyzed_{DEMO_FOLDER}"

SAMPLE_HZ = 16
POST_ROUND_S = 4.0            # keep this many seconds after the round-end tick (matches the viewer)
PATH_TOLERANCE = 12.0         # game units; grenade path simplification error bound
UNDETONATED_MAX_S = 10.0      # cap the path of a grenade that never detonated
THROW_FIRE_LEAD_TICKS = 24    # weapon_fire is logged ~7-14 ticks before the projectile appears
NEW_FILES = ("viewer_tracks.csv.gz", "grenade_throws.csv.gz", "grenade_paths.csv.gz", "viewer_tracks_meta.json")

CORE_PROPS = ["X", "Y", "Z", "yaw", "pitch", "is_alive", "steamid"]
FLAG_PROPS = [("is_scoped", 1), ("is_walking", 2), ("duck_amount", 4), ("is_airborne", 8),
              ("is_defusing", 16), ("is_in_reload", 32)]

KIND_OF_TYPE = {"CSmokeGrenadeProjectile": "smoke", "CHEGrenadeProjectile": "he", "CFlashbangProjectile": "flash",
                "CMolotovProjectile": "fire", "CIncendiaryGrenadeProjectile": "fire", "CDecoyProjectile": "decoy"}
DET_EVENT = {"smoke": "smokegrenade_detonate", "he": "hegrenade_detonate", "flash": "flashbang_detonate",
             "decoy": "decoy_detonate"}
FIRE_EVENT = "inferno_startburn"
FIRE_WEAPON = {"smoke": {"weapon_smokegrenade"}, "he": {"weapon_hegrenade"}, "flash": {"weapon_flashbang"},
               "fire": {"weapon_molotov", "weapon_incgrenade"}, "decoy": {"weapon_decoy"}}


# ============================================================
# small helpers
# ============================================================
def log(msg: str) -> None:
    print(msg, flush=True)


def as_frame(x) -> pd.DataFrame:
    """demoparser2 returns [] (a list) when an event never occurs in the demo."""
    return x if isinstance(x, pd.DataFrame) else pd.DataFrame()


def num(series: pd.Series) -> pd.Series:
    """SteamIDs and ticks can arrive as strings (pandas 3) or unsigned ints; make them plain numbers."""
    return pd.to_numeric(series, errors="coerce")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(obj, path: Path) -> None:
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def write_csv_gz(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, compression="gzip", encoding="utf-8")


# ============================================================
# round windows
# ============================================================
def load_windows(folder: Path, tickrate: int) -> pd.DataFrame:
    """Live-round windows [lo, hi] per round, identical to how the report viewer defines them."""
    r = pd.read_csv(folder / "rounds.csv").sort_values("round").reset_index(drop=True)
    for c in ("start_tick", "freeze_end_tick", "end_tick"):
        r[c] = num(r[c])
    r = r.dropna(subset=["freeze_end_tick", "end_tick"]).reset_index(drop=True)
    nxt = r["start_tick"].shift(-1)
    hi = r["end_tick"] + POST_ROUND_S * tickrate
    hi = np.where(nxt.notna(), np.minimum(hi, nxt), hi)
    w = pd.DataFrame({"round": r["round"].astype(int), "lo": r["freeze_end_tick"].astype("int64"),
                      "hi": pd.Series(hi).astype("int64")})
    return w[w.hi > w.lo].reset_index(drop=True)


def window_of(ticks: np.ndarray, windows: pd.DataFrame):
    """Round number for each tick (0 when the tick is outside every window)."""
    lo, hi, rd = windows.lo.to_numpy(), windows.hi.to_numpy(), windows["round"].to_numpy()
    idx = np.clip(np.searchsorted(lo, ticks, side="right") - 1, 0, len(lo) - 1)
    ok = (ticks >= lo[idx]) & (ticks <= hi[idx])
    return np.where(ok, rd[idx], 0)


def pairing_check(parser: DemoParser, windows: pd.DataFrame) -> dict:
    """Does this .dem belong to this analyzed folder?  Compare round freeze-end ticks."""
    ev = as_frame(parser.parse_event("round_freeze_end"))
    if ev.empty:
        return {"checked": False, "reason": "no round_freeze_end events in demo"}
    demo_ticks = set(int(t) for t in ev.tick)
    hit = sum(int(t) in demo_ticks for t in windows.lo)
    return {"checked": True, "rounds_in_folder": int(len(windows)), "freeze_end_ticks_found_in_demo": int(hit),
            "fraction": round(hit / max(1, len(windows)), 3)}


# ============================================================
# player tracks
# ============================================================
def resolve_optional_props(parser: DemoParser, probe_tick: int) -> tuple[list, list]:
    ok, missing = [], []
    for prop, _ in FLAG_PROPS:
        try:
            parser.parse_ticks([prop, "steamid"], ticks=[probe_tick])
            ok.append(prop)
        except Exception:
            missing.append(prop)
    return ok, missing


def build_tracks(parser: DemoParser, windows: pd.DataFrame, step: int, meta: dict) -> pd.DataFrame:
    ticks = set()
    for lo, hi in zip(windows.lo, windows.hi):
        ticks.update(range(int(lo), int(hi) + 1, step))
        ticks.add(int(hi))
    ticks = sorted(ticks)
    opt_ok, opt_missing = resolve_optional_props(parser, int(windows.lo.iloc[0]))
    meta["props_core"] = CORE_PROPS
    meta["props_flags_resolved"] = opt_ok
    meta["props_flags_missing"] = opt_missing
    df = parser.parse_ticks(CORE_PROPS + opt_ok, ticks=ticks)
    if df is None or len(df) == 0:
        raise RuntimeError("parse_ticks returned no rows")
    df = df[df["is_alive"].eq(True) & df["X"].notna() & df["yaw"].notna()].copy()
    tick = num(df["tick"]).to_numpy().astype("int64")
    rnd = window_of(tick, windows)
    flags = np.zeros(len(df), dtype="int64")
    for prop, bit in FLAG_PROPS:
        if prop not in opt_ok:
            continue
        col = df[prop]
        on = (num(col).fillna(0) >= 0.5) if prop == "duck_amount" else col.eq(True)
        flags |= np.where(on.to_numpy(), bit, 0)
    out = pd.DataFrame({
        "round": rnd, "tick": tick, "steamid": num(df["steamid"]).astype("int64").to_numpy(),
        "x": np.rint(df["X"].astype(float)).astype("int64").to_numpy(),
        "y": np.rint(df["Y"].astype(float)).astype("int64").to_numpy(),
        "z": np.rint(df["Z"].astype(float)).astype("int64").to_numpy(),
        "yaw": df["yaw"].astype(float).round(1).to_numpy(),
        "pitch": df["pitch"].astype(float).round(1).to_numpy(),
        "flags": flags})
    out = out[out["round"] > 0].sort_values(["round", "tick", "steamid"]).reset_index(drop=True)
    return out


def validate_tracks(parser: DemoParser, tracks: pd.DataFrame, windows: pd.DataFrame) -> dict:
    """Re-read one round at full rate and measure how far the interpolated sampled table is from the truth."""
    if tracks.empty:
        return {"ok": False, "reason": "no tracks"}
    w = windows.iloc[len(windows) // 2]
    lo, hi = int(w.lo), int(min(w.hi, w.lo + 40 * 64))
    truth = parser.parse_ticks(["X", "Y", "yaw", "is_alive", "steamid"], ticks=list(range(lo, hi + 1)))
    truth = truth[truth["is_alive"].eq(True)].copy()
    truth["steamid"] = num(truth["steamid"]).astype("int64")
    samp = tracks[tracks["round"] == int(w["round"])]
    ey, ep = [], []
    for sid, g in truth.groupby("steamid"):
        s = samp[samp.steamid == sid].sort_values("tick")
        if len(s) < 3:
            continue
        g = g.sort_values("tick")
        t = g["tick"].to_numpy(dtype=float)
        st = s["tick"].to_numpy(dtype=float)
        m = (t >= st[0]) & (t <= st[-1])
        if not m.any():
            continue
        yaw_i = np.degrees(np.interp(t, st, np.unwrap(np.radians(s["yaw"].to_numpy()))))
        d = ((yaw_i - g["yaw"].to_numpy(dtype=float) + 180) % 360) - 180
        ey.append(np.abs(d[m]))
        dx = np.interp(t, st, s["x"].to_numpy(dtype=float)) - g["X"].to_numpy(dtype=float)
        dy = np.interp(t, st, s["y"].to_numpy(dtype=float)) - g["Y"].to_numpy(dtype=float)
        ep.append(np.hypot(dx, dy)[m])
    if not ey:
        return {"ok": False, "reason": "no comparable players"}
    ey, ep = np.concatenate(ey), np.concatenate(ep)
    q = lambda a, p: round(float(np.percentile(a, p)), 2)  # noqa: E731
    return {"ok": True, "round": int(w["round"]), "compared_points": int(len(ey)),
            "yaw_err_deg": {"p50": q(ey, 50), "p90": q(ey, 90), "p99": q(ey, 99)},
            "pos_err_units": {"p50": q(ep, 50), "p99": q(ep, 99)}}


# ============================================================
# grenades
# ============================================================
def simplify(ticks: np.ndarray, xyz: np.ndarray, eps: float) -> list[int]:
    """Time-aware Douglas-Peucker: keep a point if linear interpolation BY TICK misses it by more than eps."""
    n = len(ticks)
    if n <= 2:
        return list(range(n))
    keep, stack = {0, n - 1}, [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j - i < 2:
            continue
        f = (ticks[i + 1:j] - ticks[i]) / float(ticks[j] - ticks[i])
        d = np.linalg.norm(xyz[i + 1:j] - (xyz[i] + (xyz[j] - xyz[i]) * f[:, None]), axis=1)
        k = int(d.argmax())
        if d[k] > eps:
            m = i + 1 + k
            keep.add(m)
            stack += [(i, m), (m, j)]
    return sorted(keep)


def build_grenades(parser: DemoParser, windows: pd.DataFrame, tickrate: int, meta: dict):
    g = as_frame(parser.parse_grenades())
    need = {"grenade_type", "grenade_entity_id", "tick", "x", "y", "z", "steamid"}
    if g.empty or not need.issubset(g.columns):
        meta["grenade_note"] = "parse_grenades returned nothing usable"
        return pd.DataFrame(), pd.DataFrame()
    g = g[g["grenade_type"].astype(str).str.endswith("Projectile") & g["x"].notna()].copy()
    unknown = sorted(set(g["grenade_type"].astype(str)) - set(KIND_OF_TYPE))
    if unknown:
        meta.setdefault("warnings", []).append(f"unknown projectile types skipped: {unknown}")
    g = g[g["grenade_type"].astype(str).isin(KIND_OF_TYPE)].copy()
    g["tick"] = num(g["tick"]).astype("int64")
    g["steamid"] = num(g["steamid"]).fillna(0).astype("int64")
    g = g.sort_values(["grenade_entity_id", "grenade_type", "tick"]).drop_duplicates(
        ["grenade_entity_id", "grenade_type", "tick"]).reset_index(drop=True)
    # entity ids are recycled inside a demo: a new throw starts wherever the same id has a tick gap > 2
    gap = g.groupby(["grenade_entity_id", "grenade_type"])["tick"].diff()
    new = (gap.isna() | (gap > 2)).astype(int)
    g["run"] = new.groupby([g["grenade_entity_id"], g["grenade_type"]]).cumsum()

    det = {k: as_frame(parser.parse_event(v, player=["steamid"])) for k, v in DET_EVENT.items()}
    for d in det.values():
        if not d.empty:
            d["tick"] = num(d["tick"]).astype("int64")
            d["user_steamid"] = num(d["user_steamid"]).fillna(0).astype("int64")
    fire = as_frame(parser.parse_event(FIRE_EVENT, player=["steamid"]))
    if not fire.empty:
        fire["tick"] = num(fire["tick"]).astype("int64")
        fire["user_steamid"] = num(fire["user_steamid"]).fillna(0).astype("int64")
    wf = as_frame(parser.parse_event("weapon_fire", player=["X", "Y", "Z", "yaw", "pitch", "steamid"]))
    if not wf.empty:
        wf = wf[wf["weapon"].astype(str).str.contains("grenade|flashbang|molotov|decoy")].copy()
        wf["tick"] = num(wf["tick"]).astype("int64")
        wf["user_steamid"] = num(wf["user_steamid"]).fillna(0).astype("int64")

    throws, paths, end_err, tick_off = [], [], [], []
    stats = {"runs": 0, "outside_windows": 0, "detonated": 0, "fire_forms": 0, "fired_join": 0}
    for (eid, typ, _run), r in g.groupby(["grenade_entity_id", "grenade_type", "run"], sort=False):
        kind = KIND_OF_TYPE[typ]
        stats["runs"] += 1
        t0, t1 = int(r["tick"].iloc[0]), int(r["tick"].iloc[-1])
        rnd = int(window_of(np.array([t0]), windows)[0])
        if rnd == 0:
            stats["outside_windows"] += 1
            continue
        sid = int(r["steamid"].iloc[0])
        name = str(r["name"].iloc[0]) if "name" in r.columns else ""
        det_tick, land = None, None
        if kind in DET_EVENT:
            d = det[kind]
            if not d.empty and "entityid" in d.columns:
                m = d[(num(d["entityid"]) == eid) & (d["tick"] >= t0) & (d["tick"] <= t1 + 2)]
                if len(m):
                    e = m.iloc[0]
                    det_tick, land = int(e["tick"]), (float(e["x"]), float(e["y"]), float(e["z"]))
        elif kind == "fire" and not fire.empty:
            m = fire[(fire["user_steamid"] == sid) & (fire["tick"] >= t1) & (fire["tick"] <= t1 + 3)]
            if len(m):
                e = m.iloc[(m["tick"] - (t1 + 1)).abs().argmin()]
                det_tick, land = int(e["tick"]), (float(e["x"]), float(e["y"]), float(e["z"]))
                stats["fire_forms"] += 1
        if det_tick is not None:
            r = r[r["tick"] <= det_tick]
            stats["detonated"] += 1
        else:
            r = r[r["tick"] <= t0 + int(UNDETONATED_MAX_S * tickrate)]
        if len(r) < 2:
            continue
        tk = r["tick"].to_numpy(dtype=float)
        xyz = r[["x", "y", "z"]].to_numpy(dtype=float)
        keep = simplify(tk, xyz, PATH_TOLERANCE)
        if land is None:
            land = tuple(float(v) for v in xyz[-1])
        else:
            end_err.append(float(np.linalg.norm(np.array(land) - xyz[-1])))
            tick_off.append(int(det_tick - r["tick"].iloc[-1]))
        # who threw it, from where, aiming where (weapon_fire is logged just before the projectile appears)
        thrown = None
        if not wf.empty:
            c = wf[(wf["user_steamid"] == sid) & wf["weapon"].astype(str).isin(FIRE_WEAPON[kind])
                   & (wf["tick"] <= t0) & (wf["tick"] >= t0 - THROW_FIRE_LEAD_TICKS)]
            if len(c):
                thrown = c.iloc[-1]
                stats["fired_join"] += 1
        throw_id = len(throws) + 1
        throws.append({
            "round": rnd, "throw_id": throw_id, "steamid": sid, "name": name, "kind": kind,
            "throw_tick": t0, "det_tick": det_tick if det_tick is not None else "",
            "detonated": int(det_tick is not None), "flight_s": round((int(r["tick"].iloc[-1]) - t0) / tickrate, 2),
            "throw_x": _r(thrown, "user_X"), "throw_y": _r(thrown, "user_Y"), "throw_z": _r(thrown, "user_Z"),
            "aim_yaw": _r(thrown, "user_yaw", 1), "aim_pitch": _r(thrown, "user_pitch", 1),
            "release_x": int(round(xyz[0, 0])), "release_y": int(round(xyz[0, 1])), "release_z": int(round(xyz[0, 2])),
            "land_x": int(round(land[0])), "land_y": int(round(land[1])), "land_z": int(round(land[2])),
            "n_points": len(keep)})
        for i in keep:
            paths.append((throw_id, int(tk[i]), int(round(xyz[i, 0])), int(round(xyz[i, 1])), int(round(xyz[i, 2]))))
    tdf = pd.DataFrame(throws)
    pdf = pd.DataFrame(paths, columns=["throw_id", "tick", "x", "y", "z"])
    stats["throws_written"] = int(len(tdf))
    if len(tdf):
        stats["by_kind"] = tdf["kind"].value_counts().to_dict()
        stats["mean_points_per_throw"] = round(float(tdf["n_points"].mean()), 2)
    if end_err:
        stats["path_end_vs_detonation_units"] = {"median": round(float(np.median(end_err)), 2),
                                                 "max": round(float(np.max(end_err)), 2)}
        stats["detonation_tick_minus_last_path_tick"] = {"median": float(np.median(tick_off)),
                                                         "max_abs": int(np.max(np.abs(tick_off)))}
    meta["grenade_stats"] = stats
    return tdf, pdf


def _r(row, col, nd=0):
    if row is None or col not in row or pd.isna(row[col]):
        return ""
    return int(round(float(row[col]))) if nd == 0 else round(float(row[col]), nd)


# ============================================================
# one demo
# ============================================================
def _process_demo_unlocked(dem: Path, folder: Path, hz: int, validate: bool, force: bool) -> dict:
    t_start = time.time()
    if hz <= 0 or 64 % hz:
        raise ValueError("Sample rate must be a positive divisor of 64")
    source_hash = sha256_of(dem)
    meta_path = folder / "viewer_tracks_meta.json"
    if not force and not (folder / ".viewer_tracks_updating").exists() and meta_path.exists() and all((folder / f).exists() for f in NEW_FILES):
        try:
            previous = json.loads(meta_path.read_text(encoding="utf-8"))
            if (previous.get("script_version") == SCRIPT_VERSION and previous.get("sample_hz") == hz
                    and previous.get("demo_sha256") == source_hash
                    and (not validate or previous.get("interpolation_check", {}).get("ok"))
                    and all(previous.get("sha256_files", {}).get(f) == sha256_of(folder / f)
                            for f in NEW_FILES if f.endswith(".gz"))):
                return {"status": "skipped_done"}
        except Exception:
            pass
    tickrate = 64
    ms = folder / "match_summary.json"
    if ms.exists():
        tickrate = int(json.loads(ms.read_text(encoding="utf-8")).get("tickrate") or 64)
    if tickrate % hz:
        raise ValueError(f"--hz {hz} does not divide the tick rate {tickrate}")
    step = tickrate // hz
    meta = {"script_version": SCRIPT_VERSION, "schema": SCHEMA, "demo_file": dem.name, "demo_bytes": dem.stat().st_size,
            "demo_sha256": source_hash, "tickrate": tickrate, "sample_hz": hz, "step_ticks": step,
            "path_tolerance_units": PATH_TOLERANCE, "python": sys.version.split()[0], "pandas": pd.__version__,
            "demoparser2": importlib.metadata.version("demoparser2"), "warnings": []}
    windows = load_windows(folder, tickrate)
    if windows.empty:
        raise RuntimeError("rounds.csv has no usable rounds")
    meta["rounds_in_windows"] = int(len(windows))
    parser = DemoParser(str(dem))
    pc = pairing_check(parser, windows)
    meta["pairing_check"] = pc
    if pc.get("checked") and pc["fraction"] == 0:
        raise RuntimeError("this .dem does not match the analyzed folder (no round freeze-end tick agrees)")
    if pc.get("checked") and pc["fraction"] < 0.8:
        meta["warnings"].append(f"only {pc['fraction']:.0%} of round freeze-end ticks agree with the demo")
    tracks = build_tracks(parser, windows, step, meta)
    meta["tracks_rows"] = int(len(tracks))
    meta["players_tracked"] = int(tracks["steamid"].nunique())
    if validate:
        try:
            meta["interpolation_check"] = validate_tracks(parser, tracks, windows)
        except Exception as exc:
            meta["interpolation_check"] = {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}
    throws, paths = build_grenades(parser, windows, tickrate, meta)
    if sha256_of(dem) != source_hash:
        raise RuntimeError("Original demo changed during extraction")
    tmp = folder / ".viewer_tracks_tmp"
    tmp.mkdir(exist_ok=True)
    try:
        write_csv_gz(tracks, tmp / "viewer_tracks.csv.gz")
        write_csv_gz(throws if len(throws) else pd.DataFrame(columns=["round", "throw_id"]), tmp / "grenade_throws.csv.gz")
        write_csv_gz(paths if len(paths) else pd.DataFrame(columns=["round", "throw_id", "tick", "x", "y", "z"]), tmp / "grenade_paths.csv.gz")
        meta["bytes"] = {f: (tmp / f).stat().st_size for f in NEW_FILES if f.endswith(".gz")}
        meta["sha256_files"] = {f: sha256_of(tmp / f) for f in NEW_FILES if f.endswith(".gz")}
        meta["elapsed_s"] = round(time.time() - t_start, 1)
        write_json(meta, tmp / "viewer_tracks_meta.json")
        marker = folder / ".viewer_tracks_updating"
        marker.write_text("Publication incomplete until metadata and all tables are replaced", encoding="utf-8")
        for f in NEW_FILES:
            (tmp / f).replace(folder / f)
        marker.unlink()
    finally:
        for f in tmp.glob("*"):
            f.unlink(missing_ok=True)
        tmp.rmdir()
    return {"status": "ok", "meta": meta}


def process_demo(dem: Path, folder: Path, hz: int = SAMPLE_HZ, validate: bool = True, force: bool = False) -> dict:
    try:
        from cs2di.job_lock import exclusive, lock_path
    except ImportError:
        from job_lock import exclusive, lock_path
    with exclusive(lock_path(folder)):
        try:
            from cs2di.game_catalog import notify_output, file_stamp
        except ImportError:
            from game_catalog import notify_output, file_stamp
        source_stamp = file_stamp(dem)
        result = _process_demo_unlocked(dem, folder, hz, validate, force)
        notify_output(folder, dem, owned=True, source_sha=result.get("meta", {}).get("demo_sha256"), source_stamp=source_stamp)
        return result


# ============================================================
# batch
# ============================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Write 16 Hz view-angle tracks and real grenade paths beside an analyzed batch.")
    ap.add_argument("--demos", type=Path, default=DEMO_DIR)
    ap.add_argument("--analyzed", type=Path, default=ANALYZED_DIR)
    ap.add_argument("--hz", type=int, default=SAMPLE_HZ)
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-validate", action="store_true")
    ap.add_argument("--pack", type=Path, default=None)
    a = ap.parse_args(argv)

    if not a.demos.is_dir():
        log(f"ERROR: demo folder not found: {a.demos}")
        return 2
    if not a.analyzed.is_dir():
        log(f"ERROR: analyzed folder not found: {a.analyzed}")
        return 2
    demos = demo_files(a.demos)
    if a.only:
        demos = [d for d in demos if d.stem in set(a.only)]
    if a.limit:
        demos = demos[:a.limit]
    log(f"viewer-tracks v{SCRIPT_VERSION}: {len(demos)} demo(s), {a.hz} Hz, demoparser2 {importlib.metadata.version('demoparser2')}")
    results, t_all = [], time.time()
    for i, dem in enumerate(demos, 1):
        folder = a.analyzed / dem.stem
        rec = {"demo": dem.name, "stem": dem.stem}
        if not (folder / "rounds.csv").exists():
            rec.update(status="no_analyzed_folder",
                       detail=f"expected {folder} with rounds.csv (folder name must equal the demo file name)")
            log(f"[{i}/{len(demos)}] {dem.name}: SKIPPED - {rec['detail']}")
            results.append(rec)
            continue
        try:
            out = process_demo(dem, folder, a.hz, not a.no_validate, a.force)
            rec["status"] = out["status"]
            if out["status"] == "ok":
                m = out["meta"]
                gs = m.get("grenade_stats", {})
                ic = m.get("interpolation_check", {})
                rec.update(tracks_rows=m["tracks_rows"], throws=gs.get("throws_written", 0),
                           detonated=gs.get("detonated", 0), elapsed_s=m["elapsed_s"],
                           yaw_p99=(ic.get("yaw_err_deg") or {}).get("p99"), warnings=m["warnings"],
                           bytes=sum(m["bytes"].values()))
                log(f"[{i}/{len(demos)}] {dem.name}: ok  {m['tracks_rows']:,} track rows, {gs.get('throws_written', 0)} throws "
                    f"({gs.get('detonated', 0)} detonated), {m['elapsed_s']} s, "
                    f"{sum(m['bytes'].values()) / 1024:.0f} KB" + (f"  WARN {m['warnings']}" if m["warnings"] else ""))
            else:
                log(f"[{i}/{len(demos)}] {dem.name}: already done (use --force to redo)")
        except Exception as exc:  # keep going; one bad demo must not stop the batch
            rec.update(status="failed", detail=f"{type(exc).__name__}: {exc}")
            (folder / "viewer_tracks_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            log(f"[{i}/{len(demos)}] {dem.name}: FAILED - {rec['detail']}")
        results.append(rec)

    summary = {"script_version": SCRIPT_VERSION, "schema": SCHEMA, "sample_hz": a.hz, "demos": len(demos),
               "ok": sum(r["status"] == "ok" for r in results), "already_done": sum(r["status"] == "skipped_done" for r in results),
               "failed": sum(r["status"] == "failed" for r in results),
               "no_analyzed_folder": sum(r["status"] == "no_analyzed_folder" for r in results),
               "elapsed_s": round(time.time() - t_all, 1), "results": results}
    write_json(summary, a.analyzed / "viewer_tracks_batch_summary.json")
    log(f"\nDone in {summary['elapsed_s']} s: {summary['ok']} ok, {summary['already_done']} already done, "
        f"{summary['failed']} failed, {summary['no_analyzed_folder']} without an analyzed folder.")
    if a.pack:
        n = 0
        with zipfile.ZipFile(a.pack, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(a.analyzed / "viewer_tracks_batch_summary.json", "viewer_tracks_batch_summary.json")
            for d in sorted(a.analyzed.iterdir()):
                if d.is_dir() and ((d / "viewer_tracks_meta.json").exists() or (d / "viewer_tracks_error.txt").exists()):
                    for f in NEW_FILES + ("viewer_tracks_error.txt",):
                        if (d / f).exists():
                            z.write(d / f, f"{d.name}/{f}")
                            n += 1
        log(f"Packed {n} files -> {a.pack} ({a.pack.stat().st_size / 1e6:.1f} MB). Send this zip back.")
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
