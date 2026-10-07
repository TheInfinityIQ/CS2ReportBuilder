# CS2 Coach Tools

Double-click **Open_Coach_Packet_Builder.cmd** in the repository root. Reopen an
already running window to load updates. Tk uses installed Windows Python;
calculation and extraction use the repository `.venv` when available.

## Two tabs, one selection

**Packet Builder** follows three steps: choose games, choose the player, then
build and hand off. **Utilities** contains data preparation/repair, resource
settings, retry/cancel controls, analysis-root configuration and detailed logs.
The collection/raw-folder controls and progress status are shared. Switching tabs
preserves selections; selection changes are disabled while a job is running.
Errors open Utilities. Both pages scroll on smaller screens.
See [the workflow plan](TOOL_UI_PLAN_2026-10-07.md) for decisions and evidence.

## Faster collection loading

The local [game catalog](GAME_CATALOG.md) retains rosters, identities and readiness
results. Loading checks file metadata and validates new or changed games;
unchanged compressed replay tables are reused. Extraction and repair publish
updates automatically. Utilities has **Refresh catalog for selected collection**
to force validation of the current selection. A missing catalog is populated on
first use; an unavailable catalog falls back to full validation. Packet creation
still validates source evidence under locks and hashes selected originals afresh.

## Choose exactly the games you want

1. Select an analysis collection in **Analyzed collection**, or **Choose analyzed folder…** for a
   custom collection containing individual match directories.
2. In the shared source controls, optionally **Choose demo batch…**:
   choose a batch or subfolder such as `CanadianIQ/batch_001`. Under the
   Steam `replays` layout it selects `analyzed_CanadianIQ_demos` automatically,
   when that collection already exists. For a new player collection, choose its
   intended analysis folder explicitly. For outside raw folders, choose
   the corresponding analysis collection explicitly. Matching uses exact demo
   stems inside this collection; it never searches other players or collections.
3. Review the match table. Double-click highlighted rows to toggle inclusion,
   or include/exclude visible rows. Map and name/date-text filters affect only
   visibility; hidden included rows remain selected and their count is shown.
   **Reset filters** restores the whole list. Dates are filename text,
   not inferred chronological metadata. Save/load JSON selections when useful.
4. Choose a player from the included usable matches. SteamIDs come from rosters,
   rather than filenames. The packet includes only selected matches featuring
   that player. Source analysis is not moved or renamed.

The table shows core integrity and replay readiness. Exact raw byte duplicates
are excluded by SHA-256, including renamed copies; an existing valid extraction
is preferred. Repeated stems in multiple raw subfolders are blocked until you
select a narrower folder. Without originals, recorded hashes or identical
extraction evidence detect duplicates where possible. Distinct recordings of the
same game may have different hashes and are not automatically proven duplicates.
Original identity uncertainty is visible. Saved selections are rescanned and
known identities must match before reuse.

## Prepare, repair, then build

In **Utilities**, **Analyze missing games + replays** extracts missing/invalid core analysis, then
adds viewer data; valid core analysis is reused. **Repair replay data** replaces
only the four additive viewer files for included, core-valid games. Both require
original `.dem` files. Normal v7.8 extraction now also adds validated **16 Hz**
viewer tracks by default. Its existing 2 Hz analytic tables/schema are unchanged.

Default **Require validated 16 Hz replays in packets** checks actual sample cadence,
finite positions/facing, roster/round coverage, demo pairing, interpolation
validation, grenade-table readability, and checksums when recorded. Coverage
uses live round windows and roster entries actually observed in the core position
data. Unobserved roster entries and rounds without live play are disclosed,
rather than supplied invented positions; an unobserved selected player cannot
pass the default packet replay requirement. The explicit
limited-replay override permits older/missing viewer data; it does not bypass
core coaching integrity or fabricate facing/paths. Ready does not prove every
movement, grenade boundary, or coaching claim correct.

The queue defaults to **80% CPU**, **90% RAM**, and up to eight simultaneous jobs
(or fewer on a smaller machine). Increase Max jobs if measurements justify it.
It samples total system load, starts gradually, reserves estimated job memory,
and limits supported native parser/math threads per worker. Viewer-only repair
uses a separate memory estimate from core extraction; smaller demos run first.
Native parser threads reflect the estimated RAM-feasible worker count, and the
complete job plan is saved beside each run summary. CLI hash caches remain bound
to original file identity/stat changes. These are **soft
admission targets**: existing jobs finish, and peaks can exceed predictions. Under
pressure, it stops starting more jobs rather than terminating active extraction.
Other applications and older terminals still count toward system load.

**Cancel queued jobs** leaves active jobs to finish. **Retry failed** retries only
failed jobs from the current source selection. Rerunning preparation resumes by
skipping validated ready output; cancelled jobs can be prepared later. Logs and
summary JSON remain in local `.extraction_jobs/<run>/`. A shared per-match lock
protects extraction and packet copying. Only proven dead same-host owners are
automatically recovered; unreadable or foreign locks require review. Stop older
unmodified extraction terminals before switching to this queue.

Click **Build coach packet** after selecting player/type. The source is rechecked
under locks and copied into an isolated snapshot. Each build gets a new folder;
failed builds retain diagnostics instead of publishing a ready packet. The
manifest records selected identities, replay quality, extraction provenance and
software revision. Once ready, open the folder or export a ZIP. Copy the AI
instructions into a fresh AI session with access to those files and Python.

The default destination is `06_Handoff_and_Tests/packets`. Prior packets and
reports stay unchanged. **After repair, build a new packet** to include 16 Hz
tracks and current report software. ZIP exports refuse overwrites.

## Run the data fix from PowerShell

From the repository (`CS2ReportBuilder/repo`), review a plan first:

```powershell
& .venv/Scripts/python.exe scripts/fix_viewer_data.py --dry-run
```

Repair all eligible core-valid analysis, or choose a bounded first trial:

```powershell
& .venv/Scripts/python.exe scripts/fix_viewer_data.py --batch CanadianIQ_demos --limit 1 --max-workers 1
& .venv/Scripts/python.exe scripts/fix_viewer_data.py
```

`--limit` applies to the total jobs, unlike the legacy per-batch runner. Planning
hashes original demos and skips validated ready matches. Use `--phase prepare`
only when you also want missing/invalid core analysis extracted. `--batch` may be
repeated. `--root` overrides the data root; otherwise `CS2DI_ROOT` or the normal
local demoparser path is used. Ctrl+C stops admissions and waits for active jobs.
The script uses primary `analyzed_<batch>` collections only. For unusual pairings,
use the UI to choose the analysis collection and raw folder explicitly.

This fixes viewer data. It is separate from `cs2di repair`, which upgrades old
core damage tables, and from the legacy `run_all_tracks.py` runner. The latter
also inherits the 16 Hz sidecar default but runs serially and has an older
collection-scoped lookup. Its former cross-collection fallback was removed.

## Setup and verification

Do not recreate a working environment. Install the declared parser dependencies
in the existing calculation environment if needed:

```powershell
& .venv/Scripts/python.exe -m pip install -e '.[dev,parse]'
```

A normal Windows Python with working Tcl/Tk is required to open the window.
No AI calls, credentials or uploads happen automatically. Packet/render checks
remain distinct from useful and correct coaching.

2026-10-06 verification exercised real Tk callbacks for raw mapping, inclusion,
filters, save/load, readiness gating, cancellation and a new batch with no analysis
yet. A bounded repair of copied CanadianIQ analysis produced validated 16 Hz
tracks and 496 recorded grenade paths; all 54 original core files stayed identical.
Fresh preparation of that same original demo passed core/replay gates, and all
47 comparable core tables matched the existing extraction after decompression.
The report payload used 0.0625 seconds/sample and continuous facing. A new
one-match packet built successfully for 24 rounds and passed its report-rendering
smoke check using the repaired sidecars. Test data,
logs and hash comparisons are in local
`Downloads/CS2_Workflow_Verification_2026-10-06`, outside Git.

Earlier 2026-10-04 verification built a four-match packet, passed rendering and
exported a ZIP. Automated workflow tests also cover ambiguous names, changed
originals, corrupt data, locks, resource admission, cancellation, failed job
isolation, packet provenance, and default 16 Hz extraction.

2026-10-07: the full two-tab workflow replaces the nested preparation tabs.
The builder previews packet contents without requiring users to read source code.
The receiving AI still needs file access and Python to validate/render the report.
Packet structure and coaching prompt content have not changed in this UI redesign.
