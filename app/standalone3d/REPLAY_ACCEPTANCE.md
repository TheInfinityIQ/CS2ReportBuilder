# Replay acceptance: native presentation and smooth review

The user's requirement is that the replay itself be indistinguishable from native CS2 demo playback; Toolbox's UI may differ. Faster loading, functional tests, imported game assets and approximate substitutes do not establish that result. Smooth review must preserve the recorded scene, events and timing.

On November 12 the user changed the immediate prepared-demo loading target to
under 30 seconds, prioritizing visual matching. Validation now enforces that
budget. Earlier ten-second results remain historical; the visual/smoothness
acceptance criteria are unchanged. See [VISUAL_MATCHING.md](VISUAL_MATCHING.md).

## Required evidence

- Native-reference comparisons use the same demo tick, camera, FOV, viewport aspect and relevant playback/build configuration. Exclude Toolbox's UI from the comparison. Elapsed MP4 time alone is insufficient alignment. Distinguish native demo playback from the original live player's rendered frames.
- Evaluate movement, aim/recoil, first-person arms, weapon actions, bodies, grenades, smoke/fire interactions, blood/impacts, water, material layers, lighting, sound and radar against that reference. Record missing runtime behavior explicitly. A mesh or event being present is not visual acceptance.
- Replay the same interval continuously and by direct/backward/repeated seeking. Verify state equality and measure the time until the new scene has actually been drawn, not merely until the seek command was acknowledged.
- Measure continuous playback cadence separately from CPU picture-update time and from diagnostic coroutine scheduling. Keep engine process intervals and submitted-frame intervals separate. Include first-use weapons, effects, camera changes and later rounds. Averages alone conceal stalls.
- A 60 Hz frame budget (16.67 ms) is only an initial floor, not proof of outperforming CS2. A claim of smoother playback than CS2 requires a comparable native timing baseline at the same hardware, resolution, refresh rate, demo segment and settings. Existing reference videos do not provide a fresh comparable timing baseline.
- Do not improve the score by dropping effects/shadows, reducing resolution, blurring defects, changing recorded movement or shifting event timing. Extra preparation is preferable to avoidable first-use stalls, and must be included in reported readiness time.

## Current verdict

**Still open for visual parity and frame pacing.** Original animation graphs, particles, ragdolls and shading behaviors have gaps. The prepared Anubis fixture passed its seek, resize and shutdown checks. Two 30-second runs measured 21.91 and 17.96 ms at the 99th percentile of submitted frame intervals, above the 16.67 ms budget. In the latter run, 64 of 2,913 submissions exceeded budget. The slowest was 46.80 ms, with 2.58 ms of picture-update CPU, 7.30 ms of renderer CPU and 3.11 ms of measured viewport GPU time. Those timings do not account for the entire interval. Other portions of the demo and the wider map pool need real-demo coverage. See `validation/checklist-pacing-tail/result.json` in the private replay cache.

The November 11 motion investigation found:

- Fractional position/aim interpolation already existed, but crouch eye height, velocity and first-person bob were still stepping. Those continuous values now share guarded interpolation; death, disappearance, team-change and teleport boundaries stay discrete. The actual camera/first-person path has numerical regression checks.
- Later-round weapon models were loaded on demand. All stock models referenced by the selected demo now load through the existing worker and receive a small owned-viewport warmup before Ready. This prevents missing-model waits, but does not prove that every first-use pipeline stall is gone. In the representative demo, 29 models were prepared; readiness increased to roughly 20–26 seconds in the measured full tests.
- The Compatibility path submitted approximately 23,428 draw calls in one tested view. CPU picture updates were about 5 ms while rendering was substantially more expensive. Hiding utility or post-processing barely helped, so neither was removed.
- An exact-state static-batch experiment retained sampled pixels but combined only 77 eligible objects into 23 batches, saving 54 draws per pass. It was rejected as an inadequate optimization and removed from production code. The private validation folder retains its evidence.
- An explicitly selected Vulkan Mobile experiment reduced measured GPU cost from approximately 35 ms to 4 ms in that view. It initially failed modulation-overlay tests. The Mobile shader's UNORM normalization divided a neutral multiplicative factor by two; its adapter now compensates the multiplier. Neutral, dark and bright GPU tests subsequently passed. See [Godot's Mobile fragment pipeline](https://github.com/godotengine/godot/blob/master/servers/rendering/renderer_rd/shaders/forward_mobile/scene_forward_mobile.glsl) for the normalization, and the retained GPU readbacks for this installation.
- That Vulkan experiment still failed the frame-cadence target. At that stage it was not the default renderer or qualified across the seven maps. The subsequent map/weapon qualification and default switch are recorded in LOADING_PERFORMANCE.md. No game process or installed-game settings were used or changed.

Evidence is under `data/.desktop/standalone3d/validation/motion/`. Preserve failed results alongside final results. `motion_audit.gd` separates functional interpolation checks from the cadence verdict; a green functional result must never be presented as a smoothness or native-parity pass.

The final default-renderer run (`verified-final-result.json`) passed the owned-window/control/resize checks with no renderer errors. The actual camera height interpolation error was approximately 1.34e-8 metres, and the bob-input error was zero. All five sampled later-round weapons were available immediately as models. Draw readiness still ranged from 22 to 263 ms; first-use rendering stalls are not eliminated. All 29 models were prepared before Ready (19.078 s in this run). Engine process intervals were approximately 40.2 ms on average and 53.6 ms at the 99th percentile, exceeding the initial 16.67 ms floor. `acceptance.json` therefore records functional success with both smoothness and native visual parity explicitly false. The 96 Python checks and three headless suites passed; none overrides that verdict.

## Next architectural gate

November 12 follow-up: the retained Anubis static sun-mask path is qualified
separately from other maps/revisions. Death-input alignment, independent stock
fire layers, empty-smoke sampling, immutable material sharing and first-person
self-shadows are implemented. See the dated follow-up in VISUAL_MATCHING.md and
`validation/rendering-followup/acceptance.json`. Functional/GPU witnesses and
prepared loading success do not override the false smoothness/native-parity
verdicts or the retained failed cold-cache and slow-frame runs.

The subsequent death/utility stability pass is recorded in
`validation/death-effects-followup/acceptance.json`. It preserves the last living
pose through death, makes fire patch identity/buffers/bounds stable and fixes
lingering glow/audio after extinction. Recorded smoke categories are now bound
to entity generations. A direct-RGB smoke trial passed functional checks but
failed visual review and was rejected. The retained full Anubis preparation
opened in 13.906 seconds; 2,962 engine intervals over 30 seconds averaged 10.070 ms
with p99 15.648 ms and maximum 18.872 ms. Five later-weapon seeks still needed up
to 64 ms to draw. These are scoped measurements, not universal acceptance.

Reduce world/light submission overhead using Source-compatible spatial/visibility and rendering contracts, rather than small per-frame script optimizations or indiscriminate mesh merging. Establish exact render-state and geometry equivalence before enabling a different default backend. Continue reconstructing original animation/effect runtime behavior in parallel stages of the implementation plan, without labeling approximations as completed native systems.

### First visibility implementation

The tested Anubis revision now uses its original compiled visibility data to
skip eligible hidden world surfaces while retaining original shadow casters and
all effects/transparent/unknown material families. Ten full-viewport comparisons
passed; normal embedded playback confirms automatic activation. Draw submission
fell by up to 26%. Other map revisions retain full rendering until validated.
See [WORLD_VISIBILITY.md](WORLD_VISIBILITY.md) for cache safeguards, tests and
measured limits. Startup and sustained playback still exceed their targets;
the current acceptance verdict remains unchanged.
