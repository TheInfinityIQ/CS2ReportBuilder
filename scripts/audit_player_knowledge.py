"""Inventory candidate player knowledge and locate quotes; never certify entailment.

Writes a local audit, not changes to the source corpus. Quotes are normalized for
punctuation/case/spacing; ellipsis segments are reported separately from full hits.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cs2di import config  # noqa: E402


def norm(text):
    return " ".join(re.findall(r"\w+", text.casefold().replace("\\", "")))


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def parse_answers(path):
    """Accept colon/pipe and plain label formats, including several claims per line."""
    text = path.read_text(encoding="utf-8")
    starts = list(re.finditer(r"\bCLAIM(?::|\s)", text))
    questions = list(re.finditer(r"(?m)^\s*#{1,6}\s*Q(\d+)\b", text))
    default = int(re.search(r"Q(\d+)", path.name)[1])
    records = []
    for number, start in enumerate(starts, 1):
        end = starts[number].start() if number < len(starts) else len(text)
        body = text[start.end() : end]
        parts = re.split(r"\b(QUOTE|SOURCE|WHO)\s*:?[ \t]*", body)
        record = {
            "id": f"{path.stem}-{number:03d}",
            "answer_file": path.name,
            "question": max([int(q[1]) for q in questions if q.start() < start.start()] or [default]),
            "claim": parts[0].strip(" \n|:*"),
            "quote": "",
            "source": "",
            "creator": "",
        }
        for label, value in zip(parts[1::2], parts[2::2]):
            value = value.strip(" \n|:*")
            if label == "WHO":
                value = value.splitlines()[0].strip()
            record[{"QUOTE": "quote", "SOURCE": "source", "WHO": "creator"}[label]] = value.strip('"“”')
        record["parse_complete"] = all(record[key] for key in ("claim", "quote", "source", "creator"))
        records.append(record)
    return records


def load_sources(root):
    sources = []
    header = re.compile(
        r"(?m)^=== SOURCE \| creator: (.*?) \| date: (.*?) \| title: (.*?) \| url: (.*?) ===$"
    )
    for bundle in sorted((root / "bundles").glob("cs2_bundle_*.txt")):
        text = bundle.read_text(encoding="utf-8")
        headings = list(header.finditer(text))
        for index, match in enumerate(headings):
            body = text[match.end() : headings[index + 1].start() if index + 1 < len(headings) else len(text)]
            sources.append(
                {
                    "id": f"{bundle.stem}:{index + 1:03d}",
                    "bundle": bundle.name,
                    "creator": match[1],
                    "date": match[2],
                    "title": match[3],
                    "url": match[4],
                    "text": body,
                    "normalized": norm(body),
                }
            )
    return sources


def locate(record, sources):
    declared = record["source"].replace("\\", "")
    bundle = re.search(r"cs2_bundle_\d+\.txt", declared)
    pool = [s for s in sources if s["bundle"] == bundle[0]] if bundle else sources
    quote = norm(record["quote"])
    if len(quote.split()) < 6:
        return {"location_status": "too_short_to_anchor", "matches": []}
    hits = [s for s in pool if quote in s["normalized"]]
    status = "full_normalized_quote"
    if not hits:
        segments = [norm(x) for x in re.split(r"\.{3}|…", record["quote"])]
        segments = [s for s in segments if len(s.split()) >= 6]
        # Do not silently turn partial matching into a verbatim/entailment check.
        if len(segments) > 1:
            hits = [s for s in pool if all(segment in s["normalized"] for segment in segments)]
            status = "ellipsis_segments_only"
    if not hits:
        return {"location_status": "not_located", "matches": []}
    return {
        "location_status": status if len(hits) == 1 else "ambiguous_quote",
        "matches": [{k: s[k] for k in ("id", "bundle", "creator", "date", "title", "url")} for s in hits],
    }


def audit(root):
    manifest = read_csv(root / "triage_manifest.csv")
    index = read_csv(root / "bundles_index.csv")
    sources = load_sources(root)
    answers = [record for path in sorted((root / "answers").glob("Q*.txt")) for record in parse_answers(path)]
    for record in answers:
        record.update(locate(record, sources))
    pilot = [
        json.loads(line)
        for line in (root / "pilot/pilot_claims_verified.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    dropped = [r for r in manifest if r["drop_reason"] == "too_short"]
    summary = {
        "manifest_sources": len(manifest),
        "retained_sources": len(index),
        "retained_words_from_index": sum(int(r["words"]) for r in index),
        "bundle_source_headers": len(sources),
        "parsed_answer_claims": len(answers),
        "incomplete_answer_records": sum(not r["parse_complete"] for r in answers),
        "quote_locations": dict(Counter(r["location_status"] for r in answers)),
        "question_coverage": dict(sorted(Counter(r["question"] for r in answers).items())),
        "pilot_claims": len(pilot),
        "pilot_recorded_labels": dict(Counter(r["verified"] for r in pilot)),
        "pilot_era_labels": dict(Counter(r["era"] for r in pilot)),
        "too_short_exclusions": len(dropped),
        "too_short_by_creator": dict(Counter(r["creator"] for r in dropped)),
        "too_short_post_cs2_dated": sum(r["date"] >= "2023-09-27" for r in dropped if r["date"]),
        "limits": "Quote location is not claim support, creator attribution validation, current-game verification or human calibration. Pilot labels are inherited, not independently certified.",
    }
    return summary, answers, dropped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=config.root() / "05_Coach_Knowledge/cs2_profile_build")
    parser.add_argument(
        "--output", type=Path, default=config.root() / "05_Coach_Knowledge/cs2_profile_build/audit_2026-10-07"
    )
    args = parser.parse_args()
    summary, answers, dropped = audit(args.source)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (args.output / "answer_claims.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in answers), encoding="utf-8", newline="\n"
    )
    (args.output / "excluded_short_sources.json").write_text(
        json.dumps(dropped, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
