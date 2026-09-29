"""Hard integrity gate over an analyzed (schema 3.6+/3.7) demo folder.

Fails closed: a missing or malformed file is a failure, never a pass. A soft
warning never fails a demo (it is reported so the metric layer can decide).
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED = ("match_summary.json", "integrity_checks.json", "players.csv", "rounds.csv", "player_rounds.csv")


@dataclass(frozen=True)
class DemoGate:
    demo_id: str
    path: Path
    passed: bool
    reasons: tuple[str, ...] = ()
    map_name: str | None = None
    n_rounds: int | None = None
    schema_version: str | None = None
    source_family: str | None = None
    soft_warnings: int = 0
    warning_codes: tuple[str, ...] = field(default_factory=tuple)


def _load(path: Path):
    with path.open(encoding="utf8") as fh:
        return json.load(fh)


def check_demo(path: Path) -> DemoGate:
    path = Path(path)
    demo_id = path.name
    reasons: list[str] = []
    if not path.is_dir():
        return DemoGate(demo_id, path, False, ("not_a_directory",))
    for name in REQUIRED:
        if not (path / name).is_file():
            reasons.append(f"missing_file:{name}")
    if reasons:
        return DemoGate(demo_id, path, False, tuple(reasons))
    try:
        ms = _load(path / "match_summary.json")
        ic = _load(path / "integrity_checks.json")
    except (OSError, ValueError) as e:
        return DemoGate(demo_id, path, False, (f"unreadable_json:{e.__class__.__name__}",))

    if ms.get("valid") is not True:
        reasons.append("match_summary.valid_not_true")
    if ms.get("coaching_valid") is not True:
        reasons.append("match_summary.coaching_valid_not_true")
    if ic.get("integrity_ok") is not True:
        reasons.append("integrity_checks.integrity_ok_not_true")
    if ms.get("integrity_hard_failure_count") != 0:
        reasons.append("hard_failure_count_nonzero_or_missing")
    if ic.get("errors"):
        reasons.append("integrity_errors_present")
    codes = tuple(w.get("code", "?") for w in ic.get("warnings", []) if isinstance(w, dict))
    return DemoGate(
        demo_id, path, not reasons, tuple(reasons),
        map_name=ms.get("map_name"), n_rounds=ms.get("n_rounds"),
        schema_version=ms.get("schema_version"), source_family=ms.get("demo_source_family"),
        soft_warnings=len(codes), warning_codes=codes,
    )


def scan_batch(batch_dir: Path) -> list[DemoGate]:
    """Gate every demo folder directly under ``batch_dir`` (sorted, deterministic)."""
    batch_dir = Path(batch_dir)
    return [check_demo(p) for p in sorted(batch_dir.iterdir()) if p.is_dir()]


def roster(path: Path) -> dict[int, str]:
    """SteamID64 -> display name for a demo. IDs parsed as text, never via float."""
    out: dict[int, str] = {}
    with (Path(path) / "players.csv").open(encoding="utf8", newline="") as fh:
        for row in csv.DictReader(fh):
            out[int(row["steamid"])] = row["name"]
    return out
