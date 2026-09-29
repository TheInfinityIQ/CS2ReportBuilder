import csv
import json
import pytest


@pytest.fixture
def make_demo(tmp_path):
    def _make(name="demo1", *, valid=True, coaching_valid=True, ok=True, hard=0, errors=(), warnings=(), skip=()):
        d = tmp_path / name
        d.mkdir()
        (d / "match_summary.json").write_text(json.dumps({
            "schema_version": "3.7", "valid": valid, "coaching_valid": coaching_valid,
            "integrity_hard_failure_count": hard, "map_name": "de_dust2", "n_rounds": 23,
            "demo_source_family": "faceit_sourcetv"}))
        (d / "integrity_checks.json").write_text(json.dumps({
            "integrity_ok": ok, "errors": list(errors),
            "warnings": [{"code": c, "detail": ""} for c in warnings]}))
        with (d / "players.csv").open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["steamid", "name", "team_number"])
            w.writerow(["76561198062530225", "CanadianIQ", 3])
        for f in ("rounds.csv", "player_rounds.csv"):
            (d / f).write_text("round\n1\n")
        for f in skip:
            (d / f).unlink()
        return d
    return _make


HERO = 76561198062530225
MATE = 76561198000000002
ENEMY1 = 76561198000000003
ENEMY2 = 76561198000000004


@pytest.fixture
def played_demo(make_demo):
    """A tiny analyzed demo with two rounds of events for HERO (team 2 = T).

    Round 1 (WIN):  HERO opening kill @1300, dies later @1500, and a kill lands AFTER the round-end
                    tick (@2100) that must count as a kill but never as an opening.
    Round 2 (LOSS): HERO is first to die @3400, then trades @3500.
    Expected: 3 kills, 2 deaths, 1 opening kill, 1 opening death, 1 headshot, damage 200 over 2 rounds.
    """
    import gzip

    def _write_gz(path, header, rows):
        path.parent.mkdir(exist_ok=True)
        with gzip.open(path, "wt", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)

    d = make_demo("played")
    ms = json.loads((d / "match_summary.json").read_text())
    ms.update({"tickrate": 64, "n_rounds": 2})
    (d / "match_summary.json").write_text(json.dumps(ms))
    with (d / "players.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["steamid", "name", "team_number"])
        for sid, n, t in [(HERO, "Hero", 2), (MATE, "Mate", 2), (ENEMY1, "Foe1", 3), (ENEMY2, "Foe2", 3)]:
            w.writerow([sid, n, t])
    with (d / "rounds.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["round", "start_tick", "freeze_end_tick", "end_tick", "duration_s", "bomb_plant_tick", "bomb_plant_site"])
        w.writerow([1, 1000, 1200, 2000, 12.5, "", ""])
        w.writerow([2, 3000, 3200, 4000, 12.5, "", ""])
    with (d / "player_rounds.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["round", "steamid", "name", "side", "result"])
        for rnd, res_t, res_ct in [(1, "WIN", "LOSS"), (2, "LOSS", "WIN")]:
            for sid, n, side in [(HERO, "Hero", "TERRORIST"), (MATE, "Mate", "TERRORIST"),
                                 (ENEMY1, "Foe1", "CT"), (ENEMY2, "Foe2", "CT")]:
                w.writerow([rnd, sid, n, side, res_t if side == "TERRORIST" else res_ct])
    death_h = ["tick", "attacker_steamid", "user_steamid", "attacker_team_num", "user_team_num",
               "headshot", "weapon", "attacker_last_place_name", "user_last_place_name"]
    _write_gz(d / "events" / "player_death.csv.gz", death_h, [
        [1300, HERO, ENEMY1, 2, 3, True, "ak47", "TopofMid", "Catwalk"],
        [1500, ENEMY2, HERO, 3, 2, False, "m4a1", "Catwalk", "TopofMid"],
        [2100, HERO, ENEMY2, 2, 3, False, "ak47", "TopofMid", "Catwalk"],
        [3400, ENEMY1, HERO, 3, 2, False, "awp", "LongDoors", "ShortStairs"],
        [3500, HERO, ENEMY2, 2, 3, False, "ak47", "ShortStairs", "LongDoors"],
    ])
    hurt_h = ["tick", "attacker_steamid", "user_steamid", "attacker_team_num", "user_team_num", "dmg_health_capped"]
    _write_gz(d / "events" / "player_hurt.csv.gz", hurt_h, [
        [1290, HERO, ENEMY1, 2, 3, 50],
        [1299, HERO, ENEMY1, 2, 3, 50],
        [1400, HERO, MATE, 2, 2, 30],      # team damage must not count
        [3450, HERO, ENEMY2, 2, 3, 100],
    ])
    return d.parent
