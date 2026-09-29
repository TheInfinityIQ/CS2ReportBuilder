# Roadmap

Principle: get one real Player Study in front of a real player as fast as the
evidence rules allow, then iterate on what the human says. Every phase ends
with a demo-able artifact and passing tests.

## Phase 0: Foundation (in progress)
- [x] Repo, package, CI, config, SteamID handling
- [x] Hard integrity gate, verified against the real corpus
      (Cologne 113/114 valid = 2,251 rounds; FACEIT 100 = 2,105; Premier 4 = 85; MIMY 30 = 640)
- [ ] Locate missing source: Stage 5 `build_coaching_product_slice.py` and the
      PlayerStudy Coach Handoff package (only in the owner's Downloads)
- [ ] Turn KNOWN_PITFALLS into regression tests as metrics land

## Phase 1: Digest builder (`cs2di digest`)
Input: analyzed batch + focal SteamID. Output: `evidence_digest_v1.json`.
Metric battery, each with numerator, denominator, coverage and example refs:
baseline (K/D, ADR, HS, KAST-style survival), opening duels, trades (3 s window),
zero/low-damage deaths, clutches (rebuilt from ordered deaths), buy state (freeze-end
economy, pistol rounds separated), post-kill, utility, side/map splits, per-map
confidence labels. Cross-check event-derived K/D against the scoreboard and report
the residual. Ship with golden tests from KNOWN_PITFALLS.
First subject: **MIMY** (30 demos). Regression subject: CanadianIQ, whose known
B1-B4 trajectory is the ground truth the digest must reproduce.

## Phase 2: Coach loop
Rewrite the legacy prompts to consume the digest (plus a bounded drill-down
query tool for raw rows). Define `coach_analysis` schema (<=5 findings).
Numeric-fidelity validator (ADR-003). Fresh-AI, no-context runs; compare 3+ runs
for structural stability. Coach prompt and report prompt stay separate jobs.

## Phase 3: Renderer
`player_study_report.json` -> static HTML. Fixed shell (header, coverage strip,
agenda, teaching body, summary, methodology). Start with six modules:
FindingSummary, MetricPair, ContextBreakdown, SituationExample (schematic 2D),
LimitationNote, PlayerTakeaway. Deterministic fallback composer from day one.
InfoDisclosure ("how calculated / why shown") on every quantitative module.

## Phase 4: Human evaluation
Owner review, then one independent player and one coach. Ask: can they restate
the lesson, do they trust the numbers, is it the same product each time.

## Parked (deliberately)
Longitudinal coaching and PreviousStudyReview, real-map radar (historical
provenance unresolved), Analyst Desk, training-resource registry, Cope Barn,
team/strategy modes, M10-M11 statistics gates as a report prerequisite.
Revisit after Phase 4.

## Risks I am watching
1. AI reads raw data and re-derives metrics (mitigated by ADR-003).
2. Digest becomes a second god-object (keep metrics small, tested, individually versioned).
3. Owner-only taste (N=1). Independent reviewers in Phase 4.
4. Extractor drift. Frozen per ADR-005.
5. Missing generator source for M6-M11.3 means those results are not reproducible from this repo.
