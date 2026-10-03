# Finding files without reloading the project

Start with CLAUDE.md, agent/STATE.md, and the selected task route. Open the root
00_INDEX.md, then one relevant folder map. Search the catalog before opening
large historical documents. Do not recursively read the indexes.

## Why this shape

The initial local inventory found 54,240 files in 4,867 file-containing folders
(rg-visible files, before excluding both browser profiles and tool caches).
Most are repeated analysis and packet artifacts. A handwritten summary beside
every data folder would duplicate the same schema thousands of times.

Instead, every non-internal Git repository folder gets a generated Markdown map.
Local document/source folders and demo/analysis batches get maps, while bulk
output directories are represented individually in a searchable JSONL catalog.
Browser profiles, credentials, Git internals, environments, and caches are omitted.
Fresh-coach packet folders are catalogued but never modified by this tool.

The existing TRUTH_MAP and task router remain authoritative for routing facts.
This supplements them rather than introducing another source of project rules.
Descriptions are labelled **curated**, **extracted**, or **filename**. A filename
hint is not a content review. Curated descriptions bind to a normalized source
hash and become visibly stale after edits. Neither type proves a document true.

Maps list at most 48 files and 48 child maps; the catalog holds every included
file, including the remainder. Query pages avoid making an agent read a
500-transcript directory listing. Use rg for actual content searches: this is
file discovery, not a semantic search engine or a new database.

History uses explicit document/filename dates where available, followed by
natural filename/version order for undated records. No chronological date is
inferred from filesystem modification time or upload order. Known dates and
reviewed descriptions are in navigation/metadata.json; original documents decide
authority. A newer version is not automatically accepted or a superseding ruling.

## Commands from the Git checkout

```powershell
python scripts/navigation.py build
python scripts/navigation.py check
python scripts/navigation.py find --under docs --query "coaching" --limit 10
python scripts/navigation.py find --under docs/history --offset 20 --limit 20
```

Local-only data maps and catalog:

```powershell
python scripts/navigation.py build --root ../demoparser --profile data
python scripts/navigation.py check --root ../demoparser --profile data
python scripts/navigation.py find --root ../demoparser --profile data --query "ClaudeCoachingReportsTest"
```

Override --root if the data lives elsewhere; no fixed device path is embedded in
the generator. Repository output goes to 00_INDEX.md files and .navigation/;
commit it with the source changes. Data output stays under the data root and
is never uploaded to GitHub.

## Keeping summaries true

1. Edit/add/move/remove the original source file.
2. Run build. Extracted headings/descriptions update automatically; deleted files
   disappear and obsolete generated maps are removed. Handwritten maps are never
   overwritten. Missing parents are generated automatically.
3. If a curated description needs review, read the changed source and update it:

```powershell
python scripts/navigation.py review --path docs/CRITIQUES.md --summary "Updated description after inspecting the change."
```

For local documents, add --root ../demoparser --profile data to review.
Review binds the supplied description to the inspected file hash. Do not run it
blindly to silence a failure. Status, date, predecessor, and read-when metadata
are edited in navigation/metadata.json when the source actually supports them.

4. Run build again, check, then the required pytest suite. CI independently checks
   repository freshness; it does not silently rewrite summaries or rulings.

Repo checks always hash readable source content, with CRLF normalized to LF so
Windows and Linux agree. Local warm scans reuse records when size/mtime and
metadata are unchanged; add --force for a full rehash if timestamps were preserved
or restored. Large binary demos/archives are listed by name/type/size, not decoded
or hashed. A changed filename summary does not imply a semantic audit.

## Limits and ownership

This initial pass inventories the eligible tree and extracts bounded metadata;
it is not a line-by-line human review of every transcript or experiment.
Reviewed high-value entries come from the onboarding review. New documents can
start with an extracted description, then receive a curated summary when a task
actually needs them. This amortizes review cost without pretending all files
have been understood.

The agent making a source change owns refreshing its maps in the same task.
Local data changes need a local build/check; GitHub CI cannot see the device.
Cloud Design v5 and Claude Project copies must be updated separately when their
content changes; they are not silently considered synchronized by these maps.

## Work record for 2026-10-03

Route: Intake steward, then Developer, then Post-work. Existing router/TRUTH_MAP
reused; no coach run, demo parsing, statistical threshold, or product code change.
Ledger: generator and tests; metadata; agent entry/routing/maintenance guidance;
CI freshness check; generated repository/local maps and catalogs; local legend
and Git snapshot refresh. Source artifacts remain in place. GitHub gets only code,
documentation, and repository navigation, not local data or the local catalog.

Initial output: 29 Git folder maps covering 130 source files, and 192 local maps
covering 52,223 eligible files. These are inventory counts, not semantic audits or
measured model-token savings. The root maps provide bounded entry points instead
of requiring an agent to load the complete catalog.

Verification also exposed lint-rule drift from an unpinned Ruff release. The core
E4/E7/E9/F checks are now explicit; an existing viewer statement was split across
lines without changing behavior. CI includes the navigation generator in linting.

Checks: add/edit/delete drift, stale curated summaries, safe exclusions, packet
isolation, chronology, bounded maps, handwritten-map protection, repeat-build
determinism, repository freshness, and the existing test suite.

Measured locally: warm data freshness check 10.43 seconds; root map sizes 2,863
characters (repo) and 3,126 (data). All generated Markdown links resolved. The
repeat check left all 13,671 packet files byte-identical and added no packet maps.
The full suite passes 79 tests (72 existing plus 7 navigation tests); core lint
checks pass. Source additions/edits/deletions and curated-summary drift are tested.
