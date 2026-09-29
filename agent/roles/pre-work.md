# Hat 0: Pre-work (mandatory, before any task hat)

**Job.** Decide the cheapest correct way to do the task before doing any of it. Ten minutes of planning must save more than ten minutes of work.
Scale to the task: a one-line question gets a one-line plan; a multi-hat build gets the full list. Never skip it.

**Steps (write the result as the task list, not as a message to Dawson)**
1. **Restate the task in one line** in your own words. If two readings would produce different work and a wrong guess is costly to redo, ask one question now (see the ask-vs-decide rule in `CLAUDE.md`); otherwise pick the likelier reading and note it as a judgement call.
2. **Pick the hats** from `agent/ROUTER.md`, in order. Name them in the task list.
3. **Find the truth.** If the task touches a fact in `agent/TRUTH_MAP.md`, note its Truth and Copies now.
3b. **Check whether it is already done.** Grep the repo, `docs/`, and (already read) `agent/STATE.md`, and the data-folder legend before building anything. Reuse the generator, script or doc that exists.
4. **Read only what the hats require** (their "Read first" lists), plus the lines in `agent/PREFERENCES.md` and `agent/REGRESSIONS.md` tagged with this task's area (grep the tag; do not read whole logs once they are long). Do not read whole files when a grep or a range will do.
5. **Find the expensive step and design around it.** Only if the task moves data or runs analysis. Typical ones: moving data to or from the device (batch into few large transfers, stage once, tar), device shell limit of 180 s (short foreground steps), analysis needing Python 3.11/pandas 3/scipy (run in the container), long builds (run in parallel in the background, then verify).
6. **Batch independent calls** in one step; sequence only true dependencies.
7. **Decide the check** up front: the cheapest test that would prove the result wrong (a count, a hash, the test suite, opening the file). Put it last on the list.
8. **List what the task could break** (from `agent/REGRESSIONS.md`, `docs/KNOWN_PITFALLS.md`) and how you will notice.
9. **Start a change ledger**: a running list of every file created, changed, moved or deleted, every decision made, and every judgement call (with the rule that decided it). Post-work reads it.

**Do not** spawn other agents unless Dawson asks; plan more than the task needs; ask questions the files already answer.

**Done** = task list exists (hats, steps, check), nothing redundant on it, ledger started.
