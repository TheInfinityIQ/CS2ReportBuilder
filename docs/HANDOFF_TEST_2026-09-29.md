# Handoff test, 2026-09-29: can a fresh AI with no context produce the report?

**Setup.** A pack (`coach/handoff/PROMPT.md`, `RULES.md`, `MODULES.md`, an example plan for a different player, the iTrilogy digest/findings/batch, the report software and `scripts/moment_facts.py`) was given to two fresh agents that had no project context: arm A (Sonnet-class) and arm B (Opus-class). Each had to choose moments, inspect example rounds, write `plan.json`, pass the validator/build, audit itself and write `review.md`. The reference was my own iTrilogy plan (`examples/itrilogy/coach_plan_v3.4.json`), kept out of the pack. Caveat: both agents are Claude models and shared a filesystem (told to stay in their folder; not enforced). Another vendor's model has not been tried.

**Result.** Both built valid reports first time, chose the same core story as the reference (early fights; late-round fights; first-death replays, largely the same Mirage rounds), rejected the self-kill example, kept null results, and produced claims tables. Both wrote more, better-sourced moments than the reference, and arm B applied "no role labels from position" more strictly than the reference did. Neither invented a statistic.

**Where they slipped (rules that are guidance only, nothing enforces them):**
- Arm A: "You saw him" from a view angle (visibility claim; rule in RULES.md limits). Arm A/B: ACTION moments and generic advice ("know which teammate is backing you", "let a full-health teammate take the next contact") on habits with no measured cost. Arm A: "roughly one in ten" for a share that is 7.8%.
- Numbers spelled as words pass the validator (both agents noted and used it; the reference plan did too).

**Defects in our software/docs the test exposed (all verified):** see CRITIQUES H-1..H-9.
