"""Local UI jobs: select evidence and publish a packet only after its build passes."""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .evidence import check_demo


@dataclass(frozen=True)
class Player:
    steamid: str
    name: str
    demos: tuple[Path, ...]


@dataclass(frozen=True)
class Batch:
    path: Path
    players: tuple[Player, ...]
    accepted: int
    excluded: tuple[str, ...]
    ignored: int


def discover_batches(analysis_root: Path) -> list[Path]:
    if not analysis_root.is_dir():
        return []
    return sorted((p for p in analysis_root.iterdir()
                   if p.is_dir() and not p.is_symlink() and p.name.startswith("analyzed_")),
                  key=lambda p: p.name.casefold())


def inspect_batch(path: Path) -> Batch:
    """Read rosters as strings, gate candidates, and expose exclusions to the user."""
    path = path.resolve()
    coverage: dict[str, list[Path]] = {}
    names: dict[str, Counter] = {}
    excluded = []
    ignored = accepted = 0
    for demo in sorted(path.iterdir()):
        if not demo.is_dir():
            continue
        if demo.is_symlink() or demo.name.startswith("."):
            ignored += 1
            continue
        if not any((demo / f).exists() for f in ("match_summary.json", "players.csv", "integrity_checks.json")):
            ignored += 1
            continue
        gate = check_demo(demo)
        if not gate.passed:
            excluded.append(f"{demo.name}: {', '.join(gate.reasons)}")
            continue
        try:
            with (demo / "players.csv").open(encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
            roster = {}
            for row in rows:
                sid = row["steamid"].strip()
                if re.fullmatch(r"\d{17}", sid) and int(sid) > 0:
                    roster[sid] = row["name"].strip() or sid
            if not roster:
                raise ValueError("no readable SteamID64 player roster")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            excluded.append(f"{demo.name}: player roster cannot be read ({exc})")
            continue
        accepted += 1
        for sid, name in roster.items():
            coverage.setdefault(sid, []).append(demo)
            names.setdefault(sid, Counter())[name] += 1
    players = [Player(sid, names[sid].most_common(1)[0][0], tuple(demos)) for sid, demos in coverage.items()]
    players.sort(key=lambda p: (-len(p.demos), p.name.casefold(), p.steamid))
    return Batch(path, tuple(players), accepted, tuple(excluded), ignored)


def python_for(repo: Path) -> Path:
    for relative in (".venv/Scripts/python.exe", ".venv/bin/python"):
        candidate = repo / relative
        if candidate.is_file():
            return candidate
    current = Path(sys.executable)
    console = current.with_name("python.exe") if current.name.lower() == "pythonw.exe" else current
    return console


def process_options() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def check_dependencies(python: Path):
    result = subprocess.run([str(python), "-c", "import pandas, pyarrow, scipy, PIL"],
                            capture_output=True, text=True, **process_options())
    if result.returncode:
        raise RuntimeError("The packet builder's Python dependencies are missing.\n"
                           f'From the repository, run:\n& "{python}" -m pip install -e .\n\n'
                           + result.stderr.strip())


def choose_example(repo: Path, steamid: str) -> Path:
    with (repo / "docs/PLAYER_UNIT_COUNTS.csv").open(encoding="utf-8-sig", newline="") as fh:
        identities = {r["name"].casefold(): r["steamid"] for r in csv.DictReader(fh)}
    for name, relative in (("mimy", "examples/mimy/coach_plan_v3.json"),
                           ("itrilogyy", "examples/itrilogy/coach_plan_v3.4.json")):
        p = repo / relative
        if p.is_file() and name in identities and identities[name] != steamid:
            return p
    raise ValueError("No example plan for a different player is available.")


def build_packet(repo: Path, batch: Batch, player: Player, output_root: Path, *,
                 kind="pug", on_log=lambda line: None, runner=None) -> Path:
    repo, output_root = repo.resolve(), output_root.resolve()
    if output_root.is_relative_to(batch.path) or batch.path.is_relative_to(output_root):
        raise ValueError("Choose a packet destination outside the analysis folder and its parents.")
    if player not in batch.players or not player.demos:
        raise ValueError("Select a player with at least one usable match.")
    python = python_for(repo)
    check_dependencies(python)
    example = choose_example(repo, player.steamid)
    for demo in player.demos:
        if demo.parent != batch.path or demo.is_symlink() or not check_demo(demo).passed:
            raise ValueError(f"Analysis changed or failed validation: {demo.name}. Refresh the batch.")
    label = re.sub(r"[^A-Za-z0-9_-]+", "_", player.name).strip("_")[:40] or "player"
    pid = f"P_{label}_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
    output_root.mkdir(parents=True, exist_ok=True)
    stage = output_root / f".{pid}.building"
    stage.mkdir()  # exclusive reservation; concurrent jobs cannot share this folder
    snapshot, packet = stage / "input_batch", stage / "packet"
    snapshot.mkdir()
    log_path = stage / "build.log"
    def log(line):
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        on_log(line)
    try:
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "_repair_backup", "00_INDEX.md")
        for i, demo in enumerate(player.demos, 1):
            log(f"Preparing match {i}/{len(player.demos)}: {demo.name}")
            shutil.copytree(demo, snapshot / demo.name, ignore=ignore)
        command = [str(python), "-u", str(repo / "scripts/build_packet.py"),
                   "--id", pid, "--player", player.name, "--steamid", player.steamid,
                   "--batch-dir", str(snapshot), "--out", str(packet), "--expect", str(len(player.demos)),
                   "--example", str(example), "--kind", kind, "--no-batch-copy"]
        log("Building evidence, coaching instructions and report software; checking report rendering…")
        if runner:
            result = runner(command, log)
        else:
            with subprocess.Popen(command, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, encoding="utf-8", errors="replace",
                                  env={**os.environ, "PYTHONUTF8": "1"}, **process_options()) as proc:
                for line in proc.stdout:
                    log(line.rstrip())
                result = proc.wait()
        if result:
            raise RuntimeError(f"Packet builder exited with code {result}.")
        for required in ("PROMPT.md", "MANIFEST.json", "data/digest.json", "data/findings_all.json"):
            if not (packet / required).is_file():
                raise RuntimeError(f"Builder did not produce {required}.")
        manifest = json.loads((packet / "MANIFEST.json").read_text(encoding="utf-8"))
        if manifest["steamid"] != player.steamid or manifest["matches"] != len(player.demos):
            raise RuntimeError("Built packet does not match the selected player and matches.")
        snapshot.rename(packet / "data/batch")
        logs = output_root / ".build_logs"
        logs.mkdir(exist_ok=True)
        shutil.copyfile(log_path, logs / f"{pid}.log")
        final = output_root / pid
        packet.rename(final)
        # Publishing the complete directory is the final required operation.
        # Leave diagnostics rather than deleting recursively if cleanup fails.
        try:
            log_path.unlink()
            stage.rmdir()
        except OSError:
            pass
        on_log(f"Ready: {final}")
        return final
    except Exception as exc:
        log(f"FAILED: {exc}")
        raise RuntimeError(f"No ready packet was produced.\n{exc}\n\nDiagnostics: {log_path}") from exc


def export_zip(packet: Path, destination: Path) -> Path:
    """Create a ZIP exclusively; never overwrite an existing archive or embed itself."""
    packet, destination = packet.resolve(), destination.resolve()
    if destination.is_relative_to(packet):
        raise ValueError("Save the ZIP outside the packet folder.")
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(packet.rglob("*")):
            if p.is_file() and not p.is_symlink():
                archive.write(p, p.relative_to(packet).as_posix())
    return destination
