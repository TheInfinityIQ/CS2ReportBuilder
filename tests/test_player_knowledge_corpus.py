"""Full-source preparation must not silently discard knowledge or certify review."""

import csv
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "knowledge_corpus", Path(__file__).resolve().parents[1] / "scripts/build_player_knowledge_corpus.py"
)
corpus = importlib.util.module_from_spec(spec)
spec.loader.exec_module(corpus)


def test_parallel_text_removed_only_when_all_words_match():
    same = "# Title\r\n# https://example.com\r\n\r\nProtect the bomb.\r\n[00:00] Protect the\r\n[00:02] bomb.\r\n"
    body, method = corpus.prepare_text(same)
    assert method == "duplicate_plain_copy_removed"
    assert body == "[00:00] Protect the\n[00:02] bomb.\n"
    different = "# Title\nProtect the bomb and keep support.\n[00:00] Protect the bomb.\n"
    body, method = corpus.prepare_text(different)
    assert method == "parallel_text_differs_retained"
    assert "keep support" in body
    signed = "# title\nAward changes by +500.\n[00:00] Award changes by -500.\n"
    body, method = corpus.prepare_text(signed)
    assert method == "parallel_text_differs_retained"
    assert "+500" in body and "-500" in body


def test_chunks_cover_every_character_and_can_be_reconstructed():
    text = ("A very long caption without a convenient line break " * 45) + "\nLast short.\n"
    parts = list(corpus.chunks(text, 200))
    assert "".join(p[2] for p in parts) == text
    assert parts[0][0] == 0 and parts[-1][1] == len(text)
    assert all(a[1] == b[0] for a, b in zip(parts, parts[1:]))


def fixture(knowledge):
    build = knowledge / "cs2_profile_build"
    build.mkdir(parents=True)
    fields = ["creator", "file", "date", "kind", "drop_reason", "title", "url"]
    with (build / "triage_manifest.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for name, reason in [("short.txt", "too_short"), ("stream.txt", "livestream_deferred"), ("old.txt", "pre_cs2_2023-09-27"), ("missing.txt", "")]:
            writer.writerow(dict(creator="coach", file=name, date="2024-01-01", kind="other", drop_reason=reason, title=name, url=""))
    raw = knowledge / "content_creator_transcripts/coach/transcripts"
    raw.mkdir(parents=True)
    for name in ["short.txt", "stream.txt", "old.txt", "new.txt"]:
        (raw / name).write_text("# title\n[00:00] Wait until support is ready.\n", encoding="utf-8")


def test_inventory_keeps_excluded_new_and_missing_sources_without_certifying_review(tmp_path):
    knowledge, output = tmp_path / "knowledge", tmp_path / "out"
    fixture(knowledge)
    summary = corpus.inventory(knowledge, output)
    assert summary["sources"] == 5
    assert summary["preparation"] == {"prepared": 4, "missing_source": 1}
    assert summary["reviewed_sources"] == 0
    assert len(corpus.batch(output, count=10)) == 4
    assert corpus.coverage(output)["fully_reviewed_sources"] == 0
    assert corpus.coverage(output)["pending_chunks"] == 4
    before = (output / "sources.jsonl").read_bytes()
    corpus.inventory(knowledge, output)
    assert (output / "sources.jsonl").read_bytes() == before


def test_prepared_text_edits_and_stale_review_decisions_are_rejected(tmp_path):
    knowledge, output = tmp_path / "knowledge", tmp_path / "out"
    fixture(knowledge)
    corpus.inventory(knowledge, output)
    row = next(r for r in corpus.read_jsonl(output / "sources.jsonl") if r["preparation_status"] == "prepared")
    (output / row["body_path"]).write_text("Changed", encoding="utf-8")
    with pytest.raises(ValueError, match="Prepared text changed"):
        corpus.batch(output, source_id=row["id"])
    chunk = corpus.read_jsonl(output / "chunks.jsonl")[0]
    corpus.write_jsonl(output / "chunk_reviews.jsonl", [{"chunk_id": chunk["id"], "chunk_sha256": "stale"}])
    with pytest.raises(ValueError, match="stale review"):
        corpus.coverage(output)


def test_extracted_review_needs_real_related_lesson_and_all_chunks(tmp_path):
    knowledge, output = tmp_path / "knowledge", tmp_path / "out"
    fixture(knowledge)
    corpus.inventory(knowledge, output)
    chunk = corpus.read_jsonl(output / "chunks.jsonl")[0]
    review = {"chunk_id": chunk["id"], "chunk_sha256": chunk["sha256"], "disposition": "lessons_extracted", "reason": "Inspected support cue", "reviewer": "test", "lesson_ids": ["L1"]}
    corpus.write_jsonl(output / "chunk_reviews.jsonl", [review])
    with pytest.raises(ValueError, match="Missing or unrelated"):
        corpus.coverage(output)
    corpus.write_jsonl(output / "lessons.jsonl", [{"id": "L1", "chunk_ids": [chunk["id"]]}])
    assert corpus.coverage(output)["fully_reviewed_sources"] == 1
    assert corpus.coverage(output)["pending_chunks"] == 3


def test_review_coverage_detects_source_change_and_duplicate_lesson_ids(tmp_path):
    knowledge, output = tmp_path / "knowledge", tmp_path / "out"
    fixture(knowledge)
    corpus.inventory(knowledge, output)
    chunk = corpus.read_jsonl(output / "chunks.jsonl")[0]
    review = {"chunk_id": chunk["id"], "chunk_sha256": chunk["sha256"],
              "disposition": "irrelevant", "reason": "Inspected", "reviewer": "test"}
    corpus.write_jsonl(output / "chunk_reviews.jsonl", [review])
    source = next(r for r in corpus.read_jsonl(output / "sources.jsonl") if r["id"] == chunk["source_id"])
    Path(source["path"]).write_text("Changed raw caption", encoding="utf-8")
    with pytest.raises(ValueError, match="Reviewed source changed"):
        corpus.coverage(output)
    corpus.write_jsonl(output / "lessons.jsonl", [{"id": "same"}, {"id": "same"}])
    with pytest.raises(ValueError, match="Duplicate lesson IDs"):
        corpus.coverage(output)


def test_candidate_inventory_preserves_unverified_labels_and_missing_sources(tmp_path):
    knowledge, output = tmp_path / "knowledge", tmp_path / "out"
    fixture(knowledge)
    corpus.inventory(knowledge, output)
    build = knowledge / "cs2_profile_build"
    (build / "answers").mkdir()
    (build / "answers/Q1.txt").write_text(
        'CLAIM: Wait for support. QUOTE: Wait until support is ready. SOURCE: short.txt WHO: coach\n',
        encoding="utf-8",
    )
    (build / "pilot").mkdir()
    (build / "pilot/pilot_list.csv").write_text("id,creator,file\nP01,coach,short.txt\n", encoding="utf-8")
    corpus.write_jsonl(build / "pilot/pilot_claims_verified.jsonl", [
        {"id": "C001", "src": "P01", "claim": "Wait", "quote": "Wait", "verified": "supported"},
        {"id": "C002", "src": "missing", "claim": "Unknown", "quote": "Unknown", "verified": "trimmed"},
    ])
    (build / "PILOT_cs2_profile_sections.md").write_text("Old synthesis", encoding="utf-8")
    (knowledge / "ai_chat_history").mkdir()
    (knowledge / "ai_chat_history/old_chat.txt").write_text("Historical discussion", encoding="utf-8")
    assert corpus.candidates(knowledge, output)["candidates"] == 3
    records = corpus.read_jsonl(output / "candidates.jsonl")
    assert all(r["review_status"] == "pending_source_review" for r in records)
    assert records[1]["inherited_verified_label"] == "supported"
    assert records[2]["source_ids"] == []
    assert all(len(r["candidate_sha256"]) == 64 for r in records)
    sid = records[1]["source_ids"][0]
    assert len(corpus.candidate_batch(output, count=10, source_id=sid)) == 2
    documents = corpus.read_jsonl(output / "supplemental_documents.jsonl")
    assert len(documents) == 2
    assert all(r["review_status"] == "pending_scope_and_content_review" for r in documents)
    assert json.loads((output / "candidates.jsonl").read_text(encoding="utf-8").splitlines()[1])["id"] == "P-C001"
