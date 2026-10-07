# Local game catalog

The packet window uses a rebuildable SQLite file at
`<CS2DI_ROOT>/game_catalog.sqlite3`. On Dawson's machine this is
`C:\Users\dawso\Developer\CS2ReportBuilder\demoparser\game_catalog.sqlite3`.
It stays outside Git and is not included in coach packets. No additional database
server or dependency is required.

## Contents and scope

Each analyzed game records its collection, path, map, player names/SteamIDs,
source identity, core/replay readiness, validation time and analysis-file metadata.
Raw-source records link games to their original demo paths, including batch and
series folders. Queries can filter player SteamID, collection, raw subfolder or
team name. Team names are hints parsed from `team-vs-team-map` filenames;
they do not establish roster affiliation. The packet UI continues to select games
by collection/folder and does not assemble packets by searching players globally.

Records describe last-observed availability. Querying the catalog alone does not
validate game contents. Renamed/reorganized sources are discovered when scanned
again; deleted analysis is pruned when its collection is scanned. Missing raw
files are omitted from availability queries.

## Loading and updates

The window checks analysis filenames, sizes, timestamps and file identities before
reusing a result. New/changed games are fully checked. Locks and interrupted
viewer publication markers prevent reuse. This is a local performance cache,
not protection against deliberately preserving file metadata while altering data.
Packet builds independently validate and copy source evidence under locks, and
hash selected originals afresh.

Extraction v7.8, viewer sidecar publication and the managed preparation/repair
queue update game records after publication. With cs2di available they record
validation results. Standalone scripts ship the same stdlib catalog helper and
record pending rosters/source links; the next UI scan validates these before
showing ready. Catalog errors warn without making successful extraction fail.
Validation revisions invalidate cached results when check semantics change.
Maintainers must bump `VALIDATION_REVISION` in the catalog helper when changing
core/replay gates, and keep the standalone copy identical. A forced rebuild is
also available after validation changes.

Short transactional writes and a connection timeout support concurrent jobs;
active output locks still protect evidence publication.

In Utilities, **Refresh catalog for selected collection** forces fresh checks of
the currently selected games. Missing catalogs populate on first use. An
unavailable catalog falls back to uncached UI validation. Explicit refresh/rebuild
can preserve an unreadable database as a `.broken_<id>` file and recreate it;
unsupported schema versions are reported rather than silently discarded.

To populate all discovered analysis collections, or force a complete recheck,
run from the repository:

```powershell
& .venv/Scripts/python.exe scripts/catalog_games.py
& .venv/Scripts/python.exe scripts/catalog_games.py --rebuild
```

Use `--root` and `--demos-root` for alternative roots. This does not edit analysis
or demo content. It links raw files by exact stem within their corresponding
collection. Ambiguous stems remain blocked by the normal selection workflow.
CLI population can reuse earlier extraction hashes only when the current file
fingerprint matches and the hash agrees with analyzed viewer metadata. Otherwise
a raw-selection scan computes the hash before trusting source identity.

Example availability queries:

```powershell
& .venv/Scripts/python.exe scripts/catalog_games.py --query --player 76561198000000000
& .venv/Scripts/python.exe scripts/catalog_games.py --query --team natus-vincere
& .venv/Scripts/python.exe scripts/catalog_games.py --query --raw-folder 'C:\path\to\replays\CanadianIQ\batch_001'
```

## Verification on 2026-10-07

The initial pass indexed 453 analyzed game directories in nine collections:
351 replay-ready games and 102 historical IEM analysis-only games. It linked
351 existing raw demos. SQLite's integrity check returned `ok`.

| Collection | Games | Initial validation | Cached scan |
|---|---:|---:|---:|
| CanadianIQ | 50 | 54.11 s | 1.52 s |
| Austin Major | 71 | 101.89 s | 2.19 s |
| Starladder | 68 | 102.57 s | 2.38 s |

These are observed CLI collection scans, including source linking, on the local
machine. They do not measure total window startup or promise timings elsewhere.
Changed data requires fresh validation; a new raw source can require hashing.

Automated checks cover reuse/invalidation, locks, interrupted publication,
concurrent writers, source fingerprints, corruption recovery, pending standalone
updates, queries and removal. A separate check corrupts replay data after a
cached preview and verifies that packet construction still rejects it.
The full suite passed 125 tests; the real Tk window opened successfully.
A cached CanadianIQ raw-batch scan plus player-list assembly took 1.92 seconds.
