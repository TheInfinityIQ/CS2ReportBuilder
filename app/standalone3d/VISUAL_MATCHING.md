# Visual matching — November 12

The immediate prepared-demo loading target is now **under 30 seconds**. Visual
matching has priority over the previous ten-second stretch target. The viewer
is closer to the accepted CS2 reference, but **not visually indistinguishable**.
Animation/ragdoll, particle/smoke/fire, exposure and material differences remain.

## Movement and seek follow-up

The movement controller now blends adjacent stock directional clips at the same
recorded gait phase, and blends start/stop, walking/running and crouch poses.
Previously it selected one direction and switched crouch at 50%, then softened
the change using the previously rendered frame. That produced different body
poses at the same tick after different seeks. The new body sampler has no frame
history and evaluates only body tracks, leaving weapon actions on their existing
layers. Original clips, bone transforms at single-clip endpoints and recorded
world movement are preserved. These blend ranges are presentation choices;
Valve's complete animation graph, foot locking and physics ragdolls remain open.

The real CT/T rig tests expose the former discontinuities: a 0.02-degree input
change across directional boundaries caused 30–55 degree joint changes, and
crossing half crouch displaced a bone by about 35 cm. The new tests cover both
teams and pistol/rifle/knife gaits, including the blend boundaries themselves.
Boundary changes are now below 0.1 degrees and 0.1 mm in these samples; the
same-tick seek-history difference is zero. Forty-two single-clip comparisons
also match the imported AnimationPlayer body poses. This is continuity and
preservation evidence, not a native-animation equivalence claim.

Backward seeking now reconciles the active grenade/effect IDs instead of
destroying every hierarchy. Unchanged smoke frames retain their original
texture; a 32-entry LRU reuses recently visited occupancy volumes after expiry.
That is at most 1 MiB of R8 occupancy payload in the memo, plus currently active
effects and resource overhead. A recording change clears the memo and ray
endpoints, so reused IDs cannot display another demo's smoke. HE/bullet clearing,
fire patches, lifetime, sounds and recorded timestamps retain their existing
behavior. Smoke/fire artwork and simulation were not made native by this change.

Evidence is under `validation/locomotion/`: `baseline.json`, `blended.json`,
`weapon-audit.json`, `checks.json` and the embedded-renderer results. The stock
audit exercises 420 pose cases across 42 weapons and both teams; its two existing
Zeus reload capability notices remain explicit. No asset re-extraction, demo
rebuild, installed-game write or game launch was needed.

## Atmospheric sheets and startup reuse

Fixed-tick chase captures exposed large white polygons above Anubis spawn.
Scene isolation and a triangle query identified the original `steam_001` map
sheets, rather than sky pixels or missing world geometry. Their original
`csgo_effects.vfx` material was exported as opaque PBR. The source definition
actually requires additive blending, vertex alpha, distance/fresnel opacity and
depth feathering. The new adapter reads those definitions from the retained
GLB header and uses the existing color textures and already prepared masks.
It handles all three unique atmospheric materials on this Anubis revision,
covering 62 surfaces. The opaque white polygons are fixed in
`prepared-frames/4737-baseline.png`; the underlying geometry remains present.
Fourteen independent GPU witnesses cover mix/additive alpha, vertex alpha,
depth feathering, distance/fresnel fade, front/back-face behavior and three-mask
multiplication. Godot's existing back-face normal flip is accounted for rather
than applied twice. All seven map fixtures pass these witnesses. Those fixtures
use four representative weapons on two stock players, not complete recordings.

The opacity equations follow the pinned [VRF effect shader](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/20.1/Renderer/Shaders/csgo_effects.frag.slang).
Anubis's `dust_002` steam mask has not been retained in this map cache. Its
absence remains reported as a mask fallback; no newer installed-game resource
was silently substituted. Its steam sheets still lack that mask's noise detail.
Future approved map setup now prepares masks for the shader family, instead of
only two hardcoded material names, and checks the original package revision
before importing and again before publishing. An update during mask preparation
prevents publishing its receipt. Shared `materials/default` and
`materials/particle` masks are supported alongside atmospheric masks, while
absolute paths and traversal remain rejected. Existing historical map caches
were not re-extracted.
This does not establish complete native effect/fog
behavior. The sky-sampler experiment did not fix the polygons and was reverted.

The existing small lighting-selection memo now refreshes automatically after
its source code or map dependencies change. It previously required a diagnostic
flag, leaving every normal open to repeat the same thousands of selections.
Writes remain bounded and atomic; failed writes leave playback usable. Changed
scene size/time, lighting metadata or source revision rejects the old memo.
Anubis's memo is about 474 KB and contains no textures or geometry.

The first full Anubis follow-up opened in 25.625 seconds. A subsequent run took
54.812 seconds; Windows reported 98% physical-memory use immediately afterwards.
That observation does not establish memory pressure as the only cause. The failed
timing is retained in `final-result.json`. After refreshing the lighting memo,
complete runs took 14.984 and 14.282 seconds, and the final effect correction took
14.407 seconds. The final build took **16.328 seconds** with its ordinary prepared
cache. A fresh Toolbox shader-cache run took **32.813 seconds**, missing the
30-second gate; its failure remains in `verified-result.json`. The driver cache
was not cleared. Native functional checks and cleanup passed in both runs.
The seven synthetic map fixtures took 5.0–12.875 seconds in their final checks.
These are local measurements, not a guarantee for every machine or recording.
All 116 standalone and 30 desktop Python tests pass, along with ten headless
suites. Final continuous playback averaged 28.4 ms per engine frame, with a 31.2 ms
99th percentile, exceeding the initial 16.67 ms floor. Native visual parity and
complete smoothness remain false. `acceptance.json` separates those failures
from the passing movement, shader, map and playback-function checks.

### Earlier lighting/pipeline pass

An additional final check caught an intermittent 711 ms CPU seek stall near
the end of the pistol round. The failed run is retained as
`cold-pipeline-failure.json`. Preparation now renders representative existing map
meshes for each shader/vertex layout, including shadow pipelines, before Ready.
The smallest existing mesh is selected for each layout; original meshes,
materials and textures remain shared and unchanged. The Anubis case selects 25
representatives. Seek diagnostics also retain CPU phase timings. Preparation
errors now report a failure to Toolbox instead of leaving the loading screen
waiting indefinitely. Temporary preparation also uses a separate sky radiance
state, preventing its light/camera from rebaking the main view's sky. These checks do not prove that every possible seek stall
has been eliminated.

## Implemented corrections

The retained Anubis first-person reference at tick 6837 exposed a major lighting
error: the imported sun was overwritten with the same 0.65 review intensity on
every map. Anubis actually authors brightness 6.35. The viewer now reads the
retained map's original sun strength, color, direction, shadow and specular
settings. The review slider multiplies that authored strength rather than
replacing it. An explicitly sunless map no longer inherits a previous map's sun.

The small metadata companions cover the seven already prepared maps:

| Map | Authored sun strength |
| --- | ---: |
| Anubis | 6.35 |
| Ancient | 3.8 |
| Dust2 | 2.5 |
| Mirage | 3.0 |
| Inferno | 3.0 |
| Cache | 1.9 |
| Nuke | 2.4 |

Reflection changes preserve original BC6H pixels and authored mip levels:

- Vulkan uses a real cubemap array, providing filtering across cube faces.
  Compatibility retains its 2D-array fallback. Each backend holds one reflection
  bank, without another export or texture cache copy.
- Roughness selects the square-root mip remap and dominant reflection direction
  used by the source renderer. Adjacent integer levels are explicitly mixed:
  the first fractional-LOD implementation failed a GPU interpolation witness;
  the explicit interpolation passes it. The underlying driver/runtime cause of
  the initial result has not been established.
- Original cubemap radiance coefficients provide luminance normalization against
  local baked irradiance. Dark areas no longer receive an unrestricted bright
  reflection. Each coefficient companion is bound to the original atlas hash.
- Baked directionality now clamps grazing directions and applies the original
  flatness response. Curvature uses world normals and Source position units.
- Geometric roughness suppresses subpixel specular sparkle through derivatives,
  rather than blurring the rendered image. Direct shading uses Source Lambert
  and GGX/Schlick-Smith equations with Godot's PI-scaled light-color convention
  accounted for. First-person lighting copies the same specular gate as the sun.

Preparation reads only unchanged, retained map archives and writes about 200 KB
of lighting metadata across the pool. No geometry, texture, demo or analysis
re-extraction was performed. Map hashes are checked before reading; an archive
update during preparation prevents publication. Missing/unsupported metadata
uses the existing fallback and map-setup warning. A new installed revision still
requires the existing explicit setup approval. CS2 is never started.

## Evidence and practical limits

Evidence is under `data/.desktop/standalone3d/validation/visual-match/`.
`prepared-pipelines-result.json` and `prepared-pipelines-frames/` contain the complete Anubis test,
six fixed first-person reference views, paused-frame and repeated-seek captures.
`final-pool/summary.json` contains seven map tests, each exercising lighting
controls and 34 numeric GPU witnesses, plus four representative stock weapons on
both teams. These synthetic map fixtures do not certify every recording.

The complete Anubis test reached Ready in **19.0 seconds**.
A second test with a fresh Toolbox shader cache took **21.891 seconds**
and passed the same 30-second budget. That does not clear the GPU driver cache
or establish readiness for every recording. The long seek stall did not recur
in these two tests; the worst CPU seek update in the fresh-cache test was 31.1 ms.

The numeric witnesses cover cube-face orientation, authored/fractional mip
selection, projection, irradiance normalization, direct BRDF values, geometric
roughness, flat/grazing lightmap directions, shadow channels and specular AO.
The earlier 42-weapon coverage is retained separately; no animation-bank change
was made in this pass. All 111 standalone and 30 desktop Python tests passed,
along with seven headless suites and the actual owned-renderer checks.

Manually selected static regions of the matched native tick show the sunlit
ground's mean absolute RGB error falling from about 88 to about 14 on a 0–255
scale. This excludes actors and UI; it is not a whole-frame parity score. Shadowed
walls still differ in brightness/color. Paused captures at two reference moments
were pixel-identical. One repeated seek differed at nine edge pixels above a
3/255 threshold; the other was identical. This bounded sample does not prove
flicker-free playback for every view or round.

`acceptance.json` records the current loading budget and measured readiness while
explicitly retaining `native_visual_parity: false`. The fixed review exposure,
incomplete native animation graphs/ragdolls and approximate effects remain the
next visual gaps. Failed earlier candidates are retained alongside final results.

## Source contracts

- [VRF sun upload and brightness](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/20.1/Renderer/Renderer/World/WorldLightingInfo.cs)
- [VRF environment filtering and normalization](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/20.1/Renderer/Shaders/common/environment.slang)
- [VRF radiance coefficient reduction](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/20.1/Renderer/Renderer/SceneEnvironment/SceneEnvMap.cs)
- [VRF lightmap directionality](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/20.1/Renderer/Shaders/common/lighting.slang)
- [VRF geometry/roughness functions](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/20.1/Renderer/Shaders/common/texturing.slang)
- [VRF direct BRDF](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/20.1/Renderer/Shaders/common/pbr.slang)
- [Godot light energy convention](https://github.com/godotengine/godot/blob/4.7-stable/servers/rendering/renderer_rd/storage_rd/light_storage.cpp)

The pinned reader's open-source equations guide these adapters; importing them
does not reproduce every feature of Valve's native shader or animation runtime.

## November 12 follow-up: death inputs, particles and static shadows

The selected Anubis recording now has a 64 KB death companion decoded with the
existing DemoFile/.NET runtime. It joins 221 of 222 deaths by Steam ID and tick,
using recorded server origin and death facing. Collapse fallback selection uses
hit region instead of player-slot/tick randomness. The remaining death keeps its
existing fallback. The full recording supplied no ragdoll bone transforms;
client-side body physics and impact-driven collapse are still unresolved.

Stock fire uses 131 individually filtered, compressed layers from the retained
PNGs. This prevents adjacent atlas frames contaminating their mipmaps and adds
depth feathering at opaque intersections. It adds one shared 5.21 MiB bank, not
assets per demo. Older 32-frame atlases retain their original sequence contract;
an explicit incompatible/missing new bank is rejected. Smoke handles sky depth
without unprojecting infinity and skips exactly empty integration samples. The
GPU empty-space comparison was pixel-identical; layer isolation and fire-depth
feather witnesses passed. This does not implement Source's full particle graph,
sprite crop metadata or GPU smoke simulation.

Exact immutable world-material sharing reused 445 material states. Four of six
reference frames were pixel-identical; the other two changed one and eight edge
pixels by at most 2/255. Clip hierarchy order and rig bindings are compiled once,
retaining sampled transforms and seek determinism. First-person meshes now cast
self-shadows in their private world. A controlled test on the loaded hands and
weapon changed 154 pixels, with a maximum channel difference of 0.212. The native
eye's static occlusion still gates direct sunlight; the shaded reference moment
correctly showed no additional self-shadow difference.

The retained Anubis revision is qualified for original static sun masks plus live
actor shadows. Drawing static geometry into moving cascades duplicated authored
occlusion. At the sampled view, native masks reduce draw calls from about 5,930
to 2,322. Selected ground/left-wall errors decreased slightly; shadowed-wall
brightness remains different. Qualification requires the exact frozen map
fingerprint, Mobile backend, available native shadow data, compatible render
layers and coverage of every lit static receiver. Other revisions/maps keep the
geometry-shadow path. Disabling or reopening restores/revalidates render states.

Evidence is under `validation/rendering-followup/` in the private standalone
cache. Prepared full Anubis runs measured 15.3–19.0 seconds. Seven two-player map
gallery fixtures opened in 5.4–19.0 seconds; those are not seven full-demo timings.
One gallery run failed the UI-stall threshold, and an old-cache compatibility
failure was retained and corrected; the later Anubis fixture passed. The previous
32.8-second fresh-Toolbox-shader-cache failure remains unresolved evidence.

Native visual parity and sustained smoothness remain false. Frame intervals vary
substantially; a severely slowed run is retained alongside the faster runs.
The final qualified-default run opened in 15.250 seconds and averaged 15.865 ms
per engine frame (about 63 FPS); its p99 was 18.336 ms, still above 16.667 ms.
NVIDIA reported 97–98% GPU utilization even outside an owned viewer test; that
does not identify the other workload or excuse the failed cadence gate. Exposure,
ragdoll simulation, native smoke/fire dynamics and local-light/shadow overhead
still require work. No map re-extraction, game launch or installed-file change
was performed.

Final verification: 122 standalone and 30 desktop Python checks, eight focused
headless suites, the 42-stock-weapon pose audit and seven owned map gallery
fixtures passed. A deliberately missing required fire bank stopped with a clear
error in 4.27 seconds and left no owned renderer running. The fixture now retains
early failure session logs and ends promptly when Toolbox reports a launch error.

The self-shadow adapter uses the installed engine's [Light3D shadow controls](https://docs.godotengine.org/en/4.7/classes/class_light3d.html).

## November 12: death handoff and utility stability

Death presentation now starts from the last recorded living body pose and root,
then blends for 120 ms into the existing authored collapse. The seed is rebuilt
from recorded samples and historical action times, independent of previously
displayed frames. Capturing it does not instantiate a held weapon. Per-actor
snapshot caches are bounded and cleared when the body rig changes. The actual
death fixture measured bone-pose error 3.59e-7, zero root/yaw discontinuity and
zero early-transition error after a backward seek. This fixes the transition;
it does **not** implement native ragdoll physics. The selected recording supplies
no client-simulated ragdoll bone transforms.

Fire patches now use position-based variation and canonical draw order, retaining
their appearance as network lists change or playback seeks. Unchanged patches
avoid buffer uploads; capacity grows only when needed and is retained when the
patch count shrinks. Bounds include camera-facing flame sheets. Extinguished
patches no longer leave an active glow or looping sound; both follow the visual
fade. These changes preserve the independently mipmapped stock fire layers.

The existing DemoFile reader also retains each smoke entity's original color,
seed and generation. All 128 clouds in the representative demo matched without
ambiguous generations. Known color categories select the existing warm/cool
review palette independently of the owner's later team. **Directly applying
normalized recorded RGB was rejected:** the cloud became yellow, despite the
functional tests passing. `verified-frames/` retains that failed visual trial.
The corrected captures are in `extended-frames/`. Native smoke scattering,
fluid motion and the complete fire system remain unresolved.

The final owned-Toolbox fixture opened the retained full Anubis demo in 13.906 s.
A 30.009 s continuous run covered ticks 6400–8329 and four first-use death-pose
snapshots, with 2,962 measured engine intervals: mean 10.070 ms, p99 15.648 ms,
maximum 18.872 ms. Submitted-frame p99 was 16.013 ms. This window meets the
initial 60 Hz p99 floor; it does not prove zero hitches or whole-demo smoothness.
Five later-weapon seeks drew in 25.5–64.0 ms; repeated seeks took 12.8–60.0 ms.
There were no renderer errors. Earlier slow/cold-cache failures remain valid
evidence. All 42 stock weapon pose checks, 122 standalone Python tests, 55 desktop
tests and ten focused headless suites passed. The older desktop layout tests now
explicitly opt into legacy playback and use the current library/analysis tabs.

A bounded texture diagnostic found the native Glock BC7 color's 16.8 million
base RGB pixels identical to the retained model texture, on CPU and GPU. The
original resource's eleven mips can be read directly by RenderingDevice without
recompression. Its whole native chain is 22,369,616 bytes; the uncompressed base
RGB alone is 50,331,648 bytes. This is a one-asset qualification, **not** a deployed
stock-texture replacement or measured production VRAM saving. No bulk preparation
was started.

Evidence: `validation/death-effects-followup/acceptance.json`, renderer reports,
images and focused check logs. The selected demo's 80 KB death/smoke sidecar was
installed with its previous version retained. No demos, analysis, maps, installed
game files or prepared approval receipts changed. The installed game revision
still differs from the retained map preparation; its normal approval gate remains
in place. Native visual parity and a universal smoothness verdict remain false.
