# 3D replay renderer inside Toolbox

## Replay audio and dynamic objects

Selected-demo preparation adds positional objective and player cues from
recorded events, an approximate bomb beep cadence between recorded objective
events, recognized pickup cues, and glass break cues for bound objects.
Samples come from the installed game's shared asset bank. Recognized ground
materials select footstep sounds and a camera-to-source ray attenuates
obstructed one-shot audio. Authored soundscape anchors select nearby ambient
beds when their installed scripts provide a supported track. All 114 Nuke
anchors selected a bed in the Godot fixture. Full sound operators and Foley
remain outside this implementation.

The existing replay reader records transforms, life state and door state for
networked brush breakables and doors. Playback hides a bound breakable on a
recorded removal in a delta update or a nonliving state. Ordinary visibility
changes and full-snapshot replacement do not supply destruction evidence.
The renderer matches the authored model and origin to a unique retained mesh
and creates a separate collider. Whole-map baked collision is ineligible
because it cannot remove one obstruction. The real Nuke demo verified all
four rotating doors and both breakables, including restored collision on
rewind. Other map revisions, grouped meshes and destruction debris require
separate coverage.

The current prepared-demo loading budget is **under 30 seconds** (November 12).
The earlier ten-second measurements below are historical. The latest visual
matching changes and reference evidence are in [VISUAL_MATCHING.md](VISUAL_MATCHING.md).

The [system review](SYSTEM_REVIEW.md) supersedes isolated functional pass results
as the assessment of fidelity. It covers the user's Anubis screenshots, missing
systems, source-material coverage across seven maps and the dependency order for
repair. The renderer is not a completed CS2 viewing milestone.

## Current regression repair

Lighting uses fixed review exposure and corrected dark/bright overlay compositing. World and weapon viewports use 4x MSAA plus pre-HUD edge filtering. All grenade types now have pin/hold/throw animation; recorded strength selects underhand or overhand presentation. Animation reads and grenade rendering preparation happen before Play. Prepared loading is a ten-second target, with measured 4–14 second map runs; stability takes priority. Restart Toolbox after updating the renderer. See the latest system-review section for actual rendered checks and retained evidence.

## Visual fidelity investigation — 7 November 2026

The old smoke fixture established that animations moved bones and effects had
geometry; those checks did **not** establish acceptable appearance. A recorded
Glock shot exposed a real pose defect despite that fixture passing.

### Established causes and changes

- Exported firing clips have a different reference pose from locomotion. Replacing
  the stance with the firing clip spread Glock/USP hands 1.073–1.077 metres apart.
  Recoil is now sampled relative to its own first frame and layered onto stance.
  Using skeleton rest as the reference was also tried and rejected: it raised the
  hands above the head. The final approach leaves Glock/USP hands about 0.075 m
  apart at the tested firing time and preserves rifle stance. Knife attacks retain
  their full authored motion. Bones reset before sampling, so repeated seeks do
  not accumulate recoil offsets. This remains reconstruction, not Valve's complete
  animation graph or first-person arms.
- Smoke formerly had no explicit visual expansion phase. A deterministic bloom
  front now expands over 1.25 seconds within recorded occupancy; neighboring-cell
  filtering softens hard edges. These are visual approximations, not new evidence.
  Recorded positions, occupancy and event timing remain unchanged.
- Fire formerly displayed one sharply pointed billboard per recorded patch.
  Each patch now uses three smaller, turbulent translucent flames with vertical
  billboarding and varied offsets. Diagnostic patch counts still count recorded
  patches, not flame cards. Exact engine particles and fire boundaries remain out
  of scope for this correction.
- Review sunlight was strong relative to ambient fill, with a cool ambient tint.
  Direct light was reduced, warmer fill increased and shadow bias reduced.
  Future imported local lights are no longer blanket-disabled. This is exposure
  balancing, not restored Source 2 global illumination.

### Evidence and limits

`audit_actor.gd` exercised 290 cases (29 prepared held-model definitions × two
team rigs × five actions). All models/selected clips were present; pistol firing
posture and repeated-tick pose checks passed. The capability audit separately
records the absent conventional taser reload clip instead of treating idle as a
successful reload. This matrix does not certify every animation frame or stance.
Results: `data/.desktop/standalone3d/visual-audit/all-weapons.json`; earlier
Glock/USP/AK poses: `actors.json`, `actors-final.json` in that directory.

The embedded native fixture passed at 6.063 seconds for prepared Dust2, with
rendered captures of a recorded Glock shot and smoke/fire at 0.05, 0.6 and 1.8
seconds. Captures are in
`data/.desktop/standalone3d/embedded-check/visual-frames/`; initial comparison
frames are in `visual-before/`. `visual-final-result.json` records functional
checks and clean owned-renderer shutdown. All viewing stayed inside Toolbox;
headless pose checks showed no window. No game files or analysis were rebuilt.

**Still unresolved:** mature smoke remains visibly angular/sparse in inspected
frames. Bloom and filtering do not establish authentic cloud geometry. Inspection
of the [upstream decoder](https://github.com/f-gillmann/demolens/blob/v2.5.0/internal/parser/smokevoxel.go)
confirmed the same grid/mask conventions, but that is not independent ground truth
or validation against CS2's renderer. Canonical extraction was left unchanged.

The seven prepared textured map exports each contain one punctual sun and no
imported local fixture lights. The current scene construction supplies no baked
GI/lightmap node. Their referenced image files were present; that does not prove
correct material interpretation, complete prop coverage or fidelity to the demo's
historical map. See `visual-audit/map-assets.json`. Lighting parity needs a separate
investigation of Source 2 baked-lighting transfer, rather than further arbitrary
brightness changes or pretending fixture lights were restored.

After the user identified Anubis, the material audit reproduced an opaque floating
orange/brown sheet. `anubis_dust_001` is a `csgo_effects.vfx` atmospheric material;
its glTF export omitted alpha blending and the three animated source masks. Its
base texture is a one-pixel white tint with alpha 234, so treating it as ordinary
opaque scenery exposes the underlying polygons. `lightshaft_001` has the same
unsupported effects-shader family. This is an established rendering defect,
although it does not identify every object the user may have seen.

`effect_assets.py` now prepares the small missing mask textures into the selected,
revision-bound private map cache. `map_dust.gdshader` uses those masks with the
source scale/pan parameters, conservative transparency and depth feathering.
Animation uses demo time, including seeks. This is an atmospheric shader adapter,
not a complete implementation of Valve's effects shader. Adaptation is restricted
to the two known materials; normal orange walls, crates and props retain their
standard materials. Map geometry and textures were not bulk reimported.

The same-camera native before/after captures are `embedded-check/anubis-opaque-before.png`
and `embedded-check/anubis-dust-after.png` under the standalone cache.
The inventory records 53 adapted dust/light-shaft surfaces. Native playback passed
at 5.375 seconds using the prepared replay; no shader errors were logged and the
owned renderer stopped cleanly. Twelve focused effect-mask/map-permission tests
passed, covering reuse, repair, unrelated orange materials and escaping paths.
The normal raw-demo opening path also passed at 5.859 seconds with clean shutdown.
See `anubis-effects-result.json` and `anubis-effects-raw-result.json` for the two
fixture results. These timings cover this prepared Anubis demo, not a cold boot.

The current [behaviour-first milestone and acceptance criteria](BEHAVIOUR_PLAN.md)
prioritize grenades, sound, stock models/animation, maps, radar and kill feed;
lighting/VFX can be simplified. The full milestone remains unfinished.

The first stock-gameplay pass is implemented: default SAS/Phoenix rigs,
directional movement/crouch/jump, authored firing/reload clips and animated weapon
parts, held guns and a player-eye weapon view. The tested bank contains 23 stock
weapon models and 45 stock sound samples, shared across demos. Cosmetic knives
resolve to the default knife. Recorded state and event times drive playback.
Pause/seek stop voices; other playback speeds are muted. The Sound button toggles
audio. Generic concrete footsteps and a single reload cue are approximations;
full reload Foley, acoustic occlusion and ambient/objective/death sounds remain.

With stock gameplay, grenades and revised lighting enabled, the latest run opened
the prepared raw Dust2 demo from the library in **6.656 seconds**, with seek
acknowledgement in 0.359 seconds. The strict 10-second gate passed. Real skeleton
movement, recorded reload, changing weapon-part poses, all six grenade types,
recorded smoke/fire reconstruction, player-specific flashes and spatial audio passed.
Use the native fixture's `--raw --max-ready-seconds 30` to enforce the current load budget.
Preparation reuses position tracks and does not rebuild the analysis library.

This is one measured fixture, not a promise for every map or unprepared recording.
Position caches use an
explicit decoder schema, so UI/logging edits do not force duplicate demo parsing.
Native map resources are shared across demos and keyed to source and runtime
revisions. Camera collision is prepared near initial players and extended near
the camera, instead of building every collision mesh before review can start.

Select a downloaded demo in Toolbox's Demo Review **Demos** tab and click **Watch demo**.
The **Watch** tab contains Godot's rendering and controls inside Toolbox.
There is no separate player window. The historical **Open Standalone CS2
Viewer.vbs** shortcut now opens Toolbox. The renderer never starts CS2 or Steam.
The older CS2 engine tab is available through **More options → Legacy playback — uses CS2**.

**Back to demos** opens Toolbox's physical download library under the fixed Steam
`game/csgo/replays` directory. No original-demo locator or pre-existing analysis
is required. `launcher.launch()` requires a native Toolbox parent handle and
private session directory; it refuses to start a floating player.

Runtime discovery, demo verification and startup run outside Toolbox's UI thread.
A single resource-loading thread reads tracks and map assets; scene attachment
and camera collision are built in small batches between frames. Toolbox shows a
cancellable loading screen until ready. A heartbeat detects a stalled/crashed
renderer and provides a retryable error with its session log. A loaded renderer
can reuse its map for the next recording. Original demos and analysis stay intact.

The 2026-11-06 startup follow-up profiled one already-prepared demo, without a
rebuild. Its backend step took 2.734 seconds before and 0.969 seconds after:
runtime-version probing now runs once per executable revision per worker rather
than three times, and NumPy/Pandas imports wait until decoding is actually needed.
The in-memory version cache checks executable file identity, size and timestamps
on every call; missing or changed runtimes do not inherit an old version. Failed
probes are not cached. Map consent and all existing cache integrity checks remain.
The 27 focused regression tests and a full embedded native fixture passed.
Profile artifacts are in `data/.desktop/standalone3d/jobs/latency-investigation/`;
the native result is `data/.desktop/standalone3d/embedded-check/latency-fix-result.json`.
Earlier UI validation measured 12.359 seconds followed by 7.282 seconds. Filesystem
cache residency was not controlled, so these results do not prove that the first
opening after a reboot will always meet ten seconds or establish the entire cause
of that earlier variance. No global cache flush or game-state change was performed.

Playback includes pause/resume, a seek bar, exact tick stepping, round starts,
0.25–8× speed, kill feed, stable SteamID64 player selection, player-eye, chase,
and free cameras. Space pauses, arrows seek, 1/2/3 change camera, F11 expands
this window. In free camera hold right mouse to look; WASD/QE moves, Shift
speeds up, Escape releases the mouse. F11 expands Toolbox's view. Normal game
settings are never changed.

## Prepared map pool and approval

The user-selected pool is **Ancient, Anubis, Dust2, Mirage, Inferno, Cache and
Nuke**. It is an explicit review preference, not an automatically updated Valve
competitive-pool list. The approved batch (`prepare_maps.py`) prepares only these
seven installed maps, one at a time. It reuses completed source/runtime revisions,
retains older/geometry caches, caps each map folder at 8 GB and keeps 30 GB free.
No demo or analysis is extracted by map preparation. Batch progress and per-map
results are recorded in `data/.desktop/standalone3d/jobs/selected-map-pool/`.

All seven maps were prepared and load-checked on 2026-11-06, with textured meshes
and no missing dependencies. Their current map-cache folders total **16.41 GB**
(including the reused Dust2 cache and retained preparation inputs). The final
normal-library Dust2 playback check passed at **7.344 seconds**, with a 0.359 s
seek acknowledgement. This remains a single prepared-demo measurement. The first
post-import run had a 1.016 s UI callback gap (over the fixture's 1 s limit); the
isolated confirmation passed at 0.703 s. The 54 Python/widget checks and the native
map-part roundtrip also passed. Current per-map evidence is in `validation.json`
inside that job folder.

Opening a demo never silently imports an unapproved map. Before conversion, the
backend checks the installed asset fingerprint, exact Godot version and native
cache. Missing/outdated preparation raises a structured request; Toolbox shows a
warning inside the 3D viewer with **Prepare this map** and **Cancel**. Maps outside
the chosen seven are identified explicitly. Merely displaying the warning does
not grant permission or launch a converter. Approval is bound to the displayed
asset/runtime revisions and is rejected if either changes before confirmation.
Completed approvals do not silently recreate a subsequently deleted native cache.
Uninstalled map assets produce an install-first warning with preparation disabled.

Game/renderer updates require permission for newly needed preparation. Prepared
map reuse remains independent of demo decoding. Existing game files/settings and
all prior analysis/demos stay intact; no CS2/Steam process is started.

Cache uses full-resolution, shared native texture parts inside its own revision
folder. Its previous bundled scene exceeded Godot's compressed-container raw-size
limit; [Godot stores that length in 32 bits](https://github.com/godotengine/godot/blob/master/core/io/file_access_compressed.cpp).
Individual resources avoid that limit without reducing texture resolution. The
loader verifies the compressed block table and checks every required part before
reusing this layout. Parts reference only the private map cache. Other maps retain
their working bundled scenes. A fixture verifies that native parts reopen correctly
outside the Godot project directory; oversized-table and missing-part regressions
are also covered.

## Grenades and lighting

HE, flash, smoke, Molotov, incendiary and decoy flight uses recorded projectile
samples, time-aware simplification (2 Source-unit error bound), and interpolation
by demo tick. Recycled entity indices become separate throws. Molotov/incendiary
identity uses the recorded release weapon, not only the projectile class.
All six stock grenade meshes are shared between flight, held and player-eye views.

Detonations, expiry, blindness and round resets come from events. The existing v8
entity reader supplies burning fire patches and decoded smoke occupancy updates,
including changing gaps and extinction. Godot ray-marches the smoke grid with
opaque-scene depth clipping; fire artwork follows the recorded burning patch set.
These are simplified effects, not Valve shaders or verified engine-equivalent
smoke geometry. Grenade spin, flash fade and decoy shot cadence/weapon sound are
approximations. Flash duration and recipient are recorded. The Grenades and Flash
toggles permit unobstructed review; contact sound cues are derived from abrupt
recorded path velocity changes, rather than simulated collisions. The
HUD remains readable through blindness.
Sustained spatial smoke/fire audio seeks to the current age and stops on pause,
seek, muted/non-1x playback, import or cancellation.

Preparation is selected-demo-only and separate from analysis. The tested fixture
contains 310 throws (all six types), 72 decoded smokes, 68 recorded fire areas and
221 blindness events. Its initial entity pass took about 48 seconds; the six
shared models took about 24 seconds to prepare along with companion data/sounds.
Already prepared playback does not rerun these passes. This first-open preparation
cost remains a limit on the 10-second goal for previously unprepared recordings.
No bulk analysis rebuild or game-file changes occur. The shared grenade scenes
total about 34 MB. Recorded paths remain valid across art/runtime updates; shared
art is keyed to the installed asset fingerprint and exact Godot runtime.

Lighting retains the exported map sun's direction and color, normalizes its
photometric intensity, adds cascaded shadows, a procedural sky and balanced
ambient/reflected light. The Review brightness slider changes only the viewer.
Baked Source 2 lighting and authentic skyboxes remain future work.

SHA-256 fingerprints are reused only with an unchanged OS file identity/size/time
stamp. On Windows this includes NTFS ChangeTime, so same-size in-place changes
with restored modification time still invalidate the cache. Unavailable change
stamps fall back to full hashing; a file changing during hashing is rejected.

## Status and limits

This is an early standalone renderer, not a replacement implementation of
Valve's engine. Dust2 has been tested with a complete raw FACEIT recording,
10 players, 118,178 frames at 64 Hz, 21 rounds and 158 kills. Stock models,
basic authored animation and spatial player/weapon audio are supported.
First-person arms use authored stock viewmodel clips, with separate CT/T gloves,
weapon anchors, firing, reload and equip poses. Death events retain a deterministic
authored body pose until the recorded respawn. These are not physics ragdolls.
World locomotion retains the Source-to-Godot root rotation and layers recoil and
upper-body reload over the moving lower body. Native pose checks cover all 42
currently prepared weapon/utility definitions on both teams.
Exact aim/IK and Source animation-graph blending, scopes, dynamic props and
authentic grenade spin/throw poses remain incomplete. Smoke uses decoded network
occupancy with optical boundary reconstruction, bloom and demo-time shading;
fire uses stock animated flame imagery over recorded burning patches.
Water, layer weights, packed normals and modulation/animated overlays have
dedicated material adapters. Baked lighting, skybox and some shader families
still differ from CS2.

The default fast renderer adds screen-space contact shading before transparent
effects and preserves invisible source light blockers. Shader/user data stays
inside the private Toolbox cache. The Forward+ lighting experiment is available
through `CS2_TOOLBOX_RENDERER=forward_plus`, but is not the default: its measured
16-second prepared load misses the startup target. The default Anubis fixture
loaded from the downloaded demo in 6.4 seconds after preparation; the subsequent
prepared-replay check took 5.4 seconds. Both passed embedding, seek, resize,
navigation/shutdown and actor checks without renderer errors.

The small read-only resource bridge uses the pinned ValveResourceFormat package
and a private .NET 10 runtime under the Toolbox cache. It extracts authored pose
and model metadata once; it does not run during ordinary prepared playback.
The game, Steam and game preferences are never opened or altered by this path.

## Full stock set, map matrix and review HUD

The validation set contains 34 firearms, Zeus, one default knife and six grenade
types. Cosmetic knife variants are canonicalized to that default knife.
`audit_stock_poses.gd` checks CT/T viewmodels through applicable idle, firing,
reload and draw poses; verifies authored world firing clips and upright action
poses; and opens all 36 firing and 34 applicable reload sound assets. The audit
records generic viewmodel fallbacks separately. The installed resources currently
use generic poses in this reconstruction for M4A1-S, USP-S and decoy; these are
not certified as weapon-specific Source animation-graph parity.

`validate_pool.py` runs an owned embedded map/weapon matrix on Ancient, Anubis,
Cache, Dust2, Inferno, Mirage and Nuke. Each map renders every definition for CT
and T (588 first-person cases total), with representative world captures.
Gallery placement uses floor, head-clearance and sight-line collision checks.
These are labelled **synthetic rendering fixtures**, not recorded player paths
or seven real-demo playback passes. Real recordings are separately checked on
Anubis, Dust2 and Inferno. The fixtures and results stay under
`data/.desktop/standalone3d/validation/`, outside the downloaded demo library.
The complete result is `validation/pool/results.json`; real playback evidence is
`validation/real-results.json`; stock pose/audio evidence is
`visual-audit/all-stock-poses.json`.

The review HUD has a CT/T score strip, alive counts, current/total round, recorded
phase and elapsed clock, side-grouped player buttons, observed player/weapon/HP
card and a separate chronological kill feed. Kill cards preserve recorded team
colours, names, weapon and headshot/wallbang/smoke/noscope indicators. The compact
viewport shows up to four recent kills; larger viewports show five. Missing
scores are displayed as unavailable, never inferred from kill counts. Phase
time is elapsed time, not an assumed match or bomb countdown. Scores, round
phases and kills reconstruct on seek from the small `hud.json` companion.

The expanded audit corrected the CZ75 world firing clip name, Dual Berettas
viewmodel firing and G3SG1 idle selection, valid zero-scale accessory bones,
punctuation variants in weapon aliases, and missing MP5-SD/UMP-45/CZ75 fire and
shotgun/machine-gun reload sound mappings. Workshop model texture paths are
accepted within the same bounded, revision-bound private cache.

Installed map geometry is used. The installed map's revision is **not verified
against the demo**; a recording from an older map version may misalign. Game
asset fingerprints select new caches after updates; older caches are retained.
This prevents accidentally reusing a different installed asset version, but
does not recover missing historical maps. No game update rollback is attempted.

Only the selected recording is parsed, at up to 64 Hz. The first version
accepts completed CS2 `PBDEMS2` recordings up to 2 GB / one million ticks,
at most 64 identities and 512 MiB of compact player tracks. CS:GO and CS 1.6
demos are rejected. Steam IDs stay strings, avoiding floating-point identity
loss. Positions/aim are decoded from the demo, not estimated from screenshots.

## Assets, dependencies and cache

All outputs live under `data/.desktop/standalone3d/`: map exports, replay tracks,
job progress/logs and the pinned offline map reader. Existing demos, analysis,
installed game assets and saved preferences are not modified. Closing Toolbox or
using **Stop / cancel** stops its renderer, demo preparation worker and supervised
map-reader child, including cancellation during startup.

Dust2's current asset revision has explicit approval for a textured import
(approximately 1.17 GB). Texture grants in `settings.json` are tied to source
fingerprints and become invalid after an asset change. Other maps use a smaller
geometry export. Ask before a further large/textured import. The importer checks
free space, enforces a ten-minute timeout and stops at a 3 GB cache limit.
No bulk library conversion runs at startup. UI progress reports stages, not a
predicted completion percentage for individual native parser operations.

The installed Steam Godot **4.7.2** is preferred and invoked directly as a runtime,
without launching its editor or Steam. Steam libraries are discovered locally.
A configured `godot_executable` or existing developer runtime is a fallback only
if Steam's installation is unavailable. No runtime download runs during startup.
demoparser2 and its dependencies use the existing `app/extractor/.deps` folder.
The map reader is [Source2Viewer CLI 20.1](https://github.com/ValveResourceFormat/ValveResourceFormat/releases/tag/20.1),
pinned by SHA-256 in `setup_tools.py`. If missing, explicitly run
`python app/standalone3d/setup_tools.py` to download its 53 MB official archive.
`--verify-only` checks an existing archive without downloading or installing.
Playback uses no network service, browser, VConsole, firewall rule or UAC prompt.

Source2Viewer's [export fidelity documentation](https://s2v.app/ValveResourceFormat/guides/format-support.html)
describes the interchange limitations. Credits/licenses:
[Source2Viewer](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/20.1/LICENSE),
[Godot](https://godotengine.org/license/),
[demoparser2](https://github.com/LaihoE/demoparser).
Valve assets remain local; do not bundle imported maps/textures with source releases.

## Verification

The November 9 lighting pass corrects directional self-shadowing (the repeating
bands previously visible on unrelated walls/floors), blends cascades, and uses a
filmic white point of 4 to retain sunlit material detail. Authored sun direction
and colour remain intact. A neutral ambient fill is mixed with the procedural
sky; previously sky contribution 1 ignored the ambient controls. The Light slider
now affects that fill and sky energy as well as the sun. The isolated first-person
viewport follows the world sun in camera space rather than using a fixed studio
light. It still has no world occlusion or source irradiance sampling.

Layered material adapters consume **exported PNG normals**, not raw VTex channels:
Source2Viewer already expands HemiOct into RGB and moves roughness into alpha.
The adapter no longer decodes those normals twice or reads blue as roughness.
It respects the source texture-transform flag, separate normal/modulation UV
transforms and source specular flags. Direct and indirect specular remain coupled
in this Godot adapter. Water uses depth absorption, foreground-safe refraction
and a Fresnel sky approximation, without diffuse-lighting the scene capture again.

Run `python app/standalone3d/validate_lighting.py` for seven already-prepared-map
lighting checks. This reuses the existing synthetic map fixtures and shared
assets, renders one stock rifle on both sides, and measures actual world-pixel
luminance at three Light settings. It neither imports nor rebuilds maps.
Results, source revision hashes and captures are private under
`validation/lighting/` and `embedded-check/lighting-de_*/`. Full weapon validation
remains separate. Real Anubis captures additionally retain fixed-camera no-contact
and no-shadow controls to distinguish surface/material faults from lighting faults.

These corrections alone are not Source 2 lighting parity. The subsequent authored
lighting adapter below adds supported lightmaps/probes where explicitly prepared.
The generic sky and fallback ambient fill remain approximations; geometry/export defects are separate. No
game process, settings changes or new asset preparation are required.

Final checks: all seven native lighting fixtures passed (2.656–7.734 seconds to
ready), including an independent ambient-only pixel test on each map. The real
Anubis replay passed playback/seek/actor/effect checks at 5.828 seconds with no
renderer errors and clean shutdown. These are prepared starts, not first imports
or a real-demo performance guarantee for all maps. All 57 Python tests passed.
Before/after water and final material captures are retained under
`validation/lighting/comparison/`.

### Authored bounce lighting (Source 8.2)

`source_bounce.gd` reads a small, revision-bound companion next to the shared map
cache. All seven selected revisions now have prepared HDR irradiance, directional
lightmaps and spatial probes, plus authored reflection cubemaps, sun-shadow masks
and local-light metadata. Together these companions occupy about 1.43 GiB.
Original exports, demos, analysis and installed assets/settings remain unchanged.
Nothing starts CS2. The status line distinguishes authored bounce from approximate
lighting. A newer installed revision does not silently reuse an older companion.

Static surfaces use the source draw-call lightmap flag, not simply the presence
of a secondary UV channel. Godot's imported mesh-name prefix is resolved against
the glTF names. The adapter verifies source UNORM lightmap coordinates against
the export, including the world UV scale; a changed exporter/layout stops
preparation rather than guessing. Aggregate fragments inherit lightmap eligibility
only when all source draws agree. Mixed or unknown fragments use probes/fallback.

Moving player/weapon rigs and the independent first-person hands/weapon viewport
sample authored ambient-cube probes. Probe rotations, atlas offsets, half-texel
borders, normal-squared six-face weights, spatial fades and depth interpolation
are preserved. Per-object candidate lists are bounded at eight; truncations are
reported. Volume priority/overlap selection remains an approximation of Source's
object/visibility system. Freed actor bindings are released, and weapon/side
changes receive new bindings. Authored bounce replaces ambient fill where it has
coverage instead of adding a second ambient contribution.

BC6H stays HDR/compressed in GPU texture arrays; Compatibility rejects compressed
3D textures, so depth filtering is explicit in the shader. Light multiplication
and layer blending happen in linear colour space. Compatibility converts user
ALBEDO/EMISSION after the fragment shader, so HDR results are encoded once at that
boundary. This avoids the overly orange/dark first prototype. GPU tests check all
six directions, a diagonal blend, depth filtering and colour transfer against an
independent linear reference.

`prepare_bounce.py --map de_anubis` explicitly prepares/verifies the companion;
`--pool` is a bulk operation requiring user approval. Preparation reuses the pinned
VRF 20.1 reader and existing offline .NET SDK in `tools/lighting-bridge/`, with
supervision, time/space limits, staging, SHA-256 checks and a receipt committed
last. It does not re-export meshes. The supported contract is one-layer Source
lightmap version 8.2; unknown formats/layouts stop preparation. Companion loading
falls back to labelled approximate lighting if its data is unavailable or invalid.

`prepare_reflections.py` and `prepare_direct_lighting.py` provide explicit
`--map` / `--pool` preparation using the same revision identities and supervised
reader. Native BC6H cubemaps keep their authored roughness mips; box projection,
priority and fades choose up to four overlapping volumes. No texture conversion
or per-demo copies are introduced. Static and moving surfaces sample the source
sun-shadow channel independently of dynamic geometry shadows. Enabled source
local lights populate native Godot lights (bounded at 256); photometric scaling,
barn-door shapes/cookies and local-light occlusion remain approximations.

`prepare_lightmap_uv.py` creates a small geometry bank for meshes whose lightmap
coordinates are the third UV set, which the normal Godot import discards. It
references the existing GLB buffer, preserves base/detail and blend contracts,
and remaps the source lightmap input into Godot UV2. Runtime merges this bank
after the blend-geometry bank, with map-revision and geometry-boundary checks.
This removes the shipping-crate checkerboard without disabling lightmaps.

Remaining fidelity gaps include exact Source sky/fog/postprocessing, detailed
character/cloth shaders, precise local lights and private first-person local-light
parity, full animation graphs/ragdolls and exact grenade simulation. These source
lighting adapters do not establish pixel-identical CS2 rendering.

Acceptance for the prepared Anubis revision: 4,603 source-lightmapped surfaces,
59 probe volumes, a source/export UV witness error of 3.15e-8, and a GPU ambient
cube maximum channel error below .002 (six faces plus a diagonal blend). The
actual downloaded replay passed controls/actors/effects. The added GPU fixture
checks 18 reflection orientation/mip/box-projection and static/dynamic sun-mask
cases. All 77 Python tests passed, including corrupt companion data, changed
revisions, mip layout, dependency bounds and third-UV preservation.

With all companions enabled, seven synthetic map/weapon lighting fixtures passed
in 3.406–8.172 s (Ancient 6.266, Anubis 4.453, Cache 6.235, Dust2 5.125,
Inferno 8.172, Mirage 3.406, Nuke 4.860). These measure the owned Toolbox loading
screen to ready, not every downloaded recording or a guarantee under any machine
load. The map read overlaps independent tracks/stock/lighting reads; scene changes
stay on the main thread. Mesh format flags replace unnecessary vertex-array reads.
Results are in `validation/lighting/results.json`; native captures remain under
`embedded-check/lighting-de_*/`. Earlier bounce A/B evidence remains under
`validation/lighting/bounce-*.json` and `validation/lighting/bounce-comparison/`.

After these optimizations the downloaded Anubis recording reached ready in
6.625 s with actor/effect/control and both GPU regression suites passing. The
42-definition stock matrix passed all 84 CT/T cases at 4.531 s to ready. Cancelling
the Inferno loading fixture stopped its owned renderer in 0.94 s total with a
47 ms maximum Toolbox callback gap. Retained results are
`validation/lighting/real-anubis-result.json` and `stock-weapons-result.json`;
the cancellation log is `lighting-cancel-final.log` in the cache root.

Run `python -m unittest discover -s app/standalone3d -p "test_*.py"`.

The 9 November gameplay follow-up adds recorded camera/viewmodel projection,
view punch, ammunition/armor/economy, phase countdowns, radar and optional X-ray;
distance-based gait phase and directional blending; hurt-driven cosmetic blood,
damage cues and shell ejection; source-flag-aware character roughness; and a
corrected viewer-only smoke fill from collision cells/seeds. Fire sprites use
smaller patch footprints and lifetime fades. Existing analysis/raw sidecars stay
unchanged. See `SYSTEM_REVIEW.md` for implementation limits and retained evidence.

Readiness now waits for initial rendered frames before Toolbox attaches the child
window. Map, lighting and audio/actor file reads overlap. First-use shader work is
still part of preparation; the ten-second target is not a guarantee for every map
or recording. Authored inspect clips, recorded inventory, Nuke floor selection and continuous
calibrated gait are implemented. Exact smoke/fire physics, native animation graphs,
IK, ragdolls and full Source shader parity remain approximate. The 700-frame
first/chase audit found no late-round blackout; its original cause was not established.
Prepared replay data is distinct from first-time raw-demo decoding. See the latest
repair pass in `SYSTEM_REVIEW.md` for measured loading times and limitations.

Godot's `--headless --path app/standalone3d --quit-after 5` checks the scene/scripts.
`app/desktop/embedded_smoke.py --replay <prepared-replay.json>` is a bounded native
Toolbox fixture: actual playback, tick seeking from Toolbox, player/camera
selection, floor alignment, native parent/resize/visibility, absence of floating
renderer windows, UI callback latency and renderer cleanup. Add `--raw` to also
exercise demo preparation. Its own viewport capture and JSON results are saved
privately. These checks do not use Computer Use or launch CS2.

Validated map revisions can use their original Source visibility data to reduce
world submission without removing shadows or effects. The currently enabled
revision is Anubis; changed/missing/unaudited companions keep full rendering.
See [WORLD_VISIBILITY.md](WORLD_VISIBILITY.md) for the preparation/audit gate and
performance evidence. This does not establish native-CS2 fidelity or a ten-second
startup guarantee.

The default is now the seven-map-qualified Vulkan Mobile renderer. The approved
shared stock cache, compiled Anubis collision, original sky, lighting corrections
and weapon-instance reuse are described in [LOADING_PERFORMANCE.md](LOADING_PERFORMANCE.md).
Full-demo readiness and sustained playback still miss the requested targets;
map/weapon fixture success does not establish native visual parity.
