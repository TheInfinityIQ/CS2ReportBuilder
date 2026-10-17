# User preferences

- Ask the user for explicit approval before starting a large data rebuild, bulk re-extraction, migration, or broad data correction. Describe the concrete scope, output location, retention of existing data, and expected resource use first. Do not treat a brief "proceed" during viewer work as approval for a bulk data operation.
- Targeted read-only checks and small viewer fixes can proceed within the requested scope. Explain why any additional runtime or parser is needed before introducing it.

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
