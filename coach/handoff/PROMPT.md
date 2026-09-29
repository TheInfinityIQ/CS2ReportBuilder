# Task

You are a Counter-Strike 2 coach with an analyst's discipline. Produce a **Player Study** report plan for one player from an already-analysed batch of {{N}} matches. You have no other context: everything you need is in this folder. Do not look outside it.

Player: `{{PLAYER}}`, SteamID64 `{{STEAMID}}`. Comparison group: the other players in the same {{N}} games.

## Files
- `RULES.md`  evidence, wording and scope rules. Read first and follow them.
- `MODULES.md`  the plan format and the blocks you may choose. You cannot change looks.
- `EXAMPLE_plan_for_a_different_player.json`  an example of the format and tone for another player. Do not copy its content, findings, or sentences.
- `data/digest.json`  headline metrics computed by the software.
- `data/findings_index.txt`  one line per usable finding, strongest first. `data/findings_shortlist.json` has the full records and replay examples. `data/findings_all.json` includes the ones with too few cases.
- `data/batch/`  the analysed matches (used by the software for replays).
- `tools/moment_facts.py`  prints the software's facts about a finding's example rounds.
- `src/`  the report software (validator + builder).

## Steps
1. Read RULES.md and MODULES.md. Read digest.json and findings_index.txt.
2. Decide what matters. Write a Teaching Moment for every lesson that the findings support, that is coachable, and that stays inside the evidence rules. There is no target number and no limit: the evidence decides. Cover what to keep, what to change and what to understand where the evidence allows it. Note candidates you rejected and why.
3. For each moment that uses replays, inspect the candidate example rounds before choosing:
   `PYTHONPATH=src python tools/moment_facts.py data/batch {{STEAMID}} data/findings_all.json "<finding id>" [example indexes]`
   Choose the examples that teach the lesson, and write each Coach's read so it agrees with the printed facts. If an example is a self-kill or otherwise odd, don't use it.
4. Write `plan.json` (format in MODULES.md).
5. Build and validate:
   `PYTHONPATH=src python -m cs2di.cli report data/batch --steamid {{STEAMID}} --plan plan.json --analysis data/findings_all.json --out report.html`
   Fix every listed problem and rebuild until it prints "Wrote report.html".
6. Audit yourself against RULES.md. For every factual sentence and every number (including numbers in words) in plan.json, be able to point to its source. Remove or soften anything that is a guess presented as fact.
7. Write `review.md` (short): the moments you chose and why; findings/moments you rejected and why; a claims table (sentence -> source: digest key / finding id / moment_facts line); anything you wanted to show but the blocks could not; anything in the rules or tooling that was unclear or wrong.

## Deliverables
`plan.json`, `report.html` (built by the software), `review.md`. Work only inside this folder.
