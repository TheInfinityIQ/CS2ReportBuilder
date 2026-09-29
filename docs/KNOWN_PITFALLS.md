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
| 14 | Deaths outside the round interval (post-round) skew K/D | Exclude and reconcile with scoreboard, report residual | coach chat |
| 15 | Bomb-site ids are unstable across sources | Do not use raw site id as A/B identity | E0 |
| 16 | Horizontal yaw error is not crosshair placement | No vertical/head claims | prompt |
| 17 | Null contact latency is unknown, not 0 (3 s left-censored window) | Report only uncensored; state coverage | prompt |
| 18 | Low speed is not a held angle; untraded is not untradeable | Mechanism claims need replay/deep evidence | prompt/V4 |
| 19 | Pandas nullable-NA equality breaks transitions | Explicit missing-to-value handling | M5 |
| 20 | Pro means are not targets for a solo-queue player | Context only; report both sample sizes | prompt |
| 21 | Aggregate subtraction assumes subset relationships (255-237 != 18) | Compute round-level overlap | V3-D4.1 |
| 22 | Raw ticks are not player language | Semantic anchors; seconds only when tickrate validated | V3/V4 |
