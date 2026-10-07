import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "knowledge_audit", Path(__file__).resolve().parents[1] / "scripts/audit_player_knowledge.py"
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_answer_labels_and_question_boundaries(tmp_path):
    path = tmp_path / "Q13-Q21.txt"
    path.write_text(
        '### Q13 Buying\nCLAIM: One claim. | QUOTE: "One exact quotation." | SOURCE: Video | WHO: Coach '
        'CLAIM: Another claim. | QUOTE: "Another quotation." | SOURCE: Other | WHO: Another\n'
        "### Q14 Saving\nCLAIM A plain claim.  QUOTE Plain quotation.  SOURCE Third  WHO Third coach\n",
        encoding="utf-8",
    )
    records = audit.parse_answers(path)
    assert [r["question"] for r in records] == [13, 13, 14]
    assert [r["creator"] for r in records] == ["Coach", "Another", "Third coach"]
    assert all(r["parse_complete"] for r in records)
    assert records[-1]["claim"] == "A plain claim."


def source(number, text):
    return {
        "id": str(number),
        "bundle": "cs2_bundle_01.txt",
        "creator": "Coach",
        "date": "2026-01-01",
        "title": "Video",
        "url": "https://example.com",
        "normalized": audit.norm(text),
    }


def test_location_does_not_promote_ellipsis_or_ambiguous_quotes():
    first = "one two three four five six seven"
    last = "eight nine ten eleven twelve thirteen fourteen"
    record = {"quote": first + " ... " + last, "source": "cs2_bundle_01.txt"}
    assert audit.locate(record, [source(1, first), source(2, last)])["location_status"] == "not_located"
    together = source(1, first + " omitted words " + last)
    assert audit.locate(record, [together])["location_status"] == "ellipsis_segments_only"
    assert (
        audit.locate(record, [together, source(2, together["normalized"])])["location_status"]
        == "ambiguous_quote"
    )


def test_declared_bundle_scope_and_missing_quote():
    record = {"quote": "one two three four five six seven", "source": "cs2\\_bundle\\_02.txt"}
    assert audit.locate(record, [source(1, record["quote"])])["location_status"] == "not_located"
    record["quote"] = ""
    assert audit.locate(record, [source(1, "anything")])["location_status"] == "too_short_to_anchor"
