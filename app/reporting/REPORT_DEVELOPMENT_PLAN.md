# A richer coaching report and a reason to return

Proposed product and implementation plan · 12 November 2026

Status: planning only. This document does not authorize extraction, bulk rebuilding, publication, checkout integration or changing the current player's diagnosis.

## Product objective

Make the first report feel recognisably personal and worth paying for, then make a later report answer a new, valuable question: **what changed after the player worked on the previous coaching?**

Preserve the current reading-first report: player profile → evidenced positives and insights → improvement priorities. Add breadth through better analysis modules, restore the Analyst Desk and create a portable session record. The existing acquisition, canonical identities, extractor, replay and HTML renderer remain dependencies rather than replacement projects.

The present opening-fight report is a useful slice, not a finished comprehensive assessment. Its 94 opening kills do not establish that CanadianIQ is a strong opener relative to an appropriate baseline. This plan expands what can be assessed instead of inventing a richer personality from the current small set of measures.

## 1. Recover the original Analyst Desk, using the current contract

Repository commit `1e93cfb` introduced the two-audience design. Inspected anchors: `src/cs2di/report/build.py::_analyst_desk`, `docs/DECISIONS.md::ADR-009/ADR-011`, and the corresponding README at that revision.

That Analyst Desk contained scope, all figures with counts/denominators/definitions, map and side breakdowns, alternatives and limitations for findings, open questions and calculation notes. The same report also offered evidence-digest and coaching-plan JSON downloads. The Player Study and Analyst Desk shared a computed digest.

Restore that purpose, not the obsolete implementation. The historical code used integer player identities and different post-round counting rules; those are not current requirements. Preserve canonical string IDs and today's versioned source/capability/tick semantics.

Proposed report surfaces:

| Surface | Reader's job | Content |
|---|---|---|
| Player report | Understand their playing picture and next steps | Profile, positives, explanations, selected evidence and practice |
| Analyst Desk | Examine and challenge the conclusions | Exact measures, denominators, opportunities, contexts, alternatives, counterexamples, source quality and change history |
| Session bundle | Carry the complete evidence and coaching to a future review | HTML, machine-readable session, derived records, original selected analysis files and integrity manifest |

The Desk is a secondary view/section of the same report, with an anchor/print fallback. Core player value must remain available without entering it. Its numbers must bind to the same measure records as the player-facing statements.

The Knowledge Expert also proposed a short visible note at the start of the insights module. Dawson clarified that this must not regress into an analyst reciting statistics and leaving the player to discover their meaning. Such a note is optional, written only after the coaching thesis is established, and must explain a useful gameplay concept, the relevant situation and why the distinction matters. Do not auto-compose it from the largest or most unusual metrics. Their available conversation did not establish the original Desk specification; the repository history above does. The deeper Analyst Desk remains supporting evidence, not the author of the player narrative.

### Coaching-first acceptance boundary

- Begin with a meaningful gameplay question and contextual situations, then use measurements to test the explanation. Do not begin with a table of extreme values and invent advice around it.
- Every promoted insight must explain what the player should notice, understand, retain or decide differently, with relevant information, alternatives and constraints. A statistic or a round retelling is not sufficient.
- The written explanation must teach without requiring the player to interpret a chart or enter the Desk. Include a number when its magnitude or recurrence changes the conclusion; otherwise leave it in the Desk.
- The same computed records keep observations consistent across surfaces. They do not dictate the thesis, profile identity, importance ranking or coaching language.
- Reject a module that merely adds statistics, labels a proxy as skill, or manufactures an improvement priority to fill space. Positive contributions require the same contextual judgment as corrections.
- The future regression check should ask whether a reader can explain the gameplay distinction and next decision, rather than whether the report displays all available numbers.

## 2. Build profiles from contribution facets, execution traits and context

A recognisable profile can be more expressive than a list of metrics without being a fixed persona. Separate three layers:

- **Contribution identity:** how this player contributes in the reviewed situations—opening, closing, support, trading, defending or objective play.
- **Execution signature:** how they carry out those contributions—pre-aim, exposure, movement/shot coordination, utility timing and recovery.
- **Context:** map, side, weapon/economy, round state, opponent level where verified, role opportunity and team setting.

The visible identity may combine a primary facet, a secondary facet and a development direction. For example, an *opening creator with a utility-support contribution* is an illustrative composition, not a diagnosis of CanadianIQ. Do not require every report to fill every field. “Mixed contribution” or a scoped description is preferable when the evidence does not distinguish a dominant pattern.

### Candidate contribution vocabulary

These are understandable working names and definitions to develop, not labels that can already be assigned automatically.

| Facet | What would earn it | Essential distinction |
|---|---|---|
| Opening creator | Creates first advantages across relevant opportunities | First kill is not automatically an entry role |
| Opening converter | Opening contribution is followed by useful round progression in reviewed contexts | Team wins after a first kill do not prove individual causation |
| Advantage closer | Contributes to converting rounds from a specified favourable state | Requires an advantage-state denominator, not late kills alone |
| Clutch problem-solver | Handles last-alive situations with meaningful objective/time choices | Separate 1v1 parity from outnumbered states, and clutch opportunities from advantage closing |
| Trade connector | Responds to teammates' fights and maintains actionable support in reviewed situations | A fast revenge kill or nearby teammate is not proof of a feasible trade structure |
| Flash enabler | Enemy flash effects align with relevant teammate actions in checked situations | Blind duration alone does not demonstrate enabling a teammate |
| Utility controller | Uses utility to enable, delay, deny or isolate with supported context | Smoke count, grenade damage and effective control are different things |
| Site stabiliser | Holds, delays or preserves options against pressure on defence | Site success is confounded by role, rotation and opponent route |
| Retake contributor | Adds useful entry, cover, utility or objective actions during retakes | Requires retake opportunities, not all CT rounds |
| Post-plant contributor | Plays relevant bomb/time and remaining-threat situations effectively | Post-plant survival alone is not the objective |
| Space/pressure contributor | Creates useful movement or pressure with reviewed team context | Enemy attention, intent and rotations cannot simply be assumed |
| Rotation connector | Arrives and connects to changing objectives/support needs | Fast movement between sites is not proof of a correct rotation |
| Resource enabler | Relevant purchases, drops or retained resources support later team options | Low spending or saving a weapon alone does not earn this facet |
| Late-round navigator | Makes useful objective/risk transitions in late-round contexts | Time of a kill is insufficient to infer decision quality |

Multiple names can describe the same player at different times or on different maps. The library should grow through validated concepts, not combinations invented to make every customer sound unique. The explanations and evidence should create the personal specificity.

### Profile-assignment contract

For each candidate facet define:

1. Gameplay concept and the behaviour it would explain.
2. Eligible opportunities and the player's actual opportunity count.
3. Available observations, derivations and uncertain classifications.
4. Relevant context, confounders and alternative explanations.
5. Supporting situations and actively sought counterexamples.
6. Criteria for display as a contribution, candidate or unavailable assessment.
7. The basis of any comparison described as “high,” “strong” or “improving.”

“High” needs a declared, comparable reference. An appropriately matched cohort is different from this player's own prior baseline; both differ from a raw count. Population, map/side, economy/weapon, opponent context, source quality and metric version must be considered. No pro-player benchmark is assumed. Show counts and sensible uncertainty where appropriate; use partial pooling/shrinkage only if the statistical model is specified and checked. Avoid magic sample thresholds or a black-box overall player score.

Validate classification boundaries with manually inspectable situations before automating promotion. Use separate games/time windows for confirmation where useful; do not mistake searching many traits for independent evidence of a standout identity.

## 3. Replace broad skills with a trait hierarchy

Use this chain: **gameplay concept → situation/opportunity → observable components → contextual interpretation → coaching cue**.

A trait record should preserve the concept, input fields, grain, eligibility, formula/rule, units, capability requirements, censoring/missingness, context, known confounders, evidence anchors, definition version and interpretation ceiling. Reuse common records across the profile, insights, Desk and session export.

### Crosshair placement

| Component | Useful question | Evidence and current boundary |
|---|---|---|
| Horizontal pre-alignment | How much horizontal adjustment is needed toward a relevant threat? | XY/yaw geometry is available; the existing engagement output is sampled around attributed deaths and is not an unbiased sample of every exposure |
| Vertical preparation | Is aim prepared for the relevant target height/stance? | No current verified eye/target-height model; do not grade head height or 3D error yet |
| Threat/angle selection | Is aim allocated to a plausible next danger? | Requires map/context and available information; choosing the eventual killer retrospectively creates hindsight bias |
| Hold offset | Does the held offset fit distance and plausible opponent movement? | Requires contextual geometry and exposure validation; a universal angle threshold is not meaningful |
| Angle isolation | How many relevant threats can challenge the exposure? | Needs reliable geometry/occlusion or reviewed situations; approximate spotted state is insufficient |
| Adjustment burden | What correction follows acquisition or a transition? | Needs suitable continuous yaw/tick coverage and valid timing; censored three-second windows cannot supply exact reaction latency |
| Movement–aim coordination | Does first-shot timing align with movement and the chosen weapon? | Event velocity may support a narrowly defined observation; weapon-specific accuracy/recovery must be validated before diagnosing stopping technique |
| Target transition/recovery | How does aim prepare for a subsequent plausible threat? | Continuous context and target eligibility matter; firing angles do not reconstruct spread or actual bullet paths |

The current `build_engagements()` states one row per attributed non-self death. Its probe may be first shot, first damage, approximate contact or death. That is suitable for scoped evidence, not a general “crosshair placement grade.” Include non-lethal and no-fight exposures when validating a broader claim. Existing 16 Hz viewer tracks can support spatial review, but not every fine motor or sub-tick inference.

**Angle-clearing feasibility is pending the Tool Developer's capability review.** Sampled positions and facing directions may support descriptive movement/aim sequences. They do not by themselves establish which corners were visible, cleared, relevant or known to the player. No angle-clearing table is promised as an existing capability. The requested review separates currently available observations, explicitly named proxies and the minimum additional coverage/geometry/visibility validation a stronger claim would need. Neither rendered scene geometry nor approximate spotted/PVS state is automatically authoritative analysis truth.

### Movement

Decompose movement into approach/exposure, braking and first-shot coordination, cover transitions, repeat exposures, route/objective timing, utility/weapon transitions and stance/jump choices. For each, distinguish the observed motion from whether a tactically better option existed.

Weapon, range, intentional mobility, urgency, objective, health and team state change interpretation. Speed when firing is not automatically an error. Input probes are not continuous keyboard telemetry, so they do not prove how the player counter-strafed. Shorter paths are not automatically safer or better. Inferred viewer jump animation is not authoritative action telemetry.

### Utility and support

Start with confirmed enemy/team/self/unknown outcomes, effective damage, blind events, detonation timing and available movement. Then review what the utility was meant to make possible: entry, isolation, delay, denial, survival or teammate support.

Enemy blind duration/damage establishes an observed effect, not a successful coordinated play. A teammate kill after a flash is a candidate linked event, not proof of causality or intended support. Smoke and fire-control conclusions need appropriately validated geometry and timing; approximate renderings are not measurement truth. Include harmful effects, useful low-damage utility and failed utility that was reasonable given available information.

### Opening, closing and clutching

Create explicit state episodes. Record player counts, bomb/clock state, side, alive participation, economy/weapon context, start/end ticks and outcomes. Separate opening involvement, survival, subsequent contribution and team conversion. Define advantageous closing episodes separately from 1vX clutch episodes; handle changing states, rescues, saves, simultaneous deaths and ambiguous rosters explicitly. The player needs a role in the episode to justify an individual closing claim.

A 1v1 starts at numerical parity; it must not be analysed as an outnumbered 1v2. Last-alive status, numerical advantage/disadvantage and objective advantage are separate episode attributes. One round may pass through several of these states.

## 4. Capability tiers and ownership

| Tier | Meaning | Examples for this project |
|---|---|---|
| Existing evidence | Inputs already present; a derived module may still need implementation/validation | Death/round events, counts, per-round identity, utility outcomes, event velocities where valid |
| Contextual derivation | Can potentially be developed from current files with explicit rules and reviewed fixtures | Closing/clutch episodes, conditional conversion, spatial transitions and utility/fight candidate links |
| Additional validation or telemetry | Current contract cannot support the intended claim | Verified vertical aim model, reliable angle/occlusion assessment, broad fine-grained aim coverage, continuous input claims |

Start with what can be useful now. For a missing capability, specify the coaching question, exact missing observation, why existing data cannot answer it and the minimum validated upstream change. The Tool Developer owns acquisition/extraction and shared replay. No broad re-extraction follows automatically from this plan.

## 5. A complete, portable previous-session bundle

The current `analysis.json` is a report evidence snapshot, not all source analysis. A read-only size check found approximately **172.4 MiB** across the 50 selected source-analysis directories, versus **8.9 MiB** for that snapshot. This is one measured selection, not a universal size estimate. Existing files are often compressed already.

Deliver a private portable session archive rather than inflate the HTML with the full dataset. The archive contains the readable report and all selected source-analysis files; a small session summary supports quick future intake.

Proposed logical contents:

| Item | Purpose |
|---|---|
| `report.html` | Frozen delivered player report and Analyst Desk |
| `session.json` | Player/session identity, period, prior-session links, focus, recommendations and status |
| `profile.json` | Displayed facets, candidates, evidence and qualification rules |
| `measures/` | Definitions, values, numerators/denominators, eligibility IDs, context and versions |
| `findings.json` | Observations, interpretation, alternatives, contrasts, practice and evidence references |
| `comparison.json` | Prior-session comparisons, overlap and comparability decisions, when applicable |
| `analysis/<demo-hash>/<analysis-revision>/…` | Byte-preserved selected analysis files, including all available event/coaching/track/entity files and metadata |
| `manifest.json` | Paths, byte sizes, hashes, schemas, versions, tick domains/rates, capabilities, selections and exclusions |
| `user-context.json` | Player recollections/practice notes, explicitly distinct from recorded evidence |

“All data” means every file from the selected canonical analysis directories, including data not used in coaching and flagged/excluded observations within those games. Do not silently shrink the archive to player-only statistics or a digest. The archive covers at most 50 selected games for the player, not the whole accumulated library. Original `.dem` files are a separate asset and are not required to reopen the report.

Record absent streams rather than manufacture them. Preserve unchanged historical sessions and exact source revisions. An import must verify hashes, IDs, versions, safe paths and source completeness; it must not overwrite upstream analysis or execute content from an imported file. Keep credentials and Toolbox account/job settings outside the package. The full private archive can contain other match participants' records; it is not the public marketing sample.

For repeated use, deduplicate content by demo hash plus extraction revision. A standalone delivery archive must still include all files it promises, rather than depend on invisible local references. The bundle's manifest distinguishes source extraction version, metric version, profile model, coaching revision and rendered report version.

Provenance/versioning follows established data-reuse principles; the particular session schema above is a proposed product design, not a mandated W3C format. [W3C Data on the Web Best Practices](https://www.w3.org/TR/dwbp/)

## 6. Follow-up reports compare the coaching, not just the score

On a repeat report, show:

1. What the earlier report asked the player to work on.
2. Which relevant new opportunities occurred.
3. What behaviour changed, persisted, regressed or remains unclear.
4. Which strengths remain worth retaining.
5. What to practise next, with new evidence.

Join by canonical player identity and unique match/round/episode identity. Distinguish new games from overlap and re-extractions. A rolling 50-game report may overlap heavily with the prior report; default to new-game evidence for change claims, with overlap clearly labelled. Never count the same game twice as new evidence or average averages without their denominators.

Compare compatible definitions and contexts. Changes in map mix, side, economy, weapon, teammates, opponents, patch or source coverage can explain rate changes. Use like-for-like strata or explicitly show the changed mix. If definitions change, keep the original result and optionally recompute both sessions on one approved definition, recording that restatement. Missing historical capability produces “not comparable,” not a zero baseline.

Use statuses such as improved in comparable situations, maintained, mixed/context-specific, not yet observed, insufficient opportunity and not comparable. Do not force every trait onto a progress arrow. Observational before/after change cannot establish that the report caused improvement.

The compact session record is the initial AI/coaching input. Retrieve specific rounds and source records from the full archive when needed. Do not place hundreds of megabytes of raw analysis into a prompt or treat previous coaching prose as unchallengeable truth.

## 7. Acquisition and retention through concrete value

The commercial hypothesis is that players return when the product remembers their play, identifies useful changes and demonstrates what the next review can answer. This is a hypothesis to test, not a conversion guarantee. Loyalty guidance supports valuing the ongoing customer relationship rather than maximising a single transaction. [NN/g, customer loyalty](https://www.nngroup.com/articles/customer-loyalty-vs-short-term-profit/)

Before purchase: show a realistic example of the profile, one complete insight, evidence quality and what the customer receives. Explain that follow-ups compare prior coaching with new situations. State analysis coverage and limits clearly.

In the first report: provide the complete promised value, a recognisable profile, positive contributions, a small number of meaningful priorities, the Desk and a portable session archive. Explain the next useful review question and what new play is needed to answer it.

In a follow-up: lead with the previous focus and supported change, then update the playing picture and priorities. Recognise progress and maintenance as well as new problems. A follow-up should still be useful when the honest finding is unchanged, context-specific or not yet assessable.

Offers such as a follow-up credit, a targeted review or a multi-report package are commercial experiments to consider after delivery cost and customer needs are known. No pricing, conversion uplift, subscription schedule, checkout or automatic customer messaging is approved here. No hidden online tracking is added to an offline report.

Measure first-purchase conversion against a defined qualified audience, repeat purchase in complete follow-up-eligible cohorts, refund/dissatisfaction, comprehension and whether players can identify their next action. Separate perceived personal relevance from actual learning/behaviour change. Repeat purchase alone does not explain why a player returned.

## 8. Delivery sequence and concrete acceptance

| Increment | Implementation owner | Deliverable and completion boundary |
|---|---|---|
| 1. Coaching question and capability contract | Report developer; Knowledge Expert reviews concepts, Tool Developer reviews upstream meanings | Start with useful situations and decisions; define only the opportunity/measure records they need. Distinguish opener/entry, closer/clutch, effect/support and unknown/zero; resolve angle-clearing feasibility before promising that module |
| 2. Analyst Desk and session archive | Report developer; Tool Developer consulted on canonical source enumeration | Same values in narrative and Desk; full selected-file manifest round-trips with hashes; current report preserved on failure |
| 3. Broad contribution modules | Report developer; Knowledge Expert reviews named interpretations | Opening, closing/clutch and utility/support each produce useful scoped findings, counterexamples and unavailable states |
| 4. Compositional player profile | Report developer; Knowledge Expert reviews promotion/calibration | Human-readable primary/secondary facets and development focus; no unsupported assignments or hidden score arithmetic |
| 5. Mechanics depth | Report developer for current-data derivations; upstream changes owned by Tool Developer | Scoped crosshair/movement modules; unsupported components visible as unavailable; extraction only if separately authorised |
| 6. Longitudinal report | Report developer | Prior session imported; overlapping games deduplicated; comparable behaviour and changed contexts explained; original sessions preserved |
| 7. Commercial validation | Product owner with report support | Players can explain received value; actual purchase/return evidence informs packaging and positioning |

One owner implements each increment. Other roles review concrete dependencies, with batched handoffs. Do not turn the plan into parallel feature work or rebuild the dataset just to make the architecture feel complete.

Recommended next build increment: **confirm the coaching-first and export/capability contracts, then add a thin working Analyst Desk and full session export for the existing report**. Use the current contextual coaching as the reference case; do not build a new metric catalogue first. It creates the foundation for profiles and repeat-report value before expanding mechanics. Keep it small enough to deliver and inspect; richer profile assignment follows validated contribution modules rather than preceding them.

## Local evidence inspected for this plan

- Current report builder, README, team checkpoint and retained coaching specification.
- Historical commit `1e93cfb`, particularly `_analyst_desk` and ADR-009/ADR-011. These establish historical intent, not current data semantics.
- Current `app/extractor/extract_demos_v8.py`: geometry policy, `build_engagements`, `build_utility_effectiveness` and capability handling.
- `app/extractor/README_v8.md`: entity/tick-domain and fidelity boundaries.
- One existing selected analysis directory's file inventory and headers; file sizes across the current 50-game source selection. This was a read-only scope check, not validation of all proposed traits.

The Knowledge Expert completed a bounded review. They supported a useful first purchase and a follow-up based on new comparable opportunities; contextual, multi-facet profiles; contribution/opportunity evidence rather than utility volume or raw win rates; the horizontal/vertical and movement/input distinctions; complete selected-file session copies; and improved/unchanged/unsupported comparison states. Their specific 1v1-parity and analyst-note distinctions are incorporated above. They could not recover the original Analyst Desk from their available conversation, while this developer recovered it from repository history. The larger proposed vocabulary still needs per-facet definitions and validation; the review is not blanket approval of automated labels. No new player type is assigned by this document.

Following Dawson's clarification, the Tool Developer was asked for a bounded feasibility handoff on exposure/angle-clearing inputs and complete selected-analysis session packaging. No extraction, rebuild, feature or test run was requested. Incorporate that response before treating the proposed angle-clearing/export mechanisms as agreed implementation capabilities.
