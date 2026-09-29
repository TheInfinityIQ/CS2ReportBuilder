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

