# Extractor (frozen, ADR-005)
`extract_demos_v7dot7.py` (schema 3.7, demoparser2 0.42.0, COACHING_PROFILE `batch` by default).
Source is copied verbatim from the owner's onboarding pack. Configure via the constants at the
top of the file (DEMO_DIR / OUTPUT_DIR). Layout convention:
`Demos/<batch>/*.dem` -> `v7dot7Analysis/analyzed_<batch>/<demo_id>/`.
Its own SHA-256 is recorded in each `match_summary.json` (`runtime_environment.extractor_sha256`).
Changing it requires a schema bump and a regression comparison; do not edit casually.

## v7.8 (current)

`extract_demos_v7dot8.py` is v7.7 plus one fix: `player_hurt.dmg_health_effective` (see
KNOWN_PITFALLS row 27) and your `PROJECT_ROOT/demos/<folder>` path convention. Every other line is
v7.7. Set `DEMO_FOLDER` and run it as before. Output from v7.7 and earlier can be brought to the same
columns with `cs2di repair <batch>` (dry run) then `cs2di repair <batch> --apply`.

## Viewer-tracks sidecar (additive, does not touch the frozen extractor)

`extract_viewer_tracks.py` (v1.0) writes, beside each demo's existing output, `viewer_tracks.csv.gz` (8 Hz X/Y/Z, yaw,
pitch, posture flags, live windows only), `grenade_throws.csv.gz`, `grenade_paths.csv.gz` (real projectile paths, simplified,
bounces kept) and `viewer_tracks_meta.json` (provenance, pairing check, interpolation error, join statistics).
Design and measurements: `docs/VIEWER_DATA_OPTIONS_2026-09-29.md`. Needs the original `.dem` files and the analyzed folder
(named after each demo file).

    python extract_viewer_tracks.py --demos "D:\\demos\\pugs" --analyzed "D:\\v7dot7Analysis\\analyzed_pugs" --pack tracks_pack.zip

`--limit 3` for a quick trial, `--force` to redo, `--no-validate` to skip the interpolation check. Send back the zip.


## Using the sidecar in the report (viewer v3.4)
Nothing to configure. `cs2di report` looks for `viewer_tracks.csv.gz`, `grenade_throws.csv.gz` and `grenade_paths.csv.gz` in each demo folder of the analyzed batch. When they exist the viewer draws the recorded 8 Hz view angle and the real grenade flight path, and the "What happened" box gains a line about where the player's view pointed before a kill or death. Demos without them use the event-only drawing (aim after shots, straight throw line).
