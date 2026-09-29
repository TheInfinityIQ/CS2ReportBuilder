# Source-of-truth map

One row per fact that appears in more than one place. **Truth** = the only place to edit first. **Copies** = places that must agree (derived, summarised or quoted).
When you change a truth, update every copy in the same task (post-work hat), or list the stale copy in `agent/STATE.md`. "Test" = what fails if they drift.

| Fact | Truth | Copies that must agree | Test |
|---|---|---|---|
| Order of authority between documents | `CLAUDE.md` > Precedence | Design v5 (reading guide), `docs/DECISIONS.md` ADR-006 | manual |
| What is true of the code today | code + `tests/` | every doc; if a doc disagrees with a test, the doc is wrong | pytest |
| Owner's rulings (what Dawson decided, why, how firm) | `docs/OWNER_RULINGS.md` | `agent/PREFERENCES.md` (sentiment log only), `docs/CRITIQUES.md` (O- rows), Design v5 | manual |
| Number of Teaching Moments (evidence decides; no min or max) | `docs/OWNER_RULINGS.md` | `coach/handoff/{PROMPT,RULES,MODULES}.md`, `docs/CRITIQUES.md` V-12, Design v5, packets | `test_no_cap_or_minimum_on_teaching_moments`, `test_no_count_rule_for_moments` |
| Architecture decisions | `docs/DECISIONS.md` (ADR log, append-only) | Design v5 (ADR list) | manual |
| Data traps | `docs/KNOWN_PITFALLS.md` | code comments that cite a row number | tests named in the rows |
| Product critiques and their status | `docs/CRITIQUES.md` | `docs/ROADMAP.md` (references IDs only) | manual |
| Plan, order of work | `docs/ROADMAP.md` | `agent/STATE.md` (current status and next), Design v5 roadmap | manual |
| Where things stand right now | `agent/STATE.md` | nothing (do not restate elsewhere) | size cap |
| Current extractor and schema | `extractor/README.md` | root `README.md`, `docs/DECISIONS.md` ADR-005/005A, data legend Section 5 | `test_docs_consistency` |
| Coach's rules and wording | `coach/handoff/RULES.md` | `docs/COACHING_LESSONS.md` (source; RULES wins), `PROMPT.md`, packets (generated copies) | verdict-word test |
| Verdict words | `STATUS_WORDS` in `src/cs2di/report/modules.py` | `RULES.md`, `MODULES.md`, `COACHING_LESSONS.md` | `test_docs_consistency` |
| Plan format and module list | `src/cs2di/report/modules.py` + `plan.py` | `coach/handoff/MODULES.md` | manual (H-4 shows it can drift) |
| Data folder root path | `src/cs2di/config.py` `DEFAULT_ROOT` (`CS2DI_ROOT` overrides) | `agent/ROUTER.md`, root `README.md`, data legend, `docs/DATA_FOLDER_LEGEND.snapshot.md` | `test_docs_consistency` |
| Data folder layout | data folder `00_LEGEND.md` (device) | `docs/DATA_FOLDER_LEGEND.snapshot.md`, `config.py` sub-folder names | snapshot header says refresh |
| Which coach prompt is current | `coach/handoff/PROMPT.md` (template) | each packet's `PROMPT.md` (generated); legend Section 5 | `test_docs_consistency` |
| Packets: what exists, how many | each packet's `MANIFEST.json` on the device | packets `README.md`, legend Section 8, `agent/STATE.md` | manual (regenerate README from manifests) |
| Eligible units per player | `docs/PLAYER_UNIT_COUNTS.csv` | `agent/STATE.md` mentions only the notable ones | manual |
| Current design document | Design v5 (Claude Doc, linked from Project `claude/Design_v5.md`) | none (history docs in `docs/history/` are context only) | manual |
| Hats, router, start-here | `agent/` and `CLAUDE.md` | Claude Project `claude/START_HERE.md` | path test |
| Pipeline overview | root `README.md` | Design v5 pipeline section, `CLAUDE.md` one-line description | manual |

## Known open conflicts (decisions for Dawson)
None currently open. Resolved 2026-09-29: three versions of the Teaching Moment limit; v7.7 vs v7.8 naming; stale roadmap items; retired handoff process on the device; legend calling Architecture v4.1 current.
