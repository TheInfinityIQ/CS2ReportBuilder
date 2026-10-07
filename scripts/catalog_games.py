"""Populate or query the local game catalog without modifying demo/analysis data."""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from cs2di import config  # noqa: E402
from cs2di.batch_selection import scan_matches  # noqa: E402
from cs2di.game_catalog import open_catalog, file_stamp  # noqa: E402
from cs2di.packet_jobs import discover_batches  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=config.root())
    parser.add_argument("--demos-root", type=Path, default=config.demos_root())
    parser.add_argument(
        "--rebuild", action="store_true", help="Revalidate every game; preserve/rebuild a corrupt cache"
    )
    parser.add_argument("--query", action="store_true", help="Query existing records instead of scanning")
    parser.add_argument("--player", help="Exact SteamID64")
    parser.add_argument("--team", help="Filename-derived team name")
    parser.add_argument("--raw-folder", type=Path)
    args = parser.parse_args()
    catalog = open_catalog(args.root / "game_catalog.sqlite3", recover=args.rebuild)
    if args.query:
        print(
            json.dumps(
                catalog.games(player=args.player, team=args.team, raw_folder=args.raw_folder), indent=2
            )
        )
        return
    known = {}
    previous_hashes = args.root / ".extraction_jobs/hashes_cli.json"
    if previous_hashes.is_file():
        try:
            for record in json.loads(previous_hashes.read_text(encoding="utf-8")).values():
                if isinstance(record, dict) and len(record.get("stat", [])) == 5:
                    known[tuple(record["stat"])] = record.get("sha256")
        except (OSError, ValueError, TypeError):
            pass
    for batch in discover_batches(args.root / "02_Analysis"):
        start = perf_counter()
        matches = scan_matches(
            batch,
            cache_path=args.root / ".extraction_jobs/hashes_catalog.json",
            catalog=catalog,
            force=args.rebuild,
        )
        raw = config.collection_dir(batch.name.removeprefix("analyzed_"), args.demos_root)
        if raw.is_dir():
            targets = {m.analysis.name.casefold(): m for m in matches}
            for demo in raw.rglob("*"):
                if (
                    demo.is_file()
                    and not demo.is_symlink()
                    and demo.suffix.casefold() == ".dem"
                    and demo.stem.casefold() in targets
                ):
                    match = targets[demo.stem.casefold()]
                    stamp = file_stamp(demo)
                    sha = known.get(tuple(stamp))
                    # Reuse a prior content hash only for the same unchanged file identity
                    # AND the source hash recorded in the analyzed viewer metadata.
                    sha = sha if sha and sha == match.sha256 else None
                    catalog.register_source(demo, match.analysis, sha, stamp=stamp if sha else None)
        print(
            f"{batch.name}: {len(matches)} games; {sum(m.replay.ready for m in matches)} replay-ready; {perf_counter() - start:.2f}s",
            flush=True,
        )
    print(f"Catalog: {catalog.path}", flush=True)


if __name__ == "__main__":
    main()
