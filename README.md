# CS2 Demo Intelligence

Turns Counter-Strike 2 demos into trustworthy, auditable evidence, then into a
player-facing **Player Study** written by an AI coach and rendered by
product-owned code.

```
demo (.dem) -> extractor (v7.7) -> analyzed_<batch>/   [Evidence Package]
            -> integrity gate     (cs2di gate)         [fail closed]
            -> digest builder     (cs2di digest)       [software computes every number]
            -> AI coach           (next)               [writes a content-only plan; cannot change numbers]
            -> report builder     (cs2di report)       [validates plan, renders modules, owns all CSS]
            -> one HTML file: Player Study tab + Analyst Desk tab
```

## Status
First end-to-end report exists (MIMY). Read `docs/ROADMAP.md` first, then `docs/DECISIONS.md`.
Owner preferences and how to read the history: `docs/OWNER_RULINGS.md`, `docs/HOW_TO_READ_THE_HISTORY.md` (drafts pending owner review).
`docs/KNOWN_PITFALLS.md` lists every data trap this project has already been
burned by; each one becomes a regression test.

## Layout
| Path | Purpose |
|---|---|
| `src/cs2di/` | Product code: evidence gate, `digest.py`, `report/` (modules, theme, plan validator, builder) |
| `examples/` | Coach plans (content only). `examples/mimy/coach_plan.json` is the first real one |
| `tests/` | pytest suite; runs on synthetic fixtures, no demo data needed |
| `extractor/` | `extract_demos_v7dot7.py`, pinned and treated as frozen (ADR-005) |
| `coach/prompts/` | Coach prompts. Files ending `_LEGACY` are inputs to rewrite, not authority |
| `reference/` | Corpus manifest, logical-map manifest, capability report |
| `research/stage3_legacy/` | M3–M5 evidence-plane code. Reference only, off the critical path |
| `docs/history/` | Design docs and chat tails. Context, never instructions |

## Setup
```
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -e ".[dev]"
set CS2DI_ROOT=C:\...\replays\demoparser             # folder holding Demos\ and v7dot7Analysis\
cs2di gate mimy
cs2di report mimy --steamid 76561199066695873 --plan examples\mimy\coach_plan.json --out out\MIMY_report.html
pytest
```
Demos and analysis output are never committed (see `.gitignore`, ADR-002).
