import csv
import json
import zipfile
from pathlib import Path

import pytest

from cs2di import packet_jobs as jobs

REPO = Path(__file__).resolve().parents[1]
HERO = "76561198062530225"


def test_inspection_excludes_failures_and_groups_exact_player_ids(make_demo):
    good = make_demo("one")
    second = make_demo("two")
    make_demo("bad", valid=False)
    (good.parent / ".partial.v75_tmp").mkdir()
    (good.parent / "notes").mkdir()
    with (second / "players.csv").open("a", newline="") as fh:
        csv.writer(fh).writerow(["76561198181834733", "Other", 2])
    batch = jobs.inspect_batch(good.parent)
    assert batch.accepted == 2 and len(batch.excluded) == 1 and batch.ignored == 2
    assert batch.players[0].steamid == HERO and len(batch.players[0].demos) == 2
    assert len(batch.players[1].demos) == 1


def test_selects_an_example_for_another_player():
    assert jobs.choose_example(REPO, "76561199066695873").parent.name == "itrilogy"
    assert jobs.choose_example(REPO, "76561198181834733").parent.name == "mimy"


def fake_builder(command, log):
    out = Path(command[command.index("--out") + 1])
    steamid = command[command.index("--steamid") + 1]
    count = int(command[command.index("--expect") + 1])
    assert "--no-batch-copy" in command
    (out / "data").mkdir(parents=True)
    for name in ("PROMPT.md", "data/digest.json", "data/findings_all.json"):
        (out / name).write_text("{}", encoding="utf-8")
    (out / "MANIFEST.json").write_text(json.dumps({"steamid": steamid, "matches": count}), encoding="utf-8")
    log("Smoke test passed")
    return 0


def test_jobs_preserve_sources_and_previous_packets(make_demo, tmp_path, monkeypatch):
    source = make_demo("match")
    original = (source / "players.csv").read_bytes()
    batch = jobs.inspect_batch(source.parent)
    # tmp_path is the source batch root: put outputs outside it, as the UI requires.
    output = tmp_path.parent / (tmp_path.name + "_packets")
    monkeypatch.setattr(jobs, "check_dependencies", lambda p: None)
    one = jobs.build_packet(REPO, batch, batch.players[0], output, runner=fake_builder)
    (one / "plan.json").write_text("saved coach work", encoding="utf-8")
    two = jobs.build_packet(REPO, batch, batch.players[0], output, runner=fake_builder)
    assert one != two and (one / "plan.json").read_text() == "saved coach work"
    assert (two / "data/batch/match/players.csv").read_bytes() == original
    assert (source / "players.csv").read_bytes() == original
    assert not list(output.glob("*.building"))


def test_failed_build_is_not_published_and_keeps_diagnostics(make_demo, tmp_path, monkeypatch):
    source = make_demo("match")
    batch = jobs.inspect_batch(source.parent)
    output = tmp_path.parent / (tmp_path.name + "_packets")
    monkeypatch.setattr(jobs, "check_dependencies", lambda p: None)
    with pytest.raises(RuntimeError, match="No ready packet"):
        jobs.build_packet(REPO, batch, batch.players[0], output, runner=lambda command, log: 1)
    assert not list(output.glob("P_*"))
    assert "FAILED" in next(output.glob(".*.building/build.log")).read_text()


def test_output_cannot_pollute_analysis(make_demo, monkeypatch):
    source = make_demo("match")
    batch = jobs.inspect_batch(source.parent)
    monkeypatch.setattr(jobs, "check_dependencies", lambda p: None)
    with pytest.raises(ValueError, match="outside"):
        jobs.build_packet(REPO, batch, batch.players[0], source / "packet", runner=fake_builder)


def test_zip_is_portable_and_never_overwrites(tmp_path):
    packet = tmp_path / "packet"
    (packet / "data").mkdir(parents=True)
    (packet / "PROMPT.md").write_text("coach task", encoding="utf-8")
    (packet / "data/evidence.json").write_text("{}", encoding="utf-8")
    archive = tmp_path / "packet.zip"
    jobs.export_zip(packet, archive)
    original = archive.read_bytes()
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist()) == {"PROMPT.md", "data/evidence.json"}
    with pytest.raises(FileExistsError):
        jobs.export_zip(packet, archive)
    assert archive.read_bytes() == original
    with pytest.raises(ValueError, match="outside"):
        jobs.export_zip(packet, packet / "self.zip")
