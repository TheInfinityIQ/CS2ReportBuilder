"""Run the viewer-tracks sidecar over EVERY demo under the Demos folder, recursively.

Put this file next to extract_viewer_tracks.py and run:

    python run_all_tracks.py                      # everything under PROJECT_ROOT\\01_Demos
    python run_all_tracks.py --dry-run            # only show what would run and what is missing
    python run_all_tracks.py --batch mimy --batch iTrilogy
    python run_all_tracks.py --limit 2            # 2 demos per batch, as a trial
    python run_all_tracks.py --force              # redo demos that already have tracks

What it does (additive; it never edits an existing file):
  * every top-level folder of 01_Demos is a batch: 01_Demos\\<batch>\\**\\*.dem   (sub-folders are searched)
  * each demo is paired with its analyzed folder: 02_Analysis\\analyzed_<batch>\\<demo file name>
    (if that is missing it falls back to a folder of the same name in ANY analyzed_* folder, when unique)
  * for each pair it runs extract_viewer_tracks.process_demo, which writes viewer_tracks.csv.gz,
    grenade_throws.csv.gz, grenade_paths.csv.gz and viewer_tracks_meta.json beside the existing tables
  * demos already done are skipped (safe to stop with Ctrl+C and run again); one failing demo never stops the run
  * demos with no analyzed folder are LISTED, not processed: run the v7.8 extractor on that batch first
  * writes viewer_tracks_batch_summary.json in every analyzed folder and ALL_TRACKS_RUN_SUMMARY.json in PROJECT_ROOT

The old v7.7 / v7.8 tables are not touched and not needed to change. Nothing here re-extracts them.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

import extract_viewer_tracks as evt  # must sit in the same folder

PROJECT_ROOT = evt.PROJECT_ROOT
DEMOS_ROOT = PROJECT_ROOT / "01_Demos"
ANALYSIS_ROOT = PROJECT_ROOT / "02_Analysis"


def log(msg: str = "") -> None:
    print(msg, flush=True)


def analyzed_index(root: Path) -> dict[str, list[Path]]:
    """demo stem -> every analyzed_*/<stem> folder that has a rounds.csv (for the fallback lookup)."""
    idx: dict[str, list[Path]] = {}
    for a in sorted(root.glob("analyzed_*")):
        if not a.is_dir():
            continue
        for f in a.iterdir():
            if f.is_dir() and (f / "rounds.csv").exists():
                idx.setdefault(f.name, []).append(f)
    return idx


def plan_batch(batch_dir: Path, analysis_root: Path, index: dict) -> tuple[list, list, list]:
    """-> (pairs [(dem, folder)], missing [dem], duplicates [dem]) for one batch."""
    primary = analysis_root / f"analyzed_{batch_dir.name}"
    pairs, missing, dups, seen = [], [], [], set()
    for dem in sorted(batch_dir.rglob("*.dem"), key=lambda p: str(p).lower()):
        if dem.stem in seen:  # same file name twice in one batch: the analyzed folder can only match one
            dups.append(dem)
            continue
        seen.add(dem.stem)
        folder = primary / dem.stem
        if not (folder / "rounds.csv").exists():
            alt = [f for f in index.get(dem.stem, []) if f.parent.name != primary.name]
            folder = alt[0] if len(alt) == 1 else None
        if folder is None:
            missing.append(dem)
        else:
            pairs.append((dem, folder))
    return pairs, missing, dups


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run extract_viewer_tracks over every demo under Demos, recursively.")
    ap.add_argument("--root", type=Path, default=PROJECT_ROOT, help="folder that holds 01_Demos and 02_Analysis")
    ap.add_argument("--demos-name", default="01_Demos")
    ap.add_argument("--analysis-name", default="02_Analysis")
    ap.add_argument("--batch", action="append", default=[], help="only this batch folder name (repeatable)")
    ap.add_argument("--limit", type=int, default=0, help="at most N demos per batch (trial run)")
    ap.add_argument("--hz", type=int, default=evt.SAMPLE_HZ)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-validate", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    demos_root, analysis_root = a.root / a.demos_name, a.root / a.analysis_name
    for p in (demos_root, analysis_root):
        if not p.is_dir():
            log(f"ERROR: folder not found: {p}")
            return 2
    batches = sorted(d for d in demos_root.iterdir() if d.is_dir())
    if a.batch:
        want = {b.lower() for b in a.batch}
        batches = [b for b in batches if b.name.lower() in want]
    index = analyzed_index(analysis_root)

    plans = {b: plan_batch(b, analysis_root, index) for b in batches}
    total = sum(len(p[0][: a.limit] if a.limit else p[0]) for p in plans.values())
    log(f"Demos folder: {demos_root}")
    for b, (pairs, missing, dups) in plans.items():
        done = sum((f / "viewer_tracks_meta.json").exists() for _, f in pairs)
        log(f"  {b.name:28} demos={len(pairs) + len(missing) + len(dups):4}  ready={len(pairs):4}  "
            f"already_have_tracks={done:4}  no_analyzed_folder={len(missing):3}  duplicate_names={len(dups)}")
        for m in missing[:5]:
            log(f"      no analyzed folder: {m.name}")
        if len(missing) > 5:
            log(f"      ... and {len(missing) - 5} more (run the v7.8 extractor on this batch first)")
    log(f"\n{total} demo(s) to consider. Expect roughly 5 to 60 s per demo (about 1 MB of output each).")
    if a.dry_run:
        return 0

    t_all, grand = time.time(), {"ok": 0, "already_done": 0, "failed": 0, "no_analyzed_folder": 0}
    master = {"script": "run_all_tracks.py", "tracks_script_version": evt.SCRIPT_VERSION, "sample_hz": a.hz, "batches": {}}
    n_done = 0
    try:
        for b, (pairs, missing, dups) in plans.items():
            if a.limit:
                pairs = pairs[: a.limit]
            if not pairs and not missing:
                continue
            log(f"\n=== {b.name}: {len(pairs)} demo(s) ===")
            results = [{"demo": m.name, "stem": m.stem, "status": "no_analyzed_folder", "path": str(m)} for m in missing]
            for i, (dem, folder) in enumerate(pairs, 1):
                n_done += 1
                rec = {"demo": dem.name, "stem": dem.stem, "folder": str(folder)}
                t0 = time.time()
                try:
                    out = evt.process_demo(dem, folder, a.hz, not a.no_validate, a.force)
                    rec["status"] = out["status"]
                    if out["status"] == "ok":
                        m = out["meta"]
                        gs = m.get("grenade_stats", {})
                        ic = m.get("interpolation_check", {})
                        rec.update(tracks_rows=m["tracks_rows"], throws=gs.get("throws_written", 0),
                                   detonated=gs.get("detonated", 0), elapsed_s=m["elapsed_s"],
                                   yaw_p99=(ic.get("yaw_err_deg") or {}).get("p99"), warnings=m["warnings"],
                                   bytes=sum(m["bytes"].values()))
                        log(f"[{b.name} {i}/{len(pairs)}] {dem.name}: ok, {m['tracks_rows']:,} rows, "
                            f"{gs.get('throws_written', 0)} throws, {m['elapsed_s']} s" + (f"  WARN {m['warnings']}" if m["warnings"] else ""))
                    else:
                        log(f"[{b.name} {i}/{len(pairs)}] {dem.name}: already done")
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    rec.update(status="failed", detail=f"{type(exc).__name__}: {exc}")
                    try:
                        (folder / "viewer_tracks_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
                    except OSError:
                        pass
                    log(f"[{b.name} {i}/{len(pairs)}] {dem.name}: FAILED - {rec['detail']}")
                rec["seconds"] = round(time.time() - t0, 1)
                results.append(rec)
                if n_done % 10 == 0 and total:
                    el = time.time() - t_all
                    log(f"   ... {n_done}/{total} demos, {el / 60:.1f} min elapsed, about {el / n_done * (total - n_done) / 60:.0f} min left")
            counts = {k: sum(r["status"] == s for r in results) for k, s in
                      (("ok", "ok"), ("already_done", "skipped_done"), ("failed", "failed"), ("no_analyzed_folder", "no_analyzed_folder"))}
            for k, v in counts.items():
                grand[k] += v
            master["batches"][b.name] = {**counts, "results": results}
            if pairs:
                evt.write_json({"script_version": evt.SCRIPT_VERSION, "schema": evt.SCHEMA, "sample_hz": a.hz, "demos": len(pairs),
                                **counts, "results": results}, pairs[0][1].parent / "viewer_tracks_batch_summary.json")
    except KeyboardInterrupt:
        log("\nStopped with Ctrl+C. Run again to continue: finished demos are skipped.")
    master.update(grand, elapsed_s=round(time.time() - t_all, 1))
    evt.write_json(master, a.root / "ALL_TRACKS_RUN_SUMMARY.json")
    log(f"\nDone in {master['elapsed_s'] / 60:.1f} min: {grand['ok']} ok, {grand['already_done']} already done, "
        f"{grand['failed']} failed, {grand['no_analyzed_folder']} without an analyzed folder.")
    log(f"Summary: {a.root / 'ALL_TRACKS_RUN_SUMMARY.json'}")
    return 1 if grand["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
