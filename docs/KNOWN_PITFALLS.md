# Known pitfalls (each becomes a regression test)

Sourced from the project's chat history and handoffs. "Where" names the origin.

| # | Trap | Rule | Where |
|---|---|---|---|
| 1 | Knife round shares `total_rounds_played==0` with round 1; flags don't separate them | Cut at the last `round_start` with round==1 (mp_restartgame); never trust warmup/knife flags | Claude chat, v4 |
| 2 | `round_end.total_rounds_played` is post-round (+1) | Use `rounds.csv` parser_round joins; ordinary events join on parser_round | schema 3 prompt |
| 3 | SteamID64 through float64 corrupts | Read IDs as text/int only; 0 is the world sentinel | Stage 1 |
| 4 | Unknown side turned into LOSS (NaN is not None) | unresolved side -> unresolved result | v6 audit |
| 5 | `dmg_health` is uncapped overdamage | Use capped enemy damage; exclude self/team | prompt |
| 6 | Assists: FACEIT UI excludes flash assists, engine includes | State which definition | v4 checks |
| 7 | Tournament SourceTV lacks player_blind, footstep, reload, zoom, beginplant, begindefuse | Missing stream = unknown, not zero | capability report |
| 8 | HLTV `-p1/-p2` are one map | Stitch on absolute parser_round, never segment_round | corpus manifest |
| 9 | Terminal SourceTV `round==1` reset picked as start | Fixed in v7.7; one Cologne p1 still quarantined | capability report |
| 10 | `donk666_game11` is CanadianIQ, not donk | Identify by SteamID, never folder name | corpus manifest |
| 11 | Clutch counted 146 vs true 45 in 322 rounds | Max one 1vX transition per round, from ordered deaths | coach chat |
| 12 | Buy type from round_start equipment made 71% "eco" | Classify from freeze-end economy; split pistol rounds | coach chat |
| 13 | Kill -> death in under 1 s is a trade/active-fight window, not "failed to disengage" | Separate 0-1 s, 1-3 s and true reposition analysis | coach chat |
| 14 | Kills/deaths just after the round-end tick still happen and the scoreboard counts them | Window each round from freeze end to the NEXT round's start so K/D matches the scoreboard; never let a post-round kill be an opening | coach chat, MIMY check 2026-09-28 |
| 15 | Bomb-site ids are unstable across sources | Do not use raw site id as A/B identity | E0 |
| 16 | Horizontal yaw error is not crosshair placement | No vertical/head claims | prompt |
| 17 | Null contact latency is unknown, not 0 (3 s left-censored window) | Report only uncensored; state coverage | prompt |
| 18 | Low speed is not a held angle; untraded is not untradeable | Mechanism claims need replay/deep evidence | prompt/V4 |
| 19 | Pandas nullable-NA equality breaks transitions | Explicit missing-to-value handling | M5 |
| 20 | Pro means are not targets for a solo-queue player | Context only; report both sample sizes | prompt |
| 21 | Aggregate subtraction assumes subset relationships (255-237 != 18) | Compute round-level overlap | V3-D4.1 |
| 22 | Raw ticks are not player language | Semantic anchors; seconds only when tickrate validated | V3/V4 |
| 23 | Extractor `engagements.csv` tags a kill made just after a round ended to the NEXT parser round. It can invent an "opening" (MIMY: 61 opening kills vs true 60; Anubis 9-13 vs true 8-12) or hide a real one | Derive openings from events using the round window in `digest.py`; do not read openings from `engagements.csv` | MIMY check 2026-09-28 |
| 24 | `player_death.weapon` is a lowercase code (`awp`); `*_active_weapon_name` is a display name (`AWP`, `SSG 08`). Filtering one column with the other's spelling silently drops half the rows (a fake "0 wins vs snipers", then a fake "27 of 27") | Normalize weapon names in one place before any weapon filter; test with both spellings | exploration 2026-09-28 |
| 25 | A striking split can be true of everyone (MIMY wins 67% when holding vs 38% when moving into a holder, but so does every other player: 70% vs 30%) | A finding about a player needs a peer baseline from the same games before it may be called personal | exploration 2026-09-28 |
| 26 | Some patterns are normal and should be recorded as such (trade rate 21% vs teammates 18%; unused grenades at death 43% vs everyone 44%) | Keep null results in the analyst output so the coach does not chase them | exploration 2026-09-28 |

| 27 | Same-tick damage double count (extractor ≤ v7.7) | `dmg_health_capped = user_health - health`; when one victim takes several hits in one tick every row shares the start-of-tick `user_health`, so later rows recount earlier damage (100→88→46 gives 12+54=66, truth 54). 446/446 demos affected to some degree: 0.1–0.9% excess damage, 3.3% on Premier; HE/fire utility damage inherits it. Checked against FACEIT scoreboards for 3 players: K/D exact, fix moves ADR toward FACEIT in every changed match. Damage dealt after the round-end tick is NOT an error (FACEIT ADR includes it). | Use `dmg_health_effective` (v7.8, or `cs2di repair --apply` on old output). Never recount post-round-end damage away. Tests: `tests/test_repair.py`. |
| 28 | The same match can sit in two batches (and 5 demo ids appear in two batches) | 440 demo ids but 429 distinct matches; duplicates double-count fights in both the player and the population. Before dedup MIMY's "Mirage CT A-site" weakness was credible (q=0.04); after dedup it is only leaning. | Always load fights with `load_fights` (keeps one copy per match fingerprint). Test: `test_same_match_in_two_batches_is_kept_once`. |
