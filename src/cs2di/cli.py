from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config
from .evidence import scan_batch


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cs2di")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gate", help="run the hard integrity gate over an analyzed batch")
    g.add_argument("batch", help="batch name (e.g. mimy) or a path to an analyzed_* folder")
    args = p.parse_args(argv)

    if args.cmd == "gate":
        path = Path(args.batch)
        if not path.is_dir():
            path = config.analysis_dir(args.batch)
        results = scan_batch(path)
        bad = [r for r in results if not r.passed]
        for r in bad:
            print(f"FAIL {r.demo_id}: {', '.join(r.reasons)}")
        print(f"{len(results) - len(bad)}/{len(results)} demos pass the hard integrity gate "
              f"({sum(r.n_rounds or 0 for r in results if r.passed)} rounds)")
        return 1 if bad else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
