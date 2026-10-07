# Raw demo locations

The raw replay root is now:
`C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\replays`.

- Pro: `AustinMajor_2025/spirit-vs-mouz/<original demo>.dem`.
- PUG: `CanadianIQ/batch_001/<original demo>.dem`.
- Existing batch numbers are retained, including `shakestx/batch_002`.

`CS2DI_DEMOS_ROOT` overrides the raw root. `CS2DI_ROOT` independently selects
analysis/knowledge data; its default remains the sibling `demoparser` folder.
Do not point the analysis root at Steam. Analysis collections retain their names,
including `analyzed_CanadianIQ_demos`; demo filenames and stems are unchanged.
The UI maps player folders to existing `_demos` collections and tournament folders
to same-named collections, rejecting ambiguous mappings. External folders can be
paired explicitly. Old saved raw-folder selections under `01_Demos` are translated
on load; historical packet snapshots and repair job manifests remain unchanged.

## Scripts

The packet UI, `fix_viewer_data.py`, v7.8 extractor, viewer sidecar, and
`run_all_tracks.py` use the new raw root. Local standalone copies under
`demoparser/03_Scripts/current` include the same location helper. Batch selection
in the repair CLI accepts the existing logical collection ID or physical folder
name. Use `--demos-root` for another raw root. The legacy runner's `--demos-name`
option still selects a raw subfolder relative to `--root`. Its old cross-collection
fallback is removed so a missing analysis cannot select another batch's evidence.

A repeated demo stem anywhere in one collection cannot map safely to one analysis
folder. Current direct extractors reject it before writing; the UI/managed repair
continue to block ambiguous matches and duplicate content. Do not rename raw demos
without also deliberately migrating their associated analysis IDs.

## Migration evidence

351 demos across nine collections were moved and verified against their original
SHA-256 hashes. No raw demos remain under local `01_Demos`. Player batch metadata JSON
files remain in their original local folders. Pro names were parsed against the observed CS2 map suffixes; map numbers
and continuation parts remain in filenames. 85 encounter folders
were identified across the three tournament collections. Two pairings include a
standalone map plus a numbered series: FURIA/NAVI and Vitality/FaZe at Starladder.
Those use separate `_single-map-<map>` and `_multi-map` folders. Names do not establish
bracket stage or distinguish repeated encounters without additional source data.

The local migration manifest/journal lives in
`demoparser/.extraction_jobs/raw_migration_20261006/`. It records original paths,
destinations, original demo SHA-256 identities from the completed repair run,
and post-move verification. Existing destination files are never overwritten.
The local FACEIT `Start-Collector.ps1` now writes raw files to Steam player/batch
folders while its JSON history/queues/manifests stay under local `01_Demos`.
This prevents a fresh download from recreating the old raw layout or losing batch
numbers. Direct portable collector invocation retains its legacy default unless
`--metadata-root` is supplied. The unrelated root `hiko.dem` is preserved. Analysis data and old packets are not
moved. Archived evidence records intentionally retain their original paths.

Verification: 114 repository tests, the Tk workflow callback smoke test (including
old saved selections with retained metadata folders), and five local collector
tests passed. The extraction runner's read-only plan pairs all 351 relocated demos
to their original analysis folders with zero missing folders or repeated stems.
The migration validation also confirms source identities in viewer metadata.
