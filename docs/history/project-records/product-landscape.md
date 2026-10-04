# What other CS2 tools show (context, 2026-09-28)

Sources: owner's screenshots in demoparser/data_examples (FACEIT match room, Leetify profile),
csrep.gg and csst.at pages, refrag.gg roles article, and a Tableau positions database (NER0cs).

| Tool | What it shows | Useful idea for us | What it does not do |
|---|---|---|---|
| FACEIT match room | Rating, Swing (win-chance impact), ADR, KAST, HS%, multi-kills, MVPs; duel matrix (who killed whom), head-to-head entry/trade kills and damage; utility table (thrown, unused, successful, enemies/team flashed, blind time); Match Insights: round strip, 2D map per round with kill lines and events list, per-round Swing/ADR/KAST charts | Swing = our kill/death swing; 2D map with kill lines per round; duel matrix; unused-utility | No explanation of why; per match only; no coaching |
| Leetify | Rating, focus areas (crosshair placement, HE usage, counter-strafing) scored against a goal for your rank; aim/positioning/utility radar; consistency; per-side rating; highlights | Goal-by-level framing; a few focus areas | Goals come from a population database (not allowed for us, ADR-013); generic tips |
| csrep.gg / cstracker / csst.at | Trust/anti-cheat scores, rank history, weapon table, recent matches (FK/FD, ADR, time-to-damage, pre-aim), encounters, map table | Time-to-damage and pre-aim as mechanical measures | Largely anti-cheat and aggregation; not our goal |
| Refrag roles | IGL, AWPer, star rifler, entry, support, anchor, lurker; each described by position and timing | Role vocabulary for positions | Roles are not observable from stats alone |
| Tableau positions DB | 1,903 pro players: overall role (Opener, Closer, Support, AWPer, IGL-*) and named position per map and side (e.g. Mirage CT: AWPer, A Anchor, B Anchor, A Connector, B Short) | Answer key to learn positions from early-round locations | Pro-only; used to build the method, never as a player norm |

Where we differ: we explain decisions with the player's own rounds on the map, compare only
within the player's batch, and say how sure we are.

Position recognition prototype (2026-09-28): place name at 15 s and 30 s after freeze end,
naive-Bayes over places, leave-one-player-out on 132 labelled pros in our tournament demos:
66% correct on average over 12 map-sides with 5 positions each (majority guess 10%). Next:
coordinates, more time points, confidence threshold.
