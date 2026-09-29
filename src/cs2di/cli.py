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

    r = sub.add_parser("report", help="build the Player Study + Analyst Desk HTML from a coach plan")
    r.add_argument("batch")
    r.add_argument("--steamid", required=True)
    r.add_argument("--plan", required=True, help="coach plan JSON (content only, no styling)")
    r.add_argument("--out", required=True, help="HTML file to write")

    args = p.parse_args(argv)

    if args.cmd == "gate":
        results = scan_batch(_batch_path(args.batch))
        bad = [x for x in results if not x.passed]
        for x in bad:
            print(f"FAIL {x.demo_id}: {', '.join(x.reasons)}")
        print(f"{len(results) - len(bad)}/{len(results)} demos pass the hard integrity gate "
              f"({sum(x.n_rounds or 0 for x in results if x.passed)} rounds)")
        return 1 if bad else 0

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
            html = build_report(plan, digest, batch_dir=batch, steamid=args.steamid)
        except PlanError as e:
            print("The coach plan has problems. Nothing was written.\n" + str(e), file=sys.stderr)
            return 1
        Path(args.out).write_text(html, encoding="utf-8")
        print(f"Wrote {args.out} ({len(html) // 1024} KB): {digest['scope']['demos']} games, {digest['scope']['rounds']} rounds")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
