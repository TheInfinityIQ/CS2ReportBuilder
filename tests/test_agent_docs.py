"""Check current entry links and preservation of archived instruction sources."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote

REPO = Path(__file__).resolve().parents[1]
ARCHIVE = REPO / "docs/history/agent-system/2026-10-03"
ENTRY_DOCS = [REPO / p for p in (
    "AGENTS.md", "CLAUDE.md", "README.md", "docs/PROJECT_STATUS.md",
    "docs/history/README.md", "docs/NAVIGATION.md", "docs/CLEANUP_2026-10-03.md",
    "docs/CLEANUP_2026-10-04.md", "docs/history/SOURCES.md",
    "docs/history/project-records/README.md", "docs/history/design/README.md",
    "docs/KNOWN_PITFALLS.md",
    "docs/PACKET_BUILDER_UI.md",
)]


def test_current_entry_links_resolve_inside_repo():
    missing = []
    for doc in ENTRY_DOCS:
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", doc.read_text(encoding="utf-8")):
            if re.match(r"https?://", target):
                continue
            target = unquote(target.split("#", 1)[0])
            if not target:
                continue
            path = (doc.parent / target).resolve()
            assert path.is_relative_to(REPO.resolve()), f"{doc}: link escapes checkout: {target}"
            if not path.exists():
                missing.append(f"{doc.relative_to(REPO)}: {target}")
    assert not missing, "\n".join(missing)


def test_claude_import_has_a_real_target():
    for target in re.findall(r"^@([^\s]+)$", (REPO / "CLAUDE.md").read_text(encoding="utf-8"), re.M):
        assert (REPO / target).is_file(), target


def test_archived_instruction_sources_are_unchanged():
    records = json.loads((ARCHIVE / "MIGRATION.json").read_text(encoding="utf-8"))
    assert records
    for record in records:
        path = REPO / record["archive"]
        raw = path.read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == record["normalized_sha256"], record["original"]


def test_broader_cleanup_preserves_repository_sources():
    records = json.loads((REPO / "docs/history/cleanup-2026-10-04/MIGRATION.json").read_text(encoding="utf-8"))
    repo_records = [r for r in records if r["original"].startswith("repo/")]
    assert len(repo_records) == 18
    for record in repo_records:
        path = REPO / record["destination"].removeprefix("repo/")
        assert path.resolve().is_relative_to(REPO.resolve())
        raw = path.read_bytes()
        if path.suffix == ".docx":
            assert hashlib.sha256(raw).hexdigest() == record["sha256"], record["original"]
        else:
            assert hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == record["normalized_sha256"], record["original"]


def test_history_does_not_contain_autoload_instruction_files():
    for name in ("CLAUDE.md", "AGENTS.md", "CLAUDE.local.md"):
        assert not list(ARCHIVE.rglob(name)), name


def test_coach_handoff_files_do_not_leak_development_context():
    for path in (REPO / "coach/handoff").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for name in ("agent/", "CLAUDE.md", "AGENTS.md", "PROJECT_STATUS.md"):
            assert name not in text, (path, name)
