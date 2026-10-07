# Player knowledge rebuild — 2026-10-07

The [knowledge base](../coach/player_persona/PLAYER_KNOWLEDGE_BASE.md) is now
version 0.3: a fuller synthesis with situational explanations and source links.
The [setup prompt](../coach/player_persona/PLAYER_SETUP_PROMPT.md) remains separate
and assigns no skill level, personal history, strengths or weaknesses. Both files
are copied to Downloads for handoff. They are not added to coach-generation packets.

## Available material and audit

Counts below come from the actual local manifest, bundle headers, saved answers
and pilot file, rather than the older README's pre-date-filter totals.

| Material | Observed count |
|---|---:|
| Original manifest | 2,988 sources |
| Retained bundle entries and matching source headers | 1,089 |
| Retained words recorded in bundle index | 5,815,010 |
| Parsed NotebookLM candidate records | 526 across Q1–Q55 |
| Incomplete parsed records | 0 |
| Pilot records | 570 |
| Pilot's inherited labels | 490 supported, 80 trimmed |
| Pilot's inherited era labels | 518 CS2, 50 CS:GO, 2 unclear |
| Exclusions labeled too short | 1,135 |
| Too-short exclusions dated on/after CS2 release | 1,107 |

Quote-location results for the 526 answers:

| Location result | Count | Meaning |
|---|---:|---|
| Unique full normalized match | 272 | Quote text located after punctuation/case/spacing normalization. |
| Unique ellipsis-segment match | 77 | Substantial segments located in one source; omitted material not verified. |
| Ambiguous | 14 | More than one possible source; no unique attribution. |
| Not located by this procedure | 162 | Requires alternate source recovery or correction; not automatically false. |
| Too short to anchor reliably | 1 | Insufficient quotation to locate confidently. |

These results do not verify claim entailment, attribution, chronology or current
game behavior. The parser accepts the colon/pipe and plain-label answer formats,
including multiple claims on one line. Tests check grouped-question boundaries,
missing quotations, ambiguous sources and ellipsis fragments split across sources.
The matcher scopes a declared bundle but does not certify the declared creator or
video title. Restored source links come from the matched source headers and pilot
manifest mapping, with contextual review before use.

## What was reviewed and changed

The agent reviewed surrounding passages for 62 distinct NotebookLM candidates,
12 pilot records and seven excluded shorts: 81 review items associated with
70 distinct source-video URLs. This means selected passages from those sources,
not full review of 70 videos. The review was performed by the same agent writing
the synthesis, not an independent human expert.

The new file contains about 7,849 words, including its source register, compared
with 2,524 in version 0.2. It replaces the starter instead of appending a duplicate
glossary. Coverage now includes information age, coverage handovers, movement and
weapon exceptions, utility conversion, tradeable routes, equipment planning,
defaults, lurk activation, clutches, objective play, statistics, review methods
and examples for nine named maps. Source links distinguish contextual examples
from editorial definitions and connecting explanations.

Examples of corrections/qualifications:

| Candidate | Review decision |
|---|---|
| Q3-002: spray in 90% of fights | Source itself permits long-distance/headshot exceptions. Keep the decision rationale, not a universal percentage. |
| Q6-006: native resolution unsuitable | Restore creator preference, player differences and acknowledged visual-awareness benefit. |
| Q13-Q21-040: identical entry path guarantees a trade | Source says rule of thumb; use reachable firing lines and connected timing without a guarantee. |
| Q22-Q33-067: CT 5v4 rule | Surrounding passage describes T-side action; reject claimed side/lesson. |
| Q39-Q51-016: Mirage B rule | Tunnels/window/double-door context does not establish a Mirage B lesson; exclude that attribution. |
| Q39-Q51-065: Overpass smoke set | Surrounding source places it in a Dust2 cat-execute segment; reject Overpass attribution. |
| Q39-Q51-066: Overpass cave flash | Source introduction explicitly names Ancient cave. Correct attribution and retain teammate-facing caveat. |
| Q39-Q51-083: solo Anubis execute | Source uses another map name and requires teammate drops. Keep shared-stock principle; leave map assignment unresolved. |
| Pilot C328: retained smoke | Supporting phrase recovered at 05:58 rather than inherited 05:56. Preserve the stated post-plant options. |
| Pilot C011: AWP no-scope cannot hit | Context explicitly acknowledges it may hit. Exclude any guarantee. |

The short sample recovered useful explanations of deliberate crouching,
post-plant restraint and banana sequencing. Other shorts rely on visual aim
references, or substantially repeat an existing lesson. No dropped corpus entries
were silently reclassified and no source files or NotebookLM answers were edited.
The sample demonstrates that a minimum-length filter can discard useful material;
it does not establish that all 1,107 recent short exclusions are valuable.

## Retrieval and reproduction

From the repository:

```powershell
& .venv/Scripts/python.exe scripts/audit_player_knowledge.py
```

Use `--source` for another `cs2_profile_build` folder and `--output` for an
alternative audit destination. Defaults write to local
`05_Coach_Knowledge/cs2_profile_build/audit_2026-10-07/`:

- `summary.json`: inventory, question coverage and quote-location counts.
- `answer_claims.jsonl`: all 526 parsed claims, candidate IDs and located source metadata.
- `excluded_short_sources.json`: length-filter exclusions for targeted recovery.

Local `review_cards_01.json` through `review_cards_05.json`,
`pilot_review_sample.json` and `short_review_sample.json` preserve inspected
passages. Those contextual review artifacts were assembled during this pass;
the inventory command does not regenerate the agent's review decisions.
[Source review ledger](player_knowledge_sources.json) records candidate IDs,
source metadata, context hashes, synthesis notes and knowledge-base source aliases.
Raw transcript text and local review excerpts stay outside Git.

The knowledge file uses paraphrases rather than reproducing long transcript
passages. Its source register is self-contained for an AI receiving only the two
handoff files. A user can attach the knowledge file, then paste the setup prompt
in a fresh conversation. The persona waits for the next task.

## Verification

The audit/parser and navigation suites passed 10 tests. Ruff and whitespace
checks passed. All 66 internal source references resolve; the ledger has 81
unique review IDs with the stated 62/12/7 split. The two Downloads handoff
files match their repository copies, and the setup prompt is unchanged. These
checks establish artifact consistency, not factual or behavioral validation.

## Evidence boundaries and remaining work

This pass inventories all saved questions but reviews selected supporting
contexts. It does not validate every candidate, establish complete corpus recall,
or claim exhaustive map playbooks. Foundations retained from the earlier persona
and editorial connective reasoning are not individually source-audited.

Detailed prices, awards, damage thresholds, movement/audio tricks, exact timings,
visual lineups and dated professional records are not promoted to current facts.
Valve's [May 2024 release notes](https://store.steampowered.com/news/posts/?appids=730&enddate=1719429748&feed=steam_community_announcements)
confirm a historical incendiary spread/duration change, illustrating why version
context is needed; they do not establish current 2026 numbers.

Useful next source work is targeted: recover unresolved passages where a topic
needs depth, inspect the visual reference for a proposed lineup, and independently
verify a hard fact before adding it. Reading or uploading every transcript for
every feedback task would duplicate cost without ensuring coverage.

The two-file persona has not yet undergone behavioral calibration with Dawson.
Source traceability and plausible explanations do not prove useful simulated
feedback or representative human behavior. The independent-judgment prompt
reduces neither of those questions to a guaranteed outcome.
