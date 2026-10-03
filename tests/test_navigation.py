"""Navigation must detect drift without altering evidence or isolated coach inputs."""
import importlib.util
import re
from pathlib import Path
from urllib.parse import unquote

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("navigation", REPO / "scripts/navigation.py")
nav = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nav)


def policy():
    return {name: {"statuses": [], "folders": {}, "files": {}} for name in ("repo", "data")}


def test_add_edit_delete_and_idempotence(tmp_path):
    meta = policy()
    source = tmp_path / "doc.md"
    source.write_text("# Original\nFirst description.\n", encoding="utf-8")
    assert nav.refresh(tmp_path, "repo", meta) == 0
    initial = (tmp_path / nav.INDEX).read_bytes()
    assert nav.refresh(tmp_path, "repo", meta, check=True) == 0
    assert (tmp_path / nav.INDEX).read_bytes() == initial
    source.write_text("# Edited\nChanged contents.\n", encoding="utf-8")
    assert nav.refresh(tmp_path, "repo", meta, check=True) == 1
    assert nav.refresh(tmp_path, "repo", meta) == 0
    second = tmp_path / "space [bracket].md"
    second.write_text("New source", encoding="utf-8")
    assert nav.refresh(tmp_path, "repo", meta, check=True) == 1
    nav.refresh(tmp_path, "repo", meta)
    for target in re.findall(r"\]\(([^)]+)\)", (tmp_path / nav.INDEX).read_text()):
        assert (tmp_path / unquote(target)).exists()
    second.unlink()
    assert nav.refresh(tmp_path, "repo", meta, check=True) == 1
    nav.refresh(tmp_path, "repo", meta)
    assert "space [bracket].md" not in [r["path"] for r in nav.load_catalog(tmp_path)]


def test_curated_summary_requires_review_of_new_content(tmp_path):
    source = tmp_path / "doc.md"
    source.write_text("Inspected contents", encoding="utf-8")
    meta = policy()
    digest = nav.describe(source, tmp_path, "repo", meta)["sha256"]
    meta["repo"]["files"]["doc.md"] = {"summary": "Reviewed meaning", "reviewed_sha256": digest}
    assert nav.refresh(tmp_path, "repo", meta) == 0
    source.write_text("Different meaning", encoding="utf-8")
    assert nav.refresh(tmp_path, "repo", meta) == 1
    assert "summary needs review" in (tmp_path / nav.INDEX).read_text()


def test_packet_isolation_and_profile_exclusions(tmp_path):
    meta = policy()
    packet = tmp_path / "06_Handoff_and_Tests/packets/P_test"
    packet.mkdir(parents=True)
    prompt = packet / "PROMPT.md"
    prompt.write_text("Only packet context", encoding="utf-8")
    before = prompt.read_bytes()
    for name in ("faceit_browser_profile", "faceit_firefox_profile", ".venv", ".git"):
        excluded = tmp_path / name
        excluded.mkdir()
        (excluded / "secret.txt").write_text("Never catalog", encoding="utf-8")
    source = tmp_path / "05_Coach_Knowledge/new/doc.md"
    source.parent.mkdir(parents=True)
    source.write_text("Document", encoding="utf-8")
    nav.refresh(tmp_path, "data", meta)
    assert not list(packet.rglob(nav.INDEX))
    assert prompt.read_bytes() == before
    assert (source.parent / nav.INDEX).exists()
    assert all("secret.txt" not in r["path"] for r in nav.load_catalog(tmp_path))
    assert nav.refresh(tmp_path, "data", meta, check=True) == 0


def test_maps_are_bounded_and_dates_do_not_use_mtime(tmp_path):
    meta = policy()
    history = tmp_path / "docs/history"
    history.mkdir(parents=True)
    for name in ("v10.md", "v2.md", "2026-09-28.md", "2026-09-27.md"):
        (history / name).write_text("# Topic\nDetails", encoding="utf-8")
    nav.refresh(tmp_path, "repo", meta)
    text = (history / nav.INDEX).read_text()
    assert text.index("2026-09-27.md") < text.index("2026-09-28.md") < text.index("v2.md") < text.index("v10.md")
    assert nav.describe(history / "v2.md", tmp_path, "repo", meta)["date"] is None
    for i in range(80):
        (history / f"more{i}.md").write_text("Text", encoding="utf-8")
    nav.refresh(tmp_path, "repo", meta)
    text = (history / nav.INDEX).read_text()
    assert sum(line.startswith("| [") for line in text.splitlines()) == nav.LIMIT
    assert len(nav.load_catalog(tmp_path)) == 84


def test_handwritten_index_is_not_overwritten(tmp_path):
    (tmp_path / nav.INDEX).write_text("Human document", encoding="utf-8")
    try:
        nav.refresh(tmp_path, "repo", policy())
    except ValueError:
        pass
    else:
        raise AssertionError("Must protect handwritten map")
    assert (tmp_path / nav.INDEX).read_text() == "Human document"


def test_crlf_hashes_match_lf_and_metadata_invalidates_warm_cache(tmp_path):
    source = tmp_path / "doc.md"
    source.write_bytes(b"# Doc\r\nText\r\n")
    meta = policy()
    first = nav.describe(source, tmp_path, "repo", meta)
    source.write_bytes(b"# Doc\nText\n")
    second = nav.describe(source, tmp_path, "repo", meta)
    assert first["sha256"] == second["sha256"] and first["bytes"] == second["bytes"]
    nav.refresh(tmp_path, "data", meta)
    meta["data"]["statuses"] = [["doc", "changed status"]]
    assert nav.refresh(tmp_path, "data", meta, check=True) == 1
    nav.refresh(tmp_path, "data", meta)
    assert nav.load_catalog(tmp_path)[0]["status"] == "changed status"


def test_checked_in_navigation_is_fresh():
    assert nav.refresh(REPO, "repo", nav.metadata(), check=True) == 0
