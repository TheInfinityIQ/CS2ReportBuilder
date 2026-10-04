> Historical reference retained at its original path during cleanup.
> Old instructions, priorities, and completion claims are not current
> authority. Consult [AGENTS.md](../AGENTS.md) for development rules and
> [PROJECT_STATUS.md](PROJECT_STATUS.md) for observed state. Verify
> technical claims against their evidence before relying on them.

# How to read the project history

DRAFT for owner review. Not authoritative until Dawson has read and corrected it.

## The short version

Every earlier document (designs, architecture drafts, evolution record, onboarding brief,
chat transcripts, step handoffs) came out of Dawson's ideas and suggestions, so they all
contain value. None of them is an instruction. Read each one as *what Dawson was trying to
get*, then judge the document's answer on its merits.

## Why: what went wrong before

Dawson was the "idea person". He did not review the architecture. The previous developer
repeatedly:

- lost sight of the vision, and went back to things Dawson had asked them not to do;
- built things that did not match what he meant;
- optimised one sensible-looking step at a time (contracts, gates, falsification) until the
  useful product was pushed off indefinitely.

The result: after a very large amount of engineering, the output was still less useful than
giving an AI some analysis data and asking it to interpret it. The project's own test is
"would Dawson rather use this than upload data to ChatGPT?"

## The filter to apply to any document

For each idea or decision found in the history, ask in this order:

1. **What did Dawson want from this?** (the goal behind it)
2. **Did it come from Dawson, or from a developer or AI's design choice?** Design choices
   were never reviewed by him, so they carry little weight by default.
3. **Does it make the player's or the analyst's experience better today?** If it only
   serves the machinery, question it.
4. **Was it learned from a real failure?** Failure-derived data-integrity rules are the
   exception. They earned their place (see "Rules that stay" below).

If a document says "next step is X" or "PASS", that is history, not a plan.

## Rules that stay (learned from real failures)

- UNKNOWN is not zero or false.
- SteamID64 stays exact (never a float).
- Only demos that pass the integrity gate are used.
- One example is not a tendency. Example count is not opportunity count.
- The software does the counting. The AI does not compute or invent numbers.
- Geometry and distance are sensors, not tactical truth.
- Pro data is context, not a target.
- Outcome and decision quality differ. Before/after is not proof of cause.

## Things that are open to change

Schema names, object hierarchies, stage order, module inventories, intermediate JSON,
how many layers of qualification exist, and workflow conventions. If a thing appears in
three documents, that does not make it right.

## When a request does not match anything written

Build the best reading of what Dawson plausibly means, include the obvious surrounding
behaviour (paths, defaults, validation, outputs), and flag any judgement call in plain
words. Do not freeze, and do not apply an old rule literally.
