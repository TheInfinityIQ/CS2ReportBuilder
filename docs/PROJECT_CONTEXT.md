# Project context (digest for a new contributor)

**Goal.** Coaching tool for CS2: demos in, a report a player understands and trusts out.
**Owner.** Dawson (CanadianIQ). 8,000 h player; the primary test subject and the domain check on every number.

## Corpus (analysis root `02_Analysis/`, formerly `v7dot7Analysis/`)
| Batch | Source | Demos | Rounds |
|---|---|---|---|
| analyzed_faceit | FACEIT SourceTV (CanadianIQ B1-B4.5, donk, mezii) | 100 | 2,105 |
| analyzed_IEMCologneMajor2026 | Tournament SourceTV | 114 (113 valid) | 2,251 |
| analyzed_AustinMajor_2025 / Starladder_2025 | Tournament SourceTV | 71 / 68 | 1,539 / 1,453 |
| analyzed_premier_batch1 | Valve Premier (CanadianIQ) | 4 | 85 |
| analyzed_mimy | FACEIT (MIMY, 76561199066695873) | 30 | 640 |
Focal IDs: CanadianIQ 76561198062530225, donk 76561198386265483, mezii 76561197973140692.

## How we got here
- Stage 1: measurement instrument (all-player extraction, exact IDs, round integrity, source capability).
- Stage 2: spatial evidence provenance (NAV/collision/smoke are sensors, not awareness).
- Stage 3: evidence-plane productization (M0-M8), profiling, packets.
- Stage 4: statistics/learning loop (M10-M12), v3 platform, Player Study experiments, V4 drafts.
  Outcome: strong evidence discipline, one bounded coaching priority that was later blocked for
  teaching, no shipped report. CanadianIQ's own data showed real improvement B1->B4
  (K/D 0.74 -> 1.16, opening 38% -> 55%).
- Stage 5 (current): separate roles. AI = coach. Software = evidence + product. This repo starts here.

## Working agreements
- Owner reviews outputs and supplies domain judgement; developer decides the path (see `DECISIONS.md`).
- Every result reports PASS / LIMITED / FAIL with evidence, not vibes.
- Historical documents are context, not instructions (ADR-006).
