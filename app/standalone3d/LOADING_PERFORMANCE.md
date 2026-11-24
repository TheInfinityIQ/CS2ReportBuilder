# Loading and renderer qualification — November 11

The default owned renderer now uses Vulkan Mobile with mailbox presentation on
the installed Steam Godot 4.7.2. It still never starts CS2 or changes installed
game files/settings. `CS2_TOOLBOX_RENDERER=gl_compatibility` remains available for
diagnosis. The separate render-thread experiment was rejected after a GPU colour
test failure and slower loading; it is not enabled.

## Changes in use

- The explicitly approved 33-scene stock cache is prepared once and reused across
  demos. It contains 4,160,569,124 bytes (3.87 GiB); originals are retained.
  Godot writes its own uncompressed resource format. A source revision, changed
  size/time, missing output or invalid header falls back to the original scene.
  Preparing this bank took 35 seconds in the final run. No automatic bulk bank
  preparation occurs when a source changes.
- NTFS compression was rejected: one cached Glock took about 759 ms to read
  compressed versus 68 ms uncompressed. The final cache uses neither NTFS
  compression nor RGB-to-RGBA expansion. No texture downscaling or lossy
  recompression was used.
- The retained Anubis revision has a 6.6 MB compiled-physics companion (673,869
  solid triangles). This replaces the repeated visible-mesh collision scan and
  runtime triangle generation. Player clips use a separate collision layer;
  bullet obstruction tests exclude that layer. The companion reads the original
  map archive only after its hash matches the prepared revision.
- Original Anubis BC6H sky data, entity tint, rotation and brightness are used.
  Compatibility and Vulkan account for their different sky colour contracts.
  Review brightness also controls this sky. Other missing/unsupported skies use
  the existing fallback with a preparation warning. Small map companions are
  prepared through the selected map's existing approval workflow, never by
  silently importing a newer map revision.
- Baked directional-lightmap alpha now limits direct and indirect specular, as
  in the pinned source renderer. This is one shader correction, not complete
  Source shading parity.
- Static lighting queries have a compact revision-bound cache. Source volume
  IDs are looked up by ID after priority sorting, never treated as sorted array
  offsets. Invalid selections recompute. Six Anubis reference-view comparisons
  found no pixels differing by more than 3/255 between cached and fresh queries.
- Settled death poses and unchanged actor probe parameters avoid repeated work.
  First-person weapons retain the already rendered preparation instances;
  player arms are reused across side changes. World actors retain at most four
  recently used held weapons each, evicting older instances and clearing the
  pool on a team change. Textures and geometry stay shared.

## Validation and limits

Seven existing prepared-map fixtures rendered 42 stock weapon definitions on
both teams: 588 cases without asset/shader failures. These are explicitly
synthetic placement tests, not recordings or native-CS2 visual comparisons.
All owned-window/control checks passed after the Dust2 resize retest. The test
now gives resize its own acknowledgement deadline, rather than consuming that
deadline while waiting for an unrelated seek. Gallery fixtures save their own
current screenshot; the host deletes the previous screenshot before each test.

Synthetic fixture Ready times ranged from 4.6 to 18.9 seconds. They must not be
used to claim full-demo loading under ten seconds. The complete Anubis recording
prepared all 29 referenced weapon models and 219 pose clips, with 39 fast-cache
resolutions and no fallback. It took 14.0 seconds with disabled presentation
sync and 16.3 seconds in the mailbox/instance-reuse run. In the latter, live
process intervals averaged 18.0 ms with a 22.6 ms 99th percentile. The 16.67 ms
initial smoothness floor was therefore **not met**. Five later-round weapon
seeks had their models ready, but draw readiness still ranged from 30 to 72 ms.

Evidence: `data/.desktop/standalone3d/validation/loading/`, especially
`mobile-pool/`, `verified-cache-result.json`, `instance-reuse-result.json`,
`cache-preparation-final.json` and the cached/fresh reference frames.
Failed earlier candidates are retained alongside successful results.

The remaining dominant costs are resource upload/read and world/shadow draw
submission. Further work must preserve original material, visibility and
shadow contracts. Potential native compressed-texture reuse must first prove
that the installed texture matches the retained asset revision; a Steam update
must not mix newer textures into an older cache. Native animation graphs,
ragdolls and particle/smoke behavior also remain incomplete. These tests establish
functional improvements, not indistinguishability from CS2. See
[REPLAY_ACCEPTANCE.md](REPLAY_ACCEPTANCE.md) for the unchanged parity verdict.

## Final default-path check

With no renderer/presentation environment overrides, the complete Anubis replay
was ready in **14.14 seconds**. Functional checks, embedding, resizing, seeking,
grenades, lighting GPU checks and renderer cleanup passed without renderer
errors. Live process intervals averaged 19.08 ms (99th percentile 20.93 ms),
so sustained smoothness still failed its initial gate. Repeated seeks reused
world and first-person instances; their second-pair CPU updates were 7.6 and
10.9 ms. Six full-frame reference comparisons found no pixels above the 3/255
threshold after instance reuse.

The read-only stock verification compared all 33 original/prepared scenes one
pair at a time: mesh arrays, skin bindings, skeleton/rest poses, material values,
texture pixels/mip flags and animation tracks matched. This proves equivalence
to the retained preparation inputs, not to CS2's renderer. All 107 standalone
Python tests, 30 desktop tests and seven headless suites passed. The final map
qualification is `mobile-pool/qualified.json`; explicit incomplete performance
and parity gates are in `acceptance.json`. No bulk demo/analysis rebuild or new
map-revision import was performed.
