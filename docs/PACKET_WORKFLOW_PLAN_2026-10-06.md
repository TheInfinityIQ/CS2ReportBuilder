# Approved packet workflow implementation plan

Dawson approved implementation on 2026-10-06.

1. Choose an analysis collection and optionally a raw batch folder. Map exact
   stems inside that collection; do not search players across collections or
   move analysis. Preview missing, ambiguous and duplicate matches.
2. Add inclusion controls, map/name filters and saved JSON selections. Re-scan
   saved selections and compare identities before reuse. Hash originals with
   stat-bound caches; detect identical extraction evidence where originals are
   absent. Identity uncertainty must be visible.
3. Require validated 16 Hz tracks by default, with an explicit limited-replay
   override. Check actual cadence/coverage, pairing and interpolation validation.
4. Prepare missing core analysis and sidecars through independent subprocess
   jobs and one coordinator. Add gradual concurrency with 80% CPU / 90% RAM
   admission targets and peak-memory reserves. Targets are soft, not ceilings.
5. Share per-match locks between extraction and snapshots. Mark interrupted
   sidecar publication, cancel only queued jobs, preserve logs and support
   failed-only retry. Recover locks only when a same-host process is dead.
6. Default viewer extraction to 16 Hz, including normal v7.8 runs after core
   extraction. Keep coaching-table cadence/schema unchanged. Existing analysis
   gets additive repair; old packet snapshots/reports remain unchanged.
7. Record software revision, selected identities and replay readiness in packets.
   Recheck after acquiring snapshot ownership; never publish a failed packet.
8. Test mapping, duplicates, resource admission, cancellation, locking and
   interrupted publication; check real Tk callbacks and a bounded repair using
   copied analysis. Compare core-file hashes before/after. Document dry-run/fix
   commands and commit/push verified work.

## Anticipated problems

| Problem | Response |
|---|---|
| Repeated stem with different raw files | Block ambiguity; select narrower folder. |
| Renamed duplicate | SHA-256 deduplication; invalidate cache on identity/stat change. |
| Source changes while reading | Reject and refresh rather than trusting stale identity. |
| Missing/corrupt/partial viewer data | Not ready; publication marker blocks builds/reuse. |
| Concurrent UI/extractor write | Shared match lock; one managed coordinator. Stop older terminals first. |
| Crash leaves lock | Only recover dead same-host owner; do not clear live locks. |
| Insufficient RAM for one job | Wait visibly with cancel available; never force admission. |
| Sparse tracks despite 16 Hz metadata | Inspect actual cadence, roster/round coverage and validation. |
| Save file becomes stale | Re-scan; reject changed identities and missing entries. |
| GUI Python lacks scientific packages | GUI stays stdlib; jobs use repository environment. |
| Analysis has no reportable findings | Retain existing gates and diagnostics. |

The queue stops admitting jobs under pressure and lets active jobs finish.
Per-job peak estimates require measurements; more workers are not automatically
faster. Only the coordinator writes queue summaries. Core repair skips already
valid analysis; viewer repair replaces only additive outputs. Defaults must not
silently reuse 8 Hz or unvalidated sidecars.

## Implementation evidence

Completed with batch-selection services, shared ownership locks, the managed
extraction queue, `fix_viewer_data.py`, and integrated Tk controls. The
[current guide](PACKET_BUILDER_UI.md) describes usage and limits. Verification
used copied analysis and one bounded fresh extraction; no full repair of the
owner's existing collections was launched. Both replay and core gates passed.
Repair preserved 54 core files, fresh extraction reproduced 47 comparable core
tables, and a new one-match packet passed report rendering at 16 Hz.

Final verification: 106 automated tests passed and lint was clean. Real Tk
callbacks and the visible window layout were checked separately. These checks
do not establish maximum concurrent throughput or useful coaching quality.
