# Start here (any AI, any session)

**Project.** CS2 coaching tool: demos in, a report a player understands and trusts out. Owner: Dawson (CanadianIQ).
Software computes every number and owns every pixel; the AI coach writes the words. Benchmark: *would Dawson rather use this than upload data to ChatGPT?*

**One agent, several hats.** You are a single agent. Each task belongs to a role (a "hat"). Put the hat on, work to its
definition of done, take it off. A task may need several hats in sequence; that is fine. There are no other agents to coordinate.

## Do this at the start of every session (3 minutes, in order)
1. Read `agent/STATE.md` (where things stand, what is open).
2. Read `agent/ROUTER.md`, find the task type, and read the hat file(s) it names.
3. Read `agent/PREFERENCES.md` and `agent/REGRESSIONS.md` (what Dawson liked, disliked, and what broke before).
4. For work on the data folder, read its `00_LEGEND.md` (path in `agent/ROUTER.md`). Do not browse; use the legend.

## Do this at the end of every task
- Update `agent/STATE.md` (done / open / next). Append to `agent/PREFERENCES.md` any like or dislike Dawson expressed.
  Append to `agent/REGRESSIONS.md` anything that broke or was undone. If files moved, update `00_LEGEND.md` and `MOVES_MANIFEST.tsv`.
- Report in plain words: what came out, the file, one natural next step. Do not recap the steps.

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
