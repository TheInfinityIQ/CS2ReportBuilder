# Full viewer-data repair: 2026-10-06

Dawson authorized repairing every eligible demo. All **351 demos across nine
analysis collections** now pass the final viewer readiness audit at **16 Hz**.
There are **zero remaining failures**. The repair used the viewer-only phase:
core extraction was not rerun, originals remained unchanged, and previous
packets/reports remain snapshots. Build a new packet to use the repaired data.

## Scope and results

| Collection | Demos verified |
|---|---:|
| AustinMajor_2025 | 71 |
| CanadianIQ_demos | 50 |
| Ch00per_demos | 25 |
| FoxC_demos | 25 |
| IEMCologneMajor2026 | 12 |
| MIMY_demos | 25 |
| shakestx_demos | 50 |
| Starladder_2025 | 68 |
| stealthe_demos | 25 |
| Total | 351 |

The run replaced the four viewer outputs alongside each existing analysis.
The final read-only audit checked source identity/stat consistency, existing
core gates, actual 16 Hz cadence, finite positions/facing, expected coverage,
pairing/interpolation checks, grenade tables and recorded file checksums.
It counted 143,324 recorded grenade paths. This does not establish every
trajectory boundary's accuracy or the usefulness/correctness of coaching.

## Issues corrected during the run

- The first idle coordinator could not admit a large demo because viewer-only
  jobs inherited the larger core-extraction memory estimate. It was stopped
  only after confirming no workers had started. Viewer repair now uses a
  separate estimate with headroom, starts smaller demos first, saves the full
  job plan, and sizes native thread budgets against estimated RAM-feasible
  concurrency. CLI demo hashes are cached against file identity/stat changes.
- Three early jobs wrote valid data but failed an overly strict coverage
  check. Two rosters contained a player absent from all core position data;
  one surrender round had no live freeze/end window. Coverage now follows
  recorded core observations and the extractor's live-window rules. These
  omissions are disclosed; missing movement is never invented. Selecting an
  unobserved player still blocks a default validated-replay packet.
- The three cases passed retry by reusing their intact, validated outputs.
  The original run summary retains the initial failures as historical evidence;
  the final validation record is the authoritative completion result.

Queue and coverage fixes were committed as `fe5849e`. Verification passed
110 automated tests, lint, and actual Tk callbacks, including the selected-player
coverage guard. Resource targets remain soft admission targets, not hard caps.

## Local evidence

Evidence stays outside Git under `demoparser/.extraction_jobs/`:

- `20261006_180417_f7197946/jobs.json`: all 351 planned jobs.
- `20261006_180417_f7197946/summary.json`: original run results and logs.
- `20261006_180417_f7197946/retry_summary.json`: successful three-case retry.
- `20261006_180417_f7197946/final_validation.json`: 351 passed, zero failed,
  including per-demo rates, checks and coverage disclosures.
- `20261006_185013_71e12533/`: retry job logs/results.
- `verify_full_repair.py`: the local read-only audit used for completion.

The final audit recorded two matches with unobserved roster entries and one
with a nonlive round. No coordinator remained active at completion.
See the [current UI and repair guide](PACKET_BUILDER_UI.md) for future runs.
