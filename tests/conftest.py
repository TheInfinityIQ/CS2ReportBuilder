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
