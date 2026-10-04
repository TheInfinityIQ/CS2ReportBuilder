"""Checks for current runtime documentation and named product files."""
import re
from pathlib import Path

from cs2di import config
from cs2di.report.modules import STATUS_WORDS

REPO = Path(__file__).resolve().parents[1]


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def test_verdict_words_in_code_appear_in_the_coach_docs():
    rules = read("coach/handoff/RULES.md").lower()
    for phrase in ("supported in this sample", "not proven", "no detectable difference", "not enough to tell"):
        assert any(phrase in w.lower() for w in STATUS_WORDS.values()), phrase
        assert phrase in rules, f"RULES.md no longer states the verdict phrase: {phrase}"


def test_no_count_rule_for_moments():
    bad = re.compile(r"(2|two)\s*(to|-|–)\s*(4|four)[^|\n]{0,40}(moment|lesson)|(moment|lesson)[^|\n]{0,40}(2|two)\s*(to|-|–)\s*(4|four)", re.I)
    for rel in ("coach/handoff/PROMPT.md", "coach/handoff/RULES.md", "coach/handoff/MODULES.md"):
        assert not bad.search(read(rel)), rel
    for m in re.finditer(r"(?i)(at most|max(imum)?|no more than)\s+\d+\s+(teaching )?moments", read("coach/handoff/RULES.md")):
        raise AssertionError(m.group(0))


def test_current_extractor_named_in_docs_exists_and_v77_is_labelled_superseded():
    ext = read("extractor/README.md")
    assert "Current: `extract_demos_v7dot8.py`" in ext
    assert (REPO / "extractor/extract_demos_v7dot8.py").exists()
    readme = read("README.md")
    assert "extractor (v7.8" in readme and "(v7.7)" not in readme.split("## Setup")[0]


def test_data_root_is_the_same_everywhere():
    root = str(config.DEFAULT_ROOT)
    for rel in ("README.md", "docs/DATA_FOLDER_LEGEND.snapshot.md"):
        assert root in read(rel), f"{rel} does not state {root}"


def test_packet_prompt_template_is_the_current_one():
    p = read("coach/handoff/PROMPT.md")
    assert "{{PLAYER}}" in p and "There is no target number and no limit" in p
