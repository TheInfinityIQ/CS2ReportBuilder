"""Prepare every transcript for a resumable knowledge review, without certifying it.

Source text and queues remain in the local data tree. No source is discarded on
length, date, language score or prior triage status. Review decisions are separate
from generated preparation records; inventory never marks a source reviewed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_player_knowledge import parse_answers  # noqa: E402
from cs2di import config  # noqa: E402

STAMP = re.compile(r"(?m)^\[(\d{1,2}:\d\d(?::\d\d)?)\]\s*")


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalized(text):
    return " ".join(re.findall(r"\w+", text.casefold()))


def prepare_text(raw):
    """Remove only leading metadata and a demonstrably duplicate plain copy.

    Auto-captions can include both plain and timestamped text. Only whitespace
    and timestamp differences are ignored; other differences retain both copies.
    Raw bytes remain available through the source path.
    """
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").splitlines(keepends=True)
    while lines and (lines[0].startswith("# ") or not lines[0].strip()):
        lines.pop(0)
    text = "".join(lines)
    first = STAMP.search(text)
    if first and text[: first.start()].strip():
        plain, stamped = text[: first.start()], text[first.start() :]
        # Preserve mathematical signs and punctuation: matching words alone can
        # falsely equate "+500" with "-500" or remove a qualification marker.
        def canonical(value):
            return re.sub(r"\s+", " ", value).strip()
        if canonical(plain) == canonical(STAMP.sub("", stamped)):
            return stamped, "duplicate_plain_copy_removed"
        return text, "parallel_text_differs_retained"
    return text, "single_copy"


def chunks(text, limit=14000):
    """Cover all characters once; offsets allow lossless source reconstruction."""
    if limit < 100:
        raise ValueError("chunk limit must be at least 100 characters")
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + limit // 2, end)
            if boundary >= 0:
                end = boundary + 1
        yield start, end, text[start:end]
        start = end


def write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8", newline="\n",
    )


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def inventory(knowledge, output, chunk_limit=14000):
    manifest = knowledge / "cs2_profile_build/triage_manifest.csv"
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        old = {(r["creator"], r["file"]): r for r in csv.DictReader(stream)}
    raw_root = knowledge / "content_creator_transcripts"
    paths = {(p.parent.parent.name, p.name): p for p in raw_root.glob("*/transcripts/*.txt")}
    output.mkdir(parents=True, exist_ok=True)
    bodies = output / "bodies"
    bodies.mkdir(exist_ok=True)
    source_rows, chunk_rows, by_content = [], [], {}
    for key in sorted(set(paths) | set(old)):
        prior = old.get(key, {})
        sid = "T-" + digest("/".join(key))[:16]
        path = paths.get(key)
        row = {
            "id": sid, "creator": key[0], "file": key[1],
            "title": prior.get("title", key[1]), "url": prior.get("url", ""),
            "date": prior.get("date", ""), "kind": prior.get("kind", "unclassified"),
            "prior_disposition": prior.get("drop_reason") or "retained",
            "review_status": "pending", "chunk_count": 0,
        }
        if path is None:
            row.update(preparation_status="missing_source", path=None)
            source_rows.append(row)
            continue
        raw_bytes = path.read_bytes()
        try:
            raw = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            row.update(preparation_status="decode_error", path=str(path.resolve()))
            source_rows.append(row)
            continue
        body, method = prepare_text(raw)
        body_hash = digest(normalized(STAMP.sub("", body)))
        row.update(
            path=str(path.resolve()), raw_sha256=hashlib.sha256(raw_bytes).hexdigest(),
            body_sha256=digest(body), content_sha256=body_hash,
            body_path=f"bodies/{sid}.txt", normalization=method,
            preparation_status="prepared", words=len(STAMP.sub("", body).split()),
            duplicate_of=by_content.get(body_hash),
        )
        by_content.setdefault(body_hash, sid)
        (bodies / f"{sid}.txt").write_text(body, encoding="utf-8", newline="\n")
        for number, (start, end, part) in enumerate(chunks(body, chunk_limit), 1):
            stamps = STAMP.findall(part)
            chunk_rows.append({
                "id": f"{sid}:{number:04d}", "source_id": sid,
                "start": start, "end": end, "words": len(part.split()),
                "first_timestamp": stamps[0] if stamps else None,
                "last_timestamp": stamps[-1] if stamps else None,
                "sha256": digest(part),
            })
            row["chunk_count"] = number
        source_rows.append(row)
    write_jsonl(output / "sources.jsonl", source_rows)
    write_jsonl(output / "chunks.jsonl", chunk_rows)
    summary = {
        "sources": len(source_rows), "chunks": len(chunk_rows),
        "prepared_words_including_retained_parallel_text": sum(r.get("words", 0) for r in source_rows),
        "preparation": dict(Counter(r["preparation_status"] for r in source_rows)),
        "prior_dispositions": dict(Counter(r["prior_disposition"] for r in source_rows)),
        "normalization": dict(Counter(r.get("normalization", "unavailable") for r in source_rows)),
        "exact_normalized_content_duplicates": sum(bool(r.get("duplicate_of")) for r in source_rows),
        "reviewed_sources": 0, "meaning": "Preparation coverage, not semantic knowledge extraction or review.",
    }
    (output / "inventory_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def batch(output, offset=0, count=3, source_id=None, context_chars=1200):
    sources = {r["id"]: r for r in read_jsonl(output / "sources.jsonl")}
    rows = read_jsonl(output / "chunks.jsonl")
    if source_id:
        rows = [r for r in rows if r["source_id"] == source_id]
    result = []
    bodies = {}
    for row in rows[offset : offset + count]:
        source = sources[row["source_id"]]
        if source["id"] not in bodies:
            if hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest() != source["raw_sha256"]:
                raise ValueError(f"Source changed: {source['id']}; rebuild inventory")
            body = (output / source["body_path"]).read_text(encoding="utf-8")
            if digest(body) != source["body_sha256"]:
                raise ValueError(f"Prepared text changed: {source['id']}; rebuild inventory")
            bodies[source["id"]] = body
        body = bodies[source["id"]]
        text = body[row["start"] : row["end"]]
        if digest(text) != row["sha256"]:
            raise ValueError(f"Chunk checksum mismatch: {row['id']}")
        result.append({
            "source": source, "chunk": row, "text": text,
            "preceding_context": body[max(0, row["start"] - context_chars):row["start"]],
            "following_context": body[row["end"]:row["end"] + context_chars],
        })
    return result


def candidates(knowledge, output):
    """Account for saved claims separately; inherited labels never confer review."""
    build = knowledge / "cs2_profile_build"
    sources = read_jsonl(output / "sources.jsonl")
    by_key = {(s["creator"], s["file"]): s["id"] for s in sources}
    by_title = {}
    for source in sources:
        by_title.setdefault(normalized(source["title"]), []).append(source["id"])
    with (build / "pilot/pilot_list.csv").open(encoding="utf-8-sig", newline="") as stream:
        pilot_sources = {r["id"]: r for r in csv.DictReader(stream)}
    records = []
    for path in sorted((build / "answers").glob("Q*.txt")):
        for row in parse_answers(path):
            row.update(
                id="A-" + row["id"], origin="saved_answer",
                source_ids=by_title.get(normalized(row["source"]), []),
                review_status="pending_source_review",
            )
            row["candidate_sha256"] = digest(json.dumps(row, sort_keys=True, ensure_ascii=False))
            records.append(row)
    for original in read_jsonl(build / "pilot/pilot_claims_verified.jsonl"):
        row = dict(original)
        ref = pilot_sources.get(row["src"], {})
        sid = by_key.get((ref.get("creator"), ref.get("file")))
        row.update(
            id="P-" + row["id"], origin="pilot_claim", source_ids=[sid] if sid else [],
            inherited_verified_label=row.pop("verified", None),
            review_status="pending_source_review",
        )
        row["candidate_sha256"] = digest(json.dumps(row, sort_keys=True, ensure_ascii=False))
        records.append(row)
    write_jsonl(output / "candidates.jsonl", records)
    # Supplemental documents include old syntheses, chat histories and design
    # documents. Inventory is metadata only, not a game-knowledge disposition.
    paths = set()
    for folder in ("ai_chat_history", "architecture_review", "onboarding_document",
                   "onboarding_pack", "player_knowledge_base", "strat_books"):
        paths.update(p for p in (knowledge / folder).rglob("*")
                     if p.is_file() and p.name != "00_INDEX.md"
                     and p.suffix.lower() in {".md", ".txt", ".json", ".docx"})
    paths.add(build / "PILOT_cs2_profile_sections.md")
    supplements = []
    for path in sorted(paths):
        relative = path.relative_to(knowledge).as_posix()
        supplements.append({
            "id": "D-" + digest(relative)[:16], "path": relative,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "review_status": "pending_scope_and_content_review",
        })
    write_jsonl(output / "supplemental_documents.jsonl", supplements)
    return {"candidates": len(records), "origins": dict(Counter(r["origin"] for r in records)),
            "supplemental_documents": len(supplements),
            "meaning": "Candidate and document accounting, not semantic extraction or verification."}


def candidate_batch(output, offset=0, count=10, source_id=None):
    rows = read_jsonl(output / "candidates.jsonl")
    if source_id:
        rows = [r for r in rows if source_id in r["source_ids"]]
    return rows[offset:offset + count]


def coverage(output):
    sources = read_jsonl(output / "sources.jsonl")
    source_index = {r["id"]: r for r in sources}
    chunk_index = {r["id"]: r for r in read_jsonl(output / "chunks.jsonl")}
    decisions_path = output / "chunk_reviews.jsonl"
    decisions = read_jsonl(decisions_path) if decisions_path.exists() else []
    lesson_path = output / "lessons.jsonl"
    lesson_rows = read_jsonl(lesson_path) if lesson_path.exists() else []
    lessons = {r["id"]: r for r in lesson_rows}
    if len(lessons) != len(lesson_rows):
        raise ValueError("Duplicate lesson IDs")
    reviewed = {}
    reviewed_by_source = {}
    for row in decisions:
        cid = row["chunk_id"]
        if cid in reviewed:
            raise ValueError(f"Duplicate review decision: {cid}")
        if cid not in chunk_index or row["chunk_sha256"] != chunk_index[cid]["sha256"]:
            raise ValueError(f"Unknown or stale review: {cid}")
        if row["disposition"] not in {"lessons_extracted", "duplicate", "irrelevant", "unresolved"}:
            raise ValueError(f"Invalid disposition: {cid}")
        if not row.get("reason") or not row.get("reviewer"):
            raise ValueError(f"Review needs reasoning and reviewer: {cid}")
        if row["disposition"] == "duplicate" and not row.get("duplicate_of"):
            raise ValueError(f"Duplicate review needs reference: {cid}")
        if row["disposition"] == "lessons_extracted" and not row.get("lesson_ids"):
            raise ValueError(f"Extraction needs lesson references: {cid}")
        for lid in row.get("lesson_ids", []):
            if lid not in lessons or cid not in lessons[lid].get("chunk_ids", []):
                raise ValueError(f"Missing or unrelated lesson {lid}: {cid}")
        reviewed[cid] = row
        reviewed_by_source.setdefault(chunk_index[cid]["source_id"], []).append(cid)
    for sid, ids in reviewed_by_source.items():
        source = source_index[sid]
        if hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest() != source["raw_sha256"]:
            raise ValueError(f"Reviewed source changed: {sid}; rebuild and re-review")
        body = (output / source["body_path"]).read_text(encoding="utf-8")
        if digest(body) != source["body_sha256"]:
            raise ValueError(f"Reviewed prepared text changed: {sid}; rebuild and re-review")
        for cid in ids:
            chunk = chunk_index[cid]
            if digest(body[chunk["start"]:chunk["end"]]) != chunk["sha256"]:
                raise ValueError(f"Reviewed chunk changed: {cid}")
    for lesson in lesson_rows:
        if "support_context" in lesson and digest(lesson["support_context"]) != lesson.get("context_sha256"):
            raise ValueError(f"Lesson support context changed: {lesson['id']}")
    complete = 0
    for source in sources:
        ids = [f"{source['id']}:{n:04d}" for n in range(1, source["chunk_count"] + 1)]
        if ids and all(cid in reviewed and reviewed[cid]["disposition"] != "unresolved" for cid in ids):
            complete += 1
    return {
        "sources": len(sources), "chunks": len(chunk_index),
        "review_decisions": len(reviewed), "fully_reviewed_sources": complete,
        "unresolved_chunks": sum(r["disposition"] == "unresolved" for r in reviewed.values()),
        "pending_chunks": len(chunk_index) - len(reviewed),
        "recorded_lessons": len(lessons),
        "meaning": "Human/agent recorded review coverage; no automatic entailment certification.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inventory", "batch", "candidates", "candidate-batch", "coverage"])
    parser.add_argument("--knowledge", type=Path, default=config.root() / "05_Coach_Knowledge")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--chunk-limit", type=int, default=14000)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--source-id")
    args = parser.parse_args()
    if args.offset < 0 or args.count < 1:
        parser.error("offset must be nonnegative and count positive")
    output = args.output or args.knowledge / "cs2_profile_build/comprehensive_build"
    result = (inventory(args.knowledge, output, args.chunk_limit) if args.command == "inventory"
              else batch(output, args.offset, args.count, args.source_id) if args.command == "batch"
              else candidates(args.knowledge, output) if args.command == "candidates"
              else candidate_batch(output, args.offset, args.count, args.source_id) if args.command == "candidate-batch"
              else coverage(output))
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
