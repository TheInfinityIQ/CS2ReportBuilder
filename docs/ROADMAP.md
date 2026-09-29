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
- **Digest** (`cs2di digest`): software computes every number for one player (counts, denominators,
  plain definitions, per-map and per-side splits). Cross-checked against a fresh-AI coach's numbers.
- **Report** (`cs2di report`): one HTML file, tabs for Player Study and Analyst Desk, fixed shell,
  Teaching Moments built from software modules, styling owned only by `theme.py`, plan validator
  (unknown modules, styling fields, invented numbers, missing evidence all rejected).
- First real output: MIMY, 30 games, 4 Teaching Moments (`examples/mimy/coach_plan.json`).

## Next (in order, each ends with something to open)
1. **Owner review of the MIMY report.** Feedback decides everything below. Fix what feels wrong
   before adding anything.
2. **Coach loop.** Write the prompts that make a fresh AI produce `coach_plan.json` from the
   digest (plus a way to look at selected rounds). The validator already guards the output.
   Compare several fresh runs against the hand-written MIMY plan.
3. **Map viewer (Viewer2D).** Owner ruling: a viewer without the map has little value. Needs radar
   images with verified coordinate calibration for the five maps in play. Until then the plan
   validator rejects `Viewer2D` with a clear message and timelines fill the gap.
4. **More modules as real teaching needs them** (not from a wish list): metric-over-time,
   side-by-side student/reference, utility replay, bomb context.
5. **Analyst Desk depth**: counterexamples, alternative explanations, drill-down to rounds.
6. **Second player** (CanadianIQ) to prove it is not tuned to one player.
7. **Longitudinal coaching** (memory across batches: improved / stable / regressed / resolved).
8. **Cope Barn**, kept walled off from all serious findings.

## Planned after the viewer pass (owner request 2026-09-29)
- **Dashboard tab**: per-map, per-side and over-time charts (owner likes graphs). Every moment currently has a 2D viewer and no chart. Build after the statistical corrections (E-3 advantage denominators, E-7 match-clustered tests) so the charts do not show numbers we are about to change. Use the dataviz skill.
- **Continuous facing + real grenade paths**: measured and specified in `docs/VIEWER_DATA_OPTIONS_2026-09-29.md` (8 Hz `yaw`/X/Y sidecar plus simplified projectile paths; ~20 MB for 30 demos; needs the `.dem` files). Not built yet; owner decision on sidecar vs schema bump pending.
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
