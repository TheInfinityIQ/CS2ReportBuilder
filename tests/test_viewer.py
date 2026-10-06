"""Replay provenance and timing regressions, independent of real demo downloads."""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

from cs2di.report import viewer, weapons

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("hz", [8, 16, 32])
def test_render_preserves_sidecar_sample_rate(tmp_path, hz):
    demo = tmp_path / "demo"
    demo.mkdir()
    (demo / "match_summary.json").write_text('{"map_name":"de_ancient"}')
    pd.DataFrame([dict(round=1, start_tick=0, freeze_end_tick=0, end_tick=64)]).to_csv(demo / "rounds.csv", index=False)
    sid = 76561198000000001
    pd.DataFrame([dict(round=1, steamid=sid, side="CT")]).to_csv(demo / "player_rounds.csv", index=False)
    pd.DataFrame([dict(tick=t, steamid=sid, name="Player", team_name="CT", is_alive=True,
                       X=t, Y=t, health=100, armor_value=100, active_weapon_name="AK-47", flash_duration=0)
                  for t in [0, 32, 64]]).to_csv(demo / "player_positions.csv.gz", index=False)
    (demo / "events").mkdir()
    pd.DataFrame(columns=["tick", "attacker_steamid", "user_steamid", "attacker_X", "attacker_Y",
                          "user_X", "user_Y", "weapon", "attacker_name", "user_name", "headshot"]).to_csv(
        demo / "events/player_death.csv.gz", index=False)
    step = 64 // hz
    pd.DataFrame([dict(round=1, tick=t, steamid=sid, x=t, y=t, yaw=t, flags=0)
                  for t in range(0, 65, step)]).to_csv(demo / "viewer_tracks.csv.gz", index=False)
    (demo / "viewer_tracks_meta.json").write_text(json.dumps({"sample_hz": hz, "step_ticks": step}))
    payload = viewer.round_payload(tmp_path, "demo", 1, sid)
    assert payload["facing"] and payload["dt"] == 1 / hz
    assert payload["n"] == hz + 1
    assert payload["players"][0]["xy"][2:4] == [step, step]
    assert payload["wa"] == ["ak47"]


def test_grenade_countdown_distinguishes_recorded_and_estimated(tmp_path):
    events = tmp_path / "events"
    events.mkdir()
    sid = 76561198000000001
    pd.DataFrame([dict(tick=10, x=0, y=0, entityid=1, user_steamid=sid, user_name="Player"),
                  dict(tick=12, x=10, y=10, entityid=2, user_steamid=sid, user_name="Player"),
                  dict(tick=16, x=20, y=20, entityid=3, user_steamid=sid, user_name="Player")]).to_csv(
        events / "smokegrenade_detonate.csv.gz", index=False)
    pd.DataFrame([dict(tick=74, entityid=1), dict(tick=32, entityid=3)]).to_csv(events / "smokegrenade_expired.csv.gz", index=False)
    nades = viewer._nades(tmp_path, 0, 128, {sid: "CT"})
    assert nades[0]["duration_recorded"] and nades[0]["d"] == 1
    assert not nades[1]["duration_recorded"] and nades[1]["d"] == 18
    assert nades[2]["duration_recorded"] and nades[2]["d"] == .25


def test_exact_weapon_assets_are_distinct_and_match_provenance():
    assert weapons.asset_id("AK-47") != weapons.asset_id("M4A1-S")
    assert weapons.asset_id("M4A4") != weapons.asset_id("M4A1-S")
    assert weapons.asset_id("Molotov") != weapons.asset_id("Incendiary Grenade")
    assert weapons.asset_id("Karambit") != weapons.asset_id("Butterfly Knife")
    assert weapons.asset_id("Some New Item") == ""
    folder = REPO / "assets/weapons"
    provenance = json.loads((folder / "PROVENANCE.json").read_text())
    for name, digest in provenance["svg_sha256"].items():
        assert hashlib.sha256((folder / f"{name}.svg").read_bytes()).hexdigest() == digest
    assert len(weapons.image_payload()) == 64


def test_requesting_higher_track_rate_does_not_skip_old_output(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "demoparser2", types.SimpleNamespace(DemoParser=None))
    spec = importlib.util.spec_from_file_location("viewer_extractor_test", REPO / "extractor/extract_viewer_tracks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in module.NEW_FILES:
        (tmp_path / name).write_text("test")
    demo = tmp_path / "sample.dem"
    demo.write_bytes(b"original demo")
    (tmp_path / "viewer_tracks_meta.json").write_text(json.dumps({
        "script_version": module.SCRIPT_VERSION, "sample_hz": 8,
        "demo_sha256": module.sha256_of(demo),
        "sha256_files": {name: module.sha256_of(tmp_path / name)
                         for name in module.NEW_FILES if name.endswith(".gz")}}))
    assert module.process_demo(demo, tmp_path, 8, False, False)["status"] == "skipped_done"
    with pytest.raises(FileNotFoundError):  # reads rounds.csv instead of reusing 8 Hz
        module.process_demo(demo, tmp_path, 16, False, False)
    demo.write_bytes(b"changed original")
    with pytest.raises(FileNotFoundError):
        module.process_demo(demo, tmp_path, 8, False, False)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_browser_timing_regressions():
    result = subprocess.run(["node", str(REPO / "tests/viewer_timing.cjs")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
