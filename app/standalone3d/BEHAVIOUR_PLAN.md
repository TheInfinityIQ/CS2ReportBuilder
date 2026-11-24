# Behaviour-first replay milestone

Current assessment: [system review, 7 November 2026](SYSTEM_REVIEW.md). Earlier
functional/timing checks below are historical evidence, not acceptance of water,
materials, geometry, FPV hands, death bodies, locomotion or effect appearance.

User decisions: keep all viewing inside Toolbox, use installed Steam Godot 4.7,
never start CS2, allow one-time map preparation, aim for ready-to-review in thirty
seconds afterwards (updated November 12; earlier ten-second measurements below
are historical). Current visual-matching work and its remaining limits are in
[VISUAL_MATCHING.md](VISUAL_MATCHING.md). Grenade behaviour,
spatial sound, stock models, animation, map layout, radar and kill feed are the
first usable milestone. Cosmetic weapon/knife/agent variants are excluded.

## Observed status, 2026-11-05

The approved textured Dust2 recording opened from its raw .dem in 6.531 seconds
after preparation, including verification and cache lookup. The renderer's
track/map reading took 4.282 seconds; total renderer loading took 4.489 seconds.
The test also passed playback, exact seeking, player-eye/chase selection, map
floor alignment, native parenting, resize, hide-on-navigation and shutdown.
This is one local fixture, not a general performance guarantee. First unseen
recording decoding, other maps, shader variants and future models/audio still
need separate measurements.

The native map is one compressed resource shared across demos and pinned to
source fingerprints, exact Godot version and conversion-adapter version. The
native Dust2 resource is about 742 MB after GPU texture compression. The existing interchange geometry
and textures remain as preparation inputs/fallbacks, so storage is NOT yet a
fully deduplicated asset store. Game files are read-only.

Stock gameplay update: the shared bank now includes two default player rigs,
23 stock weapons, 146 selected authored clips per rig and 45 sound samples for
the test recording. Models resolve the installed `agents/models` resources and
reject obsolete dummy meshes. Weapon skeletons are retained; authored weapon-part
poses transfer with the player's reload/fire clips. Initial visible weapons load
before readiness; other needed guns stream one at a time, prioritizing the viewed
player. Recorded motion/stance/reload state and event timing live in an independent
companion cache. Sound pauses on seek and is muted outside 1x playback.

Latest prepared raw-demo readiness with GPU-compressed map textures measured
8.266 seconds, passing the strict 10-second gate; seek acknowledgement took 0.360
seconds. Native checks passed real skeleton motion (24 changing bones),
recorded reload, two visibly changing weapon-part poses, visible player-eye weapon,
spatial sound emission, silence on seek, embedding and cleanup. Stock conversion
intermediates are removed after native serialization; runtime assets are shared,
not copied into each demo. Missing first-person arms, full animation blending/IK,
ragdolls, scopes, surface-specific footsteps, complete reload Foley, acoustic
occlusion and wider game sound coverage remain explicit limitations.

The optimized map resource uses GPU-compressed textures (about 742 MB). The
unreferenced older 1,031 MB native resource was removed after validation; source
conversion inputs and installed assets remain intact. Reload event keys normalize
JSON player numbers to integer roster indices, preventing missed lookups and
end-of-clip poses. Weapon-part tracks are sampled directly from the authored clip.

## Required behaviour and verification

Grenade/lighting pass (2026-11-06): six shared stock grenade meshes; recorded
flight, detonation/expiry, stable per-throw identities, Molotov/incendiary release
classification, player-specific blindness and decoy active/end windows. The
existing v8 entity reader provides smoke occupancy updates and burning fire patches.
Seeking reconstructs geometry, including extinction and smoke changes; loops stop
on pause/seek/import and remain muted outside 1x. Cosmetic spin, flash fade,
decoy cadence and effect artwork are approximate. The test recording covers
310 throws, 72 decoded smokes, 68 fire areas and 221 blind events.

The exported map sun direction/color now drives normalized sunlight and cascaded
shadows, with a procedural sky, balanced ambient/reflections and viewer-only
brightness. No bake or map reimport was needed. Latest normal-library raw-demo
readiness with all systems enabled: 7.687 s; seek acknowledgement 0.360 s. Native
checks passed all six projectile types, smoke/fire geometry, expiry, repeated seeks,
flash camera/duration, utility audio, lighting controls, embedding and cancellation.
The full milestone is still incomplete: radar, detailed sound coverage and exact
animation/engine parity are not delivered by this pass.

First unprepared demos still require a selected-demo entity pass (~48 s measured),
in addition to decoding and any shared asset preparation. That cost is NOT covered
by the prepared-playback 10-second result. No library-wide extraction was run.
OS-change-stamped SHA caching removes repeated full-file checks on ordinary opens;
Windows ChangeTime catches in-place writes with preserved size/mtime. Game/runtime
changes refresh shared utility art independently of recorded demo paths.

| System | Initial implementation | Acceptance |
|---|---|---|
| Maps | Installed geometry, normal collision, doors/breakables driven by demo state; simple lighting | Player, projectile and radar coordinates agree; dynamic obstructions reflect the selected tick |
| Models | Shared stock CT/T rigs and default weapon/view models; no cosmetics | Team/weapon switches, crouch, death, plant/defuse and carried equipment remain correct after a seek |
| Animation | Recorded velocity, stance, aim, jump, firing, reload and weapon state drive a small explicit animation controller | Stopping/turning/crouching and seek reconstruction have no stale animation; use approximate blends until exact pose data is supported |
| Grenades | Recorded projectile samples and throw identity; event-driven detonation/expiry | Recycled entity IDs do not merge throws; bounce paths and smoke/fire lifetime follow evidence, not a new physics simulation |
| Effects | Simple muzzle flash, bullet impact, smoke volume, flash overlay and fire footprint | Correct trigger tick, duration, position and team/player relevance; no claim of authentic volumetric smoke or lighting |
| Sound | Stock fire/reload/footstep, hit/death, grenade and objective sound events, positioned in world space | Pause silences playback; seeking clears old voices; resuming doesn't replay previous shots; speed changes have an explicit audio policy |
| Radar | Existing map overview metadata and coordinate transforms, map floor selection, stable player identities, facing, bomb and grenade markers | Same tick/team/alive state as 3D; no leakage between rounds or maps |
| Kill feed/HUD | Existing player_death evidence, weapon/headshot/teamkill/world-kill metadata, round/score/bomb state | Chronological bounded feed; correct team at event time; seek backwards restores the feed without duplicating deaths |

## Reuse and dependency order

1. Reuse extractor `safe_parse_events`, existing positional events and
   `build_grenade_tables`, particularly throw-instance segmentation for recycled
   entity IDs. Keep extraction optional for watching: extend the selected-demo
   preparation path, never rebuild the analysis library.
2. Reuse current SteamID strings, recorded weapon lookup, team changes, round
   boundaries and kill evidence. Add a versioned playback-event/state companion,
   separate from position tracks. Event schema changes must not duplicate or
   invalidate unchanged position tracks.
3. Build a read-only installed-resource provider over VPK mounts. Stock asset IDs
   are virtual resource paths; CRC/content and dependency hashes identify their
   revisions. Inspect dependencies before importing a bounded stock rig, weapon
   set and required sound bank. Do not export every cosmetic or the whole game.
4. Resolve conversion once into a shared content-addressed store for textures,
   models, animation clips and sound. Share dependencies between maps and demos;
   replace the current bundled-map texture duplication only after equivalent
   rendering is verified. Godot needs a resource reader/conversion adapter;
   pointing it at compiled VPK files alone does not supply that adapter.
5. Add recorded grenade paths, radar and event-driven sound/effects to the same
   tick clock. Seeking reconstructs persistent state and clears transient events.
6. Integrate default stock models and explicit animation states, then measure
   prepared cold-start and resident-map switching again with these assets active.

## Versioning and limits

The user-selected preparation pool is exactly Ancient, Anubis, Dust2, Mirage,
Inferno, Cache and Nuke. `prepare_maps.py` runs only this approved set, reusing
current native caches. Other installed maps are excluded. A missing or outdated
map produces a structured permission request before conversion; Toolbox displays
the warning and explicit Prepare/Cancel buttons inside the demo viewer. Outside-
pool maps retain a visible warning after approval. Requests bind the installed
asset fingerprint and exact renderer version, reject stale confirmations, and
do not silently recreate a deleted previously prepared cache. No installed game
assets means an install-first warning, with preparation disabled. Regression
checks cover no-consent/no-import, changed assets/runtime, declined requests,
the native request handshake and the application-owned warning widgets.

- Record demo protocol/build, parser version, playback schema, asset/dependency
  hashes, conversion adapter, renderer version and coordinate convention.
- Keep compatibility logic outside renderer/UI code. Reject unsupported formats
  with actionable errors, not a crash or a best-guess silent remapping.
- Do not claim an installed map matches a historical demo without evidence.
  A fingerprint detects asset changes; it does not recover historical assets.
  Pin user-provided/retained historical resources when available. Never roll back
  Steam or alter saved game configuration automatically.
- Cache invalidation follows actual dependencies. A UI/logging edit must not
  reparse a demo. A changed sound asset must not rebuild unrelated map geometry.
- Add bounded cache accounting and retention of referenced revisions before
  enabling unattended preparation across many maps or updates. Large imports
  remain separately scoped and approved.

## Completion gate

The full milestone is NOT complete while capsule players, missing audio or
missing grenade/radar behaviour remain. Test first-view readiness and time to a
usable seek on multiple prepared maps and recording sources, with all systems
enabled. Distinguish startup, demo decoding, asset preparation, GPU loading and
seek latency. Keep source/demo hashes unchanged and no CS2 process throughout.
