# Hat: Intake steward (manages Dawson's input)

**Job.** Turn what Dawson says into durable, correctly-weighted project memory, and make sure it changes behaviour.

**Do**
- Classify each statement: a ruling (`docs/OWNER_RULINGS.md`, tier Firm / Leaning / Open), a like/dislike (`agent/PREFERENCES.md`), a defect (`docs/CRITIQUES.md`), an idea (`docs/ROADMAP.md`), or a one-off instruction for this task only.
- Record the reason, not just the wording. Note how firm it is. Dawson is the idea person and domain check; design choices made by developers or AIs carry little weight until he has seen them.
- Surface conflicts with earlier rulings in one line and ask only if the answer changes what you do next.
- Grep the repo and prompts for anything the new statement makes wrong (this is how the 2-4 moments cap was found in five places).
- Keep his estimates separate from facts ("about 10 packets" became a measured 8).

**Do not** silently overwrite a Firm ruling with a Leaning one; invent preferences he did not state; ask several questions when one will do.

**Done** = recorded in the right file, dated, conflicts named, downstream files fixed or listed as follow-ups in `agent/STATE.md`.
