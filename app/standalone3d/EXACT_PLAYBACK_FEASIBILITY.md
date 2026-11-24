# Native-fidelity standalone playback: feasibility

## Decision

Continue toward a Source 2-compatible presentation runtime inside Toolbox, replacing approximations with recovered behavior in small, measured stages. Do not promise exact CS2 output. No standalone route has yet demonstrated parity with Valve's complete runtime. Executing Valve's implementation is a separate engine-based option, outside the current standalone constraint.

This investigation did not launch CS2, execute its DLLs, modify installed files or settings, or rebuild prepared maps. It used the existing Source2Viewer converter and read-only static inspection. Production playback was not changed.

## Evidence from this installation

- Installed build: client/server 2000942, patch 1.41.9.6, SourceRevision 11206718. Compatibility must bind to actual assets and protocols, not just a map name.
- Both PC and Vulkan shader archives exist in the installed core and csgo directories. This establishes availability, not successful shader reuse.
- Static inspection covered 11 engine/client modules. Interfaces such as CreateInterface and subsystem version strings are evidence of internal module boundaries, not a supported standalone embedding contract. Loading a renderer DLL alone is not a demonstrated solution.
- The resource catalogue contains 232 compiled animation graphs, including Glock first-person and pistol/rifle/knife locomotion graphs.
- A bounded, single-resource decompilation of the installed Glock graph succeeded with the existing Source2Viewer 20.1 tool. The output contains 54 distinct document/node classes and 16 control-parameter declarations, including action, action_reset, attack_type, reload_stage and ammunition. These counts describe that document, not a complete runtime or all required graph dependencies.
- Our current stock_actor/source_pose implementation manually samples and blends clips. The resource bridge imports models/clips/material data; it does not execute these original graphs.

Artifacts: `data/.desktop/standalone3d/validation/fidelity-feasibility/` contains the static module inventory/hashes, shader archive inventory, graph catalogue, Glock decompilation and compact graph summary. The decompiler's successful exit was checked against actual output, not treated as sufficient alone.

## What existing reverse engineering provides

[ValveResourceFormat's fidelity documentation](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/docs/guides/format-support.md) describes graph execution, shader inspection and particle simulation. It also identifies missing runtime inputs and unsupported behavior. glTF export loses material and animation semantics. Vulkan shader stages can be reconstructed from SPIR-V; this does not provide the engine's render scheduling or bindings. These are useful starting points, not a complete CS2 player.

[Valve's TrueView release notes](https://store.steampowered.com/news/posts/?appids=730&enddate=1762300819) explain that native playback reruns prediction but still differs from original rendered-frame timing, including reaction effects. Version mismatches also affect playback. Therefore original live-play framebuffer identity is not an appropriate acceptance promise, even for the native engine.

## Concrete development gates

1. **Animation proof:** isolate the Glock graph plus its dependencies. Implement the required node subset behind a separate presentation interface. Explicitly map each control to recorded demo state, reconstructed state or an unsupported input; never silently guess. Compare firing, reload, idle and transitions against existing native recordings. Then tackle locomotion, foot placement and first-person arms. Keep current playback until the replacement passes.
2. **Shader proof:** recover one Anubis material's shader variant, resources and render state. Reproduce its output in a bounded test scene before changing the main renderer. Godot shader translation versus a custom RenderingDevice/GDExtension path remains an engineering decision requiring this proof. No DLL loading is needed for the first experiment.
3. **Effects:** inventory the actual smoke/fire particle functions and dependencies. Separate recorded projectile/event state from reconstructed effect simulation. Bullet and HE smoke interaction, fire placement, blood, decals, ragdolls and sound mixing each need explicit coverage; recovering a particle definition is not evidence of correct simulation.
4. **Seeking:** all reconstructed systems require serializable state or deterministic checkpoint replay, including graph transitions, particles, sound cursors and random seeds. Test direct seek against sequential playback at identical ticks. Resetting actors alone cannot satisfy this gate.
5. **Versioning/performance:** key shared prepared resources by source hashes, parser/runtime version and schema. Preserve working cached revisions; never overwrite them on an update before validation. Unknown inputs/versions produce a visible compatibility limitation. Measure preparation separately from time to an interactive, fully ready frame; do not declare success from first-frame timing alone.

## Acceptance

Use the existing native first-person/chase Anubis recordings as the initial reference. Match camera, tick and settings before comparison. Gate animation/event timing, geometry/materials, effects, sound and seeking separately. Declare missing systems explicitly. Expand to the seven approved maps and stock weapons only after the representative proof passes. Pixel differences alone cannot diagnose all failures, and passing a smoke/model existence check cannot establish native fidelity.

No new runtime dependency, bulk extraction, game execution or complete renderer replacement was introduced by this feasibility pass. The next bounded implementation is the Glock graph proof, not another broad visual retuning pass.

## Implemented experiments and revised approach

The first implementation now runs a deliberately limited **Glock action-selector program** in Watch. A strict preparation-time reader compiles the actual graph wiring for ordinary/last-bullet shots, partial/empty reloads, idle and the empty-slide pose. Unsupported reachable nodes or changed connections reject the program and retain existing playback with a compatibility report. This is not the complete animation state machine: layers, game prediction, IK, draw variations and inspect graphs remain outside this proof.

Testing exposed two assumptions that were corrected: demo weapon lists contain display names and must use the existing canonical weapon resolver; and selector inputs must be captured at animation entry. Current ammunition changes during a reload, so reevaluating it every frame incorrectly changes an empty reload into a partial reload. Entry snapshots now come from the existing recorded weapon stream and are recovered independently when seeking. No new demo parser or game execution is involved. Additional clips use the existing shared actor bank and preload worker.

The original shader route also produced real output. The existing resource bridge now has an explicitly invoked, offline shader-profile experiment. It decoded the installed v72 `csgo_lightmappedgeneric` Vulkan family and recovered HLSL for material-selected static variant 56. The pixel stage has 1,008 available static configurations, with bindless resources and engine-owned buffers. Recovering code does **not** establish a working drop-in Godot shader. The production plan is therefore to port and numerically validate recovered functions incrementally; full-program execution stays isolated until its resource and render-pass contracts are demonstrated.

That experiment identified actual differences in our translation: the native layer-border offset is subtracted, and the one-layer color detail contribution multiplies the blended base color by a tint/strength-controlled doubled detail sample. These functions are now used in Watch, along with material ambient-occlusion dependencies. A requested map can receive these small shared texture dependencies while retaining its existing geometry and lighting. Only the prepared Anubis map was supplemented during this pass; no other map was imported or re-extracted. Two-layer/bump-detail materials are explicitly recorded as remaining gaps (11 definitions on this Anubis revision).

The first GPU run rejected the implementation: Godot forbids a function parameter shadowing a uniform, and the numerical fixture initially compared linear values with encoded framebuffer values. Both were corrected and the checks rerun. Passing compilation alone was not accepted.

### Measured results

Evidence lives in `validation/fidelity-feasibility/` under the private renderer cache:

- `graph-shader-result.json`: owned Toolbox playback passed, no renderer errors, 219 recorded Glock action/seek comparisons, 12 authored arm/weapon track checks, and all eight recovered-function GPU checks. Maximum GPU sample error was approximately 0.0015 in encoded color.
- Initial graph-only readiness was 8.593 s; the final combined Anubis run was 11.578 s. The owned control seek was 0.375 s. These are individual observed runs, not a ten-second guarantee.
- The final normal-library Watch test passed with the actual downloaded demo, four compiled action programs and six shared clips: Ready in 12.172 s, control seek in 0.359 s, no renderer errors. Its preparation receipt was confirmed reusable at the current source revision. `acceptance.json` summarizes the final checks while keeping `full_cs2_parity` explicitly false.
- `seven-map-results.json`: all seven already-prepared map fixtures passed the shared lighting/render checks. These fixtures use a restricted weapon set; their faster loading times must not be presented as full-feature demo loading measurements.
- 96 Python tests passed, including corrupted graph connections, missing/truncated pose dependencies, rejection of stale programs after a failed graph update, cached-map geometry retention, and unsupported bump-detail handling. Godot presentation/utility headless checks passed as well.
- `reference-alignment.json` records a decoded native frame whose visible HUD tick was manually verified as 6837. A simple elapsed-time estimate had been 64 ticks early. Native-reference visual comparison remains an open gate: the current renderer still visibly differs in effects, corpses and shading, and camera/aspect settings require controlled matching. No image-parity claim is justified.

The revised development order is: extend verified graph branches and their recorded inputs; port recovered shader functions with GPU oracles; then implement named particle/physics/sound contracts. Each system must pass direct-seek versus sequential-playback checks before expansion. Preserve the working fallback and source-version boundaries throughout. Broad constant tuning or repeated full-map exports cannot replace these proofs.
