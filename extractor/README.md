# Extractor
**Current: `extract_demos_v7dot8.py` (v7.8, schema 3.8).** `extract_demos_v7dot7.py` is the superseded, still-pinned v7.7 (ADR-005; v7.8 adopted by ADR-005A). Rule for both: change requires a schema bump and a regression comparison.

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
`PROJECT_ROOT/01_Demos/<folder>` -> `02_Analysis/analyzed_<folder>`. Every other line is v7.7. Set `DEMO_FOLDER` and run it as before. Output from v7.7 and earlier can be brought to the same
columns with `cs2di repair <batch>` (dry run) then `cs2di repair <batch> --apply`.

## Viewer-tracks sidecar (additive, does not touch the frozen extractor)

`extract_viewer_tracks.py` (v1.0) writes, beside each demo's existing output, `viewer_tracks.csv.gz` (8 Hz X/Y/Z, yaw,
pitch, posture flags, live windows only), `grenade_throws.csv.gz`, `grenade_paths.csv.gz` (real projectile paths, simplified,
bounces kept) and `viewer_tracks_meta.json` (provenance, pairing check, interpolation error, join statistics).
Design and measurements: `docs/VIEWER_DATA_OPTIONS_2026-09-29.md`. Needs the original `.dem` files and the analyzed folder
(named after each demo file).

    python extract_viewer_tracks.py --demos "D:\\demos\\pugs" --analyzed "D:\\02_Analysis\\analyzed_pugs" --pack tracks_pack.zip

`--limit 3` for a quick trial, `--force` to redo, `--no-validate` to skip the interpolation check. Send back the zip.


## Using the sidecar in the report (viewer v3.4)
Nothing to configure. `cs2di report` looks for `viewer_tracks.csv.gz`, `grenade_throws.csv.gz` and `grenade_paths.csv.gz` in each demo folder of the analyzed batch. When they exist the viewer draws the recorded 8 Hz view angle and the real grenade flight path, and the "What happened" box gains a line about where the player's view pointed before a kill or death. Demos without them use the event-only drawing (aim after shots, straight throw line).

## Run the sidecar over every batch: `run_all_tracks.py`
Next to `extract_viewer_tracks.py`. Walks `01_Demos\<batch>\**\*.dem` (sub-folders included), pairs each demo with
`02_Analysis\analyzed_<batch>\<demo file name>` (falls back to a unique same-named folder in any `analyzed_*`), and runs the
sidecar. Resumable, one failure never stops the run, demos without an analyzed folder are listed, not processed.

    python run_all_tracks.py --dry-run          # what is ready / missing
    python run_all_tracks.py --limit 2          # 2 demos per batch as a trial
    python run_all_tracks.py                    # everything (summary: ALL_TRACKS_RUN_SUMMARY.json in the demoparser folder)

v7.8 changes damage only: same tables, same sampling. The 8 Hz data exists only in the sidecar files.
