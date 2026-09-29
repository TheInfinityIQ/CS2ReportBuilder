# Decisions (ADR log)

Authoritative over everything in `docs/history/`. Each decision is reversible;
to reverse one, add a new entry that supersedes it. Do not edit history.

## ADR-001: Python package + CLI; PowerShell only as thin wrappers
The ZIP + one-off PowerShell package per step broke repeatedly on paths and
missing inputs (Stage 3/4/5 chat history). One installable package (`cs2di`),
one config module, one root variable `CS2DI_ROOT`. No path is hard-coded outside `config.py`.

## ADR-002: Git tracks code, contracts, fixtures and docs. Never data.
Demos (~107 GB), analyzed output, parquet and creator transcripts stay local.
Small synthetic fixtures live in `tests/`. Creator transcripts are excluded for
rights reasons as well as size.

## ADR-003: Software computes every number; the AI interprets
The Stage 5 plan had a fresh AI read the analyzed files and compute the batch
evidence itself. Chat history shows that fails: wrong clutch counts (146 vs 45),
wrong buy-type splits, misread trade windows, all caught only by the owner's
CS sense. So a tested **digest builder** computes the metric battery with
numerator, denominator, coverage and example references (demo/round/tick). The
coach receives the digest and may only interpret it. A validator rejects any
coach output whose numbers are not present in the digest. This keeps the
"AI is the coach, software guarantees the evidence" split but moves the
guarantee to the right place.

## ADR-004: Fail closed. UNKNOWN is not zero, missing is not false
Retained from the project's earliest hard-won rules. A missing file or
unparseable input is a gate failure, never a pass.

## ADR-005: Extractor v7.7 is frozen and pinned
`demoparser2==0.42.0`. Any extractor change bumps the schema version and ships
with a v-old vs v-new regression comparison (the v5 vs v6 method: unchanged
data must be byte-identical; every intended difference is enumerated).

## ADR-005A: Extractor v7.8 is the current pinned extractor (2026-09-29)
Adopts v7.8 (schema 3.8) under the ADR-005 rule: it changes damage only (`dmg_health_effective`, `same_tick_multi_hurt`,
effective damage in `utility_effectiveness`) and the folder convention; regression checked on 446 demos (KNOWN_PITFALLS 27);
`cs2di repair` brings v7.7 output to the same columns. v7.7 stays in the repo as the previous pin. The viewer-tracks sidecar is
additive and does not touch either extractor. ADR-005 is unchanged; this entry supersedes its "v7.7" naming only.

## ADR-006: Repo docs outrank history
Historical chats, consultant reviews and V4.x drafts inform but do not
instruct. This log, the roadmap and the tests are the authority.

## ADR-007: V4 control-plane objects are vocabulary, not a build list
AnalystFinding lifecycle, TeachingEligibility, SelectedEvidenceSet and the rest
were extracted as candidate contracts (V4-A). After ten-plus statistics
milestones that produced one coaching priority (later blocked), the critical
path is now: evidence -> digest -> coach -> render -> human review. A V4 object
is implemented only when a concrete slice needs it. The statistics-gate
machinery (M10-M11) moves to `research/`; it is not a prerequisite for a report.

## ADR-008: Keep the guardrails that came from real failures
Claim ceilings (AI may weaken, never strengthen), no causal language from
before/after data, one example is not a tendency, spatial sensors are not
tactical truth, reference pros are context not targets. These are tests and
validator rules, not prose.

## ADR-009: The coach writes content; software owns every number and every pixel
Status: accepted 2026-09-28.
A report is a plan (JSON: words, plus choices from a fixed list of modules that reference
metric ids and round ids). Software computes the metrics (`digest.py`), builds each module
(`report/modules.py`), styles everything from one file (`report/theme.py`), and assembles the
page (`report/build.py`). The plan has no fields for HTML, CSS, layout details or raw figures.
Why: the owner wanted the AI to focus on coaching, and earlier reports drifted visually and
numerically. The MIMY check showed a coach can be accurate, but it still tagged one post-round
kill wrongly through the extractor's table, so the software must be the source of numbers.
Consequences: a bad plan fails loudly with every problem listed; a new visual needs a new module.

## ADR-010: Product first, then rigor
Status: accepted 2026-09-28.
Milestones end in something the owner can open. Validation effort stays proportional to product
value; a new gate needs a failure it would have caught. Supersedes the earlier roadmap order
(digest and validator before any report).

## ADR-011: One file, two tabs, two audiences
Status: accepted 2026-09-28.
Player Study (plain language, no maths on the surface, detail behind "How is this calculated?")
and Analyst Desk (exact figures, denominators, limits, open questions) are tabs of one HTML file
built from the same digest so they cannot disagree.

## ADR-012: No "normal", "strong" or "weak" without a stated baseline
Status: accepted 2026-09-28.
A player's number only means something against a baseline. Until we have a real one, reports and
analyst output say only what the data shows ("59% of opening fights in this sample") and name the
comparison group when there is one ("the other 18 players in these 30 games"). Peer comparisons from
the same games are a control, not a population norm. A finding about a player must also survive a
peer baseline (pitfall 25) and a stability check before it can drive coaching. When many splits are
tried, expect some to look meaningful by chance; guard against that (stability across halves of
the batch, and a correction for the number of comparisons tried).
Why: the owner pointed out that "his stats are normal" can also mean we are not extracting enough,
or presenting it in a way that reveals nothing. Both are live possibilities.


## ADR-013: The batch is the only baseline (owner ruling 2026-09-28)

**Decision.** Every comparison uses only what the product will have: the demos the player submits.
Baselines are (1) the other players in the same matches (lobby peers, placed at a similar skill by
matchmaking) and (2) the player's own level and, later, their own earlier batches (continuous
coaching). No stored database, no population percentiles, no pro norms. The FACEIT API may later add
context but must never be required.

**Why.** The development corpus mixes world-class, very good and average players; comparing a user to
it would be comparing against an audience the product will never have, and against the wrong skill
level. The lobby-peer baseline is skill-matched for free.

**Allowed use of the corpus.** Developing and validating methods only (does a measure behave sensibly,
does a bug exist, how large an effect can N games detect). Never as a norm in a report.

**Consequence.** With about 20-30 games, only large situational differences can be proven (about
600-1,200 decided fights). Findings must say so; "no clear difference" is a valid result, and the
coaching must also come from round-level behaviour (trades, value of kills, playing an advantage,
utility purpose, economy, clutch discipline), see docs/COACHABLE_CONCEPTS.md.
