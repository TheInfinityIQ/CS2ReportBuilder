# Project status

Date: 2026-10-07. Distinguish observed artifacts from verified behavior.

## Observed implementation and artifacts

- A local Git checkout exists at CS2ReportBuilder/repo, alongside demoparser.
- [Raw demo locations](RAW_DEMO_LOCATIONS.md) separate Steam replays from local
  analysis. Raw folders use tournament/series or player/batch; analysis collection
  names and demo stems remain unchanged. Current scripts support both roots.
- Source implements extraction v7.8, viewer sidecar, integrity gating, digest,
  analysis, plan validation, packet generation, and HTML report rendering.
- The [packet-builder window](PACKET_BUILDER_UI.md) maps a raw batch or subfolder
  to one analysis collection. Dedicated Packet Builder and Utilities tabs share
  selections and progress; the [UI plan](TOOL_UI_PLAN_2026-10-07.md) records the
  workflow and verification. The window previews inclusion and duplicate identities, saves
  selections, and prepares or repairs data. A resource-aware queue defaults to
  80% CPU / 90% RAM soft admission targets, with logs, cancellation and retry.
  Packets require validated 16 Hz replay data unless explicitly overridden.
- The local [game catalog](GAME_CATALOG.md) caches player rosters, source paths,
  identities and replay readiness. Extraction/repair updates and a Utilities
  refresh control are connected. On 2026-10-07 it indexed 453 analyzed games
  (351 replay-ready, 102 historical analysis-only games) and 351 raw demos.
  Measured cached collection scans took 0.8-2.4 seconds, compared with
  25-103 seconds for initial validation; packet builds still revalidate sources.
- [Viewer repairs](VIEWER_REVIEW_2026-10-06.md) preserve sidecar cadence, use exact
  Valve weapon icons, show utility countdowns and correct playback/state timing.
  Normal v7.8 extraction now adds validated 16 Hz viewer sidecars by default;
  existing analytic-table cadence/schema stays unchanged. The approved
  [workflow plan](PACKET_WORKFLOW_PLAN_2026-10-06.md) is implemented. Old packets
  remain unchanged and must be rebuilt to use repaired source analysis.
- [Full viewer repair](DATA_REPAIR_2026-10-06.md) completed across 351 demos in
  nine collections. Every planned demo passed a final 16 Hz readiness audit;
  no failures remain. Observational omissions are disclosed rather than filled
  with invented tracks.
- Eight saved run_2026-09-29_fresh_subagent directories exist for CanadianIQ_1,
  CanadianIQ_2, MIMY, iTrilogyy, shakestx, ZywOo, karrigan, and xertioN under
  demoparser/06_Handoff_and_Tests/test_coaches. Earlier inspection found plans,
  reports, and reviews. Rendering does not verify every claim or player usefulness.
- Generated discovery maps/catalog exist. A six-pair pilot found mixed retrieval
  costs, including one +25.7% overhead case. It measured returned characters,
  not billed tokens, and was assessed by the index author. Maps are optional.

## Known gaps

- Independent factual and usefulness review of the eight reports remains open.
- Archived owner-statement draft says no Teaching Moment minimum; plan.py rejects an empty
  moments list and MODULES.md requires at least one. Intended behavior needs
  a product decision; cleanup has not changed the validator.
- Design v5 is referenced as an external Claude document. Its contents and
  synchronization cannot be verified through current local tools.
- Old critique, roadmap, and capability documents contain dated claims. Check
  evidence and implementation before treating completion labels as current.
- Transcript-derived knowledge still needs quote-entailment and game-correctness
  review. Saved Q1-Q55 answer coverage is not proof of a validated profile.

## Current work

The authorized documentation cleanup is complete within its authored-document
scope. Source-linked history and collection guides consolidate retrieval context;
historical accounts are archived and ambiguous snapshot names corrected. Original
evidence, saved experiments and extraction-linked paths are preserved.
README.md is the master entry and AGENTS.md the working agreement. The old agent
system is archived under docs/history/agent-system/2026-10-03.

No new product-development priority is selected by this document. Historical
decisions do not become requirements merely because they appear in several files.

## Verification records

An earlier 2026-10-03 navigation change recorded 79 passing tests. First-batch
cleanup verification is recorded in [CLEANUP_2026-10-03.md](CLEANUP_2026-10-03.md).
Broader cleanup and verification are recorded in [CLEANUP_2026-10-04.md](CLEANUP_2026-10-04.md).
Neither test-suite result substitutes for a coaching-claim audit.

## Evidence

- [Source](../src/cs2di/), [packet builder](../scripts/build_packet.py),
  [validator](../src/cs2di/report/plan.py), [module guide](../coach/handoff/MODULES.md).
- [Old owner statements](history/project-records/owner-statements-draft.md), [old roadmap](history/project-records/roadmap.md), and
  [preserved agent state](history/agent-system/2026-10-03/agent/STATE.md).
- Local saved coach outputs: demoparser/06_Handoff_and_Tests/test_coaches/.
- Local pilot: Downloads/CS2_Index_Benchmark_2026-10-03/RESULTS.md.
