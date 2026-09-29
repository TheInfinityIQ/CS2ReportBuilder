<!-- SNAPSHOT of the data folder's 00_LEGEND.md taken 2026-09-29. The device copy is authoritative; refresh this when it changes. Its purpose: a session with no device link still knows the layout. -->

# 00_LEGEND: start here

This is the map of the whole `demoparser` folder (CS2 demo analysis and coaching project).
If you know nothing about this project, read this file, find your question in Section 1, and go to the path it names. Do not browse.

**Root location:** `C:\Users\dawso\Developer\CS2ReportBuilder\demoparser`
(Moved from the Steam directory on 2026-09-29 to avoid Steam file-access restrictions.)

Last updated: 2026-09-29. If you add or move anything, update this file (Section 7 says how).

---

## 1. "I want to..." quick finder

| I want to... | Go to |
|---|---|
| Add a file and sort it later | `00_ORGANIZE_ME/` |
| Find a raw demo (.dem) | `01_Demos/<batch>/` (Section 3) |
| Find the extracted data for a demo | `02_Analysis/analyzed_<batch>/<demo name>/` (Section 4) |
| Run the extractor on a batch | `03_Scripts/current/extract_demos_v7dot8.py` |
| Add 8 Hz view angles and grenade paths (viewer data) | `03_Scripts/current/run_all_tracks.py` (uses `extract_viewer_tracks.py`) |
| Find an older extractor version | `03_Scripts/archive/` |
| Open the newest player report | `04_Reports/player_study_html/MIMY_report_v3.3.html` |
| Watch a demo of the 2D viewer or report | `04_Reports/demo_videos/` |
| Read a written coaching report | `04_Reports/written_reports/` |
| See screenshots of the report or of data | `04_Reports/screenshots/` |
| Read the coach system prompt | `05_Coach_Knowledge/onboarding_pack/CS2 Demo Coach — System Prompt.txt` |
| Read what data the extractor can produce | `05_Coach_Knowledge/onboarding_pack/data_capability_report_current.md` |
| Read the current project onboarding document | `05_Coach_Knowledge/onboarding_document/` |
| Read the architecture and design history | `05_Coach_Knowledge/architecture_review/` |
| Read pro-player and creator knowledge | `05_Coach_Knowledge/content_creator_transcripts/` and `player_knowledge_base/` |
| Find the old AI chat logs (how decisions were made) | `05_Coach_Knowledge/ai_chat_history/` |
| Find a ready-made coach packet (30 matches per player) | `06_Handoff_and_Tests/packets/<packet_id>/` (Section 8) |
| Test a fresh AI with no context | `06_Handoff_and_Tests/packets/<packet_id>/PROMPT.md` |
| See results from test coaches | `06_Handoff_and_Tests/test_coaches/` |
| Find old stage/milestone work (Stage 3, M0 to M122) | `07_Development/stage_steps/` |
| Find the awpy / demoparser library source | `07_Development/repos/` |
| Download FACEIT demos | `08_Demo_Downloading/` |
| Undo a move or find where a file used to be | `MOVES_MANIFEST.tsv` (old path, new path) |
| Find something that looks like junk or a duplicate | `_archive/` (safe to delete once you are happy) |

**AI agents: start with `CLAUDE.md` and `agent/STATE.md` in the git repo** (GitHub TheInfinityIQ/cs2-demo-intelligence). They define the task router and the role "hats"; this legend is the map of the data folder only.

The real source code for the report builder lives in the git repo `cs2-demo-intelligence` (GitHub: TheInfinityIQ/cs2-demo-intelligence), not in this folder. This folder holds data, scripts you run, and outputs.

---

## 2. Top-level folders

| Folder | Holds | Size |
|---|---|---|
| `00_ORGANIZE_ME` | Drop zone. Anything not yet sorted. | small |
| `01_Demos` | Raw `.dem` files, one sub-folder per batch | ~130 GB |
| `02_Analysis` | Extractor output for each demo | ~0.8 GB |
| `03_Scripts` | Python scripts | tiny |
| `04_Reports` | Finished reports, videos, screenshots | ~40 MB |
| `05_Coach_Knowledge` | Everything the AI coach learns from | ~320 MB |
| `06_Handoff_and_Tests` | Coach packets and test results | ~100 MB |
| `07_Development` | Old build stages, libraries | ~7 GB |
| `08_Demo_Downloading` | FACEIT downloader | ~130 MB |
| `_archive` | Old zips and leftovers; safe to delete | ~1 GB |
| `00_LEGEND.md` | This file | |
| `MOVES_MANIFEST.tsv` | Old to new path list from the reorganization | |
| `README.md` | Short version of this file | |

Numbering follows the pipeline order: download (08) -> demos (01) -> extract (03) -> analysis (02) -> report (04).

---

## 3. Demo batches (`01_Demos/<batch>/`)

| Batch | What it is | Demos | Extractor schema |
|---|---|---|---|
| `AustinMajor_2025` | Austin Major pro matches | 71 | 3.7 |
| `IEMCologneMajor2026` | IEM Cologne Major pro matches | 12 (analysis folder has 114 entries; 102 have no .dem here) | 3.6 |
| `Starladder_2025` | Starladder pro matches | 68 | 3.7 |
| `faceit` | FACEIT matches, nested by player (`Donk`, `CanadianIQ`, `Mezii`) | 100 | 3.6 |
| `iTrilogy` | iTrilogy matches. The only batch with viewer tracks so far | 30 | 3.7 |
| `mimy` | The player-study batch for player "mimy" | 30 | 3.7 |
| `stacks` | Stacks matches | 29 | 3.7 |
| (analysis only) `premier_batch1` | Premier matches; analyzed, no .dem kept | n/a | 3.7 |

Rule: the batch folder name in `01_Demos` and the suffix in `02_Analysis/analyzed_<batch>` must match exactly. The scripts rely on it.

---

## 4. What is inside one analyzed demo folder

Path: `02_Analysis/analyzed_<batch>/<demo name>/`

| File | What it is |
|---|---|
| `match_summary.json`, `header.json` | Map, teams, score, demo header |
| `players.csv`, `scoreboard*.csv` | Who played; final and per-segment scoreboards |
| `rounds.csv` | One row per round (ticks, winner, bomb events) |
| `player_rounds.csv` | One row per player per round |
| `economy.csv` | Buy and money per round |
| `events/` | One table per event type (kills, damage, grenades, ...) |
| `player_positions.csv.gz` | Coarse positions over time |
| `viewer_tracks.csv.gz` | 8 Hz position, view angle, pitch, stance flags (only where run_all_tracks.py has been run) |
| `grenade_throws.csv.gz`, `grenade_paths.csv.gz` | Every grenade thrown and its flight path (same condition) |
| `viewer_tracks_meta.json` | Settings and checks for the tracks above |
| `coaching/` | Derived coaching tables |
| `integrity_checks.json`, `repairs.json`, `_repair_backup/` | Data quality checks and any repairs |
| `available_events.json`, `source_capabilities.json`, `usercmd_availability.json` | What the demo did and did not contain |

Also in each `analyzed_<batch>/`: `viewer_tracks_batch_summary.json` after a tracks run. In the root: `ALL_TRACKS_RUN_SUMMARY.json` after `run_all_tracks.py`.

Data dictionary: `05_Coach_Knowledge/onboarding_pack/data_capability_report_current.md` and `logical_map_manifest_current.csv`.

---

## 5. Which version is current?

| Thing | Current | Older (do not use) |
|---|---|---|
| Extractor | `03_Scripts/current/extract_demos_v7dot8.py` | `03_Scripts/archive/` v5 to v7.7 |
| Tracks extractor | `03_Scripts/current/extract_viewer_tracks.py` v1.0 | none |
| Run tracks on everything | `03_Scripts/current/run_all_tracks.py` | none |
| Player report | `MIMY_report_v3.3.html` (v3.4 lives in the git repo) | v2, v3.0, v3.2 |
| Coach prompt | repo `coach/handoff/PROMPT.md` and `06_.../packets/<id>/PROMPT.md` | `05_.../onboarding_pack/SUPERSEDED_README.md` era |
| Onboarding | `05_.../onboarding_document/...LIVING_ONBOARDING_CURRENT_v1.2.docx` | files in `architecture_review/` |
| Architecture | `...Master_Architecture_v4.1.docx` | v4.0, DesignV2, V2.1 |
| Coach packets | `06_.../packets/P_<kind>_<player>/` | `06_.../current_handoff_pack/` (single-player, older) |

v7.8 = v7.7 plus two damage columns and a new path convention. Same tables, same sampling rate. The 8 Hz data comes from the tracks scripts.

---

## 6. Naming rules

- Folders start with a two-digit number for pipeline order, then a plain name.
- Reports: `<Player>_report_v<major>.<minor>.html`
- Scripts: `<name>_v<version>.py`; the newest lives in `current/`, the rest in `archive/`.
- Big zips and one-off leftovers go to `_archive/`, never the top level.
- Never rename a batch folder in `01_Demos` or `02_Analysis` without changing both.

---

## 7. Keeping this legend true

1. New files go in `00_ORGANIZE_ME/`. Ask Claude to sort them; it will move them, log each move in `MOVES_MANIFEST.tsv`, and update this file.
2. New batch: create `01_Demos/<batch>/`, run the extractor, confirm `02_Analysis/analyzed_<batch>/` appears, add a row to Section 3.
3. New script version: put it in `current/`, move the old one to `archive/`, update Section 5.
4. Nothing in this folder should sit loose at the top level besides `00_LEGEND.md`, `MOVES_MANIFEST.tsv` and `README.md`.

Note: `v7dot7Analysis/` and `report_v3.3_report/` at the top level are empty leftovers that could not be removed automatically. Ignore or delete them.

---

## 8. Coach packets (`06_Handoff_and_Tests/packets/`)

A packet is a self-contained folder for a fresh AI coach: open `PROMPT.md` inside it. Each holds exactly 30 unique analyzed matches for one player. No match appears in more than one packet. The number of Teaching Moments per report is decided by the evidence — there is no cap or minimum.

| Packet | Player | Kind | Matches | Notes |
|---|---|---|---|---|
| `P_pug_CanadianIQ_1` | CanadianIQ | pug | 30 | Earliest 30 of his 69 available pugs |
| `P_pug_CanadianIQ_2` | CanadianIQ | pug | 30 | Next 30 |
| `P_pug_MIMY` | MIMY | pug | 30 | |
| `P_pug_iTrilogyy` | iTrilogyy | pug | 30 | |
| `P_pug_shakestx` | shakestx | pug | 30 | |
| `P_pro_ZywOo` | ZywOo | pro | 30 | Austin Major 2025 maps |
| `P_pro_karrigan` | karrigan | pro | 30 | Austin Major 2025 maps |
| `P_pro_xertioN` | xertioN | pro | 30 | Austin Major 2025 maps |

`packets/README.md` has a full table with maps, rounds and finding counts. `_work/` holds build inputs (tarballs, assignment); a coach ignores it.

Pro packets lack some event streams (flash blinds, footsteps, reloads). The coach prompt says these are unknown, not zero.

---

## 9. Root folder path and the `CS2DI_ROOT` environment variable

**Current root:** `C:\Users\dawso\Developer\CS2ReportBuilder\demoparser`

The report-builder code (`cs2-demo-intelligence` repo) stores this as its default in `src/cs2di/config.py`. If you ever move the folder again, either:
- Update `DEFAULT_ROOT` in `config.py` and push, **or**
- Set the environment variable `CS2DI_ROOT` to the new path before running any script — this overrides the code default without needing a code change.

Example (Windows PowerShell, one session):
```powershell
$env:CS2DI_ROOT = "D:\NewLocation\demoparser"
python -m cs2di.cli report ...
```
