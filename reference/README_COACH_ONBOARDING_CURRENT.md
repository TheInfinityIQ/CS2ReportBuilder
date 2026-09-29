# CS2 Coach Onboarding Pack — Current

Use these files in this order before coaching:

1. `cs2_coach_prompt_v2_schema3.md`
   - Primary system/coaching instructions for schema 3.6+.
2. `corpus_manifest_current.json`
   - Canonical identities, source cohorts, cohort sizes, known mislabel, and invalid segment.
3. `logical_map_manifest_current.csv`
   - 207 logical maps: 100 FACEIT + 103 Cologne + 4 Premier. Prevents double-counting HLTV `p1/p2`.
4. `data_capability_report_current.md`
   - Measured source-specific capabilities and limitations, including the four schema-3.7 Premier demos.
5. `extract_demos_v7dot7.py`
   - Current extractor reference; includes the terminal SourceTV reset fix and per-demo capability metadata.
6. The parsed demo folders, demoparser repository, creator transcripts, and historical AI-development conversations.

## Current corpus

- 218 demo folders.
- 217 coaching-valid; 1 quarantined Cologne segment.
- 4,441 usable extracted rounds.
- 207 logical maps.
- FACEIT: 100 logical maps / 2,105 rounds.
- Cologne SourceTV: 103 logical maps / 2,251 currently usable extracted rounds.
- Valve Premier: 4 CanadianIQ maps / 85 rounds; all four schema-3.7 outputs are canonical and coaching-valid.

## Current corpus corrections

- `donk666_game11` is not a donk demo. Its actual roster contains CanadianIQ and no donk; classify it as CanadianIQ FACEIT.
- The earlier onboarding documentation said no Premier data was present. That statement is superseded: `analyzed_premier_batch1` contains four CanadianIQ Valve Premier demos.
- `furia-vs-mouz-m1-nuke-p1__INVALID_v75` remains excluded in the supplied Cologne output. It exposed a terminal SourceTV synthetic round-1 reset bug fixed in v7.7. Reparse only that segment when convenient.
- HLTV `p1/p2` files are map segments, not separate matches.

## Evidence / authority hierarchy

1. Current coaching prompt.
2. Actual parsed data and per-demo integrity reports.
3. Current extractor source and demoparser source.
4. `corpus_manifest_current.json`, `logical_map_manifest_current.csv`, and `data_capability_report_current.md`.
5. Creator transcripts as coaching knowledge/framework.
6. Historical AI chats as development/provenance reference only.

Historical conversations contain superseded hypotheses and old parser behavior. They may explain provenance or suggest questions, but they must never override current data, integrity reports, parser behavior, or current instructions.

## Reference hierarchy for coaching

1. CanadianIQ vs CanadianIQ internal contrasts.
2. CanadianIQ FACEIT vs CanadianIQ Premier as a source/environment contrast.
3. donk/mezii FACEIT for individual/pug reference.
4. Cologne population for structured professional-team context.
5. donk/mezii FACEIT ↔ tournament same-SteamID contrast for identifying environment-dependent behavior.

## Deep mode

Do not deep-parse the full corpus. Use batch mode for pattern detection, then deep-parse only representative demos/rounds when input-level evidence is required.
