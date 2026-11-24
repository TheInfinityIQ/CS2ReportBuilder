# Native CS2 viewer: integration and compatibility plan

Research baseline: November 4, 2026. Implementation progress: November 5, 2026. The game-specific capability gates below remain required.

### November 9 reference capture investigation

The installed client schema contains observer modes 0=None, 1=Fixed, 2=In-eye,
3=Chase and 4=Roaming. The old 4/5/6 camera mapping was wrong for this build.
`native_controls.verify_camera_contract` now reads the on-disk PE schema table,
checks values and contiguous entry layout, and rejects changed contracts without
loading or injecting a DLL. Camera command mapping is corrected to 2/3/4.
Name selection uses the installed `spec_player`; the removed account-selection
command is not used. Account-ID locking retains the immutable Steam identity.
These findings still do not prove observed POV identity; normal capability gates
and pixel/HUD verification remain necessary.

`native_capture/reference_fixture.py` is an explicit, bounded legacy-engine
diagnostic, separate from `app/standalone3d/`. It uses the existing preference
lease, owned process, local-control restriction and window capture. Optional
Media Foundation encoding records silent MP4s at the unchanged source resolution.
No tools are installed and game files/settings are not edited. Windows consent
is required for the existing control helper; sandbox launches cannot reach it.
Progress-file sharing conflicts no longer abort recording. Each attempt has an
independent private output folder, and accepted-reference status requires visual
POV review. Encoder-only clips made with the obsolete mode mapping were visually
rejected and are labelled diagnostics, not usable player references.

`check_reference.py` decodes the actual MP4 through Media Foundation and saves
bounded review frames, including decoder row-pitch/padding handling. The native
capture colour/occlusion/resize/reconnect fixture and seven control tests pass.
The corrected two-perspective capture was completed after Windows consent and
accepted by visual review of both native snapshots and decoded MP4 frames.
`standalone3d/reference/cs2-anubis-round1/accepted.json` in the desktop cache
identifies the two files under `attempt-894246bf82`, their SHA-256 values,
runtime fingerprint, original demo SHA and review evidence. Both are 1920x1080,
approximately 70 seconds, covering demo tick 3041 through the official first-round
end at 7451 (observed stops 7463 / 7457). First person shows SmoodAimder's HUD,
hands and weapon; chase shows his model/nameplate and Chase Cam indicator.
Both are silent visual references; native spectator HUD and X-ray remain visible.
CS2 labels this an older recording with TrueView disabled. Cleanup confirms the
owned engine stopped and saved settings/screen dimensions stayed unchanged.

## Implemented foundation, November 5

### Managed CS2 rendering now verified

The watch library is now disk-first: only physical `.dem` downloads under the central Steam `game/csgo/replays` folder and its subfolders are listed. Analysis records enrich matching SHA-256 identities but never make a missing file watchable. The November 5 check found 13 actual downloads (7 with matching analysis, 6 without), versus 585 analysis records and 14 download-index records. Unanalyzed downloads can start native playback directly. Missing/changed files refresh availability without a file picker; legacy report helpers also resolve only inside replays. Existing notes and analyses are preserved, with unavailable saved moments hidden until the raw demo returns. Refreshing this watch list does not scan/rebuild the entire analysis catalog or launch extraction.

The shipping review panel now starts and stops a private stock CS2 process; the game need not already be open. On the installed **1.41.9.6 / build 26445667**, a real ESEA Mirage demo reached `Host activate: Playing Demo`, produced hundreds of non-black **1920×1080** frames inside the panel, and stopped its owned process cleanly. The private `USRLOCAL` route was confirmed from the engine's filesystem search-path log. All **70** monitored original configuration files remained unchanged. Screen dimensions were **1920×1080** before, during and after. The concealed window was disabled for normal input; no desktop automation or Computer Use was used.

Implementation: `native_session.py` owns the engine/process group and applies only transient window attributes to its own verified PID. `native_security.py` copies the current preferences into an application-owned folder and leases existing normal configuration files with read-only sharing. The engine reads/writes its own copied configuration; no original file attributes, ACLs, bindings, resolution or display mode are altered by the integration. Existing-file leases also block replacement/deletion; new entries are monitored separately. Exclusive-fullscreen profiles remain unsupported and are rejected before launching. Steam must already be signed in. The initial direct start was denied while FACEIT anti-cheat was running, and startup succeeded after the user manually closed it; the internal policy cause was not established from the available logs. Do not stop/reconfigure it automatically.

The source stays on-screen but almost transparent and non-activating; WGC supplies full-color content before opacity. Moving the fixture entirely off-screen did not supply sufficient frames, so that approach was rejected. The native build now publishes versioned DLLs through `build/current.json`, avoiding replacement of a library already loaded by another view.

`native_compatibility.py` permits production managed launch only for a positively tested runtime/capture-library/video-profile/adapter combination. Changed fingerprints fail closed before a new engine is launched. The bounded application-owned `integrated_fixture.py` verifies actual pixels, private routing, demo activation, original settings, screen size and owned-process cleanup before publishing a record. `--require-verified` exercises the production path; the explicit compatibility-test path can evaluate an unverified candidate under the same preference protections.

Remaining: observed POV identity and free-camera mouse input, rendered-frame/tick synchronization guarantees, HDR fidelity/performance certification, broader fixture coverage, and historical runtime acquisition/selection. Current success is a representative current-build demo, not blanket compatibility with every recording.

### Embedded workspace and external control

`DemoReview` is now an owned Frame in the main Toolbox workspace. Navigation retains the same library/review and private session; F11/Escape expand and restore the Toolbox window/sidebar. No second review Toplevel is created. Application widget tests cover lifecycle, navigation and constrained layouts.

The user approved the temporary administrator-protected local control test on November 5. Read-only inspection established that the installed vconcomm.dll binds INADDR_ANY. A separate application-side `control_guard.exe` holds dynamic WFP IPv4/IPv6 receive/accept block filters for the exact CS2 executable/TCP port where the loopback flag is absent. Guard readiness precedes private CS2 startup; ownership is checked with GetExtendedTcpTable, a nonce/echo handshake precedes commands, and guard loss stops private playback. No persistent firewall rule, game plugin, binary patch or settings edit is used. Administrator consent is required for this helper; the option can be disabled to retain capture-only watching.

The installed protocol uses a 12-byte `>4sHIH` header: four-byte type, 16-bit version (212), 32-bit total length, 16-bit handle. Several community examples describe `>4sIHH`; these match small packets but desynchronize on large schema messages. Static inspection of vconcomm.dll at relative offsets 0x20D5 (version +4) and 0x2DD0 (length +6) established the actual widths. The decoder bounds and drains unknown packets and handles split/coalesced frames.

The installed seek parser also differs from legacy numeric examples: engine2.dll at relative 0x389D0–0x38A7A parses option initials `R`, `P`, `F`. `demo_gototick <tick> 0 1` ignores both numeric options and does not request a paused result. The adapter uses `demo_gototick <tick> P` (or `R P` for relative seeking). Queries without arguments take the usage/position path and return without seeking. Integration checks require stable position feedback, not a transient target tick while the engine continues playing.

The contained Mirage check confirmed pause/resume, ~61 ticks/s at 1x versus ~32 at 0.5x, forward/backward seeks with exact observed target ticks, continued 1920x1080 rendering, private routing, unchanged settings/screen size and cleanup. First-person/chase and next/previous-player requests were accepted, but POV identity is not observed. Native `demo_step_tick 1` moved from tick 211 to 213; even absolute seeks can report transient ticks before settling. Precise stepping remains disabled, and normal seeks wait for a stable paused position. The extractor's existing event ticks are demo-relative (this fixture's first freeze end is 6022, total demo ticks 102934). They must not have server_start_tick=36562 subtracted. Only explicitly declared server-tick analysis uses that origin. The matching SHA is required before round/moment use. Position feedback is engine-reported and may precede the captured frame.

`native_controls.py` exposes only structured, bounded playback actions; no free-text command console or arbitrary paths/names are accepted. `playback_controls.py` serializes socket I/O on one worker and tags messages by session generation. Positive control records separately pin runtime and adapter/helper digest; game updates require revalidation. The original Ancient crash was later traced to late baseline initialization (see follow-up below); the successful Mirage has the same older recording patch, so version mismatch alone does not establish the cause.

The final shipping-workspace fixture passed (`data/.desktop/native-last-toolbox-smoke.json`): 977 frames at 1920x1080, stable seek, restart, round 1 at demo tick 6022, selected-analysis-moment jump, same-session navigation and F11 restoration. Viewport sizes were 879x444 normally and 1916x896 expanded. Source input remained disabled; private routing, original preferences/screen dimensions, owned-process cleanup and guard cleanup passed. The worker must observe natural advancing playback before exposing controls: file/header readiness comes before CS2's delayed startup rewind/resume, which otherwise overwrites early controls. Windows consent time is tracked separately from the engine-load deadline in this fixture. Precise stepping and camera-mode selection stay disabled; accepted camera commands do not prove actual mode/POV identity.

### November 5 crash and viewport correction

**Follow-up crash fix:** the later Dust2 attempts (sessions `f725137667ca448db84abc5ac3388bb2`, `e44bfd5551a247f09bf4b38aa3e75981`) crashed in engine2.dll+0x10c5b0 while startup rewound to tick 0 from a full packet at tick 1. The original Ancient no-capture baseline also faulted at that offset. Inspection of the original recordings found a new CChicken instancebaseline entry in the first gameplay packet, absent from setup. The known late-baseline workaround now produces verified private copies without changing originals or installing game components. See `native_demo_compat.py`, `demo_compat.cjs`, and the pinned parser's `NOTICE.md`/MIT license. UTF-8 sanitization is disabled. Independent verification allows only the expected setup/table changes and rejects any changed gameplay network message or frame identity/timing.

Both repaired copies passed: Dust2 session `604992bfae654e93b6ee7c1683f459e0` delivered 1,872 frames and Ancient session `e02c14533f254b44901f7d631e52df32` delivered 1,432 frames, each for at least 30 seconds after startup at unchanged 1920x1080. Original demo SHA-256, saved settings, private configuration routing and owned-process cleanup passed. The previously working Mirage scan used its original file with no copy. Production repair permission separately pins the engine fingerprint and repair adapter/parser digest; existing analysis and notes continue to use the original download SHA. An engine/copy crash blocks that exact combination from subsequent playback. No automatic retry, bulk repair, historical engine download or re-extraction was performed.

The reported Ancient FACEIT recording (`[13-10]_SmoodAimder_Oct-29-2026_ancient_FaceIt.dem`) crashed the installed engine with access violation `0xC0000005`. The original attempt left an engine2.dll crash at offset `0x89222`. A single controlled baseline without capture and without source-window changes also exited with `0xC0000005` after 25.5 seconds, with private routing confirmed and original settings unchanged (`data/.desktop/native-baseline-ancient.json`). The engine log reports demo version 14193 versus client 14196; compatibility is a hypothesis, not a proven cause. Do not automatically retry that crash or call it a capture-only failure. No historical runtime was acquired.

The panel now checks the owned process before diagnosing capture failures and saves `playback-failure.json` in the session folder before cleanup can change the exit code. Lost-window/device recovery is limited to the same existing owned process (five-second window, at most two capture replacements); it never launches a replacement engine. The 3D tab hides analysis-only controls. Expand view/F11 and Restore/Escape change only the Toolbox window. A real ESEA Mirage check continued rendering through expansion and restoration (1,306 frames): the viewport grew from 1248x557 to 1916x995, while capture stayed 1920x1080. Private routing, unchanged original settings, unchanged screen size and owned-process cleanup passed (`data/.desktop/native-last-layout-smoke.json`). Widget tests verify restored library/analysis access and meaningful viewport height.

The capture component `native_capture/capture.cpp` runs inside Toolbox, using Windows Graphics Capture, D3D11 and DirectComposition with a two-buffer GPU path and an aspect-preserving destination transform. This component itself performs no game input, source-window manipulation, launch, or preference changes; the separate managed supervisor owns the transient source-window attributes. Animated fixtures passed frame delivery, source masking, viewer resizing at unchanged source dimensions, reconnect and actual pixel-color checks. HDR correctness, exact synchronization and the target performance budget remain unverified.

`native_viewer.py` inspects installed build/depot/version evidence, caches selected binary fingerprints, preserves runtime history and treats changed builds as unverified. The installed game was observed as build `26445667`, patch `1.41.9.6` on November 5. The read-only configuration baseline covered 70 existing files in the discovered game/Steam-user locations. A detected change stops capture without writing a configuration rollback. Runtime settings are not certified by those hashes.

`native_view_panel.py` integrates the feed and managed process, handles missing/ambiguous sources, minimized windows, no-frame/load timeouts, configuration changes, and installed-build changes. The library is collapsible to leave room for the viewport. The legacy report-link launcher remains blocked; the review workspace uses the compatibility-gated managed adapter. Selected analysis ticks remain separate from observed engine ticks until a confirmed seek; the worker initializes its own COM STA before requesting administrator consent.

UI checks use programmatic application-owned Tk widget/state/layout tests and bounded native fixtures. They do not use the Computer Use skill, desktop clicks/typing, or a user's existing game session. No historical runtime or injected game component has been installed. The controller and containment helper stay in application-owned files.

## Decision and scope

### Additional requirement: no manually running game

On November 5 the user clarified that **Toolbox may automatically start and manage a private CS2 process**. The implemented managed adapter follows that choice; no manually opened game is required. This does not waive settings preservation or authorize closing an existing user game.

Read-only export inspection of the installed `engine2.dll` found `Source2Main` and `CreateInterface`; static strings in `cs2.exe` reference `Source2Main`, `engine2`, and Source2Launcher. This supports investigating an application-owned engine host without launching the stock executable. It does not establish a supported renderer library API, a safe calling convention, external-viewport support, or user-settings isolation. Loading a DLL executes its initialization code, so do not probe it with `LoadLibrary` in the live user environment before the settings boundary is established. A host would still execute Valve's engine code and require compatible original assets. Merely renaming a game process does not satisfy the product requirement.

The installed engine also contains `host_readconfig_ignore_userconfig`; this candidate was not used because skipping preference reads could violate the settings requirement. Bounded static inspection instead established a `USRLOCAL%s` process-environment lookup before the Steam-folder fallback; the real runtime confirmed the private route through the filesystem log. Permission-token candidates were rejected because the installed Steam tree grants broad Users access and the proposed token did not provide the required boundary. Existing permissions were never altered.

Build a Windows review workspace whose central viewport displays frames rendered by the real CS2 process. Keep the demo library, events, timeline, notes, and controls in our application. Keep every Toolbox component outside the game process and game installation.

The recommended first experiment is Windows Graphics Capture plus an external VConsole control adapter. This is a plausible architecture, not yet a demonstrated end-to-end solution on this installation. Display, control, playback-position feedback, and camera input are separate capabilities with separate acceptance gates. A working video feed alone does not satisfy the complete viewer requirement.

The earlier `demo_review.py` launched a separate CS2 window and did not meet the in-application requirement. The current version contains the native capture preview described above. `cs2_jump.py` now verifies/copies manual commands and blocks automatic launch; it is not a verified automatic seek service.

Our integration must not patch game binaries, install game plugins, inject DLLs, read/write process memory for control, alter original downloaded demos, add game CFG/scripts, or persist Steam launch-option changes. Narrowly scoped, structurally verified private playback copies are permitted through the validated compatibility adapter described above; originals and their library identities remain unchanged. Temporary launch arguments and external Windows APIs are candidates only when they preserve the settings contract below. Steam and CS2 can still write caches and ordinary operational metadata; this is not permission for the viewer to cause game-setting changes.

## Hard requirement: preserve the user's game settings

Added November 4, 2026: game settings must remain unchanged during and after review, including resolution. This requirement takes priority over the proposed embedding/control techniques and performance targets. Temporarily changing a setting and restoring it afterward does not satisfy the requirement.

Preserve the current resolution, aspect ratio, display/fullscreen mode, monitor selection, refresh rate, graphics/HDR preferences, frame-rate limits, audio settings, input sensitivity, key bindings, crosshair, and other saved game preferences. Do not force a viewer-specific game configuration. Playback position, playback speed, and spectator camera selection are review actions; any action that also changes a saved preference must be excluded until a setting-preserving method is verified.

Adapt the application to the game: capture at the game's existing rendering size and scale the captured image within our own viewport. Preserve aspect ratio and use letterboxing when needed. Resizing the application must resize only our presentation surface, never the CS2 rendering window or its display mode. Application rendering targets are not instructions to set the game to 1080p or 60 Hz.

Do not pass resolution, refresh-rate, window-mode, configuration-reset, or configuration-execution overrides. Do not change game variables for FPS, background throttling, background audio, graphics, input, or capture convenience. Do not use synthetic shortcuts that toggle display mode. Evaluate every other launch argument and control action for persistence effects; process-scoped intent alone is not evidence that settings remain untouched.

The initial capture test must work with the user's existing display mode. If fullscreen, focus loss, occlusion, or audio behavior prevents the required experience, mark that approach as failing the requirement. Do not switch to windowed/borderless mode, change background audio settings, or resize CS2 as an automatic workaround. Reparenting or window-style manipulation is eligible only if it preserves these settings throughout; restore-on-exit is insufficient.

Settings preservation is an acceptance gate for every runtime/adapter profile. First validate startup, playback controls, viewport resizing, focus changes, normal exit, and crash recovery against a disposable test profile. Establish the relevant local/machine settings and Steam-user/Cloud-backed configuration locations for the tested build; do not assume one file covers them all or invent an unsupported alternate-user-directory launch option. Record a read-only baseline and inspect effective settings as well as persisted files throughout the test, including deferred writes at shutdown. A file hash alone cannot prove settings were unchanged during the session. Keep preference contents out of diagnostics.

Historical builds can migrate or reset settings, so sharing the live user's configuration with an untested older runtime is not acceptable. Verify profile isolation and unchanged effective preferences before enabling that runtime for review. An independent game-content folder by itself does not establish user-settings isolation. If settings preservation cannot be demonstrated, the profile is unavailable for the requested viewer.

Use baselines for verification and detecting regressions, not as permission to overwrite the user's settings later. If an unexpected change occurs, stop further affected operations, report it, and preserve diagnostic evidence. Never automatically restore a stale snapshot over changes the user or Steam made independently.

## Evidence and remaining uncertainty

Read-only checks established this local baseline:

| Item | Observed value | Meaning |
| --- | --- | --- |
| Steam application | 730 | CS2 installation |
| Installed Steam build ID | 26393695 | Installation fingerprint, not proof of demo compatibility |
| Game patch | 1.41.9.5 | From `game/csgo/steam.inf` |
| Client/server version | 2000940 | Separate from Steam build ID |
| Source revision | 11198439 | Additional build evidence |
| Game version timestamp | Nov 02 2026, 16:17:08 | Game-provided build date |
| Windows build | 26200.9711 | Use actual build/API availability for capability checks |
| VConsole files | `vconsole2.exe`, `vconcomm.dll` | Components are present; command support remains unverified |
| Existing analysis headers | 20 distinct `patch_version` values | Historical compatibility is already relevant; these are not necessarily 20 required installations |
| Main + Windows depot sizes | Approximately 67.8 GiB | Two installed core depots only; a complete runtime can need additional content, caches, and working space |

The main installed depot manifest is `2347770 / 3690356453703667427`; the Windows manifest is `2347771 / 5808144614069275570`. Store IDs as strings. Other installed depots must be assessed when constructing a complete historical runtime; these two entries are not a complete installation recipe.

Read-only binary inspection found VConsole communication references in the engine and `vconcomm.dll`. External implementations contain actual CMND command framing, including the D4 discriminator. However, one Python implementation contains contradictory comments about accepted protocol versions. Treat this code as research evidence, pin its exact revision before borrowing anything, and verify behavior locally rather than copying a packet constant into all adapters. [C++ command implementation](https://raw.githubusercontent.com/theokyr/CS2RemoteConsole/master/libvconsole/src/vconsole.cpp), [Python implementation](https://raw.githubusercontent.com/oxijoined/vconsole-python/master/vconsole_client.py).

The C++ reference project's documented target is `-tools` mode. That is not proof that the same interface works in ordinary retail demo playback. Determine the minimum viable launch mode experimentally and record it per adapter; do not assume developer-tool features are available in the desired review session. [Reference project requirements](https://github.com/theokyr/CS2RemoteConsole).

Prior local demo experiments produced CS2 crashes on two FACEIT recordings. The cause remains unknown. Neither a game-version mismatch nor a particular command has been established as the cause. Those failures require a plain-playback baseline before further automated seeking.

## Display architecture

```text
Toolbox / report link
        |
        v
Review workspace native host <----> Existing Python library/data service
  - library / events / notes          - demo identity and paths
  - playback controls                - round/event tick metadata
  - central GPU viewport             - saved review moments
        ^         |
        |         +----> External, versioned control adapter
        |                            |
Windows Graphics Capture             | VConsole, if verified
        |                            v
        +-------------------- Owned CS2 playback process
                               Valve's engine and original assets
```

Use a small native Windows host capable of D3D11/composition for the review window. C++/Win32 is the first prototype candidate because it maps directly to Microsoft's capture sample. Preserve the Python backend. Select the final UI framework after testing GPU surface hosting and input; no new runtime is being installed during planning. This workspace can be a separate Toolbox executable while still presenting the game inside its own application window.

Capture only the HWND belonging to our identified CS2 review session. Compose GPU frames directly into the viewport; avoid per-frame Python image conversion, PNG transfers, or local video encode/decode. Use a bounded frame queue that drops stale frames rather than allowing input-to-display delay to grow. Handle our viewport resizing, independently occurring game-window replacement, device loss, user-initiated display changes, and HDR deliberately without changing game settings. Microsoft's API exposes frame surfaces and timestamps, and requires careful buffer lifetime management. [Microsoft capture documentation](https://learn.microsoft.com/en-us/windows/apps/develop/media-authoring-processing/screen-capture).

The source CS2 window must keep rendering. Do not assume that hidden, minimized, off-screen, and covered windows behave alike. Microsoft's HWND sample explicitly excludes minimized-window capture. Test a non-minimized CS2 window covered by our workspace; then test the game's background throttling and audio behavior. If frames stop, report that state instead of showing an apparently live frozen picture. [Microsoft HWND capture sample](https://github.com/microsoft/Windows.UI.Composition-Win32-Samples/blob/master/cpp/ScreenCaptureforHWND/README.md).

Keep CS2's native audio initially. This avoids adding audio buffering or playing the same audio twice. If recording or app-specific routing is later required, capture only the owned game's process tree using Windows application loopback, with a separate synchronization test. [Microsoft process-audio sample](https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/).

### Alternative to evaluate, not the default

Reparenting CS2's window into an application panel might provide direct mouse input with less copying. It also introduces focus, raw-input, fullscreen, restoration, and cross-process DPI problems. Microsoft documents DPI-awareness resets for cross-process `SetParent`; this is a material risk on mixed-scale monitors. Do not evaluate this on the live profile unless a disposable-profile experiment first proves unchanged resolution, display mode, and preferences throughout the session. Restoring original parent/styles/placement afterward is required for cleanup but does not waive settings preservation. [SetParent documentation](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setparent).

Positioning CS2 over a hole in the application is not proof of reliable embedding. Any variant that requires forcing borderless mode or changing the game's rendering size is ruled out by the settings requirement. An otherwise eligible variant must pass occlusion, focus, viewport-resize, and minimize tests before being considered a product solution. Do not silently replace the requested in-app experience with a separate-window workflow.

## Playback control and synchronization

Investigate VConsole first. A community FACEIT round-watcher describes launching a dedicated demo session with temporary `-console -vconsole -insecure -vconport` arguments and controlling load/seek/pause externally. This is useful primary implementation evidence, not a Valve-supported compatibility guarantee. Its documentation also warns that the listener can bind to all interfaces without authentication. Connecting to `127.0.0.1` does not by itself restrict that listener. [Round-watcher implementation and limitations](https://github.com/hyper486/faceit-round-watcher).

Before enabling this path:

Conduct the initial listener-discovery experiment in an isolated test environment. Establish containment before starting a possibly network-accessible listener, rather than exposing it first and checking afterward. This is a feasibility gate, not a request to change this machine's network settings during planning.

1. Identify the launched process by PID, creation time, executable path, and build fingerprint. Steam may forward launch requests to an existing process, so a successful launch call is insufficient evidence of ownership.
2. Inspect the actual TCP listener owner and bind addresses. Validate a loopback-only configuration or an effective, explicitly managed isolation mechanism before accepting controls. If this cannot be established, leave the control capability unavailable. A random port is not isolation. Do not disable the firewall or expose the port.
3. Perform a harmless nonce/echo exchange and bounded protocol negotiation. Confirm command output and disconnect handling. Do not reuse or steal an existing user's VConsole connection.
4. Test plain demo loading before seeking. Then test pause, resume, absolute seek, speed, POV selection, and camera operations independently.
5. Treat demo-ready, seek-completed, and playback-position feedback as evidence to discover, not assumed protocol features. A log line can lag rendering; measure that relationship.

Use a dedicated review session with secure-server access disabled if that is necessary for the tested adapter. Refuse multiplayer/server-connect operations through our control layer. Do not attach automatically to the user's normal game, close their active match, or restart it to add flags. Confirm historical builds can actually launch with the user's Steam environment; a copied executable is not sufficient proof.

Commands should originate from structured actions such as `seek(demo_id, tick)` and `select_player(steam_id)`. Validate ranges, paths, quoting, and stable identity. Never turn an HTML report parameter, player name, or saved note into arbitrary console text. Use a user-scoped authenticated named pipe between our components; this protects our own IPC and does not add authentication to VConsole.

Maintain separate requested and observed state. A seek request is not a confirmed current tick. After a seek, wait for verified playback feedback and fresh frames; show a seeking state until the adapter can confirm completion. If available external interfaces cannot supply reliable tick feedback, expose that limitation and do not claim exact synchronization. Round numbers and pre-roll come from each demo's parsed events, not fixed round-duration estimates. Keep parser ticks, game ticks, and elapsed time in explicit coordinate systems, including pauses, restarts, and overtime.

Player selection uses SteamID64 strings, mapped to the relevant demo entity for that playback session. FACEIT UUIDs remain an additional identity link. Do not use mutable nicknames as primary identifiers.

Free camera is an independent feasibility gate. Captured pixels do not convey mouse input to CS2. Native spectator commands may support discrete camera actions, but smooth raw-mouse control must be demonstrated. OS input synthesis is subject to focus and integrity restrictions; never route it globally when another window has focus. `PostMessage` is not a substitute for verified raw-input behavior. [Microsoft SendInput documentation](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput).

## Compatibility as a product feature

Create separate records for runtime profiles, demo metadata, adapter capabilities, and test results. Avoid a single global supported/unsupported flag.

| Record | Required information |
| --- | --- |
| Runtime profile | Profile ID, installation path, engine family, app/build IDs, depot/manifest set, `steam.inf` values, important binary fingerprints, original-content provenance |
| Demo | SHA-256, size, source/match/map IDs, recorded date, header patch/protocol fields, source-provided build evidence when available |
| Adapter | Version, supported wire framing/commands, readiness/position mechanisms, launch options and input method |
| Validation result | Runtime + demo + adapter + OS/GPU/driver + display configuration, tested capabilities, settings-preservation evidence, failure stage, timestamps, compact diagnostic evidence |
| Analysis provenance | Demo hash, extractor/schema version, analysis output location; independent from native playback support |

Recording dates are hints. Demo header patch fields, client versions, Steam build IDs, and depot manifests are different identifiers and must not be treated as interchangeable. Prefer empirically validated compatibility relations; multiple patches may work on one runtime. A working demo does not certify all demos on the same date. Map assets, engine changes, and POV fidelity can differ even when a file loads.

Capabilities include load, capture, pause, seek, observed position, player POV, free camera, audio, and any fidelity-sensitive features. A build can pass capture but fail seek. UI states should be plain: Tested, Not tested, Partly supported, Failed, or Older version needed, with capability details available on demand. Unknown is not the same as known incompatible.

### On game updates

At app startup, before review launch, and after an observed Steam installation change:

1. Check lightweight manifest and `steam.inf` evidence. Debounce file watchers and wait for an installation to become stable; never launch through a partly applied update.
2. Recompute selected fingerprints once per changed installation, rather than hashing the whole game on every startup. Recheck process identity and version after launch to catch an update between preflight and launch.
3. Create a new untested runtime profile. Preserve the previous profile's results and keep the application's analysis data and notes accessible.
4. Stop using previously approved control and settings-preservation assumptions for the changed build. Offer a bounded compatibility check; update only capabilities actually tested. An unchanged protocol handshake does not prove unchanged seeking or unchanged configuration behavior.
5. Show one actionable update notice: what changed, which features await validation, and which already-installed tested profile is available. Do not repeatedly warn on every demo.

Metadata checks can run automatically while Toolbox is open. Active compatibility tests must wait for an idle review environment and must not launch or interrupt CS2 during gameplay. Offer an opt-in idle check or a manual Check compatibility button. This plan does not create a scheduled background task or download anything automatically.

For the application release process, maintain a small compatibility fixture suite, track official game releases, and publish adapter profiles only after the relevant tests pass. Treat release-note monitoring as a hint to investigate; the installed fingerprint is the launch-time authority. New profiles can be distributed through the application's normal verified update mechanism. Keep an adapter rollback path and an emergency disable switch for a broken profile without disabling analysis/report viewing. Do not execute remotely supplied arbitrary console scripts as compatibility updates.

### Historical runtimes and proactive preservation

Use separately selected, complete Valve runtime folders outside the active Steam installation. Never swap old DLLs into the current game or automatically roll back the user's normal installation. Match the required depots from a coherent release, preserve their manifests, and verify actual startup and demo playback before marking a profile ready.

Steam exposes depot-based distribution; historical playback tools also document obtaining older manifests through Steam. Availability, account access, disk capacity, and startup behavior must be verified for each requested version. Do not promise any date/build is permanently downloadable. Steam beta branches can help manual investigation but change the active installation, so they are not our default version manager. [Valve depot documentation](https://partner.steamgames.com/doc/store/application/depots), [historical playback guidance](https://cs-demo-manager.com/docs/guides/playback).

Suggested policy: retain a tested recent profile plus explicitly chosen historical compatibility families. Group older demos by observed requirements instead of keeping every patch. Display exact estimated download size, retained size, temporary working space, destination, and free space before creating a large runtime snapshot or depot download. Obtain approval for that concrete bulk operation under this repository's instructions. Preserve pending or incomplete downloads separately, verify them, then register the profile atomically.

Proactive preservation must happen before Steam overwrites content to guarantee retaining it. A post-update notification alone cannot recover an old build. Offer an optional, user-approved Keep known-good version policy with a storage cap, explicit retention rules, and an explanation of this limitation. Do not claim Steam updates can always be intercepted. Initially use independent copies; do not hardlink historical files to a mutable Steam installation. Consider verified block deduplication later, with retained data protected from updates and accidental cleanup.

Never delete a profile that is in use or pinned. Show the demos associated with a candidate profile before cleanup, while recognizing that another profile may also play those demos. When no compatible build is available, keep the demo and analyses, explain what is missing, and leave native playback unavailable without rewriting the demo to conceal incompatibility.

Original CS:GO recordings belong to a different engine family. Plan a distinct adapter/runtime path if needed; do not label a historical CS2 installation as CS:GO legacy support.

## Failure isolation and diagnostics

Keep the native host, data service, and CS2 process separable so a game crash does not destroy notes or the library. Persist review state before a seek or runtime transition. Session ownership must survive PID reuse checks; only stop a process positively identified as ours. Restore any window changes on normal exit and test recovery after a host crash.

Classify failure stages: launch, demo load, capture startup, control handshake, seek, input, and runtime exit. Record selected profile, demo hash, command action, observed game state, frame timing, and crash artifacts without secrets or unrelated game-console history. A changing-frame detector alone cannot distinguish a legitimately paused scene from a frozen renderer; combine frame arrival, process health, known pause state, and control feedback.

After one crash on a demo/build/action combination, stop automatic retries and flag that combination for investigation. Do not cycle through every installed build or repeatedly launch the same crashing file. Reproduce plain playback first. A single recording failure does not condemn the entire build; a successful capture test does not certify every feature.

Keep analysis schema compatibility separate: no automatic bulk re-extraction when the game updates. Existing CSV/JSON/report outputs remain available, and any schema migration must be scoped and approved independently.

## Implementation sequence and acceptance gates

Each stage has a stopping condition. Begin game-specific tests with one representative raw demo that plays normally, not the entire library. The application-owned capture fixture is implemented; the game-facing acceptance gates below are still outstanding.

| Stage | Work | Required evidence before continuing |
| --- | --- | --- |
| 0. Settings protection | Disposable-profile validation of configuration locations, isolation, effective settings, and deferred writes | No resolution/mode/preference changes; historical profiles cannot share unverified live configuration |
| 1. Stock baseline | Launch one known fixture normally after settings protection passes; record header/hash/runtime and watch beyond initial loading | Stable playback without our control/capture code and unchanged settings; investigate immediately if it crashes |
| 2. External control | Dedicated session, listener isolation, protocol/echo, readiness, pause and seeks | Observed results for each action, including backwards seeks and error handling; no game-file additions |
| 3. In-app rendering | Native WGC prototype displaying the real game at its existing display settings in the workspace | Continuous video while the source is covered, app-only resizing, correct color, recovery from window replacement; no game-setting changes and minimized behavior documented |
| 4. Integrated review | Existing events/notes driving the tested controller, observed timeline and POV | Correct demo identity, round and tick mapping, confirmed seeks, honest unsupported-state behavior |
| 5. Camera/input | Spectator mode/POV and smooth camera proof; bounded reparent alternative if needed | Input stays with the intended session; Escape/focus recovery and mixed-DPI tests pass |
| 6. Update handling | Simulated changed fingerprints/protocols and an actual separately tested build when available | Untested state, correct invalidation, no stale controls, no live-game interruption, adapter rollback works |
| 7. Historical profiles | One explicitly approved older runtime and representative old demo | Complete runtime provenance, correct selection, no mutation of current Steam content, bounded storage behavior |
| 8. Product hardening | Fixture suite and failure recovery across supported hardware/configurations | Reproducible results and published capability matrix; no blanket compatibility claims |

The fixture set should eventually cover current FACEIT, league and HLTV recordings, multi-map series identity, a known historical boundary, regulation/overtime, Unicode/spaced paths, missing raw files, and renamed players. First reuse available raw files; analysis-only folders cannot prove native playback.

Performance targets to measure, not current claims: up to a 1080p presentation surface at 60 captured frames per second when the unchanged game settings and target machine support it, with no requirement to change the source resolution, refresh rate, FPS limits, or display mode; bounded capture-to-presentation latency, reported at median and 95th percentile; no unbounded frame queue; responsive app controls while the game loads/seeks. Preserve the source aspect ratio and do not imply that scaling creates additional game-rendered detail. Measure full control-to-observed-result latency separately. Capture timestamps alone do not measure game input latency or guarantee exact rendered-tick alignment. Record game FPS, app GPU/CPU overhead, driver/monitor setup, and device-loss recovery. Test supported HDR/SDR, mixed DPI, multi-monitor and multi-GPU configurations on disposable profiles or existing configurations, app minimize/restore, and source-window occlusion; preserve settings throughout all live-user tests.

The first useful milestone is a genuinely in-app live game picture with independently verified pause and seek on one stable demo. Full free camera, historical playback, and broad update resilience follow their own gates. If background rendering or control feedback prevents that milestone, report the specific failed assumption before expanding the implementation.

## Immediate next work

Use the implemented bounded capture fixture and application-owned UI tests for regression checks. Prove settings preservation and profile isolation before game-facing experiments, then a stable stock demo, the VConsole boundary, and actual in-app game frames at unchanged settings. Confirm which playback actions can be reliable. Do not present the capture-only preview as a complete, synchronized demo viewer.

No game files, Steam settings, raw demos, analysis folders, or installed versions were changed by this planning work. No historical runtime was downloaded, and no automatic monitoring service was installed.
