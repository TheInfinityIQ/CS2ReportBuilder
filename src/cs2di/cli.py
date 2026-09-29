from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config
from .evidence import scan_batch


def _batch_path(batch: str) -> Path:
    path = Path(batch)
    return path if path.is_dir() else config.analysis_dir(batch)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cs2di")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gate", help="run the hard integrity gate over an analyzed batch")
    g.add_argument("batch", help="batch name (e.g. mimy) or a path to an analyzed_* folder")

    d = sub.add_parser("digest", help="compute the evidence digest (every number) for one player")
    d.add_argument("batch")
    d.add_argument("--steamid", required=True, help="SteamID64 of the player (as text)")
    d.add_argument("--out", help="write JSON here (default: print a short summary)")

    a = sub.add_parser("analyse", help="run the analyst: every finding for one player vs lobby peers (about a minute)")
    a.add_argument("batch")
    a.add_argument("--steamid", required=True)
    a.add_argument("--out", required=True, help="findings JSON to write")

    r = sub.add_parser("report", help="build the Player Study + Analyst Desk HTML from a coach plan")
    r.add_argument("batch")
    r.add_argument("--steamid", required=True)
    r.add_argument("--plan", required=True, help="coach plan JSON (content only, no styling)")
    r.add_argument("--out", required=True, help="HTML file to write")
    r.add_argument("--analysis", help="findings JSON from 'cs2di analyse' (enables FindingCard/KeyMoments)")

    rp = sub.add_parser("repair", help="fix known data errors in already-extracted output (dry run unless --apply)")
    rp.add_argument("batch")
    rp.add_argument("--apply", action="store_true", help="write the fix (originals are backed up first)")

    args = p.parse_args(argv)

    if args.cmd == "repair":
        from .repair import repair_batch

        res = repair_batch(_batch_path(args.batch), apply=args.apply)
        from collections import Counter

        for r in res:
            if r["status"] not in ("dry_run", "applied", "already_repaired", "not_needed_new_schema"):
                print(f"{r['status'].upper()} {r['demo_id']}: {'; '.join(map(str, r['notes']))}")
        rows = sum(r.get("rows_changed", 0) for r in res)
        cells = sum(r.get("utility_cells_changed", 0) for r in res)
        excess = sum(r.get("legacy_total", 0) - r.get("effective_total", 0) for r in res)
        print(f"demos: {dict(Counter(r['status'] for r in res))}")
        print(f"utility tables: {dict(Counter(r.get('utility_status', '-') for r in res))}")
        print(f"hurt rows corrected: {rows}; utility cells corrected: {cells}; overcount removed: {excess:.0f} HP")
        if not args.apply:
            print("Dry run: nothing was written. Re-run with --apply to write.")
        return 1 if any(r["status"].startswith(("skip_legacy", "conflict")) for r in res) else 0

    if args.cmd == "gate":
        results = scan_batch(_batch_path(args.batch))
        bad = [x for x in results if not x.passed]
        for x in bad:
            print(f"FAIL {x.demo_id}: {', '.join(x.reasons)}")
        print(f"{len(results) - len(bad)}/{len(results)} demos pass the hard integrity gate "
              f"({sum(x.n_rounds or 0 for x in results if x.passed)} rounds)")
        return 1 if bad else 0

    if args.cmd == "analyse":
        from collections import Counter

        from .analyst import analyse_batch

        res = analyse_batch(_batch_path(args.batch), args.steamid)
        Path(args.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(f"{len(res['findings'])} findings: {dict(Counter(f['status'] for f in res['findings']))}")
        return 0

    from .digest import build_digest

    batch = _batch_path(args.batch)
    digest = build_digest(batch, args.steamid)
    if args.cmd == "digest":
        text = json.dumps(digest, indent=2, default=str)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        s = digest["scope"]
        print(f"{digest['subject'].get('name')}: {s['demos']} demos, {s['rounds']} rounds")
        return 0 if s["rounds"] else 1

    if args.cmd == "report":
        from .report import PlanError, build_report

        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        try:
            analysis = json.loads(Path(args.analysis).read_text(encoding="utf-8")) if args.analysis else None
            html = build_report(plan, digest, batch_dir=batch, steamid=args.steamid, analysis=analysis)
        except PlanError as e:
            print("The coach plan has problems. Nothing was written.\n" + str(e), file=sys.stderr)
            return 1
        Path(args.out).write_text(html, encoding="utf-8")
        print(f"Wrote {args.out} ({len(html) // 1024} KB): {digest['scope']['demos']} games, {digest['scope']['rounds']} rounds")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
