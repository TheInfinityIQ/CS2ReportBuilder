# Things that broke or were undone (append-only)

Read before changing anything listed here. Product-level critiques and their status: `docs/CRITIQUES.md`. Data traps: `docs/KNOWN_PITFALLS.md`.
Format: `date | what broke | cause | how it is now prevented`.

2026-09 (history) | Long engineering with no shippable report | Optimising machinery step by step | ADR-010, product first; the test is "better than uploading data to ChatGPT"
2026-09 (history) | Fresh AI computed its own numbers; clutch counted 146 vs 45 | AI did the counting | ADR-003 digest; validator rejects numbers not in the digest
2026-09-28 | MIMY "Mirage CT A-site" weakness looked credible (q=0.04); leaning after dedup | Same match in two batches | Fingerprint dedup in `load_fights` (pitfall 28)
2026-09-29 | Steam-folder paths hard-coded in code and scripts; scripts kept old folder names after the reorganisation | Path constants outside `config.py` and not updated with the moves | All paths via `config.py` / `CS2DI_ROOT`; after any move, grep for the old name
2026-09-29 | Teaching Moments capped at 2–4 in five places (prompt, rules, modules, docs, design) | A style rule written as a limit | Firm ruling; `test_no_cap_or_minimum_on_teaching_moments`. Still capped by design: KeyMoments 1–6 rounds, MetricCluster 2–4 cards (raised with Dawson, undecided)
2026-09-29 | Plan-validator test failed on titles containing digits | Number check applies to titles, not only prose | Word test titles without digits
2026-09-29 | Device unpack looked hung; background jobs vanished | Device shell calls end at 180 s and kill background processes | Short foreground steps, `tar --skip-old-files`, verify counts after
2026-09-29 | `device_bash` reported Cloudflare 520 once | Transient | Verify the artifact exists, then continue; do not repeat non-idempotent commands
2026-09-29 | Two name collisions in pro packets (same demo names in different tournaments) | Folder names not unique across batches | Pro packets prefix `<batch>__`
