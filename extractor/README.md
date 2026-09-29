# Extractor (frozen, ADR-005)
`extract_demos_v7dot7.py` (schema 3.7, demoparser2 0.42.0, COACHING_PROFILE `batch` by default).
Source is copied verbatim from the owner's onboarding pack. Configure via the constants at the
top of the file (DEMO_DIR / OUTPUT_DIR). Layout convention:
`Demos/<batch>/*.dem` -> `v7dot7Analysis/analyzed_<batch>/<demo_id>/`.
Its own SHA-256 is recorded in each `match_summary.json` (`runtime_environment.extractor_sha256`).
Changing it requires a schema bump and a regression comparison; do not edit casually.
