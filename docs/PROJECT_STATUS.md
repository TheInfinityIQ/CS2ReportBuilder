# Project status

Date: 2026-10-03. Distinguish observed artifacts from verified behavior.

## Observed implementation and artifacts

- A local Git checkout exists at CS2ReportBuilder/repo, alongside demoparser.
- Source implements extraction v7.8, viewer sidecar, integrity gating, digest,
  analysis, plan validation, packet generation, and HTML report rendering.
- Eight saved run_2026-09-29_fresh_subagent directories exist for CanadianIQ_1,
  CanadianIQ_2, MIMY, iTrilogyy, shakestx, ZywOo, karrigan, and xertioN under
  demoparser/06_Handoff_and_Tests/test_coaches. Earlier inspection found plans,
  reports, and reviews. Rendering does not verify every claim or player usefulness.
- Generated discovery maps/catalog exist. A six-pair pilot found mixed retrieval
  costs, including one +25.7% overhead case. It measured returned characters,
  not billed tokens, and was assessed by the index author. Maps are optional.

## Known gaps

- Independent factual and usefulness review of the eight reports remains open.
- Old OWNER_RULINGS.md says no Teaching Moment minimum; plan.py rejects an empty
  moments list and MODULES.md requires at least one. Intended behavior needs
  a product decision; cleanup has not changed the validator.
- Design v5 is referenced as an external Claude document. Its contents and
  synchronization cannot be verified through current local tools.
- Old critique, roadmap, and capability documents contain dated claims. Check
  evidence and implementation before treating completion labels as current.
- Chat synthesis, document renaming, and duplicate disposition still need
  content/provenance review. Identical experiment inputs may be intentionally saved.

## Current work

The evidence-backed documentation cleanup is authorized. Its first batch resets
development instructions and onboarding while preserving original evidence.
README.md is the master entry and AGENTS.md the working agreement. The old agent
system is archived under docs/history/agent-system/2026-10-03.

No new product-development priority is selected by this document. Historical
decisions do not become requirements merely because they appear in several files.

## Verification records

An earlier 2026-10-03 navigation change recorded 79 passing tests. First-batch
cleanup verification is recorded in [CLEANUP_2026-10-03.md](CLEANUP_2026-10-03.md).
Neither test-suite result substitutes for a coaching-claim audit.

## Evidence

- [Source](../src/cs2di/), [packet builder](../scripts/build_packet.py),
  [validator](../src/cs2di/report/plan.py), [module guide](../coach/handoff/MODULES.md).
- [Old owner statements](OWNER_RULINGS.md), [old roadmap](ROADMAP.md), and
  [preserved agent state](history/agent-system/2026-10-03/agent/STATE.md).
- Local saved coach outputs: demoparser/06_Handoff_and_Tests/test_coaches/.
- Local pilot: Downloads/CS2_Index_Benchmark_2026-10-03/RESULTS.md.
