> Historical reference retained at its original path during cleanup.
> Old instructions, priorities, and completion claims are not current
> authority. Consult [AGENTS.md](../AGENTS.md) for development rules and
> [PROJECT_STATUS.md](PROJECT_STATUS.md) for observed state. Verify
> technical claims against their evidence before relying on them.

# Roadmap

Owner priority (from Stage 5): a usable product again. The engineering exists to make the
coach better, not to replace coaching with paperwork. Progress is measured by what Dawson
can open, read and react to, not by gates passed.

Benchmark for every milestone: **would Dawson rather use this than upload the data to an AI
and ask for coaching?**

## Done
- Repo, package, CI, config, SteamID handling.
- Hard integrity gate, verified on the real corpus (Cologne 113/114 = 2,251 rounds; FACEIT 100 = 2,105;
  Premier 4 = 85; MIMY 30 = 640).
- **Digest**, **analyst** (findings with verdicts and replay examples), **report** (one HTML file, Player Study + Analyst Desk tabs,
  fixed shell, module registry, single-source CSS, plan validator).
- **Map viewer (Viewer2D)** built on real radar images and demo data; v3.4 uses the 8 Hz viewer-tracks sidecar (see below).
- **Handoff test** (2026-09-29): a fresh, context-free AI produced valid reports from a pack; defects logged as H-1..H-9.
- **8 report packets** (5 pug players, 3 pro players; 30 unique matches each, none shared) built by `scripts/build_packet.py`.
- **Agent start-here system** (`CLAUDE.md`, `agent/`): task router, role hats, preference/regression/state logs.
- Reports produced: MIMY, iTrilogyy (hand-written reference plans in `examples/`).

## Next (in order, each ends with something to open)
1. **Run fresh coaches on the 8 packets**, then review them (Test reviewer hat). This is the first test on more than one player and on tournament data.
2. **Fix H-1, H-2, H-3** (example ranking, self-kills, validator gaps), then re-issue the affected packets.
3. **Statistical corrections** E-3 (advantage denominators) and E-7 (match-clustered tests), before charts show numbers that are about to change.
4. **Dashboard tab** (per-map, per-side, over-time charts) after 3.
5. **More modules as real teaching needs them** (not from a wish list): metric-over-time, side-by-side student/reference, bomb context; the H-8 blocks the coaches asked for.
6. **Analyst Desk depth and mobile**: counterexamples, alternative explanations, drill-down; U2-21..35, R-14, R-15, R-18.
7. **Longitudinal coaching** (memory across batches: improved / stable / regressed / resolved).
8. **Cope Barn**, kept walled off from all serious findings.

## Viewer v3.4 (from the external v3.3 review, see CRITIQUES R-1..R-18) - BUILT 2026-09-29 (items 1-6; item 7 mobile Analyst Desk / ARIA tabs and R-14, R-15, R-18 remain open)
Sidecar wired (`viewer_tracks`, `grenade_throws`, `grenade_paths`); tested on the 30-game iTrilogy batch (30/30 ok, 9,998 throws, facing p99 error <= 10.2 deg).
Order: (1) exact weapon-id map plus an unknown icon and a build check, (2) aim / movement / unknown pin semantics and stateless heading, (3) DOM labels plus full-screen mobile viewer, (4) local viewer filters, (5) timeline markers and step controls, (6) legend and drawer de-duplication, lazy init, (7) mobile Analyst Desk and tabs. Statistical wording (R-16, R-17) is cheap and goes in with it.
Data step in parallel: run `extractor/extract_viewer_tracks.py` on a test batch of 30 PUGs (see `extractor/README.md`), then wire the viewer to it.

## Planned after the viewer pass (owner request 2026-09-29)
- **Dashboard tab**: per-map, per-side and over-time charts (owner likes graphs). Every moment currently has a 2D viewer and no chart. Build after the statistical corrections (E-3 advantage denominators, E-7 match-clustered tests) so the charts do not show numbers we are about to change. Use the dataviz skill.
- **Continuous facing + real grenade paths**: DONE as an additive sidecar (the pending "sidecar vs schema bump" choice was settled in practice by building the sidecar; Dawson has not objected; see `docs/VIEWER_DATA_OPTIONS_2026-09-29.md` and `extractor/README.md`).
- **Viewer roster**: add money and utility inventory (present on `weapon_fire.user_balance` / `user_inventory`).

## Parked (kept in scope, deliberately not started)
Team / strategy / opponent modes, player comparison, training-resource registry, historical
radar compatibility research, M10-M11 statistics gates as a report prerequisite.

## Risks I am watching
1. Numbers in coach prose that happen to exist somewhere in the digest but mean something else.
   The numeric check is context-blind; it stops invented figures, not misused ones.
2. Owner-only taste (N=1). Get one independent player and one coach to react.
3. Extractor drift and its known boundary bugs (pitfall 23). Extractor stays frozen (ADR-005).
4. Missing generator source for M6-M11.3, so those results are not reproducible from this repo.
5. Map viewer depends on assets and calibration not yet in hand.
