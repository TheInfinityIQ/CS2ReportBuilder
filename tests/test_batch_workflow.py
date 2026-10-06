import csv
import gzip
import json
import os
import socket
from pathlib import Path

import pytest

from cs2di import batch_selection as selection, extraction_queue as queue, job_lock, packet_jobs

REPO = Path(__file__).resolve().parents[1]
HERO = "76561198062530225"


def tracks(folder, hz=16, sha=None):
    with gzip.open(folder / "viewer_tracks.csv.gz", "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["round", "steamid", "tick", "x", "y", "yaw"])
        for tick in range(64, 128, 64 // hz):
            w.writerow([1, HERO, tick, 1, 2, 90])
    for name in ("grenade_throws.csv.gz", "grenade_paths.csv.gz"):
        with gzip.open(folder / name, "wt") as f:
            f.write("round,throw_id,tick,x,y,z\n")
    (folder / "viewer_tracks_meta.json").write_text(
        json.dumps(
            {
                "sample_hz": hz,
                "tickrate": 64,
                "step_ticks": 64 // hz,
                "demo_sha256": sha,
                "interpolation_check": {"ok": True},
                "pairing_check": {"checked": True, "fraction": 1},
            }
        )
    )


def test_nested_raw_subset_deduplicates_content_inside_one_collection(make_demo, tmp_path):
    one, two = make_demo("one"), make_demo("two")
    raw = tmp_path / "raw" / "batch_001"
    raw.mkdir(parents=True)
    (raw / "one.dem").write_bytes(b"same demo")
    (raw / "two.dem").write_bytes(b"same demo")
    matches = selection.scan_matches(one.parent, raw)
    assert matches[0].analysis == one and matches[0].core_ready
    assert matches[1].analysis == two and "Duplicate" in matches[1].problem
    assert len(selection.scan_matches(one.parent, raw / "missing")) == 0


def test_ambiguous_stems_are_blocked_and_missing_core_can_be_planned(tmp_path):
    raw = tmp_path / "raw"
    for sub in ("a", "b"):
        (raw / sub).mkdir(parents=True)
        (raw / sub / "same.dem").write_bytes(sub.encode())
    matches = selection.scan_matches(tmp_path / "new_analysis", raw)
    assert len(matches) == 2 and all("Ambiguous" in m.problem for m in matches)
    one = selection.scan_matches(tmp_path / "new_analysis", raw / "a")[0]
    assert not one.problem and not one.core_ready and one.analysis.name == "same"


def test_hash_cache_invalidates_changed_original(tmp_path):
    demo = tmp_path / "a.dem"
    demo.write_bytes(b"first")
    cache = {}
    first = selection.demo_hash(demo, cache)
    demo.write_bytes(b"second")
    assert selection.demo_hash(demo, cache) != first


def test_readiness_checks_actual_cadence_source_angles_and_publication(make_demo):
    folder = make_demo()
    tracks(folder, 8, "source")
    assert not selection.replay_quality(folder, "source").ready
    tracks(folder, 16, "source")
    assert selection.replay_quality(folder, "source").ready
    assert not selection.replay_quality(folder, "changed").ready
    meta = selection.read_json(folder / "viewer_tracks_meta.json")
    meta.update(sample_hz=32, step_ticks=2)
    (folder / "viewer_tracks_meta.json").write_text(json.dumps(meta))
    assert "cadence" in selection.replay_quality(folder).reason
    tracks(folder)
    with gzip.open(folder / "viewer_tracks.csv.gz", "at") as f:
        f.write(f"1,{HERO},128,nan,2,90\n")
    assert "Non-finite" in selection.replay_quality(folder).reason
    (folder / ".viewer_tracks_updating").touch()
    assert "interrupted" in selection.replay_quality(folder).reason


def test_invalid_grenade_table_blocks_readiness(make_demo):
    folder = make_demo()
    tracks(folder)
    (folder / "grenade_paths.csv.gz").write_bytes(b"corrupt")
    assert not selection.replay_quality(folder).ready


def test_locks_refuse_live_owner_and_recover_only_proven_dead(tmp_path, monkeypatch):
    lock = tmp_path / "owner.lock"
    with job_lock.exclusive(lock):
        with pytest.raises(RuntimeError):
            with job_lock.exclusive(lock):
                pass
    lock.write_text(json.dumps({"pid": 123456, "host": socket.gethostname()}))
    monkeypatch.setattr(job_lock, "alive", lambda pid: False)
    with job_lock.exclusive(lock):
        assert lock.exists()
    assert not lock.exists()
    lock.write_text("unreadable interrupted lock")
    with pytest.raises(RuntimeError):
        with job_lock.exclusive(lock):
            pass
    assert job_lock.alive is not None
    assert (REPO / "extractor/job_lock.py").read_bytes() == (REPO / "src/cs2di/job_lock.py").read_bytes()


def test_real_process_liveness():
    assert job_lock.alive(os.getpid())


def test_queue_admission_has_cpu_headroom_and_memory_reserve():
    assert queue.can_start(queue.Resources(60, 100, 40), 20)
    assert not queue.can_start(queue.Resources(80, 100, 40), 20)
    assert not queue.can_start(queue.Resources(10, 100, 25), 20)


def test_queue_cancel_finishes_active_keeps_logs_and_summary(tmp_path):
    demo = tmp_path / "one.dem"
    demo.write_bytes(b"demo")
    jobs = [{"demo": str(demo), "analysis": str(tmp_path / str(i)), "sha256": "x"} for i in range(3)]
    cancel = tmp_path / "cancel"
    spawned = []

    class Process:
        pid = 99999999
        count = 0

        def poll(self):
            self.count += 1
            return 0 if self.count > 2 else None

    def spawn(command, **options):
        assert options["env"]["OMP_NUM_THREADS"] == "1"
        Path(command[command.index("--result") + 1]).write_text('{"status":"ok"}')
        spawned.append(command)
        cancel.touch()
        return Process()

    result = queue.run_queue(
        REPO,
        jobs,
        tmp_path / "work",
        cancel_path=cancel,
        sampler=lambda: queue.Resources(20, 32 * 1024**3, 25 * 1024**3),
        spawn=spawn,
        sleep=lambda _: None,
        log=lambda _: None,
    )
    assert len(spawned) == 1
    assert sorted(r["status"] for r in result["results"]) == ["cancelled", "cancelled", "ok"]
    assert (Path(result["run_folder"]) / "summary.json").is_file()
    assert not (tmp_path / "work/coordinator.lock").exists()


def test_queue_missing_demo_spawn_failure_and_duplicate_output(tmp_path):
    demo = tmp_path / "demo.dem"
    demo.write_bytes(b"demo")
    jobs = [
        {"demo": str(demo), "analysis": str(tmp_path / "analysis")},
        {"demo": str(tmp_path / "missing.dem"), "analysis": str(tmp_path / "other")},
    ]

    def spawn(*a, **kw):
        raise OSError("start failed")

    result = queue.run_queue(
        REPO,
        jobs,
        tmp_path / "work",
        sampler=lambda: queue.Resources(0, 32 * 1024**3, 25 * 1024**3),
        spawn=spawn,
        sleep=lambda _: None,
        log=lambda _: None,
    )
    assert len(result["results"]) == 2 and all(r["status"] == "failed" for r in result["results"])
    with pytest.raises(ValueError, match="same analysis"):
        queue.run_queue(REPO, [jobs[0], jobs[0]], tmp_path / "work")


def test_packet_rechecks_required_replay_and_original_hash(make_demo, tmp_path, monkeypatch):
    folder = make_demo("one")
    raw = tmp_path / "raw"
    raw.mkdir()
    demo = raw / "one.dem"
    demo.write_bytes(b"original")
    matches = selection.scan_matches(folder.parent, raw)
    batch = packet_jobs.inspect_batch(folder.parent, [folder], matches)
    monkeypatch.setattr(packet_jobs, "check_dependencies", lambda _: None)
    output = tmp_path.parent / (tmp_path.name + "_packets")
    with pytest.raises(RuntimeError, match="Prepare 16 Hz"):
        packet_jobs.build_packet(REPO, batch, batch.players[0], output, require_viewer=True)
    tracks(folder, sha=matches[0].sha256)
    demo.write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="Original demo changed"):
        packet_jobs.build_packet(REPO, batch, batch.players[0], output, require_viewer=True)


def test_packet_records_selected_identities_and_quality(make_demo, tmp_path, monkeypatch):
    from test_packet_jobs import fake_builder

    folder = make_demo()
    tracks(folder, sha="recorded-sha")
    matches = selection.scan_matches(folder.parent)
    batch = packet_jobs.inspect_batch(folder.parent, [folder], matches)
    monkeypatch.setattr(packet_jobs, "check_dependencies", lambda _: None)
    output = tmp_path.parent / (tmp_path.name + "_packets")
    packet = packet_jobs.build_packet(
        REPO, batch, batch.players[0], output, require_viewer=True, runner=fake_builder
    )
    manifest = selection.read_json(packet / "MANIFEST.json")
    assert manifest["replay_requirement"] == "validated_16hz"
    assert manifest["selected_matches"][0]["replay"]["hz"] == 16
    assert not manifest["selected_matches"][0]["identity_verified_from_raw"]


def test_normal_v78_run_requests_validated_16hz_by_default(tmp_path, monkeypatch):
    import importlib.util
    import sys
    import types

    spec = importlib.util.spec_from_file_location("default_core", REPO / "extractor/extract_demos_v7dot8.py")
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "one.dem").write_bytes(b"demo")
    output = tmp_path / "analysis"
    monkeypatch.setattr(core, "DEMO_DIR", raw)
    monkeypatch.setattr(core, "OUTPUT_DIR", output)
    monkeypatch.setattr(core, "RUN_INTERNAL_SELF_TESTS", False)

    def analyze(demo):
        folder = output / demo.stem
        folder.mkdir()
        (folder / "match_summary.json").write_text('{"valid":true,"coaching_valid":true}')
        return True

    monkeypatch.setattr(core, "analyze_demo", analyze)
    requested = []

    def sidecar(*args, **kwargs):
        requested.append((args, kwargs))
        return {"status": "ok", "meta": {"interpolation_check": {"ok": True}}}

    monkeypatch.setitem(sys.modules, "extract_viewer_tracks", types.SimpleNamespace(process_demo=sidecar))
    core.main()
    assert requested[0][0][2:] == (16, True, False)
    assert core.TICK_SAMPLE_EVERY == 32  # Existing analytic tables retain their cadence.


def test_viewer_estimate_uses_measurements_with_headroom():
    gib = 1024**3
    assert queue.estimate_memory(gib, 0, "viewer") == 4 * gib
    assert queue.estimate_memory(gib, 0, "prepare") == 8 * gib
    assert queue.estimate_memory(100, 4 * gib, "viewer") == int(4 * gib * 1.3)


def test_queue_starts_fitting_small_job_before_large_one(tmp_path):
    small, large = tmp_path / "small.dem", tmp_path / "large.dem"
    small.write_bytes(b"demo")
    large.write_bytes(b"large demo")
    jobs = [{"demo": str(p), "analysis": str(tmp_path / p.stem)} for p in (large, small)]
    order = []

    class Process:
        pid = 99999999

        def poll(self):
            return 0

    def spawn(command, **options):
        job = json.loads(Path(command[command.index("--worker") + 1]).read_text())
        order.append(Path(job["demo"]).name)
        Path(command[command.index("--result") + 1]).write_text('{"status":"ok"}')
        return Process()

    result = queue.run_queue(
        REPO,
        jobs,
        tmp_path / "work",
        max_workers=1,
        sampler=lambda: queue.Resources(20, 16 * 1024**3, 7 * 1024**3),
        spawn=spawn,
        sleep=lambda _: None,
        log=lambda _: None,
    )
    assert order == ["small.dem", "large.dem"]
    assert len(json.loads((Path(result["run_folder"]) / "jobs.json").read_text())) == 2


def test_coverage_distinguishes_unobserved_roster_and_unplayed_surrender(make_demo):
    folder = make_demo()
    other = "76561198000000002"
    with (folder / "players.csv").open("a") as f:
        f.write(f"{other},Unobserved,3\n")
    (folder / "rounds.csv").write_text("round,start_tick,freeze_end_tick,end_tick\n1,32,64,128\n2,200,,240\n")
    with gzip.open(folder / "player_positions.csv.gz", "wt") as f:
        f.write(f"steamid,tick\n{HERO},64\n")
    tracks(folder)
    quality = selection.replay_quality(folder)
    assert quality.ready and quality.unobserved_players == (other,) and quality.nonlive_rounds == (2,)
    with gzip.open(folder / "player_positions.csv.gz", "at") as f:
        f.write(f"{other},64\n")
    assert not selection.replay_quality(folder).ready  # Actually observed player must have tracks.
    with (folder / "players.csv").open("w") as f:
        f.write(f"steamid,name,team_number\n{HERO},Hero,3\n")
    (folder / "rounds.csv").write_text(
        "round,start_tick,freeze_end_tick,end_tick\n1,32,64,128\n2,200,220,240\n"
    )
    assert not selection.replay_quality(folder).ready  # Actually live round must have tracks.


def test_packet_refuses_unobserved_selected_player(make_demo, tmp_path, monkeypatch):
    folder = make_demo()
    other = "76561198000000002"
    with (folder / "players.csv").open("a") as f:
        f.write(f"{other},Other,3\n")
    with gzip.open(folder / "player_positions.csv.gz", "wt") as f:
        f.write(f"steamid,tick\n{other},64\n")
    tracks(folder)
    with gzip.open(folder / "viewer_tracks.csv.gz", "rt") as f:
        data = f.read().replace(HERO, other)
    with gzip.open(folder / "viewer_tracks.csv.gz", "wt") as f:
        f.write(data)
    assert selection.replay_quality(folder).ready
    batch = packet_jobs.inspect_batch(folder.parent)
    player = next(p for p in batch.players if p.steamid == HERO)
    monkeypatch.setattr(packet_jobs, "check_dependencies", lambda _: None)
    output = tmp_path.parent / (tmp_path.name + "_packets")
    with pytest.raises(RuntimeError, match="No recorded live viewer data"):
        packet_jobs.build_packet(REPO, batch, player, output, require_viewer=True)
