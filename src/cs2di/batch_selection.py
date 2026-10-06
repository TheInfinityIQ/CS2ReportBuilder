"""Batch mapping, identities and replay preflight without scientific imports."""

from __future__ import annotations
import csv
import gzip
import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from .evidence import check_demo
from .job_lock import lock_path

VIEWER_FILES = (
    "viewer_tracks.csv.gz",
    "grenade_throws.csv.gz",
    "grenade_paths.csv.gz",
    "viewer_tracks_meta.json",
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fingerprint(path):
    s = path.stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def demo_hash(path: Path, cache: dict):
    key, before = str(path.resolve()), fingerprint(path)
    if cache.get(key, {}).get("stat") == before:
        return cache[key]["sha256"]
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    if fingerprint(path) != before:
        raise ValueError(f"Demo changed while reading: {path}")
    cache[key] = {"stat": before, "sha256": h.hexdigest()}
    return h.hexdigest()


def evidence_hash(folder):
    names = ("rounds.csv", "players.csv", "player_positions.csv.gz", "events/player_death.csv.gz")
    if not all((folder / n).is_file() for n in names):
        return None
    h = hashlib.sha256()
    for name in names:
        h.update(name.encode())
        opener = gzip.open if name.endswith(".gz") else open
        with opener(folder / name, "rb") as stream:
            for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                h.update(chunk)
    return "evidence:" + h.hexdigest()


@dataclass(frozen=True)
class ReplayQuality:
    ready: bool
    hz: float
    reason: str
    sha256: str | None = None
    paths: int = 0


def replay_quality(folder: Path, expected_hash=None, hz=16, *, owned=False):
    if (not owned and lock_path(folder).exists()) or (folder / ".viewer_tracks_updating").exists():
        return ReplayQuality(False, 0, "Output busy or interrupted publication")
    if not all((folder / n).is_file() for n in VIEWER_FILES):
        return ReplayQuality(False, 0, "Viewer data missing")
    rate = 0
    try:
        meta = read_json(folder / "viewer_tracks_meta.json")
        rate = float(meta["sample_hz"])
        if expected_hash and meta.get("demo_sha256") != expected_hash:
            raise ValueError("Viewer data belongs to a different demo")
        if rate < hz or float(meta["tickrate"]) / float(meta["step_ticks"]) != rate:
            raise ValueError(f"{rate:g} Hz; {hz} Hz required")
        if not meta.get("interpolation_check", {}).get("ok"):
            raise ValueError("Interpolation validation missing or failed")
        pc = meta.get("pairing_check", {})
        if not pc.get("checked") or pc.get("fraction", 0) < 0.8:
            raise ValueError("Demo/analysis pairing unverified")
        with (folder / "rounds.csv").open(encoding="utf-8-sig", newline="") as f:
            rounds = {int(r["round"]) for r in csv.DictReader(f)}
        with (folder / "players.csv").open(encoding="utf-8-sig", newline="") as f:
            roster = {r["steamid"].strip() for r in csv.DictReader(f)}
        players, seen_rounds, previous, gaps = set(), set(), {}, Counter()
        count = 0
        with gzip.open(folder / "viewer_tracks.csv.gz", "rt", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                key, tick = (int(row["round"]), row["steamid"]), int(row["tick"])
                for name in ("x", "y", "yaw"):
                    if not math.isfinite(float(row[name])):
                        raise ValueError("Non-finite viewer coordinates or facing angle")
                if key in previous:
                    gap = tick - previous[key]
                    if gap <= 0:
                        raise ValueError("Duplicate or unordered viewer samples")
                    gaps[gap] += 1
                previous[key] = tick
                players.add(key[1])
                seen_rounds.add(key[0])
                count += 1
        if not count or not roster <= players or not rounds <= seen_rounds:
            raise ValueError("Viewer roster or round coverage incomplete")
        if not gaps or gaps.most_common(1)[0][0] != int(meta["step_ticks"]):
            raise ValueError("Actual cadence disagrees with metadata")
        path_ids = set()
        for name in ("grenade_throws.csv.gz", "grenade_paths.csv.gz"):
            with gzip.open(folder / name, "rt", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                if not (
                    {"round", "throw_id"}
                    if name == "grenade_throws.csv.gz"
                    else {"throw_id", "tick", "x", "y", "z"}
                ) <= set(reader.fieldnames or []):
                    raise ValueError("Grenade table headers missing")
                for row in reader:
                    if name == "grenade_paths.csv.gz":
                        for axis in ("x", "y", "z"):
                            if not math.isfinite(float(row[axis])):
                                raise ValueError("Non-finite grenade path")
                        path_ids.add(row["throw_id"])
        for name, digest in meta.get("sha256_files", {}).items():
            if name not in VIEWER_FILES:
                raise ValueError("Unexpected viewer checksum entry")
            if hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest:
                raise ValueError("Viewer file checksum mismatch")
        return ReplayQuality(True, rate, "Validated tracks", meta.get("demo_sha256"), len(path_ids))
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        return ReplayQuality(False, rate, str(exc))


@dataclass(frozen=True)
class Match:
    analysis: Path
    raw: Path | None
    sha256: str | None
    problem: str
    core_ready: bool
    map_name: str
    replay: ReplayQuality


def scan_matches(analysis: Path, raw: Path | None = None, cache_path: Path | None = None):
    analysis = analysis.resolve()
    cache = {}
    if cache_path and cache_path.exists():
        try:
            cache = read_json(cache_path)
        except (OSError, ValueError):
            pass
    folders = {}
    for folder in sorted(analysis.iterdir()) if analysis.is_dir() else []:
        if folder.is_dir() and not folder.is_symlink() and not folder.name.startswith("."):
            if any((folder / n).exists() for n in ("rounds.csv", "match_summary.json", "players.csv")):
                folders.setdefault(folder.name.casefold(), []).append(folder)
    candidates = []
    if raw:
        raw = raw.resolve()
        demos = sorted(
            (
                p
                for p in raw.rglob("*")
                if p.suffix.lower() == ".dem"
                and p.is_file()
                and not p.is_symlink()
                and p.resolve().is_relative_to(raw)
            ),
            key=lambda p: str(p).casefold(),
        )
        stems = Counter(p.stem.casefold() for p in demos)
        for demo in demos:
            choices = folders.get(demo.stem.casefold(), [])
            problem = (
                "Ambiguous demo name; select a narrower folder" if stems[demo.stem.casefold()] > 1 else ""
            )
            if len(choices) > 1:
                problem = "Ambiguous analysis folder"
            target = choices[0] if len(choices) == 1 else analysis / demo.stem
            candidates.append((target, demo, demo_hash(demo, cache), problem))
    else:
        for choices in folders.values():
            for folder in choices:
                sha = None
                try:
                    sha = read_json(folder / "viewer_tracks_meta.json").get("demo_sha256")
                except (OSError, ValueError):
                    pass
                candidates.append(
                    (folder, None, sha, "Ambiguous analysis folder" if len(choices) > 1 else "")
                )
    # Prefer an already valid canonical extraction over a renamed raw copy.
    candidates.sort(key=lambda item: (not check_demo(item[0]).passed, str(item[0]).casefold()))
    matches, seen = [], {}
    for folder, demo, sha, problem in candidates:
        try:
            identity = sha or evidence_hash(folder)
        except (OSError, EOFError) as exc:
            identity = None
            problem = f"Unreadable identity evidence: {exc}"
        if not problem and identity:
            if identity in seen:
                problem = f"Duplicate of {seen[identity]}"
            else:
                seen[identity] = folder.name
        gate = check_demo(folder)
        try:
            map_name = read_json(folder / "match_summary.json").get("map_name", "unknown")
        except (OSError, ValueError):
            map_name = "unknown"
        matches.append(Match(folder, demo, sha, problem, gate.passed, map_name, replay_quality(folder, sha)))
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache), encoding="utf-8")
    return tuple(matches)


def selection_record(analysis, raw, included, matches):
    return {
        "version": 1,
        "analysis": str(analysis),
        "raw": str(raw) if raw else None,
        "included": [p.name for p in included],
        "identities": {m.analysis.name: m.sha256 for m in matches if m.analysis in included and m.sha256},
    }


def match_provenance(match):
    return {
        "analysis": match.analysis.name,
        "demo_sha256": match.sha256,
        "identity_verified_from_raw": match.raw is not None,
        "replay": asdict(match.replay),
    }
