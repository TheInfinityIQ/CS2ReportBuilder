"""Data-fix script for already-extracted v7.x output. Additive, verified, reversible.

Repair ``effective_damage_v1`` (extractor <= v7.7, see KNOWN_PITFALLS 27):
- ``events/player_hurt.csv.gz`` gains ``dmg_health_effective`` and ``same_tick_multi_hurt``.
  Every existing column is left byte-for-byte as it was, including the legacy
  ``dmg_health_capped``.
- ``coaching/utility_effectiveness.csv``: the HE/fire damage cells are recomputed from the
  effective damage. Only cells whose value actually changes are rewritten.

Safety rules (do not patch data that is not broken):
1. Preconditions. The file must contain the columns the fix needs, and the legacy column
   must equal ``user_health - health`` clipped at zero on every row. If not, the file does
   not have the semantics this fix assumes: SKIP, never guess.
2. The utility table is only touched if recomputing it with the LEGACY damage reproduces the
   stored table exactly. That proves our aggregation is the extractor's; otherwise SKIP.
3. Dry run by default. ``apply=True`` writes, and first copies originals to
   ``_repair_backup/``. A ``repairs.json`` manifest records hashes, counts and totals.
4. Idempotent. A demo already carrying a matching ``dmg_health_effective`` is reported as
   already repaired and left alone. v7.8+ output is never touched.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .damage import effective_damage

REPAIR_ID = "effective_damage_v1"
UTIL_DAMAGE_COLS = [
    "he_damage_all", "fire_damage_all", "he_enemy_damage", "fire_enemy_damage",
    "team_utility_damage", "self_utility_damage", "unknown_relation_utility_damage",
    "enemy_utility_damage", "utility_damage_all",
]
NEEDED = {"tick", "user_steamid", "attacker_steamid", "user_health", "health", "dmg_health_capped"}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.replace("", np.nan), errors="coerce")


def _fmt(v: float) -> str:
    return repr(float(v))


def utility_damage(h: pd.DataFrame, dmg: pd.Series) -> pd.DataFrame:
    """Same aggregation as the extractor's build_utility_effectiveness (damage part only)."""
    a = _num(h["attacker_steamid"])
    v = _num(h["user_steamid"])
    rnd = _num(h["total_rounds_played"])
    wpn = h["weapon"].fillna("").astype(str).str.casefold()
    he = wpn.str.contains("hegrenade")
    fire = wpn.str.contains("inferno|molotov|incgrenade")
    keep = a.notna() & rnd.notna() & (he | fire)
    at, vt = h["attacker_team_name"].replace("", np.nan), h["user_team_name"].replace("", np.nan)
    rel = np.where(a == v, "self",
                   np.where(at.notna() & vt.notna(),
                            np.where(at.astype(str) == vt.astype(str), "team", "enemy"), "unknown"))
    d = dmg.fillna(0.0)
    f = pd.DataFrame({
        "steamid": a, "parser_round": rnd,
        "he_damage_all": d * he, "fire_damage_all": d * fire,
        "he_enemy_damage": d * (he & (rel == "enemy")), "fire_enemy_damage": d * (fire & (rel == "enemy")),
        "team_utility_damage": d * (rel == "team"), "self_utility_damage": d * (rel == "self"),
        "unknown_relation_utility_damage": d * (rel == "unknown"),
    })[keep]
    out = f.groupby(["steamid", "parser_round"]).sum()
    out["enemy_utility_damage"] = out.he_enemy_damage + out.fire_enemy_damage
    out["utility_damage_all"] = out.he_damage_all + out.fire_damage_all
    out.index = out.index.set_levels([out.index.levels[0].astype("int64"), out.index.levels[1].astype("int64")])
    return out


def _write_gz_csv(df: pd.DataFrame, path: Path) -> None:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    import gzip
    with gzip.open(tmp, "wt", encoding="utf-8", newline="") as fh:
        fh.write(buf.getvalue())
    tmp.replace(path)


def repair_demo(demo_dir: Path, *, apply: bool = False) -> dict:
    demo_dir = Path(demo_dir)
    hp = demo_dir / "events" / "player_hurt.csv.gz"
    up = demo_dir / "coaching" / "utility_effectiveness.csv"
    res: dict = {"demo_id": demo_dir.name, "repair": REPAIR_ID, "status": None, "notes": []}
    ms = demo_dir / "match_summary.json"
    if ms.exists():
        ver = str(json.loads(ms.read_text(encoding="utf-8")).get("schema_version", ""))
        res["schema_version"] = ver
        try:
            if tuple(int(x) for x in ver.split(".")) >= (3, 8):
                res["status"] = "not_needed_new_schema"
                return res
        except ValueError:
            pass
    if not hp.exists():
        res["status"] = "skip_no_hurt_file"
        return res

    raw = pd.read_csv(hp, dtype=str, keep_default_na=False)
    if not NEEDED.issubset(raw.columns):
        res["status"] = "skip_missing_columns"
        res["notes"].append(sorted(NEEDED - set(raw.columns)))
        return res
    h = raw.copy()
    for c in ["tick", "user_steamid", "attacker_steamid", "user_health", "health", "dmg_health_capped"]:
        h[c] = _num(raw[c])
    legacy = (h.user_health - h.health).clip(lower=0)
    ok = (legacy - h.dmg_health_capped).abs().le(1e-6) | (legacy.isna() & h.dmg_health_capped.isna())
    if not ok.all():
        res["status"] = "skip_legacy_semantics_differ"
        res["notes"].append(f"{int((~ok).sum())} rows where dmg_health_capped != user_health - health")
        return res

    eff, multi = effective_damage(h)
    changed = (eff - h.dmg_health_capped).abs() > 1e-6
    res.update({
        "hurt_rows": len(h), "same_tick_multi_rows": int(multi.sum()), "rows_changed": int(changed.sum()),
        "legacy_total": float(h.dmg_health_capped.sum()), "effective_total": float(eff.sum()),
    })
    if "dmg_health_effective" in raw.columns:
        prev = _num(raw["dmg_health_effective"])
        same = ((prev - eff).abs().le(1e-6) | (prev.isna() & eff.isna())).all()
        res["status"] = "already_repaired" if same else "conflict_existing_effective_column"
        return res

    # utility table: verify legacy reproduction first
    util_changes: list[tuple[int, str, str, str]] = []
    util_raw = None
    if up.exists() and {"total_rounds_played", "weapon", "attacker_team_name", "user_team_name"}.issubset(raw.columns):
        util_raw = pd.read_csv(up, dtype=str, keep_default_na=False)
        stored = util_raw[["steamid", "parser_round", *UTIL_DAMAGE_COLS]].copy()
        for c in stored.columns:
            stored[c] = _num(stored[c])
        stored = stored.set_index(["steamid", "parser_round"])
        stored.index = stored.index.set_levels([stored.index.levels[0].astype("int64"), stored.index.levels[1].astype("int64")])
        hh = h.copy()
        for c in ["total_rounds_played"]:
            hh[c] = _num(raw[c])
        old = utility_damage(hh, h.dmg_health_capped)
        new = utility_damage(hh, eff)
        cmp = old.reindex(stored.index).fillna(0.0)
        unexplained = old.index.difference(stored.index)
        extra = old.loc[unexplained].abs().sum().sum() if len(unexplained) else 0.0
        if (cmp - stored[UTIL_DAMAGE_COLS]).abs().max().max() > 1e-6 or extra > 1e-6:
            res["notes"].append("utility table not reproduced by legacy recompute: left untouched")
            res["utility_status"] = "skip_not_reproduced"
        else:
            newr = new.reindex(stored.index).fillna(0.0)
            pos = {k: i for i, k in enumerate(stored.index)}
            diff = (newr - stored[UTIL_DAMAGE_COLS]).abs() > 1e-6
            for key, row in diff[diff.any(axis=1)].iterrows():
                for c in row.index[row.values]:
                    util_changes.append((pos[key], c, util_raw.at[pos[key], c], _fmt(newr.at[key, c])))
            res["utility_status"] = "verified"
            res["utility_cells_changed"] = len(util_changes)
    else:
        res["utility_status"] = "skip_missing"

    if not changed.any() and not util_changes:
        res["notes"].append("no values change; columns still added so all output has one schema")
    res["status"] = "applied" if apply else "dry_run"
    if not apply:
        return res

    bak = demo_dir / "_repair_backup" / REPAIR_ID
    bak.mkdir(parents=True, exist_ok=True)
    files = {"events/player_hurt.csv.gz": {"before": _sha(hp)}}
    shutil.copy2(hp, bak / hp.name)
    out = raw.copy()
    out["dmg_health_effective"] = [("" if pd.isna(x) else _fmt(x)) for x in eff]
    out["same_tick_multi_hurt"] = np.where(multi, "True", "False")
    _write_gz_csv(out, hp)
    check = pd.read_csv(hp, dtype=str, keep_default_na=False)
    if not check[raw.columns].equals(raw):  # never leave a changed original column behind
        shutil.copy2(bak / hp.name, hp)
        raise RuntimeError(f"{demo_dir.name}: rewrite altered existing columns; original restored")
    files["events/player_hurt.csv.gz"]["after"] = _sha(hp)
    if util_changes:
        files["coaching/utility_effectiveness.csv"] = {"before": _sha(up)}
        shutil.copy2(up, bak / up.name)
        for i, c, _old, new_v in util_changes:
            util_raw.at[i, c] = new_v
        tmp = up.with_suffix(".csv.tmp")
        util_raw.to_csv(tmp, index=False)
        tmp.replace(up)
        files["coaching/utility_effectiveness.csv"]["after"] = _sha(up)
    man = demo_dir / "repairs.json"
    log = json.loads(man.read_text(encoding="utf-8")) if man.exists() else []
    log.append({**res, "files": files, "utility_cells": [
        {"row": i, "column": c, "old": o, "new": n} for i, c, o, n in util_changes],
        "applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    man.write_text(json.dumps(log, indent=2), encoding="utf-8")
    return res


def repair_batch(batch_dir: Path, *, apply: bool = False) -> list[dict]:
    dirs = sorted(d for d in Path(batch_dir).iterdir() if d.is_dir() and (d / "match_summary.json").exists())
    return [repair_demo(d, apply=apply) for d in dirs]
