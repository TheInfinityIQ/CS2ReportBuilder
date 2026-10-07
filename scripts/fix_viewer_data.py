"""Plan or run resumable 16 Hz repair; the same queue is used by the packet UI."""

from __future__ import annotations
import argparse
import importlib.util
import json
import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "extractor"))
from cs2di import config  # noqa: E402
from cs2di.batch_selection import demo_hash, replay_quality, scan_matches  # noqa: E402
from cs2di.evidence import check_demo  # noqa: E402
from cs2di.extraction_queue import run_queue  # noqa: E402
from cs2di.job_lock import exclusive, lock_path  # noqa: E402


def worker(job, phase):
    source = Path(job["demo"])
    demo, folder = source.resolve(), Path(job["analysis"]).resolve()
    if source.is_symlink() or not demo.is_file():
        raise ValueError("Original demo missing or linked")
    from cs2di.game_catalog import file_stamp

    source_stamp = file_stamp(demo)
    identity = demo_hash(demo, {})
    if identity != job["sha256"]:
        raise ValueError("Original demo changed after planning; refresh")
    with exclusive(lock_path(folder)):
        if not check_demo(folder).passed:
            if phase != "prepare":
                raise ValueError("Core analysis is missing or invalid; use Prepare missing analysis")
            if folder.name != demo.stem and sys.platform != "win32":
                raise ValueError("Core output folder must match the demo stem")
            spec = importlib.util.spec_from_file_location(
                "core_extractor", REPO / "extractor/extract_demos_v7dot8.py"
            )
            core = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(core)
            core.OUTPUT_DIR = folder.parent
            core.run_internal_self_tests()
            if not core._analyze_demo_unlocked(demo) or not check_demo(folder).passed:
                raise ValueError("Core extraction failed integrity; see log")
        import extract_viewer_tracks as tracks

        outcome = tracks._process_demo_unlocked(demo, folder, 16, True, False)
        quality = replay_quality(folder, identity, owned=True)
        if not quality.ready:
            raise ValueError(f"Viewer output not ready: {quality.reason}")
        from cs2di.game_catalog import notify_output

        notify_output(folder, demo, quality, owned=True, source_sha=identity, source_stamp=source_stamp)
    return {
        "status": outcome["status"],
        "hz": quality.hz,
        "paths": quality.paths,
        "unobserved_players": quality.unobserved_players,
        "nonlive_rounds": quality.nonlive_rounds,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=config.root())
    parser.add_argument("--demos-root", type=Path, default=config.demos_root())
    parser.add_argument("--batch", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Maximum total jobs for a bounded trial")
    parser.add_argument("--phase", choices=["viewer", "prepare"], default="viewer")
    parser.add_argument("--cpu-target", type=int, default=80)
    parser.add_argument("--memory-target", type=int, default=90)
    parser.add_argument("--max-workers", type=int, default=None)
    parser.add_argument("--jobs", type=Path)
    parser.add_argument("--cancel", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be nonnegative")
    if args.worker and not args.result:
        parser.error("--worker requires --result")
    if args.worker:
        try:
            outcome = worker(json.loads(args.worker.read_text(encoding="utf-8")), args.phase)
            code = 0
        except Exception as exc:
            traceback.print_exc()
            outcome = {"status": "failed", "detail": str(exc)}
            code = 1
        args.result.write_text(json.dumps(outcome, indent=2), encoding="utf-8")
        return code
    if args.jobs:
        jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
    else:
        jobs = []
        raw_root = args.demos_root
        if not raw_root.is_dir():
            parser.error(f"Demo root missing: {raw_root}")
        batches = sorted(p for p in raw_root.iterdir() if p.is_dir())
        if args.batch:
            wanted = {name.casefold() for name in args.batch}
            batches = [
                p
                for p in batches
                if config.collection_name(p, args.root / "02_Analysis").casefold() in wanted
                or p.name.casefold() in wanted
            ]
            if not wanted.issubset(
                {
                    n.casefold()
                    for p in batches
                    for n in (p.name, config.collection_name(p, args.root / "02_Analysis"))
                }
            ):
                parser.error("One or more requested batches do not exist")
        for batch in batches:
            analysis = (
                args.root
                / "02_Analysis"
                / ("analyzed_" + config.collection_name(batch, args.root / "02_Analysis"))
            )
            print(f"Checking batch: {batch.name}", flush=True)
            for match in scan_matches(analysis, batch, args.root / ".extraction_jobs/hashes_cli.json"):
                if match.problem or (not match.core_ready and args.phase == "viewer"):
                    print(
                        f"Excluded: {match.raw.name}: {match.problem or 'core analysis missing/invalid'}",
                        flush=True,
                    )
                elif not match.replay.ready or (args.phase == "prepare" and not match.core_ready):
                    jobs.append(
                        {"demo": str(match.raw), "analysis": str(match.analysis), "sha256": match.sha256}
                    )
    if args.limit:
        jobs = jobs[: args.limit]
    print(
        f"{len(jobs)} job(s), 16 Hz, phase={args.phase}; existing packet snapshots remain unchanged",
        flush=True,
    )
    if args.dry_run:
        for job in jobs:
            print(f"{job['demo']} -> {job['analysis']}")
        return 0
    result = run_queue(
        REPO,
        jobs,
        args.root / ".extraction_jobs",
        phase=args.phase,
        cpu_target=args.cpu_target,
        memory_target=args.memory_target,
        max_workers=args.max_workers,
        cancel_path=args.cancel,
        log=lambda s: print(s, flush=True),
    )
    if args.report:
        args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("Results: " + result["run_folder"], flush=True)
    return int(any(r["status"] == "failed" for r in result["results"]))


if __name__ == "__main__":
    sys.exit(main())
