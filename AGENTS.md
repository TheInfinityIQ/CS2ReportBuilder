# User preferences

- Defer all Demo Review performance checks and optimization until the other checklist features are implemented. Prioritize replay audio and dynamic map geometry. Retain the prior timing evidence for the later pass.

- After each Demo Review implementation or validation step, update the CS2 Demo Review Feature Checklist workbook in the CS2 Designer workspace with the result and the remaining gap. Leave open items marked X until their acceptance checks pass. In the user update, name every item that changed from X to ✓ and state what check it passed. If no items changed status, say so and describe progress on the open items. Order fixes by dependency and favor lower-effort work that will survive later changes.

- Before designing a new process, review the existing relevant Toolbox modules and workflows. Reuse their player identities, acquisition, naming, indexing, credentials, and job handling wherever they already meet the requirement; explain any necessary new mechanism.

- Ask the user for explicit approval before starting a large data rebuild, bulk re-extraction, migration, or broad data correction. Describe the concrete scope, output location, retention of existing data, and expected resource use first. Do not treat a brief "proceed" during viewer work as approval for a bulk data operation.
- Targeted read-only checks and small viewer fixes can proceed within the requested scope. Explain why any additional runtime or parser is needed before introducing it.
- Do not use the Computer Use skill for UI checks. Use application-owned widget/state/layout tests and bounded native-capture test fixtures instead.
- CS2 rendering must work without a manually opened game. Toolbox may start/manage a private CS2 engine process, but keep all integration code outside CS2, preserve normal game files/preferences, and never force changes to the user's resolution or display mode.
- The new standalone renderer (`app/standalone3d/`) must NEVER start CS2, Steam, or the native playback adapter. It may read installed assets into its private cache. On 2026-11-06 the user authorized preparing exactly Ancient, Anubis, Dust2, Mirage, Inferno, Cache and Nuke (their chosen review pool). Use the revision-bound approvals in standalone settings. Missing or outdated map preparation requires an explicit warning and approval inside the demo viewer; identify maps outside that seven-map pool. Do not automatically import the other installed maps. Existing engine playback is a separate legacy option.
- All 3D viewing must appear inside Toolbox. Godot is an owned renderer child, never a separate player window. Prefer the installed Steam Godot 4.7 runtime. Keep loading, cancellation, resizing, navigation and shutdown responsive; verify with application-owned widget/native fixtures, never Computer Use.
- The watch library must show only physical downloaded demos under `C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\replays`. Analysis is optional for watching and cannot by itself make a missing demo available. Do not show an original-demo file picker for playback.

# Token-efficient work

- Default to concise updates and final answers: outcome, validation, material limits. Do not repeat plans or previous explanations.
- Read only relevant files/sections. Use scoped `rg` searches and bounded output (usually 500–1500 tokens); expand only when evidence requires it. Do not dump whole logs, datasets, documentation navigation, or browser trees.
- Batch independent reads/checks in one tool round. Reuse established paths, tool bindings, and evidence; re-read only if changed, stale, or needed to resolve a failure.
- Define a hypothesis and stopping condition before diagnostics. Use one representative fixture first. Cancel unproductive probes; avoid repeated unchanged polling.
- Let local scripts compute counts, comparisons, and summaries. Return compact results and failures rather than raw rows.
- Run checks appropriate to the change once. Repeat/broaden only after changes, failures, or unresolved risks. Preserve correctness and required validation.
- Use screenshots for visual QA when needed; avoid redundant captures. Summarize long work with a short handoff, not duplicated history.
- Do not claim measured token savings without usage evidence. Do not change models, install tools, or rebuild data merely to optimize tokens.

Basis: [OpenAI latency guidance](https://developers.openai.com/api/docs/guides/latency-optimization) (fewer input/output tokens and requests); [Codex prompting guide](https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide) (batch reads, avoid repeated searches/edits).

Project entry points: `app/modules/viewer2d/` (renderer, `engine.mjs`, `replay.py`); `app/extractor/` (v8 extraction); `app/desktop/` (toolbox). Runtime progress/logs: `data/.desktop/`.
