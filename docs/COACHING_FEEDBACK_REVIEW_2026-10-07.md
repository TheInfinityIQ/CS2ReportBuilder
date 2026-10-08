# First-batch coaching feedback review

Reviewed 2026-10-07. The main product failure is useful teaching: identifying a
pattern has not consistently produced an understandable adjustment the player
can use. This is stronger evidence about these players' experience than about
their skill, the correctness of every reported pattern, or later improvement.

## Evidence and limits

| Source | What it establishes | Limits |
| --- | --- | --- |
| CanadianIQ's original feedback | Coaching felt underwhelming, overloaded and unlikely to change play; vague adjustments and review questions felt like homework. Weapon context, viewer explanations and Anubis imagery were missing or confusing. | One person's experience; their weapon-mechanics intuition is not a universal accuracy rule. |
| FoxC's original feedback | Wanted actionable priorities and success/failure comparisons. Questioned loss-only examples, first-damage contacts, proximity as trading support, independence of events and numeric claim validation. | Engineering concerns need checking, rather than assuming every report claim is wrong. |
| KnowledgeBaseConsultant.pdf, revision 2, 7 October | Reviews CanadianIQ, FoxC and MIMY reports and recommends connecting knowledge to contextual lessons, usable examples and bounded adjustments. | Its report-specific observations are attributed findings. This review did not independently reproduce its HTML audit; neither audit independently reviewed original demo POV. No original MIMY player feedback was supplied. |

There are two original player feedback documents and three consultant-reviewed
reports. This is an early qualitative batch, not a representative satisfaction
study or an evaluation of demonstrated skill improvement. Personal originals
remain local, outside Git.

## What the players are asking for

- Explain what to preserve, change or investigate, and why the change helps.
- Teach through a specific encounter: weapon, distance, cover, objective, usable
  teammate support and the information available at the time. Broad movement
  averages do not establish a rifle stopping problem.
- Show successful examples alongside failures, so a reported strength has a
  visible example and a lesson shows the condition that changes the decision.
- Explain a small percentage difference's practical consequence before making
  it a priority. Small differences are not automatically meaningless; neither
  are statistically detected differences automatically useful coaching.
- Complete the explanatory work in the report. A question can guide attention
  after an explanation; assigning the player to discover the problem is not
  a substitute for coaching.
- Make replay controls and symbols legible: map, orientation, timeline colors,
  lead-in and time offsets. CanadianIQ also requested stick-like player markers
  and optional translucent comparisons of routes across rounds on one map.

## Independent implementation checks

These checks inspect current code, not the unavailable original report HTML:

- `src/cs2di/analyst.py` converts `example_losses` into examples labelled
  "fight lost in this situation". This supports FoxC's concern that the supplied
  example pool emphasizes losses; it does not show which examples every report
  ultimately rendered.
- `src/cs2di/fights.py` defines initiative as first damage and builds encounters
  from hurt/death events. It cannot establish who saw or fired first, or account
  for a completely damage-free contact through those events alone.
- `src/cs2di/analyst.py` treats unavailable split-half agreement as stable in
  `_status`. This fallback is not evidence of stability. Its implications and
  within-match dependence need statistical review before changing confidence
  labels; player feedback alone does not determine the replacement method.
- `src/cs2di/report/plan.py` builds a union of allowed evidence numbers and checks
  numeric membership. That prevents some invented numbers, but does not bind a
  claim to its metric, denominator, player, side or scope. FoxC's semantic
  validation concern is supported by this distinction.
- Anubis had neither a PNG nor calibration, so the viewer fell back to a
  positional outline. This task supplies the missing radar. The other eight
  requested base images matched a pinned upstream source.

The consultant's support-readiness and weapon-context criticisms are useful
review priorities, but proximity alone cannot recover line of sight, attention,
intent or communications. Avoid replacing one weak proxy with invented context.

## Recommended next work, not implemented by this review

1. Produce one revised lesson from a supplied packet: observation, available
   context, explanation, feasible adjustment and exception/cost. Include a
   matching success/failure comparison where supported. Ask Dawson to assess
   that short output, rather than asking him to audit the full knowledge base.
2. Bind quantitative claims to explicit evidence identifiers and metric/scope
   definitions. Then review encounter coverage, example selection, clustering
   and confidence labels. Do not treat rendering or number membership as proof
   of coaching accuracy.
3. Simplify viewer explanations and test one replay's readability. Propose
   floor selection and route ghosting separately: comparable rounds, visual
   clutter and missing context make these substantial features.

The consultant supports keeping comprehensive knowledge while making existing
knowledge usable now. Complete corpus coverage is not a prerequisite for
improving these reports. Knowledge should distinguish facts, mechanisms,
applications, exceptions and teachable cues; it cannot restore missing demo
evidence or establish an unsupported personal weakness. Its illustrative lesson
entries are editorial examples, not newly verified player findings.

## Local source locations

- `demoparser/00_ORGANIZE_ME/KnowledgeBaseConsultant.pdf` (17 pages).
- `C:/Users/dawso/OneDrive/Desktop/FoxC_CoachingReportReview.txt`.
- `C:/Users/dawso/OneDrive/Desktop/CanadianIQ_CoachingReportReview.txt`.
- Consultant packet references: `P_CanadianIQ_20261007_134146_48893b4b`,
  `P_FoxC_20261007_133051_b43d52f2`, `P_MIMY_20261007_133345_1d368bc7`, under
  `demoparser/06_Handoff_and_Tests/packets`.
