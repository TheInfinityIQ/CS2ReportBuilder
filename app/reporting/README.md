# Coaching report builder

This module owns the HTML coaching report and its reproducible build process. It reads canonical Toolbox analysis without downloading demos, parsing demos, moving analysis, starting CS2 or making AI/network calls. Opening the delivered report requires only a current browser.

## Build an evidence snapshot

Refresh the existing Toolbox report catalog through **Reports → Refresh analyzed games** if source revisions have changed. The existing `app/desktop/reports.py catalog` command is the same supported catalog producer. Do not introduce another identity or download index.

From the repository root, with the existing Python environment:

```powershell
python app/reporting/analyze.py --steamid 76561198062530225 --limit 50 --output reports/CanadianIQ/analysis.json
```

Selection uses the catalog's Steam ID, demo SHA and canonical game ID. It takes at most 50 unique, complete, valid and coaching-valid games with a parsed death stream. Saved provider dates take precedence over explicit canonical filename dates. Filesystem modification time is never used. Within-day chronology is unavailable when only a day is known; the stable game-ID/hash tie-break is disclosed. Incomplete/split games are excluded rather than stitched.

The snapshot retains selected games, exclusion reasons, per-round observations, source capabilities, integrity warnings and input hashes. A round requires a complete observation, exactly five unique players per side, a reconciled side/result and a usable death sequence. Simultaneous first deaths are unknown for opening classification. Unknown streams and missing mandatory fields do not become zeros. Hashes before and after each game prevent accepting changed inputs during that read.

## Review the coaching before building

`coaching.json` is a persisted editorial input, not an automated diagnosis. Write it after reviewing candidate situations and alternatives. Bind every situation to an eligible `round_id`; include a meaningful contrast, coaching question, replacement decision and specific practice cue. Preserve material uncertainty. Do not fill the report with unsupported themes.

The shipped CanadianIQ example has one practice focus: plan for a second threat before the opening commitment, then reassess after a kill when time allows. The counts are a review signal, not proof of overaggression or avoidable deaths. Its four selected rounds include a repeated Mirage sequence with opposite round outcomes and a Palace survival contrast with a weaker opponent buy.

```powershell
python app/reporting/build.py --analysis reports/CanadianIQ/analysis.json --coaching reports/CanadianIQ/coaching.json --output reports/CanadianIQ/Coaching-Report.html
```

Use `--replace` deliberately for an existing generated output. The builder verifies frozen input hashes before and after bundling, checks the player and selected round IDs, protects analysis paths, stages HTML atomically and rejects a concurrently changed destination. It writes a companion `.build.json` with the report SHA, snapshot digest and replay input hashes. Subsequent reads of the report do not repeat analysis or editorial generation.

## Reading-first presentation

The default report now reads as player profile → insights with the evidenced positive first → written round examples → improvement priorities → source context. All four case narratives and player-count sequences are rendered directly into HTML. No tab, replay or JavaScript is required to understand the coaching. Replay and notebook tools remain in an optional disclosure, with their existing state keys and evidence anchors preserved.

The profile is scoped to opening fights in the reviewed sample. First kills creating 5v4 are an observed contribution; subsequent survival is context, not a skill rating or second strength. No role, rank or fixed player persona is inferred. This distinction was reviewed with the existing Knowledge Expert.

`presentation.css` refreshes typography, identity treatment, hierarchy and colours over the existing report styles and containers. The existing offline builder, data selection and replay provider are retained. [Research and decisions](RESEARCH_PRESENTATION.md) records the literature, applicability limits and unperformed player-comprehension study.

Run `node app/reporting/check_presentation.cjs reports/CanadianIQ/Coaching-Report.html` for the reading contract: disabled-JavaScript visibility, positive-first order, print narrative, responsive widths and core text-colour contrast. It complements the existing replay and notebook checks; it is not a full accessibility or learning-effectiveness certification.

## Player review notebook

Each teaching situation has optional notes for information available during play, the plan for the next threat and what to keep or change. Notes are keyed to the frozen evidence snapshot and round ID, saved locally when browser storage is available, and kept in memory when saving fails. Recollections remain separate from recorded evidence and coaching conclusions.

**Export all review notes** prepares JSON with the player's string Steam ID, snapshot digest, per-round demo hash/source/round/tick anchors, notes and three-match checklist. The report also exposes selectable export text when a browser blocks the download. Export again after editing; an older copy does not update. Browser storage is not a portable backup, and notes are not embedded back into the HTML file. No notes are sent anywhere automatically.

The focused `node app/reporting/check_notebook.cjs reports/CanadianIQ/Coaching-Report.html` fixture checks round isolation, reload persistence, evidence-bound export text, unavailable/corrupt storage, literal-text safety, themes and tablet layout. The November 9 environment cancelled JSON downloads; the November 12 run completed the download. The copyable export remains available for restricted browsers. Consult the current fixture result rather than treating an environment restriction as a permanent product limitation.

## Renderer integration

Reuse `app/desktop/reports.py`'s portable bundler and `viewer2d/replay.py`'s round packet builder. Embed only the reviewed teaching rounds. The generated HTML contains its styles, script, images and compressed replay packets; no server, original demo, Steam or game is required. It is about 1.9 MB for the shipped report.

The adapter changes only the in-memory export: available rounds are narrowed to the selected evidence, batch heatmaps/native playback are hidden, a parent/frame navigation bridge seeks five seconds before the opening event, closing pauses playback, and rendering skips zero-sized canvases while the modal is hidden. Shared Tool Developer files remain untouched. If the upstream viewer boot/render/template contract changes, fail with an adapter error rather than silently dropping evidence.

## Analyst Desk and full previous-session archive

The Analyst Desk is an optional evidence view after the player narrative. Its figures use the same `opening_summary` passed to the renderer; `desk.records` supplies definitions, values and denominators to both the rendered table and the report's machine-readable payload. It does not generate coaching or promote metrics into profiles.

Create a complete private archive after building the report:

```powershell
python app/reporting/session_bundle.py create --analysis reports/CanadianIQ/analysis.json --coaching reports/CanadianIQ/coaching.json --report reports/CanadianIQ/Coaching-Report.html --output reports/CanadianIQ/CanadianIQ-Session-01.zip
python app/reporting/session_bundle.py validate reports/CanadianIQ/CanadianIQ-Session-01.zip
```

The archive freezes every file in each selected analysis directory, including unused and excluded observations. It also contains the report, build record, evidence snapshot, delivered coaching, measure definitions, session identity and manifest. Browser notes remain a separate optional user export; they are not silently read from browser storage. Original demos and global credentials/job settings are outside scope.

Source ownership follows maintenance lock → sorted per-analysis locks. It rejects linked/reparse sources, checks full membership and content before accepting the snapshot, stages outside the analysis library, releases locks before compression, verifies the archive and publishes atomically. These protections cover participating writers and detected mutations; they do not claim a universal filesystem freeze against unrelated tools. The Tool Developer's writer audit governs any broader integration claim.

Read-only validation checks paths, membership, byte lengths, hashes, selected-directory revisions and player identity without extracting or executing supplied content. It is not yet a historical-session comparison engine. Imports do not overwrite canonical analysis. Existing output requires deliberate `--replace`; previously delivered sessions should normally retain their original identity and bytes.

`test_session_bundle.py` covers full unused-file preservation, source-content and membership mutation, unsafe/unlisted members and preservation of existing archives. No new extraction or parser is involved.

`coaching_data_contract.json` records the Knowledge Expert's three situation-first questions, opportunity populations, unknown/exclusion rules and claim ceilings. Data candidates require contextual review before becoming player advice or identity labels.

## Verification

### Verified Tool Developer handoff intake

`intake.py` connects a Toolbox facts handoff to an already validated session archive. It checks player/selection identity, every selected source file's revision, compressed artifact hashes, row counts, unique situation IDs and round/flash source identities before producing a review index. It reads archive metadata; archive content validation remains `session_bundle.py validate`'s responsibility. It does not generate player-facing coaching.

```powershell
python app/reporting/intake.py --readiness reports/team/CanadianIQ50_data_handoff_2026-11-13/readiness.json --session reports/CanadianIQ/CanadianIQ-Session-01.zip --output reports/CanadianIQ/coaching-review-index.json
```

The index retains the complete candidate populations, including flash detonations outside eligible rounds marked ineligible. Eligible episodes start as `eligible_interpretation_unresolved`. Review must establish what a player could notice, the supported choice, a feasible alternative and comparable positive/disconfirming situations before editing `coaching.json`. Outcome alone does not settle decision quality. The original session archive remains the delivered session; these new candidates are a separate working artifact.

Flash links verify the same affected opponent and retain `(game, source file, CSV data row)` contact references for deduplication across flashes. Damage and death rows are separate recorded events, not separate fights or causal assists. Same-tick order uncertainty remains explicit. The Tool Developer's writer audit is in the handoff folder's `README.md`: direct smoke decoding and unwrapped entity helper calls are outside the lock contract, so full-source checks do not establish universal writer exclusion.

Build a small exploratory comparison queue from that verified index:

```powershell
python app/reporting/review_queue.py --index reports/CanadianIQ/coaching-review-index.json --output reports/CanadianIQ/coaching-review-queue.json
```

This also writes readable `.md` and static `.html` companions. The HTML worksheet shows the selected recorded death/objective sequences, elapsed time from episode entry, canonical anchors and context limits without requiring interaction. Within-tick order stays unresolved; elapsed time is not remaining game clock. Raw site IDs are matched only within the same game; last-alive comparisons additionally match starting opponent count and bomb phase. Selection follows situation groups and source order without filtering wins, losses, deaths or contact. The queue is not a denominator or a representative sample. Blank review fields capture available information, feasible alternatives, supporting and disconfirming evidence, practice and observable progress before coaching edits. The queue fingerprints the exact review index. `test_intake.py` checks shared event identity/deduplication and sequence timing; `test_review_queue.py` checks game/site and bomb-phase boundaries, outcome-independent selection and preservation of unresolved coaching.

`KNOWLEDGE_AGGREGATE_REVIEW.md` preserves the expert's actual aggregate review. Contract 1.1 records that candidate discovery is accepted while player-specific diagnosis remains unapproved; follow-up progress requires observed behavior in fresh comparable opportunities, not an outcome rate alone.

### Cross-map publication policy (current)

Dawson requires the main narrative to teach recurring themes across maps rather than individual rounds. `KNOWLEDGE_THEME_REVIEW.md` records the expert's agreement and supersedes the earlier promotion of narrow illustrations. The main narrative now contains no specific round references. The four original reading examples, all eight new dispositions, replay controls and notes are inside the optional Analyst Desk. Post-plant/last-alive illustrations are retained as evidence only, not personalized improvement priorities.

`themes.py` derives per-map opening observations and distinct game/map recurrence from the frozen eligible records. The same computed object supplies narrative counts, payload and Analyst Desk table. The current evidence supports 94 opening kills in 41 games/seven maps and 25 own deaths within ten seconds across 19 games/six maps. Twelve are within two seconds across five maps. These establish recorded contribution/transition recurrence, not a shared cause, avoidable death or superiority relative to peers. Uneven map samples remain explicit.

The positive is a recorded contribution; next-exposure planning remains a practice hypothesis. A personalized diagnosis needs comparable mechanisms across maps, available information, feasible alternatives and disconfirming examples. Generic objective resetting is not a separate diagnosed deficit. There is no arbitrary case-count threshold that can substitute for that review.

The lesson renderer now rejects main-narrative situation cards without `publication_scope: cross_map_theme` or references from different maps. That is a minimum scope guard, not a statistical or causal certification. Browser checks verify a round-free main reading path, collapsed evidence and preserved replay/notes behavior. Discovery and prior archives remain unchanged; Revision 03 records this editorial correction over the same 50 games.

### Earlier situation-publication increment (superseded scope)

`KNOWLEDGE_SEQUENCE_REVIEW.md` records the expert's subsequent review of the eight actual sequences. `coaching.json:situation_insights` now supplies two bounded lessons: concrete Inferno post-plant contributions and a conditional objective-aware check illustrated by Dust2 last-alive rounds. `situation_insights.py` renders reviewed copy inside the existing Insights section and embeds the same canonical round objects in the report payload. It rejects missing editorial approval, unknown rounds and anchors outside round bounds. This is a lineage gate, not an automatic validator of tactical prose.

Positive contributions precede development content. Existing opening practice and replay cases remain primary. All eight editorial dispositions appear in the Analyst Desk and `coaching.json:situation_review`; no fixed player role, save verdict or causal positioning diagnosis was added. `reports/CanadianIQ/eight-sequence-review-outcomes.json` links publication decisions to the coaching fingerprint. The original discovery worksheet remains exploratory rather than being retroactively labeled good/bad.

Session archives copy the delivered coaching's `previous_session_ids` and `session_relationship`. The second archive is an editorial revision of the same 50 games, with zero fresh observations; it must not be treated as evidence of progress. Earlier archives are preserved. Three situation-rendering fixtures, six archive fixtures and the report/presentation browser checks cover the publication increment.

```powershell
python -m unittest discover -s app/reporting -p test_reporting.py
node app/reporting/check_report.cjs reports/CanadianIQ/Coaching-Report.html
```

The browser fixture uses the already installed Playwright and Chrome, follows the project's application-owned UI testing rule, and makes no Computer Use calls. `PLAYWRIGHT_MODULE` can point to an existing Playwright installation. It verifies exact source/round/tick navigation, populated tracks for all ten players, all four replay examples, pause-on-close, dark/light themes, keyboard tabs, source search, checklist persistence, responsive widths and absence of network requests or browser errors. Screenshots and compact results go beside the report under `verification/`.

The shipped sample was also independently recounted from raw death CSVs and checked by a read-only coaching reviewer. Browser checks do not establish tactical correctness. Revisit the diagnosis when new demos, player explanations or voice context supply better evidence.

## Metric definitions, version 1.0

| Measure | Formula and denominator | Interpretation boundary |
|---|---|---|
| Opening kill | First enemy-on-enemy death credited to the target in an eligible round; same-tick first death ambiguity excluded | Server event order, not first contact or first information |
| Kill-to-death interval | `(own death tick − own opening kill tick) / match tickrate`, among own opening-kill rounds | Not reaction time; 2s/10s are disclosed review windows, not quality thresholds |
| Survived opening-kill round | No own recorded death before round end, among eligible opening-kill rounds | Does not establish good decision-making |
| Alive count | Start from per-round canonical 5v5 roster; subtract all recorded deaths in tick order | Same-tick intermediate states ambiguous; proximity does not establish cover/trade |

No professional benchmark, skill score, visibility/perception diagnosis, guaranteed trade metric or causal improvement estimate is produced.
