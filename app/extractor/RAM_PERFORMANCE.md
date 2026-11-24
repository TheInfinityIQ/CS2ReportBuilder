# Analysis memory and CPU qualification — November 13, 2026

The user's active analysis batch was stopped before implementation. Original
demos and completed analysis were retained. Qualification used one full Anubis
demo, including all coaching tables, entity/smoke exports and validated viewer
tracks, with private outputs under
`data/.desktop/validation/analysis-performance/`.

## Accepted result

| Measure | Original | Accepted eight-worker candidate |
| --- | ---: | ---: |
| OS job peak committed memory, including children | 2,766.844 MiB | 2,010.988 MiB |
| Parent OS peak resident working set | 2,166.555 MiB | 2,151.727 MiB |
| Aggregate job CPU time | 247.500 s | 216.875 s |
| Wall-clock duration | 144.266 s | 144.859 s |
| Analysis output files compared | 67 | All equivalent |

Peak committed allocation decreased **27.32%** and CPU time decreased **12.37%**.
Wall time was essentially unchanged (+0.41%). Physical resident peak decreased
only about 0.68%; do not represent the allocation reduction as a guaranteed 27%
reduction in Task Manager's resident-RAM reading. Committed memory includes
backing in RAM/pagefile, while working set includes currently resident pages.

Windows job-object counters supply the committed-memory peak and aggregate CPU
time; `GetProcessMemoryInfo` supplies the parent's resident peak. A single full
demo pair on this machine is not an all-demo maximum-memory guarantee. Other
applications were not stopped, so wall time is also subject to external load.

## Implementation

- Release the rich/plain/positional event dictionaries after merging them; release
  unclipped originals once their retained events are established.
- Clean event dictionaries without deep-copying every unchanged table. Replaced
  tables still get independent results; cleanup does not mutate its source frames.
- Allow explicitly owned parser frames to be repaired/filtered without redundant
  full-table copies. Borrowed inputs retain their non-mutating behavior.
- Release dense/user-command data after engagement generation, and core tables
  and parser before starting the separate entity decoder. Collect cycles once
  at that stage boundary, not repeatedly inside hot loops.
- Use exact integer comparisons and select the first matching row directly for
  canonical player-ID lookups. Preserve nullable IDs and the existing fallback
  for non-integer input. No floats, coordinates, fields or sample rates are
  downcast or removed.
- `analysis_resources.py` initializes native pools before numerical imports:
  Rayon up to eight workers, Polars up to four, and BLAS/OMP/MKL defaults of one.
  Smaller CPU counts reduce those defaults; explicit environment overrides are
  honored. This is bounded concurrency, not a dedicated core or a hard RAM cap.
  A fresh process confirmed the effective default environment and Polars pool.

The original lifecycle-only candidate did **not** improve peak memory; that
measurement is retained. Four workers reduced allocation/CPU time but increased
elapsed time by 9.29%. Eight workers retained the allocation saving with nearly
the original completion time. Neither a lower sampling rate nor repeated smaller
demo parse passes was used to obtain these results.

See the [Rayon worker configuration](https://github.com/rayon-rs/rayon/blob/main/FAQ.md)
for its environment control. The qualified default initialization reproduces the
eight-worker candidate's tested environment.

## Result-preservation checks

All 67 output files from the original and accepted full-demo runs were compared.
CSV and JSONL/gzip payloads matched **exact decompressed bytes**. JSON values
matched after narrowly normalizing code-revision provenance, actual elapsed
runtime, output-directory prefixes and verified gzip-container checksums. Each
recorded container checksum was validated against its own file before comparing
decoded content. No numeric tolerance, rounding, sampling reduction or analytic
field exclusion was used. Membership, source identities, integrity gates,
coaching values, trajectories, raw smoke and entity observations were retained.

Evidence: `before/measurement.json`, `after/measurement.json` (unsuccessful first
candidate), `balanced/measurement.json`, `balanced8/measurement.json`,
`comparison-balanced8.json`, `acceptance.json`, frozen original source and logs.
Earlier measurement descriptions used a generic same-thread-policy label; the
descriptive correction retains that original label alongside the explicit
candidate policy. Measurements themselves were not changed.

The 22 extractor tests and 30 download/job tests passed. Full runs also passed
the extractor's built-in regressions and hard integrity gates.

## Interrupted-job recovery and progress

Stopping the user's original job occurred after Anubis core/entity publication
but before additive viewer tracks and the completion receipt. Previously,
Downloads rejected every existing analysis without a successful receipt.

`resume_analysis.py` now finishes only that missing tail when the core validity,
integrity, original demo hash, entity identity/checksums and existing sampling
rate match. It takes the existing maintenance and per-analysis locks, runs the
existing viewer extractor, verifies every preserved core file byte-for-byte and
validates the new viewer identity/checksums before writing the existing receipt
format. Unknown or mismatched outputs are preserved and rejected. Completed
receipts left behind by a stopped parent can be adopted without re-extraction.

The real interrupted Anubis recovery preserved all **60 existing core files**
byte-for-byte. See `recovery-before.json` and `recovery-result.json`.

Downloads also passes the child extractor's output/error handles explicitly,
so analysis-stage messages reach the existing job log. The resumed batch uses
the existing Library selection, deduplication, analysis function, locks and
`JobRunner`; it starts no downloads. Its supervisor/progress record is
`resume-status.json`, with standard Toolbox job history/logs plus
`resume-console.log`. Previously completed analyses are skipped.

The final retry encountered a newer, user-started **MIMY** download/analysis job
holding the replay-library lock. That newer job was left running; its future
analysis subprocesses load the updated resource policy. The prior SmoodAimder
batch is not running concurrently. The one-off retry supervisor now refuses a
changed owner selection rather than silently resuming a different player's plan.

Two patch-14197 demos still fail event decoding (`EntityNotFound`, no completed
competitive rounds). They remain invalid rather than being counted as successful
analysis. This memory/CPU change does not upgrade or replace the parser.
