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
