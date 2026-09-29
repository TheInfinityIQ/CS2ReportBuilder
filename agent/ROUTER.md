# Router: task -> hat(s) -> what to read -> done means

**Every task is wrapped:** `roles/pre-work.md` first, `roles/post-work.md` last (they are not repeated in the rows).
Find the task. Put on the hats in the order shown. Announce each switch in one line ("Hat: Test reviewer").
A task not listed: pick the closest hat, and add a row here when you finish.

| Dawson says something like... | Hat(s), in order | Read first | Done means |
|---|---|---|---|
| "Build / rebuild report packets", "more test data", "packet for player X" | Packet builder | `scripts/build_packet.py`, `docs/KNOWN_PITFALLS.md` #28, the packets README (`06_Handoff_and_Tests/packets/README.md` in the data folder) | N units per packet, all disjoint, gate passed, smoke build passed, delivered to the data folder, index updated |
| "Look at what the test coach produced", "review this report", "is this claim right" | Test reviewer | `docs/CRITIQUES.md`, `docs/HANDOFF_TEST_2026-09-29.md`, `coach/handoff/RULES.md` | Findings list with evidence per claim; each defect has an ID (H-n) in `docs/CRITIQUES.md` |
| "Fix the defects the review found", "add a feature", "change the report/viewer/extractor" | Developer (then Test reviewer if output changes) | `docs/DECISIONS.md`, `docs/KNOWN_PITFALLS.md`, `docs/OWNER_RULINGS.md` | Tests added and passing, docs updated, committed and pushed |
| "Turn the review into changes", "what should we change after the test" | Test reviewer -> Intake steward -> Developer | as above | Defects triaged into decisions, then code |
| "Tidy my folder", "sort what I dropped in", "where is X", "I moved something" | Librarian | data folder `00_LEGEND.md` | Files moved with a `MOVES_MANIFEST.tsv` row each; legend true |
| "I've decided...", "I didn't like...", "remember that...", "here's an idea", design questions | Intake steward | `docs/OWNER_RULINGS.md`, `agent/PREFERENCES.md` | Recorded at the right tier (Firm/Leaning/Open); conflicts with earlier rulings surfaced |
| "Write the design / roadmap / handoff doc" | Intake steward, then Developer if code follows | `docs/ROADMAP.md`, `docs/DECISIONS.md`, Design v5 (Claude Project doc `claude/Design_v5.md`) | Doc written, stale claims removed |
| "Write the coach plan for packet X" | (Not this agent's job in a normal session. A fresh, context-free coach does it: `PROMPT.md` inside the packet.) | The packet only | `plan.json` passes the validator |

## Where things live
- Code, tests, docs, coach prompts: this repo (GitHub TheInfinityIQ/cs2-demo-intelligence).
- Data (demos, analysis, packets, reports): `C:\Users\dawso\Developer\CS2ReportBuilder\demoparser` (reach it through the device link; legend: `00_LEGEND.md` there). It is not in git (ADR-002).
- The container cannot run the analysis on the device directly (device Python 3.10, no scipy); stage tarballs to the container (`device_stage_files`, <=400 MB/file), build, commit results back (`device_commit_files`, <=20 MB/file). Device shell calls die at 180 s; run long unpacks in short foreground steps.
