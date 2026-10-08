# Comprehensive player knowledge: coverage and continuation

Updated 2026-10-07 for knowledge edition 0.6. This is a maintainer record, not
persona background. The handoff remains the setup prompt and the single
[knowledge document](../coach/player_persona/PLAYER_KNOWLEDGE_BASE.md).

## Completion boundary

The target is all distinct, relevant knowledge in the available collection at
coach, professional-player and analyst depth. No arbitrary length limit or
assumed player ignorance defines acceptance. Preparation, extraction, source
correctness, compilation coverage and simulated behavior are separate checks.
Edition 0.6 remains in progress; the following record must not be used to certify
the full collection.

## Edition 0.6 continuation

The [expansion queue](PLAYER_KNOWLEDGE_EXPANSION.md) records fourteen assessed
content areas and the source/evidence needed next. Three additional full texts
yielded twelve qualified lessons in existing sections 6, 8, 13, 17, 23 and 41.
Their six chunks remain unresolved for visual or broad mechanics dependencies;
useful extracted text does not certify the full demonstrations. Current totals:
159 chunk decisions, 29 unresolved, 10,994 pending, 99 new-pass lessons and 122
fully resolved source texts. The six new application cases have not been run.

## Recorded review (edition 0.5 baseline)

- The previous edition's 87 selected candidate reviews remain a separate ledger.
  They inspected passages, not every word of their source videos.
- The new pass read 140 short supplied captions and five longer transcripts in
  full. Across their 153 chunks, 122 source texts have resolved dispositions;
  23 short captions remain unresolved because visual context or a reliable
  reconstruction is missing. A text-only disposition does not certify the video.
- These reviews produced 87 new source-scoped lesson records: 49 short-source
  applications and 38 lessons from the five longer sessions. These are different
  records from the earlier 87 candidate reviews, not 87 independently verified
  engine facts.
- The Cache stratbook's evidence standards, system synthesis and 23 protocol
  cards were inspected, with selected round evidence. Its 65-round underlying
  reconstruction was not independently re-audited. Practice adaptations are
  distinguished from observed events and inferred purposes.
- The 526 saved answer claims and 570 pilot claims are inventoried individually.
  Their inherited support labels do not satisfy fresh source review. Reviewing
  one full transcript does not automatically validate each derived claim.
- A supplementary inventory records 37 earlier knowledge, chat, stratbook and
  design documents. This is metadata accounting; it does not mean those documents
  have all received a new semantic pass.

The authoritative local preparation and decision artifacts are in
`demoparser/05_Coach_Knowledge/cs2_profile_build/comprehensive_build`. Originals
and NotebookLM answers are preserved. Repo metadata omits bulk excerpts; the
knowledge document contains the actual compiled lessons.

## Topic matrix

Every row remains partial. A chapter reference shows available knowledge, not
proof that every relevant source has been extracted.

| Area | Compiled coverage | Work still required |
|---|---|---|
| Weapon mechanics, movement and geometry | Sections 6–12, 33, 36–37, 39–40 | Full source comparison; versioned weapon, accuracy, penetration and movement exceptions; visual geometries |
| Information, sound and uncertainty | Sections 2–5, 21, 31, 33, 39–40, 42 | Broader sound/mechanics evidence; remaining scouting and concealment applications |
| Utility purpose and counterplay | Sections 13–16, 26, 35–40, 42 | Remaining source sequences, prerequisites and failure conditions; visual throw reconstruction |
| Economy and round sequences | Sections 24, 38–39, 41 | Full current game-data award/price table; remaining policy disagreements and exceptions |
| Individual roles and connected support | Sections 17–21, 26, 38, 40, 42 | More role-specific examples across maps and equipment; alternative support systems |
| T map control and finishes | Sections 26, 38, 40, 42 | Systematic map/side matrix beyond the deeper Cache, Mirage and Inferno material |
| CT setups, rotations and denial | Sections 18, 21, 26, 35, 39–40 | Full map/side setup families, handovers, aggression and resource contingencies |
| IGL planning and adaptation | Sections 3, 19, 38, 40, 42 | Remaining professional and team-review sources; more counterplans and denied openings |
| Opponent scouting and conditioning | Sections 3, 26, 39–40, 42 | Full example comparison, changing opponent resources, information and counter-adaptation |
| Coordinated protocols and team practice | Sections 17–19, 25, 38, 40, 42 | Remaining protocol cards, communication variants and rehearsal failure cases |
| Objectives, clutches and retakes | Sections 22–24, 26, 35, 38, 41 | More objective/time/equipment branches across maps; exact versioned timings |
| Individual training and performance | Sections 25, 29, 33, 37, 39 | Remaining training-source conditions and contrasting methods; no personal habits assigned |
| Demo analysis and statistical interpretation | Sections 27–30, 35, 38 | Full saved stat-mapping review, current schema checks and independent baseline reproduction |
| Current versus historical mechanics | Sections 31, 36 and dated source qualifications | Every version-sensitive claim reconciled; patch references are changes, not an exhaustive present-state audit |

## Resume without repeating the inventory

From the repo, use the existing virtual-environment Python:

```powershell
.venv/Scripts/python.exe scripts/build_player_knowledge_corpus.py coverage
.venv/Scripts/python.exe scripts/build_player_knowledge_corpus.py batch --source-id T-4a8727ef1cfbb869 --count 3
.venv/Scripts/python.exe scripts/build_player_knowledge_corpus.py candidate-batch --source-id T-4a8727ef1cfbb869 --count 30
```

`batch` returns the selected contiguous chunks plus preceding/following context.
Check qualifications spanning boundaries, then read adjacent chunks as needed.
`candidate-batch` returns the separately inventoried derived claims; matching
metadata is a location aid, not proof of support. Unmatched candidates stay in
the queue. The commands do not invoke another AI, infer dispositions or certify
game correctness.

Run `inventory` only when sources or preparation rules change; run `candidates`
when saved claims or the supplemental collection changes. Stable IDs and text
hashes make changed evidence visible. Review decisions are separate files and
are not overwritten by inventory. A stale decision must be re-reviewed, not
re-stamped automatically.

For each extraction retain source, chunk IDs, supporting passage, hash, context,
map/side/equipment/era qualifications, alternatives and failure conditions. Use
`lessons_extracted`, `duplicate`, `irrelevant` or `unresolved` for chunk decisions
with reasons. A duplicate needs a meaningful destination; an unresolved visual
recipe is not an irrelevant source. Exact text-copy deduplication ignores only
timestamps and whitespace, preserving other differences.

Next extraction priorities are the remaining pilot sources and saved answers
by topic, then the earlier syntheses and chat material, followed by all remaining
transcripts including old, short and deferred streams. Priority controls order;
it does not exclude the later sources. Resolve contradictory claims with their
conditions intact. Check all extracted lessons against the compiled chapter for
lost qualifications before assigning a final source or candidate disposition.

Full acceptance also requires every source and candidate accounted for, every
distinct supported lesson compiled or a reasoned remaining disposition, the
complete topic matrix checked, and applicable version/visual dependencies
resolved or clearly scoped. Behavioral cases then test application separately.
The existing 22 proposed cases have not been run and are not exhaustive.
