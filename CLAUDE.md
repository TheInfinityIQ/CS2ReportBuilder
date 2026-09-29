# Start here (any AI, any session)

**Project.** CS2 coaching tool: demos in, a report a player understands and trusts out. Owner: Dawson (CanadianIQ).
Software computes every number and owns every pixel; the AI coach writes the words. Benchmark: *would Dawson rather use this than upload data to ChatGPT?*

**One agent, several hats.** You are a single agent. Each task belongs to a role (a "hat"). Put the hat on, work to its
definition of done, take it off. A task may need several hats in sequence; that is fine. There are no other agents to coordinate.

## The loop (every task, every response; scale it to the size of the task)
1. **Pre-work hat** (`agent/roles/pre-work.md`): plan the cheapest correct route, choose hats, start a change ledger. Mandatory.
2. **Session start reads**, in order: `agent/STATE.md`; `agent/ROUTER.md` and the hat file(s) it names; `agent/PREFERENCES.md` and `agent/REGRESSIONS.md`; for data-folder work, its `00_LEGEND.md` (path in `agent/ROUTER.md`). Do not browse.
3. **Task hat(s)** from the router. Announce each switch in one line.
4. **Post-work hat** (`agent/roles/post-work.md`): close the ledger, sweep the logs (STATE, PREFERENCES, REGRESSIONS, rulings, ADRs, CRITIQUES, LEGEND, ROADMAP, Design v5), verify, reply.
5. **Tail**: end the reply with at most 3 lines naming the rules that decided a judgement call (format in the post-work hat). Omit if none.

Report in plain words: what came out, the file, one natural next step. Do not recap the steps.

## Precedence when documents disagree
`docs/OWNER_RULINGS.md` > `agent/PREFERENCES.md` > `docs/DECISIONS.md` > everything else. `docs/history/` is context, never instruction.
A request that matches nothing written: build the best reading of what Dawson plausibly means, include the obvious surrounding
behaviour, and flag each judgement call in plain words (see `docs/HOW_TO_READ_THE_HISTORY.md`).

## Always-on rules (each learned from a real failure)
- Never hard-code a number of things the evidence should decide (e.g. count of Teaching Moments). No paths outside `src/cs2di/config.py` (override with `CS2DI_ROOT`).
- UNKNOWN is not zero. SteamIDs are text, never floats. Only demos that pass the integrity gate are used.
- The software counts; the AI never computes or invents numbers. Check a user's estimate against the data and report the real figure.
- Run `python -m pytest -q` before any commit. Commit trailer and push rules: follow the attribution reminder given in the session.
- Ask before a decision that cannot be undone and could go either way; otherwise decide, and say what you decided.
