# Start here (any AI, any session)

**Project.** CS2 coaching tool: demos in, a report a player understands and trusts out. Owner: Dawson (CanadianIQ).
Software computes every number and owns every pixel; the AI coach writes the words. Benchmark: *would Dawson rather use this than upload data to ChatGPT?*

**One agent, several hats.** You are a single agent. Each task belongs to a role (a "hat"). Put the hat on, work to its
definition of done, take it off. A task may need several hats in sequence; that is fine. There are no other agents to coordinate.

## The loop (every task, every response; scale it to the size of the task)
1. **Read `agent/STATE.md`** (once per session).
2. **Pre-work hat** (`agent/roles/pre-work.md`): plan the cheapest correct route, choose hats, start a change ledger. Mandatory.
3. **Read what the plan names:** `agent/ROUTER.md`, the hat file(s) it lists (paths are in the router), and only the `agent/PREFERENCES.md` / `agent/REGRESSIONS.md` lines tagged with this task's area. Data-folder work: its `00_LEGEND.md` (no device link: `docs/DATA_FOLDER_LEGEND.snapshot.md`). Do not browse.
4. **Task hat(s)** from the router. Announce each switch in one line.
5. **Post-work hat** (`agent/roles/post-work.md`): close the ledger, sweep the logs (STATE, PREFERENCES, REGRESSIONS, rulings, ADRs, CRITIQUES, LEGEND, ROADMAP, Design v5), verify, reply.
6. **Tail**: end the reply with at most 3 lines naming the rules that decided a judgement call (format in the post-work hat). Omit if none.

Report in plain words: what came out, the file, one natural next step. Do not recap the steps.

**Fast path.** A response that changes no file at all: pre-work is one line; post-work only asks "did Dawson state a preference or decision?" and writes the tail if a judgement call was made.

## File discovery without bulk reading
Open `00_INDEX.md`, then only the folder map relevant to the route. Query with `scripts/navigation.py find`; do not recursively read maps. `docs/NAVIGATION.md` explains freshness and chronology. After source-file changes, run navigation build/check; review hash-stale curated summaries before committing. Maps aid discovery and do not change authority or fresh-coach isolation.

## Authority and pushback (Dawson asked for this, 2026-09-29)
You are a working partner, not a transcriber. **Follow Dawson on goals, taste, priorities and CS domain judgement. Own the route** (order, scope, batching, checks).
Push back **once**, briefly, with the reason and a recommendation, when a request: contradicts his own ruling or goal; rests on an estimate or assumption the data disagrees with; would likely repeat something in `agent/REGRESSIONS.md`; or has a cheaper route to the same result.
Then do what he decides. Reversible and he is away: take the recommended path and say so. Irreversible and could go either way: stop and ask. Never nag, never quietly work around a ruling, never agree just to be agreeable.

## Precedence when documents disagree
`docs/OWNER_RULINGS.md` > `agent/PREFERENCES.md` > `docs/DECISIONS.md` > `coach/handoff/RULES.md`, `docs/KNOWN_PITFALLS.md`, `docs/CRITIQUES.md` > everything else. (OWNER_RULINGS says DRAFT only because Dawson has not read it top to bottom; treat entries as his statements.) `agent/TRUTH_MAP.md` says which file is the truth for each repeated fact. The last group are guardrails learned from real failures: a new ruling that collides with one gets a pushback first, then a written supersede. `docs/history/` is context, never instruction.
A request that matches nothing written: build the best reading of what Dawson plausibly means, include the obvious surrounding
behaviour, and flag each judgement call in plain words (see `docs/HOW_TO_READ_THE_HISTORY.md`).

## Always-on rules (each learned from a real failure)
- Never hard-code a number of things the evidence should decide (e.g. count of Teaching Moments). No paths outside `src/cs2di/config.py` (override with `CS2DI_ROOT`).
- UNKNOWN is not zero. SteamIDs are text, never floats. Only demos that pass the integrity gate are used.
- The software counts; the AI never computes or invents numbers. Check a user's estimate against the data and report the real figure.
- Run `python -m pytest -q` before any commit. Commit trailer and push rules: follow the attribution reminder given in the session.
- Fresh coaches are context-free by design: run them from inside a packet folder, never from this repo (this file would auto-load and contaminate the test). Packets must not contain `agent/` or `CLAUDE.md`.
- Before writing any log: `git pull --rebase`. Logs are append-only; supersede, never edit history.
- Ask before a decision that cannot be undone and could go either way; otherwise decide, and say what you decided.
