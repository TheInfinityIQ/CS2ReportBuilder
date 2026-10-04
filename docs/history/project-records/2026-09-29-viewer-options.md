# Extraction options for the 2D viewer (measured 2026-09-29)

Question from the owner: can extraction record grenades, view angle and other data the 2D viewer needs,
thinly (not every tick, interpolate between samples)? **Yes. Both are cheap, and neither needs the heavy `deep` profile.**

Method: demoparser2 0.42.0 on the only demo available in the workspace (`test_demo.dem`, Mirage, 9 live
rounds, 631 s). MIMY's own demos are not in the workspace, so sizes below are per 9 rounds; a full match is roughly 2.5x.

## 1. View angle: already a normal player property
`parse_ticks(["X","Y","yaw","pitch",...])` works and is fast (8 Hz over the whole demo: 0.4 s). The extractor
already requests `yaw`/`pitch` for its dense engagement table; it just never writes them into `player_positions`
(which is 2 Hz and has no angle). `usercmd_*` is NOT needed for facing: it is for mouse/button forensics.

Sampling at a lower rate and interpolating (yaw unwrapped, circular), error against the true 64 Hz value:

| Rate | yaw error median / p90 / p99 | position error median / p99 | live-round file, X/Y/yaw only |
|---|---|---|---|
| 2 Hz (today's table rate) | 0.5 / 9.3 / 42 deg | 2.5 / 24 units | 77 KB (36 KB delta-coded) |
| 4 Hz | 0.2 / 3.8 / 22 deg | 0.7 / 8.6 units | 147 KB (59 KB) |
| **8 Hz (recommended)** | **0.0 / 1.2 / 8.5 deg** | **0.2 / 2.7 units** | **278 KB (94 KB)** |
| 16 Hz | 0.0 / 0.3 / 2.9 deg | 0.0 / 0.8 units | 517 KB (141 KB) |

The p99 yaw error is fast flicks, which no low rate captures; 8 Hz is visually clean. Only live windows
(freeze end to round end + 4 s, the same window the viewer plays) and only alive players.

## 2. Grenades: real flight paths exist
`parse_grenades()` returns projectile x/y/z per tick with the thrower's SteamID (0.9 s for the whole demo).
The extractor already has `build_grenade_tables()` for it but only runs it in `deep` mode.
- Full rate: 87k rows, 367 KB. Every 4th tick: 96 KB.
- **Simplified with Ramer-Douglas-Peucker (3D, 12-unit tolerance): about 6 points per throw, keeping bounces, 10 KB for the whole demo.**
- Flash and HE paths end exactly on the `*_detonate` event: 0.02 units, within 1 tick, same thrower in 100% of 82 throws.
- Smokes: the projectile entity lives on for the whole 22 s cloud, and a "stopped moving" rule was NOT reliable
  (median 9 ticks early, some large misses). End every path at the matching `*_detonate` event tick instead
  (join on SteamID + type + tick inside the run). Entity ids are reused (KNOWN_PITFALLS 31), so split runs on a tick gap.

## 3. Also cheap, useful for the viewer
- Per-frame flags at 8 Hz: `is_scoped`, `ducking` (one small int).
- At 2 Hz (already the table's rate): `balance`, `has_helmet`, `has_defuser`, inventory, for the roster (money, utility).
- `inferno_expire` (fire end) is already an event; the viewer now uses it.
Not recommended: `usercmd` (mouse deltas, buttons) and 64 Hz dumps. They are forensic, roughly 8x larger, and add nothing visible.

## 4. Where to put it (ADR-005 freezes the extractor)
- **Recommended: an additive sidecar step**, `extractor/extract_viewer_tracks.py`, run once per batch against the
  original `.dem` files. It reads each folder's own `rounds.csv` for the live windows and writes
  `viewer_tracks.csv.gz` and `grenade_paths.csv.gz` beside the existing outputs. No schema 3.7 file changes, so no
  regression comparison and no re-extraction. Demo folder name = demo file stem.
- Alternative: fold it into an extractor v7.9 / schema 3.8. Cleaner long-term, but needs the schema bump and regression run.
- Size for 30 demos at 8 Hz: about 20 MB plain, about 7 MB delta-coded (vs 1.7 MB per demo folder today).
- Blocker: the `.dem` files are not in this workspace; the step has to run where they live or they need uploading.

## 5. What the viewer gains
Pins and cones follow true facing all the time (not only at shots); real grenade arcs and bounces instead of a straight
line; crosshair placement and "who was looking where at contact" become possible coaching evidence, not just drawing.
The viewer would use the new files when present and fall back to today's event-based yaw and straight throw line.
