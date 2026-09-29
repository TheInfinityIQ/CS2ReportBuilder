import ast
import gzip
import json
from pathlib import Path

import pandas as pd
import pytest

from cs2di.damage import effective_damage
from cs2di.repair import UTIL_DAMAGE_COLS, repair_demo, utility_damage

ROOT = Path(__file__).resolve().parents[1]
A, B, V = 76561198000000001, 76561198000000002, 76561198000000009


def hurts(rows):
    cols = ["tick", "attacker_steamid", "user_steamid", "user_health", "health", "weapon",
            "total_rounds_played", "attacker_team_name", "user_team_name"]
    df = pd.DataFrame(rows, columns=cols)
    df["dmg_health_capped"] = (df.user_health - df.health).clip(lower=0)
    return df


def test_same_tick_hits_are_not_double_counted():
    # the audit's example: 100 -> 88 -> 46 on one tick; legacy says 12 + 54 = 66
    h = hurts([[10, A, V, 100, 88, "ak47", 0, "T", "CT"], [10, B, V, 100, 46, "awp", 0, "T", "CT"]])
    eff, multi = effective_damage(h)
    assert eff.tolist() == [12, 42] and multi.all()
    assert h.dmg_health_capped.sum() == 66 and eff.sum() == 54


def test_row_order_does_not_matter_and_single_hits_unchanged():
    h = hurts([[10, B, V, 100, 46, "awp", 0, "T", "CT"], [10, A, V, 100, 88, "ak47", 0, "T", "CT"],
               [20, A, B, 100, 73, "ak47", 0, "T", "CT"], [30, A, V, 20, 0, "ak47", 0, "T", "CT"]])
    eff, multi = effective_damage(h)
    assert eff.tolist() == [42, 12, 27, 20]
    assert multi.tolist() == [True, True, False, False]


def test_unknown_victim_is_never_chained_and_unknown_stays_unknown():
    h = hurts([[10, A, None, 100, 88, "ak47", 0, "T", "CT"], [10, B, None, 100, 46, "ak47", 0, "T", "CT"],
               [11, A, V, None, 50, "ak47", 0, "T", "CT"]])
    eff, multi = effective_damage(h)
    assert eff.iloc[:2].tolist() == [12, 54] and not multi.any()
    assert pd.isna(eff.iloc[2])


def test_extractor_copy_matches_package():
    src = (ROOT / "extractor" / "extract_demos_v7dot8.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "effective_damage")
    ns = {"pd": pd}
    exec(compile(ast.Module([fn], []), "x", "exec"), ns)
    h = hurts([[10, A, V, 100, 88, "ak47", 0, "T", "CT"], [10, B, V, 100, 46, "hegrenade", 0, "T", "CT"],
               [10, A, V, 100, 30, "inferno", 0, "T", "CT"], [12, A, B, 90, 0, "awp", 1, "T", "T"]])
    a, b = effective_damage(h), ns["effective_damage"](h)
    pd.testing.assert_series_equal(a[0], b[0])
    pd.testing.assert_series_equal(a[1], b[1])


def _demo(tmp_path, rows, schema="3.7"):
    d = tmp_path / "demo1"
    (d / "events").mkdir(parents=True)
    (d / "coaching").mkdir()
    (d / "match_summary.json").write_text(json.dumps({"schema_version": schema}))
    h = hurts(rows)
    with gzip.open(d / "events" / "player_hurt.csv.gz", "wt", newline="") as fh:
        h.to_csv(fh, index=False)
    u = utility_damage(h, h.dmg_health_capped).reset_index()
    u.insert(2, "flash_detonations", 0)
    u.to_csv(d / "coaching" / "utility_effectiveness.csv", index=False)
    return d


ROWS = [[10, A, V, 100, 88, "hegrenade", 3, "T", "CT"], [10, B, V, 100, 46, "hegrenade", 3, "T", "CT"],
        [50, A, B, 100, 60, "ak47", 4, "T", "CT"]]


def test_dry_run_writes_nothing(tmp_path):
    d = _demo(tmp_path, ROWS)
    before = {p: p.read_bytes() for p in d.rglob("*") if p.is_file()}
    r = repair_demo(d)
    assert r["status"] == "dry_run" and r["rows_changed"] == 1 and r["utility_cells_changed"] > 0
    assert {p: p.read_bytes() for p in d.rglob("*") if p.is_file()} == before


def test_apply_is_additive_verified_and_idempotent(tmp_path):
    d = _demo(tmp_path, ROWS)
    old = pd.read_csv(d / "events" / "player_hurt.csv.gz", dtype=str, keep_default_na=False)
    assert repair_demo(d, apply=True)["status"] == "applied"
    new = pd.read_csv(d / "events" / "player_hurt.csv.gz", dtype=str, keep_default_na=False)
    pd.testing.assert_frame_equal(new[old.columns], old)  # every original column untouched
    assert pd.to_numeric(new.dmg_health_effective).tolist() == [12, 42, 40]
    u = pd.read_csv(d / "coaching" / "utility_effectiveness.csv")
    row = u[u.steamid == B].iloc[0]
    assert row.he_enemy_damage == 42 and row.enemy_utility_damage == 42
    assert (d / "_repair_backup" / "effective_damage_v1" / "player_hurt.csv.gz").exists()
    assert json.loads((d / "repairs.json").read_text())[0]["rows_changed"] == 1
    assert repair_demo(d, apply=True)["status"] == "already_repaired"
    assert len(json.loads((d / "repairs.json").read_text())) == 1


def test_unexpected_semantics_are_skipped_not_patched(tmp_path):
    d = _demo(tmp_path, ROWS)
    p = d / "events" / "player_hurt.csv.gz"
    df = pd.read_csv(p)
    df.loc[2, "dmg_health_capped"] = 99  # not user_health - health: some other definition
    with gzip.open(p, "wt", newline="") as fh:
        df.to_csv(fh, index=False)
    before = p.read_bytes()
    assert repair_demo(d, apply=True)["status"] == "skip_legacy_semantics_differ"
    assert p.read_bytes() == before


def test_utility_table_left_alone_when_not_reproduced(tmp_path):
    d = _demo(tmp_path, ROWS)
    up = d / "coaching" / "utility_effectiveness.csv"
    u = pd.read_csv(up)
    u.loc[0, UTIL_DAMAGE_COLS[0]] += 5
    u.to_csv(up, index=False)
    before = up.read_bytes()
    r = repair_demo(d, apply=True)
    assert r["utility_status"] == "skip_not_reproduced" and up.read_bytes() == before


@pytest.mark.parametrize("schema", ["3.8", "4.0"])
def test_new_schema_is_never_touched(tmp_path, schema):
    d = _demo(tmp_path, ROWS, schema=schema)
    assert repair_demo(d, apply=True)["status"] == "not_needed_new_schema"
