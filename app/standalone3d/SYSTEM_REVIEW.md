# Standalone viewer system review — 7 November 2026

## Motion and native-equivalence acceptance — 11 November 2026

`REPLAY_ACCEPTANCE.md` now records the stricter acceptance bar. Current native visual parity and smoothness are **not accepted**. Recorded continuous movement inputs now interpolate consistently between ticks, and this demo's 29 stock weapon models load/warm before Ready. Numerical, functional and GPU checks remain separate from frame-cadence acceptance. Rendering submission cost remains the principal bottleneck in the representative Anubis view. An unhelpful static-batch prototype was rejected; a faster Vulkan experiment is retained as an explicit override, with a repaired modulation adapter, and has not replaced the default renderer. See the retained motion validation reports for timings and failures rather than interpreting earlier functional passes as proof of fidelity.

## Source-runtime reconstruction pass — 11 November 2026

See `EXACT_PLAYBACK_FEASIBILITY.md` for the tested/revised plan and remaining gates. Watch now uses a compiled subset of the original Glock graph's action selectors, including last-bullet and empty-magazine reload clips. Selector entry inputs come from the existing recorded stream and survive backward seeks. This is not a full animation graph interpreter.

The installed Vulkan shader was decoded and a material-selected variant recovered. Its verified layer-border offset, one-layer color-detail formula and material ambient-occlusion dependencies now feed the existing renderer. Only Anubis received small missing texture dependencies during this pass; existing geometry and lightmaps were retained. Two-layer/bump-detail composition remains incomplete and is reported by the material audit.

Retained evidence is `data/.desktop/standalone3d/validation/fidelity-feasibility/`: 219 recorded action/seek comparisons, 12 authored track checks, eight GPU expression checks, all seven prepared-map rendering checks, and 96 Python tests passed. The final combined Anubis fixture reached Ready in 11.578 s; ten seconds is not guaranteed. A decoded native frame was manually matched by its visible tick (6837); it still shows differences in corpses, effects and shading, so visual parity has not passed.

The standalone renderer still does not start CS2, change installed files/settings, or execute Valve's engine DLLs. The offline shader profiler is an explicitly invoked experiment; it does not run during Watch. Recovered shader code is evidence for incremental adapters, not proof of a drop-in replacement renderer.

## Regression repairs — 10 November 2026

This section supersedes the 9 November results below for the reported lighting, shadow-patch, grenade and anti-aliasing regressions. Earlier node/transform checks missed visible pin/throw animation and display-pipeline defects; those results were insufficient visual acceptance.

- Removed instantaneous screen-average exposure, which made scene brightness respond immediately to view changes and effects. Review exposure is now fixed within the map profile's authored bounds. The existing brightness control remains available.
- Isolated the Anubis stair/water-edge black patches to multiplicative overlay materials. Disabling sunlight shadows, local-light shadows, water or the first-person model did not remove them; disabling overlays did. The Compatibility renderer's per-draw exposure was darkening neutral modulation overlays. Its normalized buffer also clipped bright multipliers. The repair compensates exposure and uses matched darkening/brightening passes with linear-light ratios/deltas, retaining animated caustics and markings. It does not hide those overlays or disable the authored map shadows. The supplemental screen-depth contact approximation was removed.
- Connected stock pin-pull, charge/hold and underhand/overhand grenade clips for all six utility types. Decoy arms share the stock flashbang family. The existing network reader now exposes recorded throw strength and animation timestamps, converted to demo time. World utility poses preserve locomotion; additive zero scale is treated as a neutral delta rather than collapsing the skeleton.
- Enabled 4x MSAA in the world and first-person viewports. A pre-HUD edge filter also smooths shader/transparency edges, without filtering the UI text.
- Preloaded immutable player/weapon pose data on the resource worker. A small owned offscreen viewport prepares grenade rendering before readiness; its materials are retained for reuse. The measured Anubis preparation covered 216 pose clips and all six projectile types. No game process, game-file/settings edits, map reimport or bulk demo/analysis rebuild was used.

Retained verification is `data/.desktop/standalone3d/validation/nov10/acceptance.json`, with comparison frames in `final-frames/`:

- Actual SmoodAimder Anubis round: all 10 throws present through 2,268 successive ticks and backward seeks; rendered flight pixels checked for all six utility models; 24 CT/T underhand/overhand pose combinations, with idle/pin/throw body-layer checks.
- Full 60-frame caustic cycle: no near-black pixels in the pinned stair patch; brightness variation remained small and nonzero, confirming the animation was retained. An additional 18-frame, world-anchored camera-motion check passed.
- Actual GPU tests verify neutral and zero-opacity overlays preserve gray, dark and bright modulation remain functional, bright-background changes do not pump unchanged geometry, and MSAA/post filtering produce intermediate edge pixels. The measured geometry/filtered edge counts were 0→52 and 0→132 respectively.
- All seven prepared maps passed the lighting/native-host checks with no renderer errors. Ready times were Ancient 14.266 s, Anubis 7.719 s, Cache 9.250 s, Dust2 9.844 s, Inferno 10.672 s, Mirage 3.890 s and Nuke 7.140 s. The quality run allows additional preparation time while retaining ten seconds as a reported target.
- All 42 stock weapons passed 84 CT/T rendering cases. The actual Anubis regression run opened in 10.063 s; the normal cached-demo Watch path opened in 11.641 s. These times include the new preparation. First-time raw-demo decoding can take longer.
- 89 Python viewer tests, 20 desktop lifecycle/integration tests and five headless Godot suites passed.

Restart Toolbox once to load the updated renderer. These checks validate the reported regressions, not full Source-engine visual/physics equivalence. The existing fidelity limitations below still apply.

## Historical repair pass — 9 November 2026

This section supersedes the historical follow-up below. Full native-engine fidelity is still a separate acceptance goal; functional tests are not proof of pixel equivalence.

- Weapon presentation now reads the existing DemoFile network entities, including the correct reserve-ammo array element and actual inspect animation states/timestamps. Inspection cancels on firing, translates the network clock to demo ticks, and retains its original start through the outro. Twenty-one shared authored inspect clips are available; the current source catalog has no corresponding viewmodel clips for USP-S/M4A1-S. No generic substitute is presented as native animation.
- Locomotion uses 72 measured planted-foot calibrations. Cadence is integrated once from existing decoded movement, action and direction into a small deterministic companion, rather than dividing total distance by a new stride on every turn. Clip changes preserve phase; seeks do not inherit future transitions. Knife attacks no longer inherit a walking-cycle phase. Viewmodel bob remains a small deterministic approximation.
- Sparse inventory, duplicate utility counts, armor, money and ammunition supplement the HUD. Player lists start collapsed, radar occupies the upper left, Nuke has a lower-floor selector, and compact score/player cards avoid clipped names.
- Source post-processing profiles and color LUTs are read separately from the existing map caches. The GPU applies authored rational tone curves, signed white-point normalization and grading. Negative-valued curves on Dust2/Mirage/Nuke are explicitly tested. Exposure reduction is bounded and seek-stable; it is an approximation of Source's histogram/adaptation.
- Smoke uses reconstructed free-space occupancy, 20-unit cells, billowing detail, timed expansion and recovery. Recorded HE events open transient clearings. Actual FireBullets messages supply firing origins/directions, with wall-clipped cosmetic channels; these nominal rays are not authoritative hit positions or a reconstruction of Valve's fluid solver. The pre-tone-map team tint is calibrated against the native first-person recording.
- Fire retains all four authored stock sprite sequences (131 frames), shared once across demos, rather than repeating only sequence zero. Existing raw grenade/analysis evidence is retained.
- Static/dynamic lighting bindings are separated; conservative spatial indexing avoids a full probe-volume scan per material. Inferno and Cache can mount a single package made from already-prepared native resources. It is revision/runtime-bound and falls back to the original cache. No game files were edited and no map/demo was bulk re-extracted.
- Already-prepared demos now reuse a checked preparation receipt through the normal Watch path. Existing SHA/change-stamp fingerprints, installed-map revisions, Godot version, preparation-code revision, sampling rate and companion-file stamps invalidate reuse when inputs change. Cache misses return to the existing preparation/approval workflow; they do not import maps silently.
- Window attachment no longer queries Windows' cross-thread lock while attachment is in progress. Posted resizes are checked for acknowledgement and retried. Stop requests a graceful renderer exit, then applies a bounded forced fallback; the host remains alive until its child closes.

Validation retained under the private standalone cache:

- 89 Python viewer tests and 20 desktop lifecycle/integration tests pass. Godot presentation, utility, HUD and 1,000-query probe-index tests pass.
- All 42 stock weapons pass 84 CT/T rendering/pose cases, including embedded resize, seek and clean shutdown (`validation/all-stock-final.json`).
- All seven prepared-map lighting/native-host cases pass (`validation/lighting/acceptance-results.json`). Recorded ready times: Ancient 9.219 s, Anubis 6.125 s, Cache 7.235 s, Dust2 7.719 s, Inferno 7.734 s, Mirage 4.015 s, Nuke 7.250 s. Affected Cache/Dust2 cases were rerun after the attachment repair; unchanged lighting cases were retained.
- The actual SmoodAimder Anubis prepared replay passes at 7.859 s, with no renderer errors, acknowledged resize, a 360 ms maximum host callback interval and no black frames in 700 all-player first/chase late-round views. Maximum measured seek work was 20.151 ms (`validation/gameplay-acceptance.json`). This does not establish the original blackout's cause.

The normal demo-opening path also passes at 8.406 s after this preparation, with acknowledged resize and no renderer errors (`validation/final-watch-acceptance.json`).

Timing applies to prepared replay data and warmed shared assets. First demo decoding and first shader/resource preparation after changes are additional work; earlier cold/update runs exceeded ten seconds. Do not promise every raw demo will open within ten seconds after map preparation alone.

Remaining fidelity limits: Source animation-graph/IK equivalence, physics ragdolls, exact smoke/fire simulation and acoustic propagation, source histogram exposure, and unrecorded bullet impacts. Unknown source shader families remain visible in the coverage report. Do not turn these checks into an assertion that every CS2 visual feature is reproduced.

## Decision

The viewer is an incomplete reconstruction, not an accepted CS2 demo-viewing
milestone. Successful loading, changing bones, nonzero voxel counts and a valid
kill feed do not establish visual or gameplay fidelity. The user's Anubis images
are evidence of missing systems as well as bugs. Further work should follow the
dependencies below rather than add a material-name exception for each screenshot.

This review used the existing SmoodAimder Anubis recording (SHA prefix
`1c0db4765ef6`), its prepared map `de_anubis_72f45768ff0154af40b4`, the source
material metadata retained in glTF, the existing replay companion, and the current
Godot code. It also inventoried the other six prepared textured maps. It did not
launch CS2, modify installed files/settings, bulk re-extract demos, or reimport maps.

## Implemented repairs and current validation

### Gameplay follow-up — 9 November 2026

This increment addresses the native-video findings below; the older table records
the findings at the time of that pass, rather than today's complete implementation.

- Selected-demo `presentation.json` now transfers recorded clip/reserve ammunition,
  armor/helmet, money, game-rule round time, player/viewmodel FOV and offsets, and
  sparse inspect flags. A separate bounded float stream supplies recorded view
  punch. Unknown fields stay unknown. Inspect flags are retained for future clip
  support; their presence does not mean inspect playback is implemented.
- Camera projection now converts Source's base 4:3 horizontal FOV to vertical FOV;
  the private arms camera uses the recorded viewmodel FOV/offsets. Recorded punch
  contributes to the observer view. This improves framing without altering CS2.
- Ground-distance phase and 120 ms directional-clip blending reduce locomotion
  discontinuities. Seeking clears transition history. This is not Source's full
  animation graph, procedural movement bob, foot locking or native ragdolls.
- Radar, optional team-colored X-ray outlines, recorded equipment and round/freeze
  countdowns supplement score/alive/kill-feed presentation. The bomb phase still
  shows elapsed time; no unrecorded bomb countdown is invented. Radar currently
  uses the upper-floor image on Nuke; a lower-floor selector remains outstanding.
- Recorded hurt events drive a short blood spray and damage edge cue. Shells
  eject from shot events. Those meshes/positions are cosmetic, not exact wound,
  impact or casing physics. Missing bullet impacts remain unavailable.
- Source character material flags now distinguish cloth and skin response,
  including a cloth roughness floor and weak grazing sheen. The integrated
  check bound 165 material instances (90 cloth, 15 skin). These are supported
  feature approximations, not a complete Source character shader implementation.
- Viewer-only smoke reconstruction corrects a central format error: network masks
  mark collision cells, not smoke density. It fills free cells from recorded seeds,
  uses 20-unit world-aligned cells and linear inner-block bit order. Original/raw
  analysis remains untouched. Four flood steps approximate the GPU fluid footprint;
  exact native bloom/turbulence, bullet/HE clearing and recovery remain outstanding.
  Format reference: https://docs.pureskill.gg/datascience/adx/cs2/csds/spec/#smoke_voxel---telemetry
- Fire sprites now use smaller footprints and height at each recorded burning patch,
  with bounded start/end fades. Source sprite frames are retained. Exact particle,
  ground contact, embers and smoke behavior remain incomplete.
- Toolbox defers Windows child-window attachment until renderer loading completes,
  preventing the loading renderer's window thread from sharing Toolbox input queues.
  Readiness waits for initial rendered frames, rather than file loading alone.
  Map, lighting and audio/actor reads overlap; no visual feature is removed.

Validation: 84 Python viewer regressions, 10 desktop lifecycle regressions, and
Godot HUD/utility fixtures pass. The real Anubis fixture passed at **9.875 seconds**
to ready, with a 47 ms maximum loading callback gap, clean shutdown and no renderer
errors. Cancellation during loading completed in 1.91 seconds with a 47 ms gap.
One previous run exceeded the target at 17.171 seconds during initial shader use;
prepared repeats before the latest read overlap ranged 8.968–10.453 seconds. Thus
these measurements do not guarantee every recording/first shader preparation is
under ten seconds. Forward+ remains optional after a 24.484-second check.
With the final first-frame readiness gate, the real Anubis repeat took **10.047 s**,
with a 63 ms loading callback gap and all playback assertions passing, no renderer
errors and clean shutdown. Its overall harness correctly failed the strict 10 s
budget. `final-result.json` records this latest result, not the earlier 9.875 s run.

After the first-frame readiness correction, all seven synthetic map fixtures passed
their rendering assertions without renderer errors. Six passed the complete harness:
Ancient 9.922 s, Anubis 7.157 s, Cache 8.172 s, Dust2 7.235 s, Mirage 4.515 s and
Nuke 7.890 s. Inferno missed the target at 13.015 s; its map-resource read remains
the main delay. Enabling resource-loader subthreads was investigated and reverted
after worsening Inferno to 17.359 s. Results: `validation/lighting/results.json`.

The full 42-definition stock matrix rendered all 84 CT/T cases with no model/pose
failures and no renderer errors, reaching ready in 8.609 s. However, the overall
native harness failed its resize assertion. The callback gap was 359 ms, within
the existing 1000 ms limit; the earlier attribution to a callback-limit failure was
incorrect. This is not an end-to-end pass: asynchronous resize acknowledgement
requires investigation. Evidence: `validation/reference-first-person/all-stock-result.json`
and `all-stock-playback.json`. Cold shader readiness and Inferno performance remain
open work alongside the visual limitations listed above.

The late-round audit rendered **700 frames**: all ten players, first/chase cameras,
ticks 6400–7488 every 32 ticks. No black frame was detected; minimum sampled central
luminance was .0564 and maximum seek update 19.956 ms in the normal renderer. The
reported blackout remains **unreproduced**, not proven fixed, and this sampling
cannot exclude single-tick or machine-specific failures. Dense smoke alone is not
accepted as its cause.

Retained evidence: `validation/reference-first-person/gameplay-result.json`
(blackout/visual pass) and `final-result.json` / `final-playback.json` (latest
prepared opening), under the private standalone cache. No new game launch, installed
file/settings change, broad analysis correction or bulk asset rebuild was needed.

### First-person native-video pass — 9 November 2026

Reviewed the accepted SmoodAimder first-person MP4 across the entire round using
46 decoded frames: freeze/buy samples followed by one-second samples throughout
live play and round end. Compared the existing renderer at ticks 4737, 5877, 6453,
6837, 7070 and 7270 in a fixed 1280x720 viewport, including projection variants.
The actual encoded native frame HUD verifies ticks 5877 at video 45 s, 6453 at
54 s and 6837 at 60 s. This is a frame/state pass plus code-path inspection,
not a claim that every video frame or every animation transition was reviewed.
The cached reference is silent and CS2 explicitly disables TrueView for this old
demo. Cosmetic knife/glove/weapon/agent differences are outside acceptance scope.

| System | Reference evidence and current gap | This pass |
| --- | --- | --- |
| Aim and locomotion | Native camera turns continuously. Our positions interpolated while camera/body yaw and pitch stepped at sample boundaries. Gait still switches discrete directional clips using absolute time; there is no full animation-graph or foot-lock reconstruction. | Fixed shortest-path yaw and pitch interpolation on continuous living segments; guard death, absence and teleport boundaries. Full gait blending remains open. |
| First-person framing | Native Glock is offset to the right with different arm coverage; ours is much more centered. The 68-degree private camera and fixed pose root are not a verified transfer of Source viewmodel projection/offsets. Source profile records viewmodel FOV 60 and offsets 1.25, 2, -1.5, but those values alone do not establish the engine's projection convention. | Captured projection variants for diagnosis; deliberately did not ship an unverified FOV adjustment. |
| Weapon handling | Native footage shows knife inspect/turnover, switch/draw motion, movement bob/sway and gun recoil/reload transitions. We have idle/draw/fire/reload poses but no inspect event/state, procedural bob/sway, or full transition graph. | Open. Existing authored clips are not evidence of complete behavior. |
| Smoke | At native 54-62 s the A-site smoke is warm, dense and softly lit; at 63 s the camera enters a brown cloud. Our matched frames show blue-grey, coarse lobes and different silhouette/height. | Added reference-calibrated owner-team display tints, shared deterministic fine-detail noise and later transparent compositing so behind-cloud flames/sprites do not draw over smoke. Tint remains a visual approximation; shape, lighting, exact bloom and bullet/HE clearing remain open. |
| World/character lighting | Native stone has more balanced brightness and contact shading. Our sunlit flooring clips too brightly, and cloth/armor response is too dark/glossy in places. | Open: exposure/tonemap, source material interpretation, local-light shape and environment transfer need calibration. No global brightness tweak is presented as a fix. |
| Combat feedback | Native frames show shell ejection, impacts, blood/surface marks, damage presentation and physically settled bodies. Current output lacks parts of that feedback; death poses are not native physics ragdolls. | Open. Do not fabricate evidence-grade impacts from missing events. |
| HUD | Native footage shows radar, clip/reserve ammunition, armor, inventory/economy and a phase countdown. Our HUD has score/round/alive/feed/HP and an elapsed phase clock, with much less player state. | Added a first-person crosshair, hidden for dead/scoped/free/chase views. Radar, ammo/armor/inventory and a recorded countdown remain missing. |
| Spectator readability | Native X-ray outlines reveal players through smoke/geometry with side colors and observer identity. Ours has labels/roster without equivalent silhouettes. | Open; needs an explicit review toggle rather than claiming game visibility. |
| Molotov and audio | This POV does not provide a clear sustained flame close-up, and the MP4 has no audio. | Not validated by this recording; use chase/targeted evidence and an audio reference before claiming parity. |
| Blackout | Dense native smoke darkens the image near video 63 s. Sampled Toolbox round-end views did not reproduce a fully black viewport. | Unresolved. Do not equate darker smoke with proof of the reported bug's cause. |

Validation after this pass: the embedded real-demo fixture passed at 7.407 s to
ready with no renderer errors; the 28-jump cold-seek audit passed, including angle
wrap/death/teleport and play-state regressions. The HUD widget fixture checks
crosshair visibility/layout/seek state, and all 77 Python regressions pass.
Evidence and retained renderer-source hashes live under
`data/.desktop/standalone3d/validation/reference-first-person/`: `comparison.png`,
native contact sheets and full-size frames, `baseline/`, `after/`, `result.json`
and `renderer-revisions.json`. The comparison images use matched demo ticks but
still show the unresolved projection/framing mismatch; they are not pixel scores.
No CS2 launch, game-setting changes, broad data rebuild or bulk asset extraction
was needed for this pass.

### Lighting integration update — 9 November 2026

The approved seven-map companion preparation is complete. All seven installed
revisions now use authored static irradiance/direction, spatial ambient cubes,
roughness-filtered local reflection cubemaps and static/dynamic sun-shadow masks.
Enabled local light entities populate native Godot lights. Shared companions take
about 1.43 GiB; no installed assets, original demos or analysis were changed.

The investigation also found an importer-wide UV defect: extra detail UVs pushed
source lightmap coordinates into a third channel that Godot discarded. Small
revision-bound geometry companions now preserve that channel as UV2 while retaining
base UVs and blend attributes. The visible Anubis crate checkerboard is corrected
with authored lighting enabled. This is an import-contract fix, not a material-name
exception or a brightness adjustment.

Seven native lighting fixtures pass without renderer errors at 3.406–8.172 s to
ready, including Inferno at 8.172 s after parallel map-resource reading and removal
of unnecessary vertex-array copies. The 77 Python tests pass. An additional GPU
fixture checks reflection face ordering/orientation, authored roughness mips,
box projection and static/player sun-shadow sampling (18 cases). Results:
`data/.desktop/standalone3d/validation/lighting/results.json`.

Still approximate: local-light photometry, barn-door/cookie projection, private
first-person local-light parity, full Source material/character shading, sky/fog/
postprocessing, animation graphs, physical ragdolls and exact smoke/fire simulation.
Synthetic coverage and successful loading do not establish 1:1 visual acceptance.

### Earlier gameplay and material validation

### Pistol-round playback investigation — 9 November 2026

The user's latest reports of harsh lighting, janky locomotion, grenade appearance
and an end-of-round blackout reopen visual acceptance; the earlier functional
passes do not contradict that report. Native CS2 reference capture is tracked in
`app/desktop/NATIVE_VIEWER_PLAN.md`. A corrected native first/chase reference pair
has now passed POV review, including decoded video frames. The accepted manifest
is `standalone3d/reference/cs2-anubis-round1/accepted.json` in the desktop cache.
Each silent 1080p video covers the full first-round interval (about 70 seconds).
Reference-based visual corrections are still pending; obtaining these videos
does not resolve the reported locomotion, lighting, grenade or blackout defects.

One deterministic playback issue was fixed: +/-10-second buttons and arrow keys
always called the absolute seek routine, which paused playback. Relative skips
now preserve the previous play/pause state while still clearing stale audio.
The cold-start Anubis regression covers 28 first/chase jumps through combat,
round-end and respawn, plus forward/backward state preservation. It measures
collision-building work as well as seek updates. The run passed with maximum
16.924 ms seek and 10.569 ms collision work, at 6.610 s to ready, without renderer
errors. Evidence: `validation/lighting/pistol-seek-result.json`; native screenshots
are in `embedded-check/seek-audit/`. The sampled SmoodAimder views did not reproduce
the blackout; it remains unresolved, and these timings do not certify all players
or all ticks. No broad data rebuild or game-file modification was performed.

The original findings below are retained as the investigation record. They no
longer describe the current implementation for the repaired systems.

Expanded validation now covers the full stock set: 34 firearms, Zeus, one default
knife and six grenades. All seven selected maps passed 84 CT/T first-person
render cases each, including source-family surface coverage and renderer-error
checks. The final stock audit also validates authored world firing clips and 70
firing/reload sound assets. The separate real-recording passes on Anubis, Dust2
and Inferno reached playback in 6.593, 6.734 and 9.328 seconds respectively.
Thirty Python regressions and the HUD state/layout fixture pass. Evidence is in
`data/.desktop/standalone3d/validation/summary.json`; synthetic rendering coverage
is explicitly distinguished from actual recording playback.

The expanded checks corrected CZ75 world firing, Dual Berettas firing and G3SG1
idle mappings, zero-scale hidden accessory bones, weapon display-name aliases,
missing firing/reload sound mappings and workshop model texture paths. The HUD
now uses recorded scores, round phases and richer kill events. Generic Valve
viewmodel poses remain for M4A1-S, USP-S and decoy; their exact weapon-specific
animation-graph fidelity is still unverified. The measurements below document
the earlier representative Anubis repair pass rather than superseding the full
matrix evidence.

- **Materials/water:** retained Source layer weights before Godot's vertex
  optimization, bound the replacement geometry by exact node paths, restored
  layered normals/modulation and water waves/refraction. Anubis applies 1,280
  layered, 125 overlay and 22 water surfaces with zero binding failures.
  Static-overlay blend mode 3 now uses modulation x2, and caustics advance through
  their 60 source atlas frames. This removes the repeated atlas patterns and
  opaque black unused atlas cells visible in the supplied screenshots.
- **Actors:** retained the root rotation that converts Z-up source animation to
  Godot's Y-up world. Clearing it had put live models sideways/underground while
  still passing a changing-bones test. Manual sampling preserves the layered
  recoil pose; lower-body directional movement continues during reloads.
  The Glock grip separation measures 0.075 m, an upright head 1.624 m and the
  sampled death pose's head 0.150 m above its origin. Seeking out of death resets
  the pose. Corpse lifetimes use the recorded death and next living sample.
- **First person:** separate CT/T glove rigs use complete authored viewmodel
  hierarchies, secondary weapon poses and source weapon anchors in an independent
  transparent viewport inside Toolbox. Idle/fire/reload/draw pose and placement
  checks pass for both teams across all 32 currently prepared definitions.
  No standalone player window or CS2 process is used.
- **Shots/effects:** recorded fire ticks drive muzzle flashes, authored recoil
  and spatial audio. Recorded impact events have a separate small companion and
  render only when supplied by the recording. This Anubis demo does not contain
  those events. Fire now uses the installed game's animated flame imagery across
  recorded burning patches. Smoke treats network boundary occupancy as an
  optical surface with continuous support, deterministic bloom and volume
  shading. Flash review uses a bounded haze so the scene remains visible.
- **Lighting/performance:** restore authored invisible light blockers as
  shadow-only geometry, retain sun direction/color, use sky ambient and add
  contact shading in the fast renderer. Its latest raw-demo check reached ready
  in 6.422 seconds; the separate prepared-replay check took 5.406 seconds.
  Both passed with zero renderer errors. The richer Forward+ path was tested
  inside Toolbox but kept optional because prepared loading remained 16 seconds.
  Shader caching now works inside the private cache.
- **Geometry:** original glTF and native Anubis agree on 4,979 meshes and
  3,654,355 triangles, including 73 arch/bridge groups with 89,994 triangles.
  New bridge captures show the plank surface intact. A controlled two-sided
  comparison changed zero bridge pixels and one arch-view pixel, ruling out
  face culling for those views. No global culling change or fabricated geometry
  was applied. Historical installed-map equivalence remains unverified.

The embedded fixture now fails on renderer/script/shader errors as well as
control failures. It checks upright firing, hand separation, backward leg
movement during reload, death/revival, viewmodel bones and shot flashes.
Functional readiness is still separate from exact engine fidelity: physical
ragdolls, full Source animation graphs and exact smoke/fire
simulation are not claimed. Broader seven-map visual acceptance is pending;
the material adapters apply generically when an approved map is prepared.

## Original findings: observed versus still unproven

| Reported symptom | Established evidence | System that needs correction |
|---|---|---|
| White/missing water | Anubis has two `csgo_water_fancy.vfx` entries. Their wave/refraction/fog/debris parameters survive in source metadata, but no corresponding water renderer exists. | Material-family conversion, including required secondary textures and parameter semantics. A blue plane would not resolve this. |
| Wrong textures/glyphs | 53 material entries declare layer requirements and 14 declare static-overlay/decal shaders. Examples include `anubis_wood_planks01` and hieroglyphic walls, with separate layer colors, modulation masks and normals. | Preserve blend weights, UV conventions, vertex data and decal blending. Counts are review requirements, not proof that every one of those entries is visibly broken. |
| Gaps in bridge/arches | Reproduced the user's tick 6205 view. The export contains the layered plank material. The only mixed tools-surface mesh found contains tools surfaces only; there is no evidence that the tools filter explains the bridge. | Compare installed world/prop/LOD meshes, exported triangles, native visibility, winding/culling and transforms. Exact cause remains open. Do not hide it behind a map-version disclaimer or disable culling globally. |
| Body disappears | `main.gd` explicitly requires `present and alive` for actor visibility. No corpse lifecycle/ragdoll track is implemented. | Actor state after death, round cleanup and deterministic seek reconstruction. This is a missing feature, not a texture problem. |
| Missing shooting presentation | This recording contains 4,509 `weapon_fire` events, including utility/melee. Recoil selection and sound exist; muzzle flashes, shot impacts and complete viewmodel recoil/presentation do not. | One tick-driven event presentation layer, shared by sound, world gun, viewmodel and effects. Do not treat an existing event or changing bone as a visible shot. |
| No backwards walking | All eight authored pistol walk directions are present. The earlier pose matrix primarily exercised forward movement; clip availability does not prove correct directional playback. Exported clips did not supply usable root-motion tracks in the targeted inspection. | Explicit velocity-to-local-axis mapping, lower/upper-body layering and speed/phase synchronization. Backward/diagonal motion must be visually accepted, not assumed from clip names. |
| No first-person hands | The viewer attaches a world gun to the camera. Stock preparation removes first-person meshes, and there is no dedicated arms/viewmodel controller. | Separate FPV asset/rig and animation path, sharing weapon identity and events with the third-person gun. Moving the world model closer to the camera cannot supply hands. |
| Sparse/angular smoke | Reproduced around ticks 6345/6498. Occupancy has changed over time, but rendering and geometry reconstruction are not visually accepted. In the inspected 6200–6650 window there was no HE within 512 Source units of the active smoke anchors. | Validate decoding, interior density, temporal reconstruction, depth/occlusion and dissipation independently. This check does not exclude an earlier blast or prove the decoder is wrong; it gives no basis to label this screenshot a correct HE clearing. |
| Non-CS2 Molotov flames | Burning patch data is present; visuals are procedural billboard cards. The previous change made the cards less pointed but did not reproduce CS2 particles. | A patch-driven flame/ember/smoke renderer and particle/material compatibility. Keep observed footprint/timing separate from approximate art. |
| Opaque flash | The old flash cue could reach alpha 1 and simulate an opaque white screen. | Corrected now: observer-only, soft flash haze capped at 28%; scene visibility is retained. It must not be interpreted as the flashed player's actual visibility. |
| Lighting mismatch | Current scene conversion supplies no baked GI/lightmap node; the seven exports each retain one punctual sun. Exposure adjustments cannot recover the omitted lighting pipeline. | Source lighting/material transfer and a versioned fallback policy. Further arbitrary brightness changes are not the architectural fix. |

## Required implementation order

1. **Material and geometry contract.** Treat glTF as interchange, not a universal
   Source shader implementation. Preserve source shader identity, material flags,
   layers, texture channels, UV/projection rules, vertex blend data, transparency,
   instancing/LOD and source provenance. Dispatch by supported shader family and
   features, with unknown combinations explicitly marked for review. Water,
   layered surfaces and decals are the first representative adapters. Compare
   bridge geometry before deciding whether conversion or rendering needs repair.
   The existing two-name dust adapter remains a bounded workaround, not this contract.
2. **Actor/event/viewmodel state.** Reuse canonical player IDs, weapon aliases,
   recorded state and event ticks. Model equip/fire/reload/death/round-reset as
   transitions reconstructed on seek. Add proper FPV rigs/arms and a lower-body
   locomotion plus upper-body action controller. Add post-death representation
   using recorded state where available; any fallback physics must be explicitly
   approximate and deterministic. Extend only the selected-demo companion if
   additional events/poses are needed; unchanged position tracks and analysis stay.
3. **Effects renderer.** Consume those same tick transitions. Muzzle position,
   shot indication, impact evidence, smoke phases/clearing and burning patches
   must be correct before judging detailed appearance. Use a coherent volume and
   particle/material system rather than independent spheres/cards per new symptom.
   A missing impact endpoint must remain unavailable rather than be invented as evidence.
4. **Lighting and version integration.** Transfer supported lighting inputs and
   report unsupported ones. Bind conversions to installed resource dependencies,
   converter/shader adapter, renderer version and feature coverage. Retained
   historical map assets need their own identity; an installed-map fingerprint
   does not establish that the map matches a demo. Preserve preparation consent.

The owner of these increments is the Toolbox developer. Report/coaching code
must continue using canonical analysis/evidence, not treating this renderer's
approximations as new measurements. No new parser/runtime is proposed by this
review. Large new imports/rebuilds require a separately concrete scope and approval;
none were started here.

## Acceptance without rediscovering omissions one screenshot at a time

`fidelity_audit.py` now inventories source shader families and required adapters
for all seven prepared maps. Each selected-map preparation retains a small,
versioned `fidelity.json` receipt. The combined report is
`data/.desktop/standalone3d/visual-audit/system-coverage.json`. Unknown shader
families are not silently counted as supported. This is a static coverage report,
not a visual certification or a preparation blocker; all current maps correctly
retain `fidelity_ready: false`.

Use one pinned acceptance sequence per affected system, with fixed cameras and
ticks: Anubis 5578 (water), 6205 (bridge), 6345 (materials), 6498 (smoke/fire),
6684 (death context), plus recorded shot and flash cases. Include FPV/chase/free,
eight-direction walking/running/crouching, gun/knife/grenade switching, fire and
reload, death/round reset, and seek forward/back through every transition.
For smoke include bloom, mature occlusion, a documented actual clearing, recovery
and expiry with negative controls. For models require correct hands/grips/pose,
not just a nonempty animation. Compare source geometry and material descriptors
as well as screenshots, so a visually hidden defect cannot pass by disappearing.

Keep **functional reliability**, **visual/gameplay acceptance** and **performance**
as distinct results. An embedding/seek pass must never turn missing arms/water/
bodies into a fidelity pass. Reuse results at unchanged revisions; rerun affected
cases after related changes, then the required integrated acceptance sequence.
Measure prepared startup separately from one-time asset/demo preparation. Retain
the 10-second target and shared caches; do not sacrifice core behavior merely
to pass a startup timing. Broader seven-map runtime acceptance remains outstanding.

## Changes and validation in this review

- Added the source-coverage inventory and contract tests; no geometry/cache rebuild.
- Added the five user-reported ticks and an actual recorded flash to the existing
  application-owned capture fixture, rather than launching separate probes per symptom.
- Implemented bounded, feathered flash haze and updated the flash control wording.
- The viewer now identifies itself as an incomplete-fidelity preview; interactive
  readiness is still separate from this assessment.
- 16 focused tests passed, followed by the five affected audit tests after adding
  unknown-family coverage. The native integrated Anubis fixture passed at 6.016 s,
  including flash bounds, seeking, effects, embedding and clean shutdown. The seven-map
  static inventory completed. These results are not acceptance of the unresolved systems.

Artifacts: `data/.desktop/standalone3d/embedded-check/system-review-result.json`,
the six retained captures in `embedded-check/system-review-frames/`, and
`visual-audit/locomotion.json` under the standalone cache. No Computer Use or game
process was used.
