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
    for name, slug in hats.items():
        assert (REPO / f"agent/roles/{slug}.md").exists()
        assert name in router
