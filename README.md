# CS2 Demo Intelligence

Turns Counter-Strike 2 demos into trustworthy, auditable evidence, then into a
player-facing **Player Study** written by an AI coach and rendered by
product-owned code.

```
demo (.dem) -> extractor (v7.7) -> analyzed_<batch>/   [Evidence Package]
            -> integrity gate     (cs2di gate)         [fail closed]
            -> digest builder     (planned, Phase 1)   [software computes every number]
            -> AI coach           (Phase 2)            [interprets; cannot change numbers]
            -> renderer           (Phase 3)            [fixed shell + registered modules]
            -> Player Study (HTML/JSON)
```

## Status
Phase 0 (foundation). Read `docs/ROADMAP.md` first, then `docs/DECISIONS.md`.
`docs/KNOWN_PITFALLS.md` lists every data trap this project has already been
burned by; each one becomes a regression test.

## Layout
| Path | Purpose |
|---|---|
| `src/cs2di/` | Product code (config, ids, evidence gate; digest/coach/render to come) |
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
pytest
```
Demos and analysis output are never committed (see `.gitignore`, ADR-002).
