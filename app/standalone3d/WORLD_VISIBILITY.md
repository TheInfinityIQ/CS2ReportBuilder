# Source visibility in the standalone viewer

The optional world optimization uses the installed map's compiled
`world_visibility.vvis_c`, read through the existing pinned VRF 20.1.7467 library.
It neither runs CS2 nor modifies installed assets or saved game settings. Godot
4.7.2 Steam and the existing Compatibility renderer remain the tested defaults.

## Rendering contract

- Only static, opaque geometry from recognized original Source shader families
  is eligible. The original material classification is required: the glTF export
  incorrectly labels some ambient effects opaque. Effects, foliage, water,
  overlays, transparent/billboard/displaced meshes and unknown materials retain
  full drawing.
- Camera-hidden geometry keeps its original shadow casting. Non-casters can
  stop drawing; casters become shadow-only. Local light tests use their entire
  conservative influence bounds, not just their origin.
- Tight unknown bounds remain always visible. Expanded bounds include adjacent
  free-space cells around solid/thin surfaces. Unknown camera regions, including
  free-flight outside the visibility volume, restore all original drawing.
- Runtime changes use packed visibility differences. Only changed instances are
  submitted when the camera crosses visibility clusters; no position, camera,
  lighting-strength, resolution or recorded-event changes are made.

## Cache and activation

`visibility_assets.prepare(game, native_scene)` creates a small shared companion
for an **already prepared, unchanged map revision**. It does not extract the map
or decode demos. It uses the existing .NET SDK/reader and managed dependencies.
No extra image conversion runtime or per-demo copy is required.

Preparation does not enable culling. An owned-renderer comparison must pass
before `visibility_assets.certify(manifest, report)` publishes the selector under
`data/.desktop/standalone3d/visibility/<map-revision>/active.json`.
The companion is tied to the source fingerprint, scene identity, material
classification, lighting metadata and hashed visibility binaries. The renderer
also compares its point queries against native-reader probes. Missing, changed,
damaged or unsupported data keeps full rendering. Keep the algorithm version in
the Python/Godot readers synchronized when changing the cache's meaning.

The replay worker reads a validated companion directly, including when reusing
an existing demo preparation. Reloading restores the previous scene first.
Other map revisions remain on full rendering until independently prepared and
validated. This workflow does not bypass the existing map approval policy.

## November 11 evidence

Enabled for cached Anubis revision `72f45768ff0154af40b4`, visibility CRC
`20181c46`. It binds 4,993 targets, including 4,328 eligible static meshes.
Native-reader checks cover 62 known points and two unknown points.

Ten first-person/chase views across early and later rounds passed a full-viewport,
every-pixel comparison. The gate permits at most six pixels above a 3/255 channel
tolerance; observed counts were 0–2. This establishes a narrow render-equivalence
check for this optimization, **not native-CS2 visual parity**. The failed prototype
that removed an ambient steam card was rejected before activation.

Draw submission fell by up to 26% in these views. One camera region deliberately
kept full rendering and had no reduction. The balanced disabled/enabled/enabled/
disabled motion test measured approximately 49.8 ms versus 39.7 ms average frame
intervals, about a 20% reduction, across 224 measured frames per condition.
Both optimized runs still exceeded a 16.67 ms frame budget, with worst frames of
45.2 and 65.8 ms. Cell changes took approximately 1.2 ms in this interval. ABBA
repetitions are retained separately to expose warming/order effects.
There is no native-CS2 timing
baseline and no claim of outperforming CS2.

Normal embedded Toolbox playback confirms automatic activation, camera/player
selection, seeking, resize/ownership and clean shutdown. Measured Ready time was
18.266 seconds, including existing stock-asset warmup; the ten-second target
remains unmet. Visibility binding itself took 30.652 ms.

Private evidence: `validation/world-rendering/full-frame-proof-result.json`,
`enabled-check-2-result.json`, `motion-balanced-result.json`, and the headless
`test_world_visibility.gd` result under the standalone cache. The latter checks
shadow preservation, effects, displacement, unknown regions, corruption,
production selection and map-revision rejection. Python tests exercise activation
and dependency-change gates.
