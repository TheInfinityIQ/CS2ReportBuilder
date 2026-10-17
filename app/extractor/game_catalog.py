"""Rebuildable local game/roster catalog. Cached validation never replaces build gates.

The identical stdlib-only module ships beside standalone extractors. When the
full package is unavailable it publishes pending records for validation by the UI.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from .demo_layout import data_root
except ImportError:
    from demo_layout import data_root

VERSION = 1
# Bump when core/replay validation semantics change, independently of SQLite schema.
VALIDATION_REVISION = 1


def signature(folder):
    """Detect additions, removals and edits without decoding evidence tables."""
    if not folder.is_dir() or folder.is_symlink():
        return None
    files = []
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            return None
        if path.is_file() and path.name != "00_INDEX.md":
            stat = path.stat()
            files.append(
                [
                    path.relative_to(folder).as_posix(),
                    stat.st_size,
                    stat.st_mtime_ns,
                    stat.st_ctime_ns,
                    stat.st_ino,
                ]
            )
    return files


def file_stamp(path):
    stat = path.stat()
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


def roster(folder):
    try:
        with (folder / "players.csv").open(encoding="utf-8-sig", newline="") as stream:
            return [
                {"steamid": row["steamid"].strip(), "name": row["name"].strip()}
                for row in csv.DictReader(stream)
                if re.fullmatch(r"\d{17}", row.get("steamid", "").strip()) and int(row["steamid"].strip()) > 0
            ]
    except (OSError, ValueError, KeyError):
        return []


def team_hints(stem):
    match = re.fullmatch(
        r"(.+)-vs-(.+?)-(?:m\d+-)?(?:ancient|anubis|dust2|inferno|mirage|nuke|overpass|train|vertigo)(?:-p\d+)?",
        stem,
    )
    return list(match.groups()) if match else []


class Catalog:
    def __init__(self, path=None):
        self.path = Path(path) if path else data_root() / "game_catalog.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, VERSION):
                raise ValueError(f"Unsupported game catalog version {version}")
            db.execute(
                "CREATE TABLE IF NOT EXISTS games (analysis TEXT PRIMARY KEY, collection TEXT NOT NULL, signature TEXT, expected_hash TEXT, verified INTEGER NOT NULL, payload TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS players (analysis TEXT NOT NULL, steamid TEXT NOT NULL, name TEXT NOT NULL, PRIMARY KEY (analysis, steamid))"
            )
            db.execute("CREATE INDEX IF NOT EXISTS player_games ON players(steamid)")
            db.execute(
                "CREATE TABLE IF NOT EXISTS teams (analysis TEXT NOT NULL, name TEXT NOT NULL, PRIMARY KEY (analysis, name))"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS sources (raw TEXT PRIMARY KEY, analysis TEXT NOT NULL, fingerprint TEXT, sha256 TEXT)"
            )
            db.execute(f"PRAGMA user_version={VERSION}")

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def get(self, folder, expected_hash=None):
        folder = folder.resolve()
        if (folder / ".viewer_tracks_updating").exists():
            return None
        try:
            from .job_lock import lock_path

            lock = lock_path(folder)
        except ImportError:
            from job_lock import lock_path

            lock = lock_path(folder)
        if lock.exists():
            return None
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT signature, expected_hash, verified, payload FROM games WHERE analysis=?",
                (str(folder),),
            ).fetchone()
        if not row or not row[2] or row[1] != expected_hash:
            return None
        if json.loads(row[0]) != signature(folder):
            return None
        payload = json.loads(row[3])
        # Initial v1 population predates the explicit revision field.
        if payload.get("validation_revision", 1) != VALIDATION_REVISION:
            return None
        return payload

    def put(self, folder, expected_hash, before, payload, *, verified=True, owned=False):
        folder = folder.resolve()
        if before is None or before != signature(folder) or (folder / ".viewer_tracks_updating").exists():
            return False
        try:
            from .job_lock import lock_path
        except ImportError:
            from job_lock import lock_path
        if not owned and lock_path(folder).exists():
            return False
        payload = {
            **payload,
            "roster": roster(folder),
            "teams": team_hints(folder.name),
            "validated_at": datetime.now(timezone.utc).isoformat() if verified else None,
            "validation_revision": VALIDATION_REVISION,
        }
        if before != signature(folder):
            return False
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT OR REPLACE INTO games VALUES (?,?,?,?,?,?)",
                (
                    str(folder),
                    str(folder.parent),
                    json.dumps(before),
                    expected_hash,
                    int(verified),
                    json.dumps(payload),
                ),
            )
            db.execute("DELETE FROM players WHERE analysis=?", (str(folder),))
            db.executemany(
                "INSERT OR REPLACE INTO players VALUES (?,?,?)",
                [(str(folder), p["steamid"], p["name"]) for p in payload["roster"]],
            )
            db.execute("DELETE FROM teams WHERE analysis=?", (str(folder),))
            db.executemany(
                "INSERT OR REPLACE INTO teams VALUES (?,?)",
                [(str(folder), team) for team in payload["teams"]],
            )
        return True

    def source_hash(self, raw):
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT fingerprint, sha256 FROM sources WHERE raw=?", (str(raw.resolve()),)
            ).fetchone()
        return row[1] if row and row[0] and json.loads(row[0]) == file_stamp(raw) else None

    def register_source(self, raw, folder, sha=None, *, stamp=None):
        raw = raw.resolve()
        if sha is None:
            sha = self.source_hash(raw)
            stamp = file_stamp(raw) if sha else None
        verified_stamp = json.dumps(stamp) if sha and stamp is not None and stamp == file_stamp(raw) else None
        if verified_stamp is None:
            sha = None
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT OR REPLACE INTO sources VALUES (?,?,?,?)",
                (str(raw), str(folder.resolve()), verified_stamp, sha),
            )

    def rosters(self, collection):
        with closing(self.connect()) as db:
            rows = db.execute(
                "SELECT analysis, payload FROM games WHERE collection=? AND verified=1",
                (str(collection.resolve()),),
            ).fetchall()
        return {Path(path): json.loads(text)["roster"] for path, text in rows}

    def games(self, *, player=None, collection=None, raw_folder=None, team=None):
        """Query availability. Team names are filename hints, not roster affiliation."""
        query, values = "SELECT g.analysis, g.verified, g.payload FROM games g WHERE 1=1", []
        if player:
            query += " AND EXISTS(SELECT 1 FROM players p WHERE p.analysis=g.analysis AND p.steamid=?)"
            values.append(player)
        if collection:
            query += " AND g.collection=?"
            values.append(str(Path(collection).resolve()))
        if team:
            query += (
                " AND EXISTS(SELECT 1 FROM teams t WHERE t.analysis=g.analysis AND t.name=? COLLATE NOCASE)"
            )
            values.append(team)
        with closing(self.connect()) as db:
            rows = db.execute(query + " ORDER BY g.analysis", values).fetchall()
            sources = db.execute("SELECT raw, analysis FROM sources").fetchall()
        found = []
        for path, verified, text in rows:
            if not Path(path).is_dir():
                continue
            raw_paths = [raw for raw, analysis in sources if analysis == path and Path(raw).is_file()]
            if raw_folder and not any(
                Path(raw).is_relative_to(Path(raw_folder).resolve()) for raw in raw_paths
            ):
                continue
            found.append(
                {"analysis": path, "verified": bool(verified), "raw_paths": raw_paths, **json.loads(text)}
            )
        return found

    def prune(self, collection):
        with closing(self.connect()) as db, db:
            paths = db.execute(
                "SELECT analysis FROM games WHERE collection=?", (str(collection.resolve()),)
            ).fetchall()
            for (path,) in paths:
                if not Path(path).is_dir():
                    for table in ("games", "players", "teams", "sources"):
                        db.execute(f"DELETE FROM {table} WHERE analysis=?", (path,))


def open_catalog(path=None, *, recover=False, log=print):
    try:
        return Catalog(path)
    except sqlite3.DatabaseError as exc:
        if not recover or getattr(exc, "sqlite_errorcode", None) not in {
            sqlite3.SQLITE_CORRUPT,
            sqlite3.SQLITE_NOTADB,
        }:
            raise
        from uuid import uuid4

        target = Path(path) if path else data_root() / "game_catalog.sqlite3"
        backup = target.with_name(target.name + ".broken_" + uuid4().hex)
        target.rename(backup)
        log(f"Preserved unreadable catalog at {backup}; rebuilding from source files.")
        return Catalog(target)


def notify_output(folder, source=None, quality=None, *, owned=False, source_sha=None, source_stamp=None):
    """Catalog failures are reported but cannot turn successful extraction into failure."""
    try:
        folder = Path(folder).resolve()
        catalog = Catalog()
        if not folder.is_dir():
            catalog.prune(folder.parent)
            return
        before = signature(folder)
        meta_path = folder / "viewer_tracks_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
        sha = meta.get("demo_sha256")
        try:
            from .batch_selection import replay_quality, evidence_hash
            from .evidence import check_demo

            gate = check_demo(folder)
            quality = quality or replay_quality(folder, sha, owned=owned)
            payload = {
                "evidence_identity": sha or evidence_hash(folder),
                "core_ready": gate.passed,
                "replay": asdict(quality),
                "map_name": meta.get("map", "unknown"),
            }
            summary = folder / "match_summary.json"
            if summary.exists():
                payload["map_name"] = json.loads(summary.read_text(encoding="utf-8")).get(
                    "map_name", "unknown"
                )
            verified = True
        except ImportError:
            payload = {
                "core_ready": False,
                "replay": {"ready": False, "hz": 0, "reason": "Awaiting catalog validation"},
                "map_name": "unknown",
            }
            verified = False
        catalog.put(folder, sha, before, payload, verified=verified, owned=owned)
        if source:
            catalog.register_source(Path(source), folder, source_sha, stamp=source_stamp)
    except Exception as exc:
        print(f"WARNING: game catalog update deferred: {exc}", flush=True)
