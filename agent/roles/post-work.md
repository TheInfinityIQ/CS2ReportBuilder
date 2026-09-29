# Hat Z: Post-work (mandatory, after the last task hat, before replying)

**Job.** Turn this response's ledger into a true project record, then write the reply's tail. This is how the big logs stay accurate without anyone re-reading everything.

**Steps**
1. **Close the ledger.** Complete it from `git status` / `git diff --stat`, the moves you made, files sent to the device, and decisions taken this response. Anything not in the ledger did not happen.
2. **Sweep the logs.** For each kind of change, decide whether the log needs a line. Update only when the answer is yes; "no change" is a valid result.

| If this response... | Consider updating |
|---|---|
| finished, started or blocked something | `agent/STATE.md` (Where things stand / Open / Next; add one line to Recent work) |
| Dawson liked, disliked or decided something | `agent/PREFERENCES.md` (Log); if it is a firm decision, `docs/OWNER_RULINGS.md` with the reason and tier |
| broke something, was undone, or nearly repeated an old mistake | `agent/REGRESSIONS.md`; a data trap also goes in `docs/KNOWN_PITFALLS.md` with a test |
| changed how the product works or a design choice | `docs/DECISIONS.md` (new ADR, never edit old ones); Design v5 (`claude/Design_v5.md`) if the change makes it wrong |
| found or fixed a defect in a test output | `docs/CRITIQUES.md` (H-n row, status) |
| moved or added files in the data folder | `00_LEGEND.md`, `MOVES_MANIFEST.tsv`, the packets README |
| added, removed or changed a hat, a router row, or a workflow | `agent/ROUTER.md`, the hat file, `CLAUDE.md` |
| changed a plan or priority | `docs/ROADMAP.md` |
| changed `CLAUDE.md`, the router or a hat | re-upload `CLAUDE.md` to the Claude Project as `claude/START_HERE.md` (the copy must match; the repo wins if they differ) |
| changed `00_LEGEND.md` in the data folder | refresh `docs/DATA_FOLDER_LEGEND.snapshot.md` (a dated copy so a session with no device link still knows the layout; the device copy is authoritative) |
| pushed a log over its size cap | archive the oldest lines to `agent/archive/` and keep the lasting lesson |
| left any doc stating something now false | fix it now, or list it in `agent/STATE.md` > Open |

3. **Verify the record.** `git pull --rebase` before writing logs (append-only; two sessions may be editing). If the work is unfinished, write an `In progress` line in `agent/STATE.md` saying what is done, what is not, and where the partial files are.
    Run `python -m pytest -q` if the repo changed (the agent-docs test catches dead paths). Commit and push docs changes with code. Confirm files delivered to the device exist.
4. **Write the reply.** What came out, the file, one natural next step. No recap of steps. Then the **tail** (below).

**Fast path** (only if no file changed at all; writing any log or code leaves it): skip the sweep except "did Dawson state a preference or decision?"; still write the tail if a judgement call was made.

## The tail (last lines of every reply that made a judgement call)
Purpose: let Dawson see which rules steered a judgement call, so he can change the rule.
- Include only rules that actually **decided** a call where the files did not dictate the answer. Not every rule consulted.
- **At most 3 items.** If more applied, keep the ones most likely to be wrong or most worth revisiting. If none, omit the tail entirely (never write "none").
- One line per item: `handle` — the call it decided, in a few words. Handles are exact and findable:
  `OWNER_RULINGS › <bold heading>`, `ADR-nnn`, `Pitfall #n`, `CRITIQUES <ID>`, `RULES #n`, `PREFERENCES <date>`, `CLAUDE.md › <heading>`, `Design v5 › <section>`, `ROUTER › <row>`.
- Format:

  *Judgement calls used:*
  - `OWNER_RULINGS › Don't shrink the platform` — kept Viewer2D in scope despite the deferral
  - `ADR-010` — shipped the packets before extra validation

**Do not** cite a rule to sound careful; cite a rule you did not actually use; list files you merely read; leave a stale log because "nothing big changed" without checking the table.

**Done** = ledger closed, each table row considered, logs updated or knowingly left, tests green if code changed, reply and tail written.
