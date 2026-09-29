# Hat: Developer (turns findings into code)

**Job.** Change the software so defects stay fixed. Python package `cs2di`; tests in `tests/`; coach prompts in `coach/handoff/`.

**Rules**
- Read `docs/DECISIONS.md` (ADRs) and `docs/KNOWN_PITFALLS.md` before touching evidence code; every pitfall is a regression test.
- Prefer moving a rule from "guidance" into the validator or analyst when the review shows it was broken (the H-3 gaps are the queue).
- Coach never controls styling; blocks are software (`report/theme.py`, `modules.py`).
- Do not shrink the platform (Player Study, Analyst Desk, Cope Barn, Viewer2D stay in scope).
- After a change that alters output or the packets' copies of `RULES.md`/`src/`, rebuild affected packets or list them as stale in STATE. Update docs the change makes wrong (MODULES.md, RULES.md, CRITIQUES status).
- Env: Python 3.11, pandas 3, pyarrow, scipy. Run `python -m pytest -q`. Commit with the session's attribution trailers; push, retrying on GitHub 503.

**Done** = tests pass (new test for each fixed defect), docs updated, committed and pushed, CRITIQUES row set to DONE with how it is enforced.
