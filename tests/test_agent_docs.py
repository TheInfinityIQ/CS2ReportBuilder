"""The agent start-here docs must not point at repo files that do not exist."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCS = [REPO / "CLAUDE.md", *sorted((REPO / "agent").rglob("*.md"))]
TOKEN = re.compile(r"`([A-Za-z0-9_./-]+)`")
ROOTS = ("agent/", "docs/", "scripts/", "coach/", "src/", "tests/", "extractor/", "examples/", "assets/")


def test_every_repo_path_in_agent_docs_exists():
    missing = []
    for doc in DOCS:
        for tok in TOKEN.findall(doc.read_text(encoding="utf-8")):
            if tok.startswith(ROOTS) and not (REPO / tok).exists():
                missing.append(f"{doc.relative_to(REPO)}: {tok}")
    assert not missing, "\n".join(missing)


def test_every_hat_in_the_router_has_a_file():
    router = (REPO / "agent/ROUTER.md").read_text(encoding="utf-8")
    hats = {"Intake steward": "intake-steward", "Packet builder": "packet-builder", "Test reviewer": "test-reviewer",
            "Developer": "developer", "Librarian": "librarian"}
    for slug in ("pre-work", "post-work"):
        assert (REPO / f"agent/roles/{slug}.md").exists()
        assert f"roles/{slug}.md" in (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    for name, slug in hats.items():
        assert (REPO / f"agent/roles/{slug}.md").exists()
        assert name in router


CAPS = {"CLAUDE.md": 60, "agent/STATE.md": 60, "agent/PREFERENCES.md": 80, "agent/REGRESSIONS.md": 60}


def test_logs_and_start_files_stay_within_their_caps():
    over = []
    for rel, cap in CAPS.items():
        n = len((REPO / rel).read_text(encoding="utf-8").splitlines())
        if n > cap:
            over.append(f"{rel}: {n} > {cap} (archive the oldest lines to agent/archive/)")
    for hat in (REPO / "agent/roles").glob("*.md"):
        n = len(hat.read_text(encoding="utf-8").splitlines())
        if n > 45:
            over.append(f"{hat.relative_to(REPO)}: {n} > 45")
    assert not over, "\n".join(over)


def test_coach_handoff_files_do_not_leak_the_agent_system():
    for f in (REPO / "coach/handoff").glob("*.md"):
        t = f.read_text(encoding="utf-8")
        assert "agent/" not in t and "CLAUDE.md" not in t, f
