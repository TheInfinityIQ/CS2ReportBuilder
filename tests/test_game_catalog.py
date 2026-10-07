import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cs2di import batch_selection as selection, job_lock
from cs2di.game_catalog import Catalog, file_stamp, notify_output, open_catalog, signature
from test_batch_workflow import HERO, tracks


def test_warm_load_skips_replay_and_identity_reads_but_rechecks_changes(make_demo, tmp_path, monkeypatch):
    folder = make_demo()
    tracks(folder)
    catalog = Catalog(tmp_path / "catalog.sqlite3")
    original = selection.replay_quality
    reads = []
    monkeypatch.setattr(
        selection, "replay_quality", lambda *a, **k: (reads.append(a[0]), original(*a, **k))[1]
    )
    identities = []
    monkeypatch.setattr(selection, "evidence_hash", lambda p: (identities.append(p), "evidence:one")[1])
    first = selection.scan_matches(folder.parent, catalog=catalog)
    assert first[0].replay.ready
    assert selection.scan_matches(folder.parent, catalog=catalog) == first
    assert len(reads) == len(identities) == 1
    # A changed roster must invalidate both readiness and player availability.
    (folder / "players.csv").write_text("steamid,name,team_number\n76561198000000000,New player,3\n")
    changed = selection.scan_matches(folder.parent, catalog=catalog)
    assert not changed[0].replay.ready
    assert len(reads) == len(identities) == 2
    assert not catalog.games(player=HERO)
    assert catalog.games(player="76561198000000000")
    selection.scan_matches(folder.parent, catalog=catalog, force=True)
    assert len(reads) == 3


def test_lock_and_incomplete_publication_cannot_reuse_ready_cache(make_demo, tmp_path):
    folder = make_demo()
    tracks(folder)
    catalog = Catalog(tmp_path / "catalog.sqlite3")
    assert selection.scan_matches(folder.parent, catalog=catalog)[0].replay.ready
    with job_lock.exclusive(job_lock.lock_path(folder)):
        assert catalog.get(folder) is None
        assert not selection.scan_matches(folder.parent, catalog=catalog)[0].replay.ready
    assert catalog.get(folder)["replay"]["ready"]
    (folder / ".viewer_tracks_updating").touch()
    assert catalog.get(folder) is None
    assert not selection.scan_matches(folder.parent, catalog=catalog)[0].replay.ready


def test_player_team_batch_queries_and_removed_games(make_demo, tmp_path):
    folder = make_demo("natus-vincere-vs-the-mongolz-m1-nuke")
    tracks(folder)
    catalog = Catalog(tmp_path / "catalog.sqlite3")
    selection.scan_matches(folder.parent, catalog=catalog)
    raw = tmp_path / "raw/batch_001/game.dem"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"demo")
    catalog.register_source(raw, folder)
    assert (
        len(catalog.games(player=HERO, team="THE-MONGOLZ", raw_folder=raw.parent, collection=folder.parent))
        == 1
    )
    assert not catalog.games(team="unknown")
    moved = folder.with_name("moved")
    folder.rename(moved)
    catalog.prune(tmp_path)
    assert not catalog.games()


def test_cached_raw_hash_requires_unchanged_verified_fingerprint(tmp_path):
    catalog = Catalog(tmp_path / "catalog.sqlite3")
    raw = tmp_path / "game.dem"
    raw.write_bytes(b"first")
    catalog.register_source(raw, tmp_path / "analysis", "sha", stamp=file_stamp(raw))
    assert catalog.source_hash(raw) == "sha"
    catalog.register_source(raw, tmp_path / "analysis")
    assert catalog.source_hash(raw) == "sha", (
        "Availability updates must retain a verified unchanged source hash"
    )
    stamp = file_stamp(raw)
    raw.write_bytes(b"changed")
    assert catalog.source_hash(raw) is None
    catalog.register_source(raw, tmp_path / "analysis", "old-sha", stamp=stamp)
    assert catalog.source_hash(raw) is None


def test_concurrent_updates_are_complete_and_changed_snapshot_is_not_saved(make_demo, tmp_path):
    catalog = Catalog(tmp_path / "catalog.sqlite3")
    folders = [make_demo(f"game{i}") for i in range(12)]
    for folder in folders:
        tracks(folder)

    def save(folder):
        before = signature(folder)
        quality = selection.replay_quality(folder)
        from dataclasses import asdict

        return Catalog(catalog.path).put(
            folder, None, before, {"core_ready": True, "map_name": "de_nuke", "replay": asdict(quality)}
        )

    with ThreadPoolExecutor(max_workers=6) as pool:
        assert all(pool.map(save, folders))
    assert len(catalog.games(player=HERO)) == 12
    before = signature(folders[0])
    (folders[0] / "new.txt").write_text("changed")
    assert not catalog.put(folders[0], None, before, {})
    with sqlite3.connect(catalog.path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_corrupt_catalog_recovery_preserves_old_file(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    path.write_bytes(b"broken cache")
    with pytest.raises(sqlite3.DatabaseError):
        Catalog(path)
    catalog = open_catalog(path, recover=True, log=lambda _: None)
    assert catalog.games() == []
    assert next(tmp_path.glob("*.broken_*")).read_bytes() == b"broken cache"


def test_extraction_publication_updates_catalog_under_its_lock(make_demo, tmp_path, monkeypatch):
    monkeypatch.setenv("CS2DI_ROOT", str(tmp_path))
    folder = make_demo()
    tracks(folder, sha="source-sha")
    with job_lock.exclusive(job_lock.lock_path(folder)):
        notify_output(folder, owned=True)
    catalog = Catalog()
    assert catalog.get(folder, "source-sha")["replay"]["ready"]
    assert catalog.games(player=HERO)
    assert json.loads((folder / "viewer_tracks_meta.json").read_text())["demo_sha256"] == "source-sha"


def test_standalone_catalog_is_identical():
    root = Path(__file__).resolve().parents[1]
    assert (root / "src/cs2di/game_catalog.py").read_bytes() == (
        root / "extractor/game_catalog.py"
    ).read_bytes()


def test_cached_preview_cannot_bypass_fresh_packet_validation(make_demo, tmp_path, monkeypatch):
    from cs2di import packet_jobs

    folder = make_demo()
    tracks(folder)
    catalog = Catalog(tmp_path / "catalog.sqlite3")
    matches = selection.scan_matches(folder.parent, catalog=catalog)
    batch = packet_jobs.inspect_batch(
        folder.parent, [folder], matches, rosters=catalog.rosters(folder.parent)
    )
    assert matches[0].replay.ready
    (folder / "grenade_paths.csv.gz").write_bytes(b"corrupted after preview")
    monkeypatch.setattr(packet_jobs, "check_dependencies", lambda _: None)
    output = tmp_path.parent / (tmp_path.name + "_packets")
    with pytest.raises(RuntimeError, match="No ready packet"):
        packet_jobs.build_packet(
            Path(__file__).resolve().parents[1],
            batch,
            batch.players[0],
            output,
            require_viewer=True,
            runner=lambda *a: pytest.fail("Corrupt evidence must never reach report rendering"),
        )
    assert not list(output.glob("P_*"))


def test_standalone_pending_record_is_discoverable_but_never_cached_as_ready(
    make_demo, tmp_path, monkeypatch
):
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "extractor"))
    monkeypatch.setenv("CS2DI_ROOT", str(tmp_path))
    spec = importlib.util.spec_from_file_location(
        "standalone_game_catalog", root / "extractor/game_catalog.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    folder = make_demo()
    tracks(folder)
    with job_lock.exclusive(job_lock.lock_path(folder)):
        module.notify_output(folder, owned=True)
    catalog = Catalog()
    assert catalog.games(player=HERO)[0]["verified"] is False
    assert catalog.get(folder) is None
    assert selection.scan_matches(folder.parent, catalog=catalog)[0].replay.ready
    assert catalog.games(player=HERO)[0]["verified"] is True


def test_new_validation_revision_requires_fresh_checks(make_demo, tmp_path, monkeypatch):
    import cs2di.game_catalog as module

    folder = make_demo()
    tracks(folder)
    catalog = Catalog(tmp_path / "catalog.sqlite3")
    assert selection.scan_matches(folder.parent, catalog=catalog)[0].replay.ready
    assert catalog.get(folder)
    monkeypatch.setattr(module, "VALIDATION_REVISION", module.VALIDATION_REVISION + 1)
    assert catalog.get(folder) is None
    assert selection.scan_matches(folder.parent, catalog=catalog)[0].replay.ready
    assert catalog.get(folder)["validation_revision"] == module.VALIDATION_REVISION
