# CS2 Current Corpus Capability Report — v7.6 + v7.7 Premier Addendum

## Purpose

This report describes what the **current 218-folder coaching corpus** can and cannot support before player coaching begins. It combines the original v7.6 FACEIT/Cologne corpus with four CanadianIQ Premier demos parsed under schema 3.7. It is a data-capability audit, not a coaching report.

## Corpus

- Demo folders: **218**
- Hard-valid/coaching-valid folders: **217**
- Invalid/quarantined folders: **1**
- Usable extracted rounds: **4,441**
- FACEIT demo files: **100 / 2,105 rounds**
- IEM Cologne Major 2026 SourceTV files: **114**, of which **113 valid / 2,251 extracted rounds**
- Cologne logical maps after stitching `p1/p2`: **103**
- Split Cologne maps: **11**
- Total logical maps represented: **207**
- Valve Premier/MM source demos: **4 / 85 rounds**, all canonical and coaching-valid

The original v7.6 archive contained FACEIT + tournament SourceTV only. The current onboarding corpus now additionally includes four CanadianIQ Valve Premier demos in `analyzed_premier_batch1`; all four pass schema-3.7 hard and soft integrity gates.


## Premier addendum — measured on the four schema-3.7 CanadianIQ demos

All four Premier demos are canonical, `coaching_valid=true`, full-match extractions with zero hard integrity failures and zero soft integrity warnings.

- Games: **4**
- Rounds: **85**
- Maps: Inferno 21 rounds, Anubis 42, Mirage 22
- Engagement rows: **624**
- `player_death`, `player_hurt`, `weapon_fire`, `fire_bullets`: present in **4/4**
- `player_blind`, `player_footstep`, `weapon_reload`, `weapon_zoom`: present in **4/4**
- grenade detonation/burn streams: present in **4/4**
- `bomb_beginplant`, `bomb_planted`, `bomb_begindefuse`: present in **4/4**
- `bomb_defused`: present in **2/4** (event occurrence dependent)
- `bomb_exploded`: present in **4/4**

Premier engagement-field coverage across 624 PvP deaths:

- first relevant shot tick: **97.8%**
- first damage tick: **100%**
- horizontal attacker yaw error: **100%**
- attacker/victim 2D speed: **99.7%**
- attacker/victim approximate visible-by counts: **100%**
- attacker nearest living teammate distance: **89.6%**
- victim nearest living teammate distance: **88.6%**
- first mutual approximate contact: **58.2%**
- uncensored attacker contact→first-shot latency: **52.9%**
- uncensored victim contact→death latency: **60.3%**

The Premier sample is much smaller than CanadianIQ's FACEIT sample. Use it as a source/context contrast, not as an equally precise baseline.


## Identity/reference cohorts

| Cohort | Canonical SteamID | Context | Sample |
|---|---|---|---:|
| CanadianIQ | `76561198062530225` | FACEIT | 79 games / 1,641 rounds |\n| CanadianIQ | same SteamID | Valve Premier | 4 games / 85 rounds |
| donk | `76561198386265483` | FACEIT | 11 games / 251 rounds |
| donk | same SteamID | Cologne tournament | 14 logical maps / 357 rounds |
| mezii | `76561197973140692` | FACEIT | 10 games / 213 rounds |
| mezii | same SteamID | Cologne tournament | 14 logical maps / 293 rounds |

`donk666_game11` is mislabeled by folder: its roster contains CanadianIQ and does not contain donk. It belongs in the CanadianIQ cohort.

The same SteamIDs link `donk666`→`donk` and `mezii--`→`mezii` across FACEIT/tournament sources. This gives an unusually useful same-player cross-context reference.

## One newly discovered v7.6 edge case

`furia-vs-mouz-m1-nuke-p1__INVALID_v75` is correctly rejected by the integrity gate, but it revealed a new SourceTV boundary pattern.

The segment contains four genuine completed rounds, followed by a synthetic `round==1` reset at the **end** of the file. v7.6 selected that final reset as the segment start and therefore reconstructed zero completed rounds.

This is a parser-boundary bug, not bad underlying demo data.

- paired `p2` begins at absolute `parser_round=4`;
- the invalid `p1` contains genuine round ends for parser rounds 0–3;
- current canonical tournament aggregates should exclude this `p1`;
- v7.7 fixes this terminal-reset case;
- only this segment needs re-parsing to complete the map; the other 213 valid outputs do not need to be rerun solely for this fix.

## Engagement table coverage

Across the **213 valid demos in the original v7.6 FACEIT/Cologne corpus**:

- attributed PvP deaths: **29,630**
- `coaching/engagements.csv` rows: **29,630**
- reconciliation: **100%**

### FACEIT engagement-field coverage

- first relevant shot tick: **97.7%**
- first damage tick: **100%**
- horizontal attacker yaw error: **100%**
- attacker/victim 2D speed: **~99.9%**
- attacker approximate visible-by count: **100%**
- victim approximate visible-by count: **100%**
- attacker nearest living teammate distance: **90.9%**
- victim nearest living teammate distance: **87.7%**
- first mutual approximate contact: **53.0%**
- uncensored attacker contact→first-shot latency: **47.6%**
- uncensored victim contact→death latency: **55.8%**

### Cologne SourceTV engagement-field coverage

- first relevant shot tick: **97.7%**
- first damage tick: **100%**
- horizontal attacker yaw error: **100%**
- attacker/victim 2D speed: **~99.9%**
- attacker approximate visible-by count: **100%**
- victim approximate visible-by count: **100%**
- attacker nearest living teammate distance: **92.9%**
- victim nearest living teammate distance: **89.0%**
- first mutual approximate contact: **41.9%**
- uncensored attacker contact→first-shot latency: **36.6%**
- uncensored victim contact→death latency: **45.6%**

The lower contact-latency coverage is expected from the conservative 3-second pre-death window and left-censor rules. Null latency must be treated as unknown, not zero.

## Source capability matrix observed in this corpus

| Event/signal | FACEIT | Cologne SourceTV | Coaching consequence |
|---|---:|---:|---|
| player_death | 100/100 demos | 113/113 | cross-source safe |
| player_hurt | 100/100 | 113/113 | cross-source safe |
| weapon_fire | 100/100 | 113/113 | cross-source safe |
| fire_bullets | 100/100 | 113/113 | shot inaccuracy/spread/recoil comparable |
| player_blind | 100/100 | **0/113** | detailed flash outcomes are FACEIT-only here |
| player_footstep | 100/100 | **0/113** | do not compare footstep event rates |
| weapon_reload | 100/100 | **0/113** | use combat snapshot reload state on HLTV |
| weapon_zoom | 99/100 | **0/113** | use combat snapshot scope state on HLTV |
| flashbang_detonate | 100/100 | 113/113 | throw/detonation timing available |
| smokegrenade_detonate | 100/100 | 113/113 | available |
| hegrenade_detonate | 100/100 | 112/113 | available where event occurs/parses |
| inferno_startburn | 100/100 | 113/113 | available |
| bomb_beginplant | 100/100 | **0/113** | begin-plant timing not cross-source |
| bomb_planted | 100/100 | 112/113 | plant completion usable |
| bomb_begindefuse | 94/100 | **0/113** | begin-defuse timing not cross-source |
| bomb_defused | 91/100 | 100/113 | defuse completion usable |
| bomb_exploded | 90/100 | 105/113 | explosion completion usable |

A missing unsupported stream is **unknown**, not a count of zero.

### Important flash implication

Tournament `coaching/utility_effectiveness.csv` can contain zero `enemy_blind_events` because the underlying `player_blind` stream is absent. Those zeros are not evidence that pro flashes blinded nobody.

For Cologne use:
- flash detonations/positions/timing;
- engine aggregate `scoreboard_segment_delta.enemies_flashed_total_segment` (non-zero and populated in the tournament corpus);
- utility damage;
- replay context.

Do not compare FACEIT per-flash blind-duration metrics against tournament zeros.

## User commands

Every valid FACEIT and tournament demo resolved **15 of 19** probed usercmd property families. The 32-tick probes show meaningful changing values for:
- view angles;
- mouse dx/dy;
- forward/lateral movement;
- button-state bitfields;
- weapon selection;
- input-history payloads.

The standard batch output is still only a **capability probe**, not full-match input telemetry. It proves deep analysis is possible; it does not support population-level claims about counter-strafe key timing or mouse paths.

Use deep profile only for selected demos/rounds after batch analysis identifies a mechanism worth investigating.

## What the corpus can show very well

1. **Round impact**
   - opening kills/deaths;
   - alive-state progression;
   - trade timing;
   - post-plant;
   - man-advantage conversion;
   - low-impact/late kills.

2. **Fight construction**
   - teammate distance;
   - approximate exposure count;
   - round timing;
   - distance;
   - inventory/utility held;
   - whether the player was isolated or supported.

3. **Mechanical state at combat**
   - movement speed;
   - accuracy penalty;
   - crouch/airborne/scope/reload state;
   - recoil indices;
   - ammo;
   - fire_bullets inaccuracy/spread/recoil.

4. **Horizontal crosshair burden**
   - exact XY+yaw angular error at the engagement probe tick;
   - not vertical head placement.

5. **Economy**
   - balance/equipment/spending/inventory per player/round;
   - team-level buy context.

6. **Utility**
   - damage and detonation timing/position on both sources;
   - detailed blind outcomes on FACEIT;
   - aggregate enemies-flashed on tournament scoreboard.

7. **Macro position**
   - 2 Hz alive-player rotations/spacing/map presence.

8. **Professional reference context**
   - same-source FACEIT comparison against donk/mezii;
   - full Cologne population for structured pro-team reference;
   - same-player FACEIT↔tournament contrast for donk/mezii.

## What it cannot establish from batch output alone

- intention;
- communication/callouts;
- consciously heard audio cues;
- exact BSP line-of-sight;
- vertical/head-height pre-aim;
- continuous whole-round mouse path;
- exact key-by-key counter-strafe sequence;
- full subtick input history;
- whether a grenade was a memorized lineup;
- exact tactical role without contextual inference.

These should trigger replay review or a small deep-mode reparse, not confident prose.

## Best reference strategy

### CanadianIQ vs CanadianIQ
Primary comparison. Internal contrasts are the cleanest:
- CT/T;
- map;
- weapon;
- buy;
- round phase;
- isolation;
- successful vs failed engagements.

### CanadianIQ vs donk/mezii FACEIT
Best for:
- individual movement/shot discipline;
- duel geometry;
- opening behaviour;
- solo/pug spacing;
- mechanics under a matchmaking environment.

### CanadianIQ vs Cologne population
Best for:
- structured spacing;
- advantage conversion;
- trade structure;
- utility/economy discipline;
- post-plant/retake patterns.

### Donk/mezii FACEIT vs their tournament selves
Use this to identify which elite behaviours persist across environments and which are team-system dependent. This is particularly valuable for avoiding inappropriate "pro team CS" prescriptions in solo queue.

## Recommendation before coaching

1. Use the revised schema-3 prompt.
2. Give the coach the corpus manifest and logical-map manifest.
3. Exclude the one invalid FURIA–MOUZ Nuke p1 segment.
4. Reparse only that segment with v7.7 when convenient.
5. Do not treat `donk666_game11` as a donk reference.
6. Treat the four schema-3.7 Premier demos as a distinct CanadianIQ comparison cohort; do not merge FACEIT and Premier baselines without labeling the source.
7. Start with CanadianIQ's internal baseline, then add matched pro reference context.
8. Escalate only a few representative demos to deep mode after recurring patterns are found.
