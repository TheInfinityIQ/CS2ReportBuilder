# Owner rulings (reasons first)

DRAFT for owner review. Nothing here is authoritative until Dawson has corrected it.

How to use this file: each entry says what Dawson said, why, and how firm it is. Use the
reason, not just the wording, when a case comes up that isn't covered.

Tiers: **Firm** = stated clearly or repeated. **Leaning** = came from one reaction; follow by
default, revisit freely. **Open** = not settled; do not fill the gap with an assumption.

## Report structure

- **Fixed shell, changing body.** Same coverage strip, header, agenda, then Teaching
  Moments, then summary, then downloads/methodology every time. *Why:* familiarity builds
  trust; only the coaching content should vary. **Firm.**
- **Teaching Moment = one lesson.** It answers one player question or teaches one concept
  and ends with a takeaway. Charts and viewers are evidence, not the lesson. **Firm.**
- **Every evidence block says why it is shown / why the example was chosen.** **Firm.**
- **Notes at two levels.** Short caveats in an ⓘ beside the number; fuller detail in one
  Notes list at the bottom. **Leaning** (agreed 2026-09-28, untested with real reports).

## Two products, one file

- **Player Study has no math on the surface.** No statistical terms, intervals or nested
  denominators visible by default. Anything numeric-technical sits behind a "How is this
  calculated" control. *Why:* a player should not have to read statistics to learn.
  **Firm.**
- **Analyst Desk is its own thing** with the exact metrics, denominators, sample sizes,
  capability state, counterexamples and uncertainty. **Firm.**
- **One HTML file with tabs, like a folder.** Tabs to switch between Player Study and
  Analyst Desk. **Firm.**

## Look and feel

- **The AI never controls styling.** All CSS, colors, layout rules, spacing, control
  behaviour and button labels belong to the software. The AI supplies words and picks
  blocks. *Why:* consistency; the AI kept changing the look. **Firm.**
- **Blocks are software, not AI-written HTML.** The AI asks for "a 2D viewer" and the
  software builds it. **Firm.**
- **Literal player names; T/CT color distinction; no FOCAL labels.** **Firm.**
- **No engineering words in player view** (for example "ticks"). **Firm.**
- **No unnecessary statistical intervals or nested denominators on the main surface.**
  **Firm.**
- **No artificial pre/post/death buttons in the viewer.** **Leaning.**
- **Student and reference side by side** when comparing. **Leaning.**

## Viewer

- **A viewer without the map has little practical value.** Playback over time was much
  better than a still picture, but the map is what makes it useful. **Firm.**
- **Current radar images may be shown as a labelled orientation layer only.** They are not
  evidence unless compatibility is proven. **Firm** (from project rules).

## Coaching voice and content

- **Should sound like real Counter-Strike coaching,** not robotic or Mad-Libs prose.
  **Firm.**
- **The number of Teaching Moments is set by the evidence, never by a rule.** No minimum and no
  maximum in prompts, validator or docs. Every moment must still stand on a supported finding and
  teach one lesson; detail that does not teach goes to the Analyst Desk. *Why:* a fixed count
  either pads thin evidence or hides a supported lesson. **Firm** (2026-09-29; supersedes the
  earlier "only a few things per report", which was Leaning; two older versions of the limit also existed and are dead: "2 to 4" in the repo prompt, and "10 max, 5 or under is the target" in the owner's old device handoff pack).
- **Should change its mind and remember.** Stop coaching solved problems; question earlier
  claims when new evidence contradicts them. **Firm** as a direction; **Open** for the
  first build (single batch only).
- **Challenge every apparent finding,** even when the data looks strong. **Firm.**
- **Would I use this instead of uploading data to ChatGPT?** The overall benchmark. **Firm.**

## Process

- **Ask for a feature, get a coherent version.** Include the obvious surrounding behaviour;
  Dawson gives minor feedback. Not literally "one go", but that spirit. **Firm.**
- **Don't shrink the platform.** Player Study, Analyst Desk, Cope Barn, Viewer2D and the
  longitudinal coach stay in scope even when deferred. **Firm.**
- **Cope Barn stays separate** from serious findings and coaching state. **Firm.**

## Baselines

- **Compare only within the player's own batch.** The dev corpus spans pros to average players and
  the product will not have a database. Compare with the other players in the same matches and with
  the player's own level; later with their own earlier batches. FACEIT API only as optional context.
  **Firm** (2026-09-28). See ADR-013.
- **Coach what human coaches coach.** Use the creator transcripts to decide what is coachable, then
  find the demo evidence for it. **Firm** (2026-09-28).

## Open questions

- What the first "good enough" Viewer2D map looks like, given radar/historical limits.
- Whether Analyst Desk should be editable or read-only in the first build.
