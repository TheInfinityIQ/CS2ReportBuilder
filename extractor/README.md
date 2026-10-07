# Extractor
**Current: `extract_demos_v7dot8.py` (v7.8, schema 3.8).** `extract_demos_v7dot7.py` is the superseded, still-pinned v7.7 (ADR-005; v7.8 adopted by ADR-005A). Changes to core table semantics require a schema bump and regression comparison; additive viewer outputs preserve the core schema.

## v7.7 (superseded)
`extract_demos_v7dot7.py` (schema 3.7, demoparser2 0.42.0, COACHING_PROFILE `batch` by default).
Source is copied verbatim from the owner's onboarding pack. Configure via the constants at the
top of the file (DEMO_DIR / OUTPUT_DIR). Layout convention:
`01_Demos/<batch>/*.dem` -> `02_Analysis/analyzed_<batch>/<demo_id>/`.
Its own SHA-256 is recorded in each `match_summary.json` (`runtime_environment.extractor_sha256`).
Do not edit casually.

## v7.8 (current)

`extract_demos_v7dot8.py` is v7.7 plus one damage fix and a path convention: `player_hurt` gains
`dmg_health_effective` and `same_tick_multi_hurt` (the legacy `dmg_health_capped` is kept unchanged), HE/fire
`utility_effectiveness` uses the effective damage (KNOWN_PITFALLS row 27), and paths follow
`PROJECT_ROOT/01_Demos/<folder>` -> `02_Analysis/analyzed_<folder>`. It retains the core table cadence. Set `DEMO_FOLDER` and run it as before. Normal v7.8 runs now add validated 16 Hz viewer sidecars after successful core extraction. Output from v7.7 and earlier can be brought to the same
columns with `cs2di repair <batch>` (dry run) then `cs2di repair <batch> --apply`.

## Viewer-tracks sidecar (additive to the core analysis)

`extract_viewer_tracks.py` (v1.1) writes, beside each demo's existing output, `viewer_tracks.csv.gz` (16 Hz X/Y/Z, yaw,
pitch, posture flags, live windows only), `grenade_throws.csv.gz`, `grenade_paths.csv.gz` (real projectile paths, simplified,
bounces kept) and `viewer_tracks_meta.json` (provenance, pairing check, interpolation error, join statistics).
Design and measurements: `docs/VIEWER_DATA_OPTIONS_2026-09-29.md`. Needs the original `.dem` files and the analyzed folder
(named after each demo file).

    python extract_viewer_tracks.py --demos "D:\\demos\\pugs" --analyzed "D:\\02_Analysis\\analyzed_pugs" --pack tracks_pack.zip

`--limit 3` for a quick trial, `--force` to redo, `--no-validate` to skip the interpolation check. Send back the zip.


## Using the sidecar in the report (viewer v3.4)
`cs2di report` looks for `viewer_tracks.csv.gz`, `viewer_tracks_meta.json`,
`grenade_throws.csv.gz` and `grenade_paths.csv.gz` in each demo folder. It preserves
the cadence recorded in sidecar metadata, including 16 Hz (`--hz 16`), and draws
recorded facing and grenade flight paths when available. The default extraction
rate is now 16 Hz. Changing `--hz` now reprocesses output from a different rate
instead of silently skipping it. v7.8 core player_positions remain 2 Hz.

Demos without sidecars show stable circle markers and event-only direction lines;
their replay notice identifies missing continuous facing. Dashed straight throw
connections indicate missing paths and do not animate invented trajectories.
See [the viewer review](../docs/VIEWER_REVIEW_2026-10-06.md) for verified behavior,
remaining limitations and the implemented preparation workflow.

## Run the sidecar over every batch: `run_all_tracks.py`
Next to `extract_viewer_tracks.py`. Walks the Steam replay root (or `--demos-root`)
recursively, pairs each demo only with its own analysis collection, and runs the
sidecar. Resumable, one failure never stops the run, demos without an analyzed folder are listed, not processed.

    python run_all_tracks.py --dry-run          # what is ready / missing
    python run_all_tracks.py --limit 2          # 2 demos per batch as a trial
    python run_all_tracks.py                    # everything (summary: ALL_TRACKS_RUN_SUMMARY.json in the demoparser folder)

Core `player_positions` stays 2 Hz. Continuous 16 Hz facing/positions and recorded
grenade paths live in the additive viewer files. See the
[packet UI guide](../docs/PACKET_BUILDER_UI.md) for the managed queue and resumable
`fix_viewer_data.py` repair; it uses one selected collection per raw batch, without
the legacy runner's cross-collection fallback. Repair does not update old packets.

## Raw location versus analysis location

Current extractors use separate roots. See [raw-demo locations](../docs/RAW_DEMO_LOCATIONS.md).
`DEMO_FOLDER` remains the logical analysis collection ID (for example,
`CanadianIQ_demos`); its raw folder resolves to `replays/CanadianIQ`.
Both v7.8 and the sidecar scan nested series/batch folders and reject repeated
stems before extraction. Ship `demo_layout.py`, `job_lock.py` and `game_catalog.py` alongside the
standalone scripts. Successful core/sidecar publication updates the local
[game catalog](../docs/GAME_CATALOG.md). Without the full cs2di package, standalone
updates record rosters and source locations as pending; the UI validates them
before showing ready. Catalog errors emit warnings without failing extraction. The superseded v7.7 is retained unchanged as historical code.
