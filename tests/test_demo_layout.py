"""Relocated raw data must keep its existing analysis collection identities."""

from pathlib import Path

import pytest
from cs2di import config
from cs2di.demo_layout import collection_name, demo_files


def test_separate_roots_and_saved_player_batch(tmp_path, monkeypatch):
    data, raw = tmp_path / "data", tmp_path / "replays"
    monkeypatch.setenv("CS2DI_ROOT", str(data))
    monkeypatch.setenv("CS2DI_DEMOS_ROOT", str(raw))
    analysis = data / "02_Analysis"
    (analysis / "analyzed_CanadianIQ_demos").mkdir(parents=True)
    batch = raw / "CanadianIQ/batch_001"
    batch.mkdir(parents=True)
    assert config.demos_dir("CanadianIQ_demos") == batch.parent
    assert config.analysis_dir("CanadianIQ_demos") == analysis / "analyzed_CanadianIQ_demos"
    assert collection_name(batch.parent, analysis) == "CanadianIQ_demos"
    assert config.relocated_selection(data / "01_Demos/CanadianIQ_demos/batch_001") == batch
    assert config.relocated_selection(data / "01_Demos/Tournament") == raw / "Tournament"
    assert config.relocated_selection(tmp_path / "external") == tmp_path / "external"
    assert config.demos_dir("Tournament") == raw / "Tournament"
    (analysis / "analyzed_CanadianIQ").mkdir()
    with pytest.raises(ValueError, match="Ambiguous"):
        collection_name(batch.parent, analysis)


def test_nested_series_and_colliding_stems(tmp_path):
    for series, filename in [("a-vs-b", "game.dem"), ("c-vs-d", "other.DEM")]:
        folder = tmp_path / series
        folder.mkdir()
        (folder / filename).write_bytes(b"demo")
    assert len(demo_files(tmp_path)) == 2
    (tmp_path / "c-vs-d/GAME.dem").write_bytes(b"different demo")
    with pytest.raises(ValueError, match="Duplicate demo stem"):
        demo_files(tmp_path)


def test_standalone_layout_copy_is_identical():
    repo = Path(__file__).resolve().parents[1]
    assert (repo / "src/cs2di/demo_layout.py").read_bytes() == (
        repo / "extractor/demo_layout.py"
    ).read_bytes()


def test_all_tracks_never_falls_back_to_another_collection(tmp_path, monkeypatch):
    import importlib

    repo = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(repo / "extractor"))
    runner = importlib.import_module("run_all_tracks")
    raw, analysis = tmp_path / "CanadianIQ", tmp_path / "analysis"
    raw.mkdir()
    (raw / "game.dem").write_bytes(b"demo")
    (analysis / "analyzed_CanadianIQ_demos").mkdir(parents=True)
    wrong = analysis / "analyzed_another/game"
    wrong.mkdir(parents=True)
    (wrong / "rounds.csv").write_text("round\n1\n")
    pairs, missing, duplicates = runner.plan_batch(raw, analysis)
    assert not pairs and missing == [raw / "game.dem"] and not duplicates
    nested = raw / "batch_002"
    nested.mkdir()
    (nested / "GAME.dem").write_bytes(b"different")
    pairs, missing, duplicates = runner.plan_batch(raw, analysis)
    assert not pairs and not missing and len(duplicates) == 2
