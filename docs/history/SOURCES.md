# Source-linked project history

Reviewed 2026-10-04. This guide consolidates retrieval context, not the original
evidence. Current implementation is summarized in [project status](../PROJECT_STATUS.md).
Local paths below are relative to the sibling demoparser folder; those files are
not distributed with GitHub. Agent statements in chats are historical claims.

## Development sequence and lessons

| Phase | What the sources establish | Where to inspect |
|---|---|---|
| Extractor iterations | Round boundaries, knife rounds, missing event streams and entity semantics repeatedly changed derived statistics. Missing streams cannot establish zero events. | Local ai_chat_history/script_creation_claude.txt and extractor-v5-v7-chatgpt.txt; [earlier audit, section 2](project-records/2026-09-28-chat-audit.md). Current code: [extractor guide](../../extractor/README.md). |
| Stage 3 M11 onward | Earlier chat records describe repeated zero eligible/replicated opening tendencies. That supports the historical gate's refusal to emit a claim, not proof that no useful coaching exists. | Local ai_chat_history/ChatGPT_Stage3End.txt and ChatGPT_Stage4End.txt; 07_Development/stage_steps/Stage3_M11 through Stage3_M113_FACEIT_FLASH/. |
| M121 to V4B3 | A support-oriented lesson was proposed, challenged for confounding, then blocked. V4B3_ai_handoff.json records all three reviewer outcomes as INSUFFICIENT_EVIDENCE and action_status BLOCKED. | 07_Development/stage_steps/Stage3_M121_FIRST_LEARNING_LOOP/, V4B1_CURRICULUM_FALSIFICATION_GUARDRAILS/, V4B2_CONTEXTUAL_CANDIDATE_POOLS/, V4B3_CONTEXT_ENRICHMENT_MULTICHAT/. The abstract concept was not disproved. |
| V4V1 viewer | V4V1_ai_handoff.json keeps action_status BLOCKED and says the viewer cannot override semantic state. A playback check does not authorize the lesson. | 07_Development/stage_steps/V4V1_TEMPORAL_VIEWER2D_FOUNDATION/V4V1_ai_handoff.json. |
| V4.0 to V4.1 | Architecture shifts toward composition plans rendered by software, with eligibility/control-plane proposals. V4.1 explicitly remains a candidate in its document header. | [Design collection](design/README.md); local architecture_review/ includes v4.0 and advisory consultant reviews. |
| Stage 5 | Chat proposes developer/coach separation, a fixed shell and content-only plan. Its earlier two-pass experiment is historical; use actual packet templates for today's process. | Local ai_chat_history/Stage5.txt and ClaudeDemoparserFilesReview.txt; [packet prompt](../../coach/handoff/PROMPT.md) and scripts/build_packet.py. |
| 2026-09-29 coach runs | ClaudeCoachingReportsTest.txt says eight plans/reports/reviews were built, explicitly without wording/data audit. It reports numeric-validator friction, replay selection issues and unclear metric definitions. | Local ai_chat_history/ClaudeCoachingReportsTest.txt and 06_Handoff_and_Tests/test_coaches/*/run_2026-09-29_fresh_subagent/. These reports still need evaluation. |
| Knowledge-profile work | Dawson requests transferable CS2 knowledge without simulated memory gaps. The older experienced-player persona is a different artifact. Chat reports quote checks and token costs; quote existence does not establish entailment or coaching accuracy. | Local ai_chat_history/ClaudeAIKnowledgeBase.txt; cs2_profile_build/ and player_knowledge_base/. |
| 2026-10-03 onward | Development agreement reset; stale accounts archived and discovery made optional. Six-pair index pilot measured characters, not billed tokens, and included an overhead case. | [Cleanup record](../CLEANUP_2026-10-03.md), [broader cleanup](../CLEANUP_2026-10-04.md), [retired system](agent-system/2026-10-03/README.md). |

Prefix local chat/design/profile paths above with `05_Coach_Knowledge/`.
Stage names establish relative milestone order; they do not establish author
dates, acceptance or current product requirements. Explicit dated reviews can be
found in [project records](project-records/README.md).

## Conflicts that must survive summarization

- The old owner-statement draft says no Teaching Moment minimum. The current
  validator rejects an empty moments list and the module guide requires at least
  one. Cleanup records the discrepancy; it does not choose intended behavior.
- Older chats describe no local Git checkout and pending coach runs. The checkout
  and eight saved run directories now exist. Those statements are stale context.
- Earlier plans include more eligibility machinery than the current report
  pipeline. Do not claim the current validator implements all historical gates.
- A numeric allowlist can accept a number used in the wrong context. Formatting
  and schema validity cannot establish a correct coaching interpretation.
- `ClaudeCoach.json` contains a decodable initial JSON value followed by material
  that prevents parsing the whole file as one JSON document. Preserve the export;
  do not silently repair it or treat extraction as a complete semantic review.
- The older chat audit is useful for retrieval but its completion states and
  extracted scratchpad line numbers need checking against surviving originals.

## Current knowledge-build artifacts

The local triage_manifest.csv has 2,988 rows: 1,089 kept and 1,899 dropped.
Drop reasons are 1,135 too short, 489 pre-CS2 date, 268 livestream deferred and
7 non-English/noise. bundles_index.csv has 1,089 source rows. The older README's
1,578 count predates date filtering. These are artifact counts, not quality scores.

Answer files covering Q1 through Q55 exist, including substantive Q39-Q51 and
Q52-Q55 files. They are candidate knowledge, not verified facts. No completeness,
quote-entailment or CS2 correctness audit was performed during this cleanup.
Use local cs2_profile_build/README.md for source locations and verification gaps.

Full chat-by-chat descriptions and old-name aliases are in the local
05_Coach_Knowledge/ai_chat_history/README.md. Consult one relevant transcript;
the entire chat corpus is not startup context.
