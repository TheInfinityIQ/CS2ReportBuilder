# Viewer review and batch workflow

## Evidence inspected before these repairs

Reviewed Downloads/report.html and the 30.04-second Downloads/2DViewer.mp4,
including recording frames at 5, 15 and 25 seconds. The report uses the current
viewer JavaScript. Its ten replay payloads all contain `dt=0.5`, `facing=false`
and no recorded grenade path. The named CanadianIQ packet contains 50 demos,
1,071 rounds, and no viewer_tracks.csv.gz files. These are observations of this
packet, not claims that all local analysis lacks viewer tracks.

Both repo/extractor/extract_demos_v7dot8.py and the local
demoparser/03_Scripts/current copy still sample player_positions every 32 ticks:
2 Hz at 64 ticks/second. v7.8 changed damage accounting, not that sampling rate.
At inspection the separate viewer-track extractor defaulted to 8 Hz and accepted `--hz 16`.
The subsequent approved implementation defaults it to 16 Hz and invokes it after
normal core extraction; see the [current workflow guide](PACKET_BUILDER_UI.md).
Existing files and packets remain snapshots; updating software does not add
missing measurements to them.

## Findings and implemented repairs

| Finding | Evidence and consequence | Repair |
|---|---|---|
| Player shape changes | Missing continuous yaw triggers aim pointer after events, movement tail between events, dot while stationary. This is deliberate fallback behavior, not proof of corruption. | Constant circular marker; separate recorded-direction line when evidence exists. Movement no longer masquerades as facing. Visible sample-rate/facing notice. |
| Coarse motion | All ten supplied replays interpolate half-second position samples; sharp turns between samples are unavailable. | Preserve actual sidecar cadence instead of assuming 8 Hz. Synthetic 8/16/32 Hz checks confirm intermediate samples survive. Missing data still needs extraction. |
| Premature state | Health/item grid used nearest sample, revealing later states up to half a sample early. | Hold the latest preceding sample. Death events remove players at their recorded event time, using SteamID rather than player names. |
| Duplicate animation callbacks | Pause left a scheduled callback alive; restarting before it fired could create two playback loops. | Cancel pending frame on pause and allow only one scheduled frame; deterministic clock regression. |
| Playback continues out of sight | Closing replay drawers previously left playback active. | Pause on drawer close and browser visibility change; scrubbing pauses too. |
| Inaccurate weapons | Canvas shapes represented categories, so unrelated rifles shared a drawing. | Exact Valve silhouettes imported from installed CS2 with CRC/hash provenance, embedded offline. Text fallback for items without a model image. |
| Missing grenade timers | No countdown code existed. Dashed rings represent approximate smoke/fire extent, not time. | Active smoke/fire countdowns with thrower names below the map; `~` explicitly marks fallback lifetime estimates. Recorded expiry events determine measured lifetimes. HE/flash animation length is not presented as a fuse timer. |
| Invented flight animation | Missing path data still animated a projectile along a straight endpoint connection. | Retain the labelled dashed endpoint connection but do not animate a claimed flight path without recorded points. |
| Label jumping | Player labels changed collision priority whenever players' vertical positions crossed. | Keep stable player priority, with the subject first. Dense groups can still crowd labels; this is not a guarantee of collision-free layout. |
| Silent reuse of old cadence | The sidecar extractor skipped completed files based only on script version. Asking for 16 Hz could reuse 8 Hz output. | Skip only when the requested sample rate also matches. Mirrored this fix into the local current script while preserving its configuration. |

Smoke/fire extents remain illustrative circles; actual dynamic smoke volumes,
irregular fire spread, walls and elevation are not reconstructed. The viewer is
still a top-down evidence aid, not the game's renderer. Continuous yaw and
trajectory accuracy require the original demos and validated sidecar files.
Round/post-round timing and the two-layer Nuke layout merit separate fixtures;
they are not certified by this review. Grenade matching still uses nearest
compatible throws when sidecar identity is unavailable. Mixed trajectory quality
is described explicitly rather than claiming every grenade has a real path.

## Batch-builder options — proposed, not implemented

The raw tree retains subfolders such as CanadianIQ_demos/batch_001. Analysis
instead collects matches directly under analyzed_CanadianIQ_demos. Moving those
analysis folders would disrupt existing paths; a selection record can bridge
the two layouts.

| Order | Feature | Evidence and reason |
|---|---|---|
| 1 | Select a raw-demo folder, match its `.dem` stems to one chosen analysis collection, and preview a match checklist | Current folder layouts differ. Exact matching preserves physical paths and batch intent; unmatched and ambiguous names must be visible, not guessed from player names. |
| 2 | Show readiness per match: core extraction, integrity gate, viewer cadence, facing and trajectory coverage | This 50-match packet passed report generation without continuous facing. Build success and replay quality are different checks. Require explicit acknowledgement when requested replay quality is missing. |
| 3 | Prepare missing viewer data at a selected cadence, default proposal 16 Hz, then build the packet | The additive extractor already supports 16 Hz; no core-table schema change is needed. Verify pairing, cadence and validation metadata before calling a match ready. |
| 4 | Save a named batch selection and offer include/exclude, date/map filters, and an explicit final included-match list | A logical batch can be narrower than its analysis collection. Selection records avoid reorganizing source evidence and make builds repeatable. |
| 5 | Detect duplicates by original demo hash, with cached hashes bound to file identity; flag suspected same-match variants separately | Analysis summaries inspected here have no original demo hash. Filename matching alone cannot detect renamed copies. Equal bytes and repeated recordings of the same match are different cases. |
| 6 | Record software revision, extraction versions, selected demo hashes and replay coverage in the packet manifest | Packets embed their own software. Older packets retain the old viewer after repository repairs; provenance explains which behavior a report actually used. |
| 7 | One extraction queue with per-demo progress, cancellation between jobs, failed-only retry, and optional CPU/memory targets | Multiple terminals manually achieve concurrency but obscure ownership, status and aggregate resource use. One coordinator can govern both core and viewer extraction stages. |

Recommended first UI milestone: raw-folder mapping, inclusion preview and replay
readiness. Then add viewer preparation and the resource-aware queue. This is a
workflow proposal that Dawson subsequently approved on 2026-10-06. It is now
implemented; the [current guide](PACKET_BUILDER_UI.md) describes controls and repair
commands. Verification used copied analysis and a bounded fresh extraction.

## Adaptive extraction design

Use independent subprocess jobs per demo, with one coordinator and one writer
for batch-level manifests/summaries. Reserve each demo's output so two jobs cannot
write it simultaneously. Calling the existing whole-batch script repeatedly
against a shared output would cause competing batch-summary writes.

Start with one job and measure whole-system CPU, available RAM and each worker's
peak memory. Benchmark a few representative demos at increasing concurrency;
choose by completed demos/minute and validation results, not CPU percentage
alone. The extractor repeatedly queries events/ticks, and the parser does its
heavy work in Rust. Profile stage times before consolidating parser passes or
assuming Python threads will solve the bottleneck.

Proposed default targets: approximately 80% total CPU and at most 90% total RAM
use. Sample at roughly one-second intervals; add a job only after sustained CPU
headroom and enough available memory for its estimated peak plus a reserve.
Stop admitting jobs when either target is approached; use different resume
thresholds to avoid oscillation. In-flight jobs finish normally. Limit native
library threads per worker where supported and measured, so each new process
does not independently claim every core.

These are soft targets, not hard ceilings. Reducing queued/active concurrency
does not instantly release an in-flight parser's memory. One large demo can
exceed its prediction. Prefer extra headroom and waiting to killing valid work;
hard Windows resource limits would be a separate design with retry/checkpoint
behavior. Memory available to start another job is more useful than a single
"memory used" percentage. psutil supplies system CPU, available memory and
process memory measurements; it does not itself throttle jobs.

Sources: [parser implementation](https://github.com/LaihoE/demoparser),
[psutil CPU documentation](https://psutil.readthedocs.io/stable/#psutil.cpu_percent),
[available memory](https://psutil.readthedocs.io/stable/#psutil.virtual_memory).
The design above is engineering judgment informed by those APIs and this
repository's output ownership; resource targets are Dawson's requested values.

## Verification and reproducible review copy

Re-rendered the supplied report using its embedded coach plan, digest and
findings against the named packet's unchanged analysis. Saved a separate
Downloads/CS2_Viewer_Audit_2026-10-06/report_fixed.html; originals and the packet
remain unchanged. No AI coaching text was rewritten. This repair copy still
contains 2 Hz data and cannot recover unmeasured turns or facing.

Browser checks cover offline images, no JavaScript errors, approximately one
second of playback per wall-clock second at 1×, scrubbing, expand/Escape and
390/1440-pixel viewport screenshots. Regression tests exercise higher-rate
payloads, exact asset identity/hashes, expiry provenance, rate-aware extraction
reuse, past-only state, death timing and animation cancellation. These checks do
not establish grenade-boundary accuracy or coaching usefulness. The full suite
passed 93 tests, with lint clean; browser timing advanced 1.05 replay seconds
over the one-second 1× check. Only 43 used weapon silhouettes were embedded.
