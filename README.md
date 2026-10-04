# CS2 Demo Intelligence

A CS2 coach: game demos become evidence, then a report that helps a player
understand what to improve. Dawson supplies product direction and evaluates
coaching as a player; engineering choices are supported by evidence.

## Find the relevant starting point

| Question | Source | What it provides |
|---|---|---|
| How should an agent work? | [Working agreement](AGENTS.md) | Collaboration defaults and evidence-based engineering guidance. |
| What exists and what is uncertain? | [Project status](docs/PROJECT_STATUS.md) | Observations, verification evidence, gaps, and current work. |
| How does a demo become a report? | Pipeline below; [extractor guide](extractor/README.md) | Component orientation and extraction details. |
| How are coach packets made? | [Packet builder](scripts/build_packet.py); [runtime templates](coach/handoff/PROMPT.md) | Generated inputs; consult RULES.md and MODULES.md when changing packets. |
| Why did earlier versions make a choice? | [Source-linked history](docs/history/SOURCES.md) | Development sequence, preserved conflicts, and original chat/experiment locations. |
| Where is local data and research? | [Layout snapshot](docs/DATA_FOLDER_LEGEND.snapshot.md) | Locations in the sibling demoparser tree; dated claims need checking. |
| Where is an unknown file? | Targeted search; [optional navigation](docs/NAVIGATION.md) | Maps/catalog when paths are unclear. No mandatory index detour. |

## Current implementation

```text
demo -> extractor (v7.8, schema 3.8) -> extracted evidence
     -> viewer-tracks sidecar -> integrity gate -> digest -> analyst findings
     -> AI coach content plan -> plan validator -> HTML report
```

Software currently calculates metrics and renders report modules. The coach
supplies a content plan. The report has Player Study and Analyst Desk tabs.
These describe implementation; historical choices are not automatically renewed
requirements. Saved report builds still need factual and usefulness review.

| Location | Purpose |
|---|---|
| src/cs2di/ | Evidence loading, digest, analysis, repair, CLI, and report code. |
| extractor/ | Demo extraction and viewer-track sidecar. |
| coach/handoff/ | Runtime prompt, rules, and plan/module reference embedded in packets. |
| scripts/ | Packet generation, replay evidence helpers, and optional discovery tooling. |
| tests/ | Synthetic checks; the test suite does not require demo downloads. |
| docs/history/ | Prior designs and instructions, retained as historical evidence. |
| reference/ and research/ | Frozen snapshots and older implementations; CURRENT is not proof of freshness. |

## Setup and checks

Python 3.11 or newer is required. From this checkout in PowerShell:

```powershell
python -m venv .venv
& .venv/Scripts/python.exe -m pip install -e '.[dev]'
& .venv/Scripts/cs2di.exe --help
& .venv/Scripts/python.exe -m pytest -q
```

Extraction additionally needs the pinned parser dependency in the `parse` extra;
see the extractor guide before running it. Setup creates a local environment;
do not reinstall dependencies for every task.

Data defaults to `C:\Users\dawso\Developer\CS2ReportBuilder\demoparser`.
Override it before a command when working elsewhere:

```powershell
$env:CS2DI_ROOT = 'C:\path\to\demoparser'
& .venv/Scripts/cs2di.exe gate mimy
```

The sibling demoparser folder holds local demos, analysis, knowledge material,
packets, and reports. Extraction-linked demo/analysis paths remain unchanged.
GitHub holds software and documentation; local demo and analysis data stay local.
