# CS2 Demo Intelligence

Turns Counter-Strike 2 demos into trustworthy, auditable evidence, then into a
player-facing **Player Study** written by an AI coach and rendered by
product-owned code.

```
demo (.dem) -> extractor (v7.8, schema 3.8) -> analyzed_<batch>/   [Evidence Package]
            -> viewer-tracks sidecar (8 Hz view angle, grenade paths)  [additive]
            -> integrity gate     (cs2di gate)         [fail closed]
            -> digest builder     (cs2di digest)       [software computes every number]
            -> analyst            (cs2di analyse)      [findings with verdicts, replay examples]
            -> AI coach           (fresh, context-free; runs from a packet)  [writes a content-only plan]
            -> report builder     (cs2di report)       [validates plan, renders modules, owns all CSS]
            -> one HTML file: Player Study tab + Analyst Desk tab
```

## Status and where to start
**AI agents and new contributors: read `CLAUDE.md`, then `agent/STATE.md`.** They hold the current status, the task router and the rules of engagement.
Which document is the truth for which fact: `agent/TRUTH_MAP.md`. Design: Design v5 (a Claude Doc, pointed to by `docs/DECISIONS.md` and the Claude Project).
Owner rulings and how to read the history: `docs/OWNER_RULINGS.md`, `docs/HOW_TO_READ_THE_HISTORY.md`. Data traps (each a regression test): `docs/KNOWN_PITFALLS.md`.

## Layout
For AI file discovery, use [00_INDEX.md](00_INDEX.md) and the relevant folder map.
[Navigation maintenance](docs/NAVIGATION.md) explains the searchable catalog,
document chronology, and CI freshness check. The local data tree has separate
maps; demo/analysis data and its catalog remain off GitHub.

| Path | Purpose |
|---|---|
| `CLAUDE.md`, `agent/` | Start-here file, task router, role hats, preference/regression/state logs, source-of-truth map |
| `src/cs2di/` | Product code: evidence gate, `digest.py`, `analyst.py`, `report/` (modules, theme, plan validator, builder) |
| `scripts/` | `build_packet.py` (coach packets), `moment_facts.py` (facts about example rounds) |
| `coach/handoff/` | The current coach prompt, rules and module guide (packets are built from these) |
| `coach/prompts/` | Legacy prompts (`*_LEGACY`): inputs to rewrite, not authority |
| `examples/` | Coach plans (content only) for other players, used as format examples |
| `tests/` | pytest suite; synthetic fixtures, no demo data needed |
| `extractor/` | `extract_demos_v7dot8.py` (current), `extract_demos_v7dot7.py` (superseded), viewer-tracks sidecar; see `extractor/README.md` |
| `reference/` | Frozen snapshots (corpus manifest, capability report). "_current" in their names means "as of Stage 5", not "up to date" |
| `research/stage3_legacy/` | M3-M5 evidence-plane code. Reference only |
| `docs/history/` | Design docs and chat tails. Context, never instructions |

## Setup
```
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -e ".[dev]"
set CS2DI_ROOT=C:\Users\dawso\Developer\CS2ReportBuilder\demoparser   # folder holding 01_Demos\ and 02_Analysis\ (this is also the default in config.py)
cs2di gate mimy
cs2di report mimy --steamid 76561199066695873 --plan examples\mimy\coach_plan.json --out out\MIMY_report.html
pytest
```
Demos and analysis output are never committed (see `.gitignore`, ADR-002).
