# The agent system: what it is, what it is not

**Purpose.** One agent, several hats, a start-here file, and logs of history and sentiment, so any session starts fast and keeps to the project's rulings without re-reading everything.

**Non-goals (do not build these without Dawson asking):** multiple agents talking to each other; scheduled or autonomous runs; a database; hats for tasks that do not recur; automation that edits rulings on its own.

**Files and who reads them**
| File | Read when | Cap |
|---|---|---|
| `CLAUDE.md` | every session, first | 60 lines |
| `agent/STATE.md` | every session | 60 lines |
| `agent/ROUTER.md` + the hat files it names + `pre-work`, `post-work` | every task | hats 45 lines each |
| `agent/PREFERENCES.md`, `agent/REGRESSIONS.md` | by area tag | 80 / 60 lines, then archive |
| `docs/OWNER_RULINGS.md`, `DECISIONS.md`, `KNOWN_PITFALLS.md`, `CRITIQUES.md` | when the hat says | none (reference) |

**Copies that can drift (post-work syncs them):** `CLAUDE.md` <-> Claude Project `claude/START_HERE.md`; data-folder `00_LEGEND.md` <-> `docs/DATA_FOLDER_LEGEND.snapshot.md`; the Design v5 doc <-> `docs/DECISIONS.md`.

**Changing the system.** Edits that change Dawson's authority, the tail, or the Non-goals need his OK. Other edits: make them, update the router and `CLAUDE.md`, note it in STATE Recent work.

**Known limits.** Untested with a fresh agent until the dry run in STATE says otherwise. A hat is only as good as its Done line: if a session skips the post-work sweep, the logs go stale; the reviewer of that session should check.

**Discovery maps (2026-10-03).** Open `00_INDEX.md`, then one task-relevant folder map;
use `scripts/navigation.py` to page/search the catalog. `docs/NAVIGATION.md` owns
maintenance instructions. Source edits require a build/check and review of stale
curated descriptions. Generated summaries are not rulings, evidence, or new hats.
