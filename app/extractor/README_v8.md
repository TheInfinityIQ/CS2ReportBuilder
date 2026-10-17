# Extractor v8

`extract_demos_v8.py` retains the v7.8 coaching pipeline and adds a second, networked-entity pass using the pinned **DemoFile.Game.Cs 0.44.1** package. The original v7.8 script is unchanged. The helper source is included under `entity_v8/` and is built automatically when needed.

## Rebuild every local demo

`python app/extractor/rebuild_all_v8.py` prints a plan; add `--run` to execute it. The resumable runner processes every collection under `data/demos`, one demo at a time, writing fresh analysis under `data/analysis/v8_rebuild/analyzed_<collection>_v8/`. Existing analysis is preserved. It checks a 12 GB free-space reserve between demos, continues after individual failures, and retains per-demo logs/progress in `data/.desktop/rebuild-v8/`.

Open `http://127.0.0.1:8766/modules/viewer2d/rebuild.html` for progress and **Stop after current demo**. Closing the page does not stop the worker. Resume with the same `--run` command: completed results are skipped only when source size/time, extractor revision, and output readiness still match. Failed/interrupted outputs belonging to this run can be replaced; unrelated existing output is preserved. `--stop` requests a graceful stop from the command line. Smoke decoder failures and core extraction failures are different; successful output metadata retains smoke fidelity/status limits.

## Setup requirements

Requires Python 3.10+ and the **.NET 9 SDK** (not just the runtime). Python packages:

```powershell
python -m pip install -r app/extractor/requirements-v8.txt
```

Alternatively, install with `--target app/extractor/.deps`; v8 loads this ignored local dependency folder automatically. The first entity extraction restores the official NuGet package and builds the helper. Later runs use the compiled helper until its source changes. NuGet access is needed on the first build.

## Extract a collection or one demo

Run from the project root:

```powershell
python app/extractor/extract_demos_v8.py --demos data/demos/CanadianIQ_demos
```

The default output is a separate collection under `data/analysis/analyzed_CanadianIQ_demos_v8`. Use `--demo "path/to/game.dem"` for one demo and `--output "path/to/output-collection"` to choose the output root. Recursive batches reject duplicate demo names. A per-demo folder that already exists is rejected unless `--replace` is supplied deliberately.

Full extraction runs the original core integrity checks, then validates entity sidecars before publishing the new analysis. A backend or validation failure preserves the previous canonical output. The player/trajectory viewer pass remains separate; its failure is reported and gives a nonzero exit status. `--no-player-viewer` skips that player pass, but does not disable v8 entities.

The restored `demo_layout.py`, `job_lock.py`, `game_catalog.py`, and `extract_viewer_tracks.py` are the supporting modules referenced by the original script. They were missing from this checkout. Default data paths now resolve to this project's `data/` and `data/demos/`; `CS2DI_ROOT` and `CS2DI_DEMOS_ROOT` still override them.

## Add only the new entity data

This does not rerun coaching analysis or replace existing analysis tables:

```powershell
python app/extractor/extract_demos_v8.py --demo "data/demos/CanadianIQ_demos/batch_001/CanadianIQ_09-17-2026_0dot78_Ancient_LOSS.dem" --entities-only --analysis "data/analysis/analyzed_CanadianIQ_demos/CanadianIQ_09-17-2026_0dot78_Ancient_LOSS" --round 24 --output data/analysis/v8_rounds
```

The result is `data/analysis/v8_rounds/<demo-name>/viewer_v8/`. Omit `--round` to capture the existing analysis's whole match. Without `--analysis`, entity-only mode captures the full demo including warmup. An analysis demo hash, when present, must match the original demo. `--round` requires `--analysis` and only works with `--entities-only`.

Default entity position sampling is **16 Hz**; use `--entity-hz 64` for every demo tick. Available rates divide 64. Creation observations, ownership changes, removals, and smoke updates are packet-driven even when positions use a lower sample rate.

## New files

Each demo has a `viewer_v8/` directory:

| File | Contents |
| --- | --- |
| `loot_tracks.jsonl.gz` | Actual unowned weapon/utility/C4 entity positions, item names and definition indices, serial-aware identities, observed pickup/removal transitions. Positions follow movement rather than using a dead player's location. |
| `inferno_patches.jsonl.gz` | Individual networked fire-patch world positions and burning flags, including changing patch sets and extinction. |
| `smoke_frames.jsonl.gz` | Smoke detonation center, effect tick, seed, voxel-update counter, declared payload size, and losslessly preserved raw voxel buffer as Base64. |
| `smoke_voxels.jsonl.gz` | Experimental decoded 32³ occupancy grid, run-length encoded, with 12-unit cells. |
| `smoke_decode_meta.json` | Decoder status, rejected entities, occupancy changes, and explicit fidelity limits. |
| `entity_meta.json` | Demo SHA-256, backend/version, tick domain, sampling, row counts, capabilities, semantic limits, validation results, and file hashes. |

All three streams contain JSON objects, one per line, compressed with gzip. An `upsert` contains `tick`, `id`, and `state`; that state persists until the next update, `pickup`, or `removed`. IDs are **string-encoded full entity handles**, including the serial number, so recycled indices do not merge separate objects. The state also carries `entityIndex` and `serial`. Window exports include entities already present at the start and do not invent removals at the end.

`tick` is the demo tick used by demoparser, not the server network tick. Raw `effectNetworkTick` and `dropNetworkTick` fields retain their network clock and must not be mixed directly with `tick`; `networkTickOffsets` records observed clock offsets. Prefer stream `tick` for viewer playback.

## Accuracy limits

- **Loot:** records networked item positions and ownership. An invalid owner handle identifies an unowned entity; a transition to a valid owner is recorded as `pickup`. `removed` only means the entity left the networked set and does not guess why. Coordinates retain the demo's network precision and sampling limits.
- **Fire:** records actual patch centers and burning flags. Rendering the visual edge around each center still requires a rendering policy; the data is not an engine-rendered flame polygon. Older game schemas unsupported by the pinned backend can fail extraction rather than producing invented patches.
- **Smoke:** preserves raw updates and attempts the published demolens chunk decoder with enclosed-interior filling. This is reverse engineered; grid placement, density, fading, and engine visual parity remain unverified. The tested round decodes eight smokes without format failures, but does not reproduce visible HE holes. The viewer does not fabricate holes in decoded mode. Unsupported formats are reported and raw bytes retained. `voxelBase64` is the full network vector; `payloadBytes` is its buffer length, while `declaredBytes` is the separate valid-size field.
- **Alignment:** when existing event tables are available, fire/smoke starts are checked against them within one tick and eight world units. The separate smoke event and entity-center fields differed by up to 3.45 units in the full validation demo. Metadata reports the actual largest difference rather than rounding it away. This check verifies event alignment, not the fidelity of a rendered smoke volume.
- Existing CSV analysis alone cannot generate these new tracks; the original `.dem` is required.
- **Shots:** v8 always attempts `bullet_impact` with player positions, even if event discovery omits it. Many demos (including the Ancient test match) contain no such events. The viewer uses recorded firing origins for flashes and requires matched recorded impact endpoints for shot lines. It does not reconstruct spread or map collision from firing angles.

The 2D viewer reads validated v8 entity streams beside an analysis folder. It uses recorded loot and burning patch centers, and decoded smoke when decoding completes without failures. Older analysis retains illustrative effects. Fire edge/glow and smoke opacity/fade remain rendering approximations. Decoder attribution and MIT license are in `entity_v8/DEMOLENS_LICENSE.txt`.

Dedicated local check: open `http://127.0.0.1:8766/modules/viewer2d/?sample=utility-check.json`. The three buttons jump to smoke bloom, molotov spread, and a nearby HE. This separate export preserves the user's default example round. Rebuild it with `replay.py --source <analysis-relative-path> --round 24 --entities <viewer_v8-folder> --output app/modules/viewer2d/utility-check.json`.

## Validation

```powershell
python -m unittest discover -s app/extractor -p test_viewer_entities_v8.py
dotnet build -c Release app/extractor/entity_v8/EntityExtractor.csproj
```

Unit checks cover ownership lifecycles, serial identities, tick windows/order, fire patches, smoke byte preservation, round selection, and preservation of previous sidecars on backend failure. Real-demo validation outputs are kept under ignored `data/analysis/v8_validation/` and `data/analysis/v8_full_validation/`.

Backend reference: https://github.com/saul/demofile-net (MIT); pinned package: https://www.nuget.org/packages/DemoFile.Game.Cs/0.44.1.
