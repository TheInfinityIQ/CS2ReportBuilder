# 2D round viewer

A local, dependency-free viewer for the extractor's CSV analysis. The interface uses existing radar and SVG weapon assets. No internet connection or frontend build is required.

From the project root, run:

```powershell
python app/modules/viewer2d/server.py
```

Open http://127.0.0.1:8765. The included example is **Ancient, round 24**, from `data/analysis/analyzed_CanadianIQ_demos/CanadianIQ_09-17-2026_0dot78_Ancient_LOSS`. It contains ten players, 34 grenade throws, flashes, a bomb plant, and eight eliminations. The round buttons load other rounds locally; the match menu discovers analysis folders with viewer sidecars.

## Controls

- Play/pause: button or Space. Playback speeds: 0.25×–4×.
- Scrub the bottom timeline; hover to preview the time. Arrow keys skip five seconds; Home/End jump to round boundaries.
- Click a round number or an elimination/plant event to jump.
- Wheel or +/− to zoom, drag to pan, click a pawn/roster row to follow, click again to release. ⌖ resets the camera.
- Aa toggles name/health pills; ⌁ toggles grenade trails; ⛶ enters fullscreen.
- On Nuke, Train, and Vertigo, Shift-click ⌖ to switch the lower radar overlay.

## Rendering

Pawn jump size follows a smooth, time-based pulse with zero slope at takeoff and landing; world Z does not set the rendered radius. Recorded jump events confirm takeoff when available. Older exports without those events use a conservative airborne ballistic-rise detector, rejecting grounded ramps/stairs, brief steps, ledge drops, constant-speed climbs and missing-data gaps. This fallback is an inference, not proof of a jump input. Long falls do not prolong the animation. Crouch size also interpolates between samples. **Replay jump** follows an example at half speed and pauses after landing. All animation derives from replay time, including when scrubbing backward. This change requires no data rebuild.

Player positions and circular yaw interpolate from 16 Hz sidecars. Pawns show held weapons, sniper scope crosshairs, flash whitening, crouch size, airborne scaling relative to the previous grounded height, and a defuse ring. Name pills fill proportionally to health. The roster shows health, inventory utility, money when recorded, and elimination/reload/flash status. The map draws firing rays, grenade trajectories and interpolated flight, expanding/fading smoke and fire, brief explosion rings, temporary HE smoke holes, bomb state, inferred ground loot, death crosses, and a kill feed.

**Data limits for older sources:** fire/smoke footprints and nearby HE holes are illustrative. Ground weapons/utility are inferred at death locations and removed on nearby matching pickups. Bomb drops/pickups/plants use explicit events. Health, inventory, and held weapons change at available snapshots/events; positions are the denser interpolated track. The round clock assumes the standard 115-second round and 40-second bomb timer.

**Shots:** exported rounds prefer the recorded `fire_bullets` origin. Lines require a same-shooter `bullet_impact` within two ticks; multiple endpoints are retained for pellets/penetration, without guessing their segment order. Shots without impact data show only a firing flash. The Ancient fixture contains 201 shots and no bullet-impact events. These displays do not reconstruct spread, wall collision, or full bullet travel; aim/yaw is never drawn as an invented long ray. v8 attempts bullet-impact extraction even when event discovery omits it.

Grenade flight is hidden until its first recorded path sample; seeking before that sample does not reveal a future position. Between recorded samples, flight remains interpolated. No trajectory is invented for missing path data.

## Export another portable round

```powershell
python app/modules/viewer2d/replay.py --source analyzed_CanadianIQ_demos/CanadianIQ_09-17-2026_0dot78_Ancient_LOSS --round 24
```

The output is `example-round.json`. It contains only the selected round, its source name, and round navigation metadata. A static HTTP server can show this exported round; cross-round/match browsing requires `server.py`. Do not open index.html directly with file:// because browsers restrict JSON/module loading there.

## Integration and verification

For validated v8 sources, recorded ground-item positions and burning fire-patch centers replace inferred effects. Successfully decoded smoke uses an experimental voxel projection; HE holes and engine-identical smoke shapes remain unverified. The dedicated `?sample=utility-check.json` preview has smoke, molotov, and HE jump buttons. See the extractor's `README_v8.md` for provenance and limits. The data limits above apply to older sources without v8 sidecars.

Decoded smoke is shaded as a dense, softly feathered cloud within its recorded projection. Fire uses nearby Delaunay triangles, short links, and small patch footprints in one nonzero fill, so overlapping pieces do not create opacity seams. Joins are limited by distance and height, and removed/nonburning patches no longer contribute. The interpolated boundary is a visualization policy, not engine collision geometry or a damage-area measurement.

`replay.build_replay(source, round_number)` returns the JSON contract; Steam IDs remain strings. `engine.mjs` contains pure, independently testable time/interpolation calculations. `viewer.js` owns the canvas UI. `server.py` binds only to loopback and serves this module, map/weapon assets, read-only analysis APIs, and the local rebuild progress page. Its sole POST action requests a graceful rebuild stop and requires a matching Origin header.

```powershell
node --test app/modules/viewer2d/test_engine.mjs app/modules/viewer2d/test_geometry.mjs
python -m unittest discover -s app/modules/viewer2d -p test_replay.py
```

The Python integration tests skip if the local analysis fixture is absent. The generated round can be regenerated without changing source files.

## Opening movement heat map (opening-passages-1)

Enable **Heat map** in the viewer sidebar. Defaults: 40 seconds after freeze end,
with **Cut off after first kill / death** enabled. The first recorded live death
(including world deaths, suicides and teamkills) cuts off EVERY player's window,
before player selection. With cutoff disabled, each player's own death still
ends their contribution. Round end always caps the window. The slider covers
1–120 seconds; reset restores timing, side, scope and roster defaults.

The overlay is a static opening summary, independent of scrubbing/playback.
CT is blue, T orange. Both / CT / T selects actual recorded sides, including
overtime; no chronological-half or fixed overtime-switch inference is used.
Scope is all games in the verified bundle on the replay's map or one game on
that map. Other map coordinate systems are never mixed. Sample counts and
exclusions appear beneath the controls.

### Identity and availability

PUG/player bundles authorize only the stable tracked SteamID64, enforced both in
the UI and `/api/heatmap`; a forged/restored other-player selection is rejected.
FACEIT account UUIDs are linked only through observed `game_player_id` metadata.
FACEIT-hosted ESEA team collections remain team mode. Unknown identity disables
heat maps; a folder or nickname never supplies an account or team identity.

New Toolbox analyses retain `context.heatmap_identity` in `analysis_source.json`.
Team identity contains two stable team IDs, the selected team ID, and verified
SteamID roster membership. HLTV metadata can instead carry stable team IDs from
the source links plus exact per-match clan-name linkage; canonical round-side
clan names must match unambiguously. Missing/ambiguous linkage disables that
game rather than merging teams by their display names. Historical analyses are
not automatically rewritten or re-extracted.

An explicit `heatmap_identity.json` may live beside a match or at its collection
root (up to three parent levels). Player form:

```json
{"version":1,"mode":"player","tracked_player_id":"76561198062530225"}
```

Team form uses `mode: "team"`, `selected_team_id`, and `teams`, each with a stable
`id`, display `name`, and string SteamID64 `players` array. This is a verified
metadata binding, not a browser override. A declared player collection cannot
be upgraded to team mode by such a binding. The user-confirmed legacy binding
for CanadianIQ/SmoodAimder is stored at `data/analysis/Analysis_SmoodAimder/`.

Team controls show roster unions, game/round coverage, individual checkboxes,
group select-all with indeterminate states, and stable opponent IDs with counts.
Only players actually present and observed in a round contribute; substitutes
are not added as simultaneous extra players. A missing selected participant's
movement makes that side's round ineligible, instead of silently counting zero.

### Definition and limits

Player question: where did the selected players repeatedly travel during their
opening windows? This is deterministic route evidence, not a coaching diagnosis.
Inputs: canonical round boundaries/sides, movement sidecars, map calibration,
death stream capability, integrity metadata and stable identity bindings.

World positions map to a 64×64 radar grid. Movement smaller than a conservative
12-world-unit deadband does not add stationary jitter heat. Valid moving segments
are clipped at the exact time/death boundary and traversed through crossed cells.
Each entry into a different cell contributes one route passage; returning adds
another. Stationary observations remain eligible but add no heat. Gaps over
0.5 seconds, non-increasing time and implausible transitions (400 units/second
plus 24 units of tolerance) are not bridged. These conservative rules may omit
legitimate fast vertical motion or very short movements; this is not distance,
dwell time, visibility, support, engine collision, or tactical value.

Selected-player passages are summed within each eligible round/side. Each game's
rounds are averaged first, then eligible games receive equal weight separately
for CT and T. Short first-death windows are never stretched to the chosen slider
duration. No observations/absent roster entries are not observed zero movement.
Valid canonical competitive rounds are used; explicit warmup/non-competitive,
incomplete rounds and missing death capability are excluded.

Demo SHA identities deduplicate copies; persisted canonical match ID + map groups
logical game segments where available. Completed-round score totals identify
rounds across side switches/segments; without those fields, demo identity plus
parser round is used conservatively. A more complete valid copy wins over an
incomplete duplicate. Unknown identity cannot establish cross-file deduplication.

Rendering uses a fixed 3×3 smoothing kernel and fixed intensity response
`alpha = 235 * (1 - exp(-mean_entries / 0.5))`. The scale never follows a filtered
maximum. Overlapping layers combine light; use CT or T to inspect one layer.
Current radar calibration contains no validated height thresholds, so stacked
maps are explicitly labelled **All-level projection** rather than implying floor
connectivity. No new extraction or spatial floor classifier is introduced.

### Execution and verification

The local server prepares only movement/roster/death data in one background
worker; it does not repeatedly build full utility replay packets. It streams
logical games and bounds prepared caches (two datasets, one million samples per
dataset), merged games (one million samples / 256 rounds), result caches (eight),
job records (twelve) and concurrent queued/running work (three). Requests use
actual input file revisions plus semantic version/settings. Slider requests are
debounced 250 ms; cancellation and client generations reject stale responses.
Polling reports phase and completed game counts. Bounds surface explicit errors.

The Toolbox's **HTML reports** page builds portable multi-game/multi-map files via
`app/desktop/reports.py`. Exports inject `globalThis.heatmapProvider` (context,
compute, cancel) and `globalThis.replayProvider` (embedded assets/matches/rounds).
`portable-heatmap.mjs` computes the same route-entry algorithm in a Web Worker;
Python/JavaScript parity tests cover clipping, global deaths, equal game weights,
OT sides, duplicates and missing observations. Prepared movement and replay rounds
are compressed and decoded lazily; movement and round caches hold two datasets.
No server, external assets, API keys, downloads or new extraction are required.
The map picker changes coordinate systems; all-games scope includes only embedded
games on that map. Player exports enforce the chosen Steam ID in both controls
and provider validation. Team filters validate opponents and roster membership.
The original Ancient one-off export remains an independent older artifact.

Regression tests: `python -m unittest discover -s app/modules/viewer2d -p test_heatmap.py`
and `python -m unittest discover -s app/desktop -p test_heatmap_identity.py`.
The fixtures check global first-death cutoff, own deaths, unknown capabilities,
stationary/repeated movement, cadence equivalence, gaps/teleports, boundaries,
actual CT/T and overtime, equal game weight, copies/incomplete copies, missing
selected participants, stable identities, nickname changes, substitutes, scope,
opponent validation, PUG request rejection and revision-aware caching.

Semantics are independently versioned by `opening-passages-1`; changing thresholds,
grid, units, denominators or eligibility requires a version update and regression
review. The heat map is exploratory evidence and does not claim a persistent
habit, player intent, or decision quality.
