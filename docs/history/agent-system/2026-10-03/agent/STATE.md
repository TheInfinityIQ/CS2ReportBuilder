# Current state (update at the end of every task)

Last updated: 2026-09-29.

## In progress
(none)

## Where things stand
- Pipeline works end to end: extractor v7.8 + viewer-tracks sidecar -> gate -> digest -> analyst findings -> coach plan -> validator -> report. 62 tests pass.
- **8 report packets** built and delivered in the data folder (`06_Handoff_and_Tests/packets/`): P_pug_{CanadianIQ_1, CanadianIQ_2, MIMY, iTrilogyy, shakestx}, P_pro_{ZywOo, karrigan, xertioN}. 30 unique matches each, 240 in total, none shared. Generator: `scripts/build_packet.py`.
- **No coach has yet written a plan from these packets.** The earlier single-packet handoff test (iTrilogyy) worked; see `docs/HANDOFF_TEST_2026-09-29.md`.
- Number of Teaching Moments is set by the evidence (no min, no max). Data folder moved to `C:\Users\dawso\Developer\CS2ReportBuilder\demoparser`; `config.py` default updated.
- Design v5 exists as a Claude Doc / Project doc `claude/Design_v5.md`; it does not yet mention packets or this `agent/` system.

## Open
- Device has no git checkout of the repo; a local AI session there needs `git clone ... repo` (see the pointer file) before it can read `CLAUDE.md`.
- Known defects: H-1 (example rounds are file-order and loss-skewed), H-2 (self-kill examples), H-3 (validator gaps: small and spelled-out numbers), H-4..H-9 in `docs/CRITIQUES.md`.
- Decision for Dawson: lift the KeyMoments 1–6 round cap and the MetricCluster 2–4 cards limit?
- Pro (tournament) packets lack flash-blind, footstep and reload streams (unknown, not zero).
- CanadianIQ has 9 unused pugs (82 unique, 17 shared with MIMY, 69 available, 60 used).
- Eligible units per player: `docs/PLAYER_UNIT_COUNTS.csv`. donk has 29 eligible pro maps, one short of a packet; mezii has 38.
- ADR-014..017 proposals exist in Design v5, not yet in `docs/DECISIONS.md`.
- 00_LEGEND.md Section 8 lists the packets; MODULES.md still needs no change.

## Likely next tasks (Dawson decides)
1. Run fresh coaches on some or all 8 packets, then Test reviewer hat on the outputs.
2. Developer hat: fix H-1..H-3 and re-issue packets.
3. Intake steward: move ADR-014..017 into DECISIONS.md if approved; update Design v5.

## Recent work (newest first; keep the last 10 lines)
- 2026-09-29: Rolled out. Design v5 Doc updated (authority order, ADR-005A, packets, agent loop). Pointer `CLAUDE.md` placed in the data workspace root (`CS2ReportBuilder\`). No git checkout exists on the device; all commits are made from the cloud container.
- 2026-09-29: Consistency audit. Fixed: root README and extractor README (v7.8 current), ADR-005A, stale ROADMAP, COACHING_LESSONS vs RULES, retired handoff pack and PASTE_TO_FRESH_AI moved to `_archive/`, legend rows (coach prompt, design, onboarding). Added `agent/TRUTH_MAP.md` and `tests/test_docs_consistency.py`.
- 2026-09-29: Stress-tested the hats system: dry run by a fresh read-only agent on 3 prompts (4 donk packets, review a visibility claim, reword 'no detectable difference'). It chose the right hats and pushed back where it should. Fixed 12 doc gaps (reading order, router paths, no-device fallback, wording route, unit counts, tail handles). Added authority/pushback clause, log tags and caps, agent/README.md.
- 2026-09-29: Added pre-work and post-work hats and the judgement-call tail. Built the `agent/` hats system (`CLAUDE.md`, router, five hats, logs). Moved data folder to `C:\Users\dawso\Developer\CS2ReportBuilder\demoparser`. Built and delivered 8 packets; removed the Teaching Moment count rule.

## Superseding status 2026-10-03
- A local Git checkout now exists at CS2ReportBuilder/repo; the earlier no-checkout statement is superseded.
- Eight fresh-coach outputs exist locally with plan/report/review; claims and human usefulness remain unaudited. The earlier no-plans statement is superseded.
- Navigation maps/catalog and source-hash summary reviews are implemented; repository freshness is checked in CI. See docs/NAVIGATION.md.
- Claude Project START_HERE and cloud Design v5 copies need synchronization; local tools do not provide access to those project documents.
- Current next work remains owner-selected; the eight saved coach outputs can be reviewed without repeating the runs.
- 2026-10-03 recent work: generated 29 repository and 192 local maps; 79 tests pass. CI now checks map freshness and explicit core lint rules. Source artifacts remain in place.
