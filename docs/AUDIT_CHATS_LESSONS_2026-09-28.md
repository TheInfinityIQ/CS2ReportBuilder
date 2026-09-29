# Audit of the AI chat history: bugs, coaching lessons, awpy/demoparser2, undelivered asks, process failures

Audience: the incoming senior developer. Goal: do not regress on lessons already paid for, and see what was overlooked.
Nothing under `/home/claude/cs2-demo-intelligence` was modified. No emojis. All paths absolute.

## 0. Conventions and sources

Short names used in citations:

| Short name | Path |
|---|---|
| CHATS | `/mnt/user-data/uploads/demoparser/CoachOnboarding/AIChatHistory/` |
| script_creation_claude.txt | CHATS (byte-identical in size to `ClaudeCoach1.txt`, 18153 bytes) |
| script_creation_chatGPT.txt, script_creation_chatGPT_2.txt, script_creation_grok.txt | CHATS |
| ChatGPT_awpyIntegration.txt, ChatGPT_Stage3End.txt, ChatGPT_Stage4End.txt, chat_gptCoach2.txt, coaching_example.txt, Stage5.txt, cs2_coach_prompt.md, ClaudeCoach2.txt | CHATS |
| ClaudeCoach.json (raw export, 3 conversations) | CHATS; I extracted plain text to the scratchpad as `claude_conv1_text.txt` (coaching, 2025-09 batch 1-2 work), `claude_conv2_text.txt` (coach prompt, extract v2 to v5, validation against FACEIT photos), `claude_conv3_text.txt` ("Validating CS2 coaching accuracy", B4.5) |
| GrokCoach.json (raw export, 3 conversations) | CHATS; extracted to scratchpad `grok_all.txt` |
| scratchpad | `/tmp/claude-0/-home-claude-cs2-demo-intelligence/9c7c0964-e29a-5b43-9c66-fe4a32abe220/scratchpad/` |
| DesignV2.1 / Evolution / V4.1 / Living Onboarding | `.../scratchpad/txt/*.docx.txt` (converted from `CoachOnboarding/Design/*.docx`) |
| KP#n | row n of `/home/claude/cs2-demo-intelligence/docs/KNOWN_PITFALLS.md` (26 rows) |
| OWNER_RULINGS, UX_REVIEW | `/home/claude/cs2-demo-intelligence/docs/OWNER_RULINGS.md`, `UX_REVIEW_2026-09-28.md` |
| Device | `C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\replays\demoparser` (reached via `mcp__remote-devices__device_bash`) |

Line numbers (L###) refer to the text file named. For `claude_conv*_text.txt` and `grok_all.txt` they refer to my extracted files.

"KP status" column: `KP#n` = already a row; `PARTIAL (KP#n)` = the row touches it but misses the specific trap or the fix; `NOT` = no row.

## 1. Scope, limits, honesty notes

Read fully: all eleven requested chats, the two raw JSON exports, `cs2_coach_prompt.md`, full `Stage5.txt` (60 KB device version), repo docs (KNOWN_PITFALLS, DECISIONS, PROJECT_CONTEXT, ROADMAP, OWNER_RULINGS, HOW_TO_READ_THE_HISTORY, UX_REVIEW), the converted design docs (DesignV2.1 CURRENT, Evolution Record v1.0, Master Architecture v4.0 draft and v4.1, V4 Consultant Review, Living Onboarding v1.2, Architecture Review v1.1).

Sampled only (not read in full): device `Development/Steps` handoffs (I read `M1221_ai_handoff.json`, `M123_ai_handoff.json`, head of `M123_historical_radar_inventory.json`, `V4V1_ai_handoff.json`, listing of `Stage3_M121_FIRST_LEARNING_LOOP`), consultant PDFs (I read `G_v4.pdf`, `Gemini_v2.pdf` in full; `Claude_v2.docx.pdf` only the AWPy parts; `DeepSeek.pdf` and `Grok_v2.docx.pdf` not read beyond a grep for map/awpy).

Not read at all: `extract_demos_v7dot7.py`, the content-creator transcripts (`CoachOnboarding/ContentCreator/*`), `Misc/FaZe_Cache_T_Side_Stratbook.docx`, the demos themselves, the code of this repo (the three background agents cover awpy code, demoparser2 use and extractor bug catalogue; this report is chat-derived and does not duplicate them).

Things I could not find or verify (details in section 9):
- `ChatGPT_awpyIntegration.txt` contains NO awpy integration. Its name is a misnomer; it is the v5/v6/v7 extractor-improvement chat. The real AWPy "Stage 2" (design 12E to 12J) chat is not in the package; it is known only through DesignV2.1 A.10.
- The owner's suggestion to replace the extractor with `parse_events(["all"])` (ClaudeCoach.json conv3, MSG 2) is not answered in the export; the conversation ends with tool calls. I found no record of the question being resolved.
- `V4V2_MAP_DUAL_PANE_VIEWER` on the device is an EMPTY folder. The living onboarding says a package was prepared; no returned handoff exists.

## 2. Bug and data-trap catalogue

Column meaning: symptom, root cause, fix, source with short quote, KP status.

### 2A. Round and match structure

| ID | Symptom / root cause / fix | Source and quote | KP status |
|---|---|---|---|
| A1 | Knife round and real round 1 share `total_rounds_played==0`. `round_end.iloc[0]` is a phantom; every round label from round 2 on is shifted for the whole match. Fix: cut at last `round_start` with `round==1`; dedup keep-last. | script_creation_claude.txt L123: "Every round label from round 2 onward is shifted by one, for the entire match, in every demo it processes." | KP#1 |
| A2 | Grok "fixed" the knife round by dropping the whole `total_rounds_played==0` row, which also holds the merged real round 1, so round 1 kills/deaths/assists vanished from every stat. | script_creation_claude.txt L127: "Grok didn't just exclude the knife round — it threw away all of your actual first-round kills/deaths/assists". script_creation_grok.txt L70, L136: "total_rounds_played ≥ 1". | PARTIAL (KP#1 states the cut, not the "dropping the row loses round 1" failure) |
| A3 | `is_warmup_period` and `is_match_started` do not separate the knife round. An earlier Claude claim that they "cleanly excluded pregame junk" was wrong for knife. | claude_conv1_text.txt L314 (earlier claim); script_creation_claude.txt L131: "the knife round shows is_match_started=True and is_warmup_period=False — identical to a real live round". | KP#1 ("never trust warmup/knife flags") |
| A4 | Halftime side swap: score computed as count of `winner=='CT'` vs `'T'` over the whole match gave impossible scorelines. Fix: track the target's side per round (or use `team_clan_name`), compare to winner. | claude_conv1_text.txt L314: "teams swap sides at halftime"; "impossible scorelines (14-7, 15-7, etc.)". script_creation_claude.txt L135: "team_clan_name (stable across the halftime side-swap...)". | NOT |
| A5 | Match-start detection used `rs["round"]==1`. `round` exists only in FACEIT/get5 demos; Valve MM and HLTV `round_start` has only fraglimit/objective/timelimit/tick. KeyError aborted the whole demo. Fix: FACEIT heuristic primary, fallback to last `total_rounds_played==0` `round_start`. | grok_all.txt (bug 2 in the script-findings summary, L~310); claude_conv3_text.txt L174 (extract_demos_v5 header): "round column, which is injected by FACEIT/get5 server plugins and does NOT exist in Valve MM or HLTV demos". claude_conv2_text.txt L117. | NOT (KP#7 and #9 are about streams and terminal reset, not the `round` column) |
| A6 | `list_game_events()` under-reports on FACEIT: omits `round_start` and `round_end`. v2 gated on it, round table never built, `start_tick` stayed null, warmup/knife unclipped, kills inflated by up to 3 per match with no error. 58/58 demos affected. Fix: never gate core events on the listing (schema 2.1). | claude_conv2_text.txt L204: "`list_game_events()` under-reports on FACEIT demos — it omits `round_start` and `round_end` entirely"; L239 "My bug."; grok_all.txt: "kills inflated by up to 3 per match with no error raised". | NOT |
| A7 | A round that ends in surrender (buy time) never fires `round_freeze_end`. Positional lookups shifted later rounds; side/result unresolved; match reported 1-9 when truth was 1-10. Fix: per-round tick keyed on `total_rounds_played`; fall back to that round's own `round_start` tick. | claude_conv2_text.txt L287-293, L361; grok_all.txt: "reported 1-9 when the true score was 1-10". | NOT |
| A8 | Round count derived from "last round with a recorded kill" silently drops zero-kill rounds (forced losses, surrenders, admin decisions) at the tail. Fix: trust the `round_end` count. | claude_conv2_text.txt L379: "silently truncating any zero-kill round (forced losses, surrenders, admin decisions)". | NOT |
| A9 | Round timing read positionally (`rf2.iloc[idx]`) rather than keyed; a gap mid-match would shift every later round. | claude_conv2_text.txt L381: "read positionally ... rather than keyed by round number". | PARTIAL (KP#2 says join on parser_round) |
| A10 | `round_end.total_rounds_played` is post-round (+1); combat events report R-1. | claude_conv2 / conv1 (cs2_coach_prompt notes); grok_all: "reports R while combat events report R-1". | KP#2 |
| A11 | Kills just after round end still count on the scoreboard; opening kill mis-tagged to next round. | chat_gptCoach2.txt L1331-1343: "Scoreboard: 250 kills / 210 deaths ... six-death residual". | KP#14, KP#23 |
| A12 | Target player not found (alt/smurf nickname, `donk666_game11` is "Myself666"): every round side/result null, match written as a plausible 0-0 with `valid=true`. Fix (schema 2.2): `valid` requires target resolved and every round resolved. | grok_all.txt: "donk666_game11 reported valid 0-0 across 23 rounds because the player was under 'Myself666'"; claude_conv3_text.txt L17 (quoting line 141 of a ChatGPT transcript): "the requested target wasn't in that demo's roster, so the apparent 0–0 result is meaningless". | PARTIAL (KP#10 covers identity-by-SteamID, not the valid-flag-lies failure) |
| A13 | M5 player-state transitions crossed round boundaries and contaminated some M6 candidates. Caught late (M8.5). Fix: round-safe transitions (M6R to M8R); also evidence refs were row-ordinal (later hash-bound). | ChatGPT_Stage4End.txt L22: "M5 transitions could cross round boundaries and had already contaminated some M6 candidates". DesignV2.1 A.14 (frozen self-review): "M5 player-state transition logic can span round boundaries". | NOT (KP#19 is about pandas NA, not round-crossing) |
| A14 | Mid-match bot substitutions and disconnects make the engine scoreboard aggregate drift by 1 kill/death/assist in about 2/58 matches; the event-level recount is the reliable side in those cases. | claude_conv2_text.txt L386: "Mid-match bot substitutions ... drift the engine's own scoreboard aggregate by ±1". | NOT |
| A15 | Reconciliation against the engine scoreboard is the only external oracle. Result at v3: K/D exact 56/58, assists (excluding flash) exact 32/58. This should be a regression test. | claude_conv2_text.txt L302: "K/D exact match: 56/58; assist(excl flash) exact match: 32/58". chat_gptCoach2.txt L1331: "reconcile event-derived K/D against the scoreboard". | NOT as a test (KP#6 covers assist definition only) |

### 2B. Identity, encoding, types

| ID | Symptom / root cause / fix | Source and quote | KP status |
|---|---|---|---|
| B1 | Any steamid column containing a null becomes float64; 17-digit SteamID64 corrupts (`...530225` to `...530224`). `attacker_steamid == target` silently matches nothing, damage computes as zero. ChatGPT and Claude both quoted the corrupted ID without noticing. Fix: nullable `Int64`; snap corrupted values to the nearest roster ID. | claude_conv2_text.txt L125: "true steamid ... 76561198062530225 ... int() of it: 76561198062530224"; L156; grok_all.txt: "Downstream equality tests ... silently match nothing; damage computes as zero". | KP#3 (the "snap to roster" repair for already-written data is not stated) |
| B2 | Unresolved side becomes LOSS because `team is not None` passes for NaN. 22 of 16,378 all-player rows (0.134%) in v6. Fix: unresolved side gives unresolved result. | ChatGPT_awpyIntegration.txt L~425: "v6 all-player result derivation: FAIL on 22/16,378 rows (0.134%)"; grok_all.txt L1013 (draft code `if team is not None and pd.notna(winner)`). | KP#4 |
| B3 | Winner and reason are strings on FACEIT/get5 and integers on Valve (winner 2=T, 3=CT; reasons 8/9 name the loser). Unnormalised logic gave all-LOSS on Valve demos. | grok_all.txt (bug 7): "FACEIT/get5 → strings; Valve → integers ... Un-normalized logic produced all-LOSS on Valve demos."; claude_conv2_text.txt L141 ("Fix reason enum"). | NOT |
| B4 | Nullable Int64 NA equality breaks transitions. | ChatGPT_Stage4End (M5 lineage). | KP#19 |
| B5 | Folder names are not identity (`donk666_game11` is CanadianIQ). | corpus manifest (repo). | KP#10 |

### 2C. Damage and stat definitions

| ID | Symptom / root cause / fix | Source and quote | KP status |
|---|---|---|---|
| C1 | `dmg_health` is uncapped: a 117 hit on a 74 HP player is recorded 117. Mean ADR error about 24 (35 to 41 percent inflation) over 30 matches. Fix `user_health - health` clipped at 0, exclude team damage. Residual to scoreboard 1 to 2 ADR after fix. | grok_all.txt (bug 6): "A 117-damage AK hit on a 74-HP player is recorded as 117." | KP#5 |
| C2 | FACEIT UI assists exclude flash assists, engine `assists_total` includes them. | claude_conv2_text.txt L379-386. | KP#6 |
| C3 | `weapon_fire` also logs knife swings and grenade throws; unfiltered shots-fired denominator about 15 percent high (accuracy understated). | claude_conv2_text.txt L65-75 (prompt-writing turn): "an unfiltered shots-fired denominator is wrong by ~15%". | NOT |
| C4 | "Team blind events 167 > enemy blinds 153" (used to argue flash discipline problem) conflated self-blinds with teammate-blinds: 74 of 167 were self, so 93 teammate vs 153 enemy. Even ChatGPT's corrected pass carried this. | claude_conv3_text.txt L~135: "conflates self-blinds with teammate-blinds ... 74 of those 167 are self-blinds". chat_gptCoach2.txt L905-909 is the original claim. | NOT |
| C5 | Clutch counted 146 vs true 45 (322 rounds). Fix: max one 1vX transition per round from ordered deaths. | chat_gptCoach2.txt L1103; claude_conv3_text.txt L~117: "146 vs. 45 clutch situations". | KP#11 |
| C6 | Buy type from `round_start_equip_value` inverted the split (230 eco/81 full/11 force vs true 218/33/71) because it measured what the player walked in with. | claude_conv3_text.txt L~119. | KP#12 |
| C7 | Kill then death under 1 s is a trade/active-fight window, not "failed to disengage". | chat_gptCoach2.txt L1103: "I'm not capable of deciding to take a fight less than 1 second after the first one". | KP#13 |
| C8 | Opportunity to add, not a bug: "deaths where the player dealt zero damage that round" is cheap and three analyses converged on it. | claude_conv2_text.txt L390. | n/a (it was used in later coaching; not in metric docs) |

### 2D. Source and version traps

| ID | Symptom / root cause / fix | Source and quote | KP status |
|---|---|---|---|
| D1 | `is_strafing`, `buttons`, `aim_punch_angle` are absent on FACEIT demos (57/57 in two batches). A counter-strafe metric via the button bitfield is therefore impossible on the owner's own data; an earlier Claude recommendation had assumed it. Fix (v5): stop requesting them on FACEIT; they resolve on Valve/HLTV. | claude_conv2_text.txt L247: "One correction to what I told you last time: `buttons`, `is_strafing` and `aim_punch_angle` are dropped on all 30 FACEIT demos. Counter-strafe detection via the button bitfield isn't available". | NOT (KP#7 is about tournament streams, not FACEIT props) |
| D2 | demoparser2 omits unresolved props silently; exception handling does not catch it. Fix: diff requested vs returned columns into `notes.dropped_props`. | grok_all.txt (bug 8); script_creation_claude header in extract v5 (claude_conv3_text.txt L174). | NOT |
| D3 | Demo tickrate is not server tickrate: FACEIT 64, MM 32 (every other tick missing); tournament demos usually native. First and last ticks contain NaNs. | claude_conv3_text.txt L~170 (LaihoE README search result): "Demo tickrate is not the same as server tickrate ... First and last ticks often have many NaN values". claude_conv2: "Tickrate is confirmed 64 — freeze time is exactly 1280 ticks". | PARTIAL (KP#22 only says validate tickrate before seconds) |
| D4 | Tournament SourceTV lacks player_blind, footstep, reload, zoom, beginplant, begindefuse. Missing stream is unknown not zero. | capability report. | KP#7 |
| D5 | HLTV `-p1/-p2` files are one map; stitch on absolute parser_round. | corpus manifest. | KP#8 |
| D6 | Terminal SourceTV `round==1` reset picked as start. | capability report. | KP#9 |
| D7 | NAV v36 (StarLadder Inferno) is real but unsupported by AWPy (accepts 30 to 35). Registry is fail-soft. | DesignV2.1 L375, L615; ChatGPT_Stage4End.txt L39. | NOT (design doc only) |

### 2E. Fields, units, semantics that lie

| ID | Symptom / root cause / fix | Source and quote | KP status |
|---|---|---|---|
| E1 | Dead players keep coordinates in `player_positions` (12,138 of 48,050 rows) at their death spot; map-control analysis without `is_alive` counts corpses. | claude_conv2_text.txt L69: "Dead players keep coordinates ... counts corpses as map presence." | NOT |
| E2 | Three weapon spellings: `ak47` (death/hurt), `weapon_ak47` (weapon_fire), `AK-47` (state columns). | claude_conv2_text.txt L65-75; later reproduced as KP#24. | PARTIAL (KP#24 names two) |
| E3 | Always-empty or lying fields on FACEIT: `attackerblind` always False; `player_blind.user_flash_duration` always 0.0 (use `blind_duration`); `grenade_thrown`, `molotov_detonate` empty; `bomb_planted.site` is an entity index (706/634), not A/B. | claude_conv2_text.txt L65-75; grok_all.txt final bullet list of the script-findings summary. | PARTIAL (KP#15 covers only site ids) |
| E4 | `grenades.csv.gz` is 88 percent non-trajectory rows (2,030,877 rows in game1, 239,432 with coordinates). Rows without coordinates are the per-tick held-inventory stream, the only way to know what a player died holding. | claude_conv2_text.txt L65-75. | NOT |
| E5 | Units: X/Y/Z and velocity are Hammer units (0.01905 m); `player_death.distance` is already metres, do not convert; pitch is positive downward. | claude_conv2_text.txt L482 (prompt edit): "`player_death.distance` is already **metres** — do not convert". | NOT |
| E6 | `approximate_spotted_by` is the engine's spotted-by mask, not a BSP ray trace; phrase as approximate visibility. | coaching_example.txt L84; ChatGPT_awpyIntegration.txt L1050. | NOT (KP#16-18 are adjacent, not this) |
| E7 | Horizontal yaw error is not crosshair placement; no vertical/head claims. | prompt. | KP#16 |

### 2F. Analysis-logic traps

| ID | Trap | Source and quote | KP status |
|---|---|---|---|
| F1 | "Rounds you survive convert at 95.5 percent; rounds you die convert at 27.8 percent" was presented as "your lurk is high-impact conditional on survival". Surviving to round end is largely a consequence of the team winning, so the gap is close to tautological. The owner sensed it ("quite surreal") but the assistant then built a survival-first drill plan on it. The word tautology never appears in any chat or repo doc. | grok_all.txt L1250: "Your lurk is high-impact *conditional on survival*"; L1322 owner: "The survival conversion rate of 95% is quite surreal." | NOT (KP#25/26 adjacent) |
| F2 | "Stationary deaths" mixed different concepts (opponent stationary vs you, different velocity thresholds). | coaching_example.txt L195: "'stationary deaths' mixed together different concepts". ChatGPT_awpyIntegration.txt L17: will not inherit "stationary attacker = you dry-peeked a held angle". | PARTIAL (KP#18) |
| F3 | Untraded death is not automatically a positioning error for a lurker/anchor. | grok_all.txt L1223 owner: "I'm hesitant to accept these critism's entirely seeing that because I am lurking..."; L1226 assistant: "The earlier report treated every untraded death as a pure leak". | PARTIAL (KP#18, KP#20) |
| F4 | Pro numbers are context, not targets. | coaching_example.txt L~203: "donk's figure is extraordinary and should not become 'you need a 73% opening win rate.'" | KP#20 |
| F5 | Aggregate subtraction assumes subsets (255-237). | V3-D4.1. | KP#21 |
| F6 | Striking splits true of everyone; need a peer baseline. | exploration. | KP#25 |
| F7 | The rifle-speed pair (61 vs 84) compared two different moments (kill speed at own first shot, death speed at the enemy's) and was coloured good/bad. | UX_REVIEW_2026-09-28.md L10. | NOT |
| F8 | "20 of 20 won" survival stat omitted the comparison pair ("21 of 44 won when you died later"). | UX_REVIEW_2026-09-28.md L11. | NOT |
| F9 | Multiple comparisons: recurrence tracked over 16+ dimensions, no forking-path ledger; regression to the mean makes "improved after coaching" easy to overstate. | Claude_v2 consultant (Claude_v2.docx.txt L3063-3082); G_v4.pdf 3.5. | NOT |
| F10 | CanadianIQ gold set is circular (n=1); coaching QA was undefined. | DesignV2.1 A.14 L485 and L2042: "CanadianIQ gold set circular; coaching QA undefined". | NOT |
| F11 | First-pass numbers sounded authoritative and were wrong until the owner pushed back; corrected pass matched ground truth to the tick. | claude_conv3_text.txt L~150: "sloppy first pass, accurate second pass". | process lesson (see 7) |

### 2G. Pipeline and process artefacts

| ID | Trap | Source and quote | KP status |
|---|---|---|---|
| G1 | v7 "selective dense sampling" accidentally became half-match 64 Hz for 10 players; files 19-25 MB each even compressed. | ChatGPT_awpyIntegration.txt L1292: "'selective dense sampling' had accidentally become half-match 64 Hz × 10 players". | NOT |
| G2 | v7.1 disabled dense ticks to save space, which silently emptied every engagements table. | ChatGPT_awpyIntegration.txt L1570: "all eight coaching/engagements.csv files are empty". | NOT |
| G3 | The retained runnable source for M6-M11.1 stops at M3-M5 bundles: passed artefacts cannot be re-audited at source level. | ChatGPT_Stage4End.txt L39-area: "retained runnable .py/.ps1 stage source stops at the M3–M5-era bundles". | NOT |
| G4 | M11 gate reported `success:false` for a legitimately expected zero-family result (the design allows zero); the non-technical owner had to relay files. | ChatGPT_Stage3End.txt: "one of its acceptance gates evaluated false"; earlier "unnecessary local-file dependency" on `M102_handoff.json`. | NOT |
| G5 | `ClaudeCoach.json` export is malformed JSON (adjacent top-level objects). | ChatGPT_Stage4End.txt L~30. | n/a |

Coverage tally: 26 KP rows exist. Of the 58 numbered items above (my count), 20 map cleanly to an existing row, 8 are partial, 27 are NOT listed, and 3 are not applicable (C8 opportunity, F11 process lesson, G5 export quirk). The highest-value NOT items for regression tests: A4, A5, A6, A7, A8, A12 (valid flag), A14, A15, B3, C3, C4, D1, D2, E1, E4, E5, F1, F7, F8, G1, G2.

## 3. Coaching-quality lessons

### 3.1 What the owner most valued (evidence)

1. Coaching that changes its mind. Stage5.txt L50-59 (ChatGPT's own summary of the B1-B4 coaching_example): "it reversed previous bad interpretations instead of defending them; distinguished Batch 1 through Batch 4; noticed that the movement-speed story was more complicated than 'stop moving'; identified the opening-duel improvement as something that genuinely persisted; recognized when teammate-distance numbers had exhausted their usefulness; noticed Mirage regressing while Anubis became a genuine strength; shifted the coaching objective as your play evolved" and then: "That feels like coaching."
2. The owner's benchmark: Stage5.txt L7: "even after we've spent all this time developing all the tools we haven't created something as useful as coaching I've received by simply providing the AI some analysis data and telling them to interpret". OWNER_RULINGS: "Would I use this instead of uploading data to ChatGPT? The overall benchmark. Firm."
3. Specific, checkable claims with denominators and honest caveats. coaching_example.txt L~210: "Only 64 of your 307 deaths (~20.8%) were followed by a teammate killing your killer within six seconds"; "79% of your deaths happened after at least one teammate had already died"; "I don't want to overinterpret a raw distance because maps and roles matter enormously".
4. Diagnosis that separates opponent state from own state: "Are you entering fights with enough control to convert movement into an accurate shot, or are you still transitioning/repositioning when the opponent's shot arrives?" (coaching_example.txt L~196) replaced "you hold still too much".
5. Pro data used as context at the right moment, not from day one: coaching_example.txt L971: "Early on, comparing you too closely with pros would have risked overwhelming the basic diagnosis." and L~1000 "That is exactly the role I think the pro demos should play for us now."
6. Ending on a few sharp questions rather than a verdict list: coaching_example.txt L1013: "those four questions are likely to teach you more than another generic lesson about crosshair placement or counter-strafing".
7. Coaching the situations behind averages: "Now I want to coach the situations that create those averages." (coaching_example.txt end).
8. Positives and role context. Owner to Grok (grok_all.txt L1322): "please also ensure we highlight positives of how I play so that I can lean into those ... A top coach is better than this." And L1223 on lurk/anchor.
9. Fixed, stable report shell; one lesson per Teaching Moment; no statistics on Player Study; literal names, T/CT colours; no "ticks"; AI never controls styling (OWNER_RULINGS, Firm).

### 3.2 What the owner rejected (evidence)

1. Confident narratives resting on unchecked numbers. chat_gptCoach2.txt L1105: "I am frankly disappointed and I need you to show you know what you're talking about instead of throwing stuff that sounds good at me." The numbers were 146 clutches (true 45), inverted buy types, sub-1 s deaths treated as decisions, six-death residual.
2. Generic advice. chat_gptCoach2.txt L909: "So I would stop giving you the generic advice: 'Flash more.'" (the assistant itself); owner's whole framing in coaching_example is against "another generic lesson about crosshair placement or counter-strafing".
3. Blanket rules that ignore role. Grok "stop dying alone" rejected by owner (grok_all.txt L1223); assistant conceded (L1278): "blanket 'stop dying alone' advice is too coarse for your role".
4. Robotic/templated output. Stage5.txt L137: "It should not reduce the coach to filling predefined statistical Mad Libs."; L954 "templated conclusions / statistical Mad Libs"; L1413 "allow considerably more genuine coaching reasoning than later rigid templates permitted".
5. Rigour that never reaches the player. Stage5.txt L61: "Later work became substantially more rigorous, but the system progressively spent more effort proving that it was permitted to say something than proving that what it eventually said was valuable to you." L72: "we then spent a substantial development chain around contracts, candidate populations, falsification objects, selection governance and blocked teaching state while you still did not have a better everyday coaching product."
6. Mapless viewer. OWNER_RULINGS: "A viewer without the map has little practical value ... Firm." Stage5.txt L824: "a mapless viewer still did not provide enough practical value."
7. Internal jargon in the player view ("FOCAL", "ticks", nested denominators).

### 3.3 Hollow-coaching patterns to police

- Sounding-good conclusions (see F11). The corrected numbers were right; the first-pass narrative ("second-order aggression", "you hurt teammates more than enemies") was wrong. Tests must run before prose.
- Survival/impact statistics that are consequences (F1).
- Colour-coded good/bad on unpaired or unlike measures (F7, F8).
- Findings true of everyone presented as personal (KP#25).
- Verdicts from proximity: fight_consequence_support_context was correctly blocked after three independent reviews found proximity did not show support (Stage5.txt L68). The lesson: keep null results visible; but the product then went 100+ steps without shipping a report.
- Pro means as targets (KP#20).
- The system "challenged its own interpretation" so hard it produced no CoachingPlan (M11.1/M11.2: 0 eligible cells, 0 replicated candidates). ChatGPT_Stage4End.txt: "the system failed safely ... it refused to manufacture a coaching finding". That is correct for a claim gate and wrong as a product answer; the coaching_example approach (hypothesis, questions, replay to check) is the missing middle.

### 3.4 Good examples worth keeping as golden fixtures

- coaching_example.txt Batch 1 to Batch 4 arc (opening fights 38.5 percent; T-side opening 31.3, 23.5, 57.5 percent; "You didn't merely become better at surviving CT positions").
- claude_conv3_text.txt tick-exact verification table (kills 250, deaths 204, clutches 45, kill-then-death within 3 s 37/250) as a reconciliation template.
- Grok lurk re-evaluation turn (grok_all.txt L1226-1319) as a model of accepting owner context, minus the survival tautology.

## 4. awpy and demoparser2

### 4.1 demoparser2

Tried and worked:
- Query-style parser: `parse_event(s)`, `parse_ticks`, `parse_grenades`, `parse_header`, `parse_player_info`, `list_game_events`. ChatGPT_awpyIntegration.txt L~20: "demoparser2 behaves as a query-oriented parser ... rather than a conventional event-callback parser." Each public query is a full parser walk (ChatGPT_Stage4End.txt L39).
- Ideas taken from LaihoE examples: `game_time`/`round_start_time` (removes tick math), scoreboard props at final tick, `last_place_name` for bomb site (claude_conv2 prompt-writing turn). Adoption of `last_place_name` site resolution: not verified.
- Capped damage, all-player extraction (v6), dense ticks around engagements (v7), engagements and usercmd availability (v7.6/7.7).
- The project uses a FORK of demoparser2 ("the fork's own Cargo.toml and pyproject.toml" - Claude_v2.docx.txt L234; DesignV2.1 L1810: "risk loading an upstream demoparser beside the project fork").

Failed or bitten:
- `list_game_events()` under-reporting (A6). Silent prop drops (D2). FACEIT-absent props (D1). Tick data 64 vs 32 Hz (D3). `round` column FACEIT-only (A5).
- 22/16,378 NaN-side rows (B2) and dense-tick size explosion (G1, G2).

Decided: never gate on `list_game_events`; use `total_rounds_played` keyed tables; treat unresolved props as unknown.

Opportunities or open threads:
- Owner's `parse_events(["all"])` proposal: unresolved in export (see section 1). Worth a one-hour A/B on a FACEIT and an MM demo: event rows lost (the owner's worry) vs noise.
- Place names via `last_place_name` on events and ticks: cheap, and would give the coaching TEXT stable location words. Caution: the owner asked to avoid unnecessary place/role clutter in the viewer (Stage5.txt L~830), although M1221 added `player_place_labels`, so use them in prose and keep the viewer light.
- Held-inventory stream in `grenades.csv.gz` (E4): "what did I die holding" is a coaching-grade metric (unused grenades at death 43 percent vs everyone 44 percent is KP#26, so this was used once on exploration).
- HLTV/tournament demos at native tickrate: better for reaction-time work (KP#17 left-censoring).

### 4.2 awpy

Facts, quoted:
- The chat named `ChatGPT_awpyIntegration.txt` has no awpy work (see section 1).
- The only awpy decision record is DesignV2.1 A.10 and Appendix G.4 (L1810): "AWPy currently uses demoparser2 as its demo backend and provides NAV, plotting, statistics and visibility utilities. This project explicitly rejects awpy.Demo, AWPy round reconstruction and AWPy statistics on the authoritative decode path because that would create duplicate decoding/round semantics and risk loading an upstream demoparser beside the project fork."
- Used: NAV (versions 30-35; v36 unsupported, DesignV2.1 L615, L1827), VPhys to `.tri` to BVH `VisibilityChecker` as a static collision sensor. Stage4End L39: "VphysParser/BVH/VisibilityChecker are appropriately being treated as static-collision sensors rather than awareness truth." M10.5-M10.11 froze static LOS as an optional mechanism sensor, not an opportunity or promotion rule.
- Design rule: 12G "Exact 2025 versions were not available from the inspected AWPy-data release history; current geometry was explicitly rejected as historical evidence." (DesignV2.1 L366).
- Radar: Living Onboarding L114, L151: "V4-V2 uses current AWPy radar/map transforms only as a clearly disclosed orientation layer." But `M123_ai_handoff.json`: decision `M123_PASS_PROVENANCE_AUDIT_RADAR_UNRESOLVED`, `candidate_asset_count: 0`, `selected_profile: null`, safety contract "filename_only_never_authorizes_asset", "current_game_asset_never_auto_authorized", "radar_and_transform_both_require_explicit_verified_provenance". `V4V1_ai_handoff.json`: `"real_radar_gate": "Requires explicitly validated historical radar + transform profile."`. `M1221_ai_handoff.json`: `viewer_mode: WORLD_COORDINATE_SCHEMATIC_FALLBACK`, `historical_radar_substituted: false`.
- The V4V2 map dual-pane package: living onboarding L277 "real AWPy map binding awaits user environment"; device folder `Development/Steps/V4V2_MAP_DUAL_PANE_VIEWER` is empty. Never run.
- `awpy-env` at `%LOCALAPPDATA%\CS2Coach\awpy-env\Scripts\python.exe` exists in the living onboarding (L166-167), so an environment was built.

Reasoned "no" versus "never done":

| Item | Reasoned decision? | Evidence |
|---|---|---|
| `awpy.Demo`, rounds, stats as the authoritative path | Reasoned NO | DesignV2.1 L1810, L607 |
| Current-game geometry/radar as HISTORICAL evidence | Reasoned NO (defensible) | DesignV2.1 L366; M123 safety contract |
| Current radar as a disclosed orientation layer only | Reasoned YES, but NEVER DELIVERED | Living Onboarding L151; V4V2 folder empty |
| awpy as an independent cross-check of round/kill/damage semantics (would have caught A1-A8 early) | Not found discussed at all | no chat mentions it; design rule forbids only the authoritative path |
| awpy plotting/heatmap/radar rendering for the player report | Not found discussed | consultants: Grok "2D radar cannot teach every mechanical skill" (A.14) |
| NAV areas/place names to give stable locations to coaching language | Not found discussed as a coaching use; NAV was used as sensor only | Stage4End L39 |

I could not verify awpy 2.x capabilities beyond what the chats and design docs say. My own knowledge (awpy ships radar images and calibration constants, plotting, a NAV area API, and a demo-derived stats module) is not confirmed from this package; the separate awpy audit agent covers the actual repo.

Decision consequence: the radar block is an over-application of fail-closed. The owner has ruled (Firm) that the viewer needs the map and that a labelled orientation layer is acceptable. Consultants said the same. G_v4.pdf 3.9: "A schematic viewer may be pedagogically weak for the exact spatial lessons (positioning, trades) that motivate the product ... a bounded calibration experiment ... should be able to close that question." Gemini_v2.pdf section 4 gave a cheap safeguard: control points, hash, and a drift threshold that falls back to text. M123 still ended "Historical radar binding remains unresolved" and moved on.

## 5. Asked for or promised, never delivered (status as of 2026-09-28)

| Feature | Where asked or promised | Status and evidence |
|---|---|---|
| Viewer2D with real map radar | OWNER_RULINGS Viewer (Firm); Stage5.txt L83, L824, L844; ROADMAP Next; G_v4 3.9 | Temporal schematic viewer exists (V4V1, 48 cases). Map-backed dual pane prepared, never run (empty device folder). M123: radar unresolved. |
| Longitudinal coach memory (stop coaching solved problems, question earlier claims) | OWNER_RULINGS "Should change its mind and remember ... Firm as a direction; Open for the first build"; Stage5.txt L767 "Longitudinal Coaching Is Probably One of the Product's Strongest Advantages" | Stage 5 slice covers B1-B4 batches (Stage5.txt L1483, L1561: "78 B1-B4 tagged demos"); no persistent memory of prior claims/prose. G_v4 3.5: longitudinal statistics unresolved; PreviousStudyReview should wait. |
| Cope Barn | Stage5.txt L31, L906; V4.1 consultant table: "Remove Cope Barn concept entirely - Not selected - Owner sees value in the entertainment mode" | Concept only; only quarantine from serious state exists (Stage5.txt L89). |
| Player Study | Stage5.txt L79 | "actionability and example rationale remained unresolved". A descriptive pack and bounded AI interpretation exist. |
| Analyst Desk | Stage5.txt L87 | "largely a defined product concept rather than an implemented full workspace". |
| Population baselines / pro comparison | ADR-012 (no "normal/strong/weak" without a baseline); coaching_example.txt L971; ROADMAP Parked: team/opponent/comparison | M10 built 14,750 opportunity rows across 357 demos and 891 players (Stage4End) and a frozen z threshold 3.637; M11.1/11.2 found 0 eligible cells. Whether any baseline feeds Player Study copy: not verified. Pro corpus (donk, mezii) is used as context in the chat coaching only. |
| Drills, cues, transfer tests | M11 contract "cue, drill, transfer test, countermetric" (Stage4End); Stage 4 plan: "qualified tendency -> one priority -> cue -> drill -> match test -> balancing metric" | Contract frozen; no CoachingPlan emitted (0 eligible families). `M121_coaching_plan_v1.json` and `M121_player_brief_v1.json` exist on the device; not read. ROADMAP Parked lists "training registry". |
| Owner's "ask for a feature, get it coherently" | Stage5.txt L9 | Process ask, see section 6. |
| Multiple explanations and positives in coaching | grok_all.txt L1322 | Delivered ad hoc in chats; not a requirement in the coaching prompt or the report shell as far as I saw. |
| Replace/verify extractor with `parse_events(["all"])` comparison | claude_conv3 MSG 2 | Not answered in the export. |
| Second-player generalisation gate | DesignV2.1 A.14 (Claude, Grok consultants); G_v4 3.4 "Reinstate the second-player gate" | M11.2 ran non-CanadianIQ pug and donk/mezii validation and found nothing replicated; a human second-player review is absent. |

## 6. Process failures (with concrete examples)

1. Regression to things the owner forbade. Stage5.txt L5: "they routinely kept the vision I had out of their mind and continued to either regress to previous things I had asked them not to do or they demonstrated failed understanding". The owner's own repeated rulings (map needed, no engineering words, AI never styles, fixed shell) had to be captured in OWNER_RULINGS.md at the end, still marked DRAFT.
2. Fix-one-break-another in extractors. Knife handling (A1) then Grok's fix dropped round 1 (A2); Claude's first flag-based fix was wrong (A3); v2 gated on `list_game_events` (A6) then fixed only in v3/v4; v6 NaN to LOSS (B2); v7 fixed dense size by disabling dense ticks and thus emptied engagements (G1, G2).
3. Contradicted own earlier advice. claude_conv2 L247: "One correction to what I told you last time" (counter-strafe via buttons). claude_conv1 L314 admitted the CT/T tally bug after presenting "impossible scorelines".
4. Ignoring own prompt. chat_gptCoach2.txt L1109: "I drifted away from the standard in your own coaching prompt", which "explicitly says to compute rather than estimate, use economy.csv ... rebuild 1vX states from the ordered player_death sequence".
5. Scope shrink and verdicts too early. Grok's initial "first row ... knife/warmup ... will be excluded" (script_creation_grok.txt L67); ChatGPT B4.5 first pass with three wrong headline numbers (C5-C7).
6. Reverting requested things by attrition. The owner's feedback was that the map is what makes the viewer useful; M1221, M123 and V4V1 each note "historical radar unresolved" and ship the schematic. The map-backed package (V4V2) that finally tried an orientation layer was prepared but never run (empty device folder).
7. Rigour displaced product. Stage5.txt L61, L72 (quotes in 3.2). Consultant G_v4: "V4 adds six new objects, 40+ module families, 12 candidate ADRs and a nine-phase roadmap ... Stop expanding the design and build the V4-B spine against real data." DesignV2.1 A.14 Grok: "the product still looked more like an analysis system than a learning system".
8. Owner as file courier for non-technical debugging. ChatGPT_Stage3End.txt: PowerShell `-ExecutionPolicy Bypass` runs, "Upload Stage3_M11\M11_handoff.json", `success:false` on an expected zero result, a hidden dependency on an old `M102_handoff.json`.
9. Provenance gaps. Stage4End L39: retained runnable source stops at M3-M5; M85F "omitted due to size"; ClaudeCoach.json malformed; `ChatGPT_awpyIntegration` name does not match content; Stage 2 AWPy chat missing.
10. Single-reviewer validation. G_v4 3.4: "Validation is concentrated in one person ... apparently a single focal player."
11. Circular validation. DesignV2.1 L2042 "CanadianIQ gold set circular; coaching QA undefined"; consultant bias-control (v3.1) noted a prompt naming suspected weak spots is not independent replication.
12. First-pass authority. claude_conv3: "jumping to a conclusion with a plausible-sounding methodology, presenting it confidently, and only correcting it when you apply pressure."

## 7. Suggested guardrails for the new senior developer

Add to KNOWN_PITFALLS.md (proposed rows, each a regression test):
1. Halftime swap: derive score from per-round side or clan, never raw CT/T tallies (A4).
2. Never gate core events on `list_game_events()`; the test asserts `round_start`/`round_end` parse when the listing omits them (A6).
3. `round` column is FACEIT-only; match-start must fall back on Valve/HLTV (A5).
4. Missing `round_freeze_end` (surrender): key by `total_rounds_played`, fall back to `round_start`; test with 1-10 ct_surrender (A7).
5. Zero-kill rounds must survive: trust `round_end` count (A8).
6. `valid` must be false unless target resolved and every round has result (A12).
7. Winner/reason: normalise FACEIT strings and Valve ints (winner 2=T,3=CT; reasons 8/9 name loser) before any side logic (B3).
8. FACEIT lacks `buttons`, `is_strafing`, `aim_punch_angle`; no counter-strafe claim from buttons on FACEIT (D1).
9. Diff requested vs returned props on every parse (D2).
10. Scoreboard reconciliation as a build gate: K/D exact rate (56/58 at v3) and assist definition stated; bot-substitution matches flagged (A14, A15).
11. Shots-fired denominators exclude knife and grenade `weapon_fire` rows (C3).
12. Self-blind vs teammate-blind vs enemy-blind reported separately (C4).
13. Dead players keep coordinates; `is_alive` filter for map presence (E1).
14. Units: `distance` metres, Hammer units elsewhere (E5).
15. `approximate_spotted_by` is not LOS; wording rule (E6).
16. Outcome-derived stats (survival, alive at end) cannot be presented as impact without checking direction of causation (F1).
17. Paired measures must be measured at the same event and never colour-coded good/bad when unpaired (F7, F8).
18. Extractor batch profiles must have an output-shape smoke test (non-empty `engagements.csv`, file size budget) (G1, G2).

Process guardrails:
- Ship the coaching product loop first. The owner's benchmark is "better than pasting analysis into ChatGPT". Build a report that includes a small number of hypotheses, checked with software-computed numbers, ending in questions plus replay. Keep the gates as claim ceilings, not as reasons to say nothing.
- Deliver the map. Use awpy radar plus calibration as a labelled orientation layer now (owner ruling: Firm; project rule already allows it). Keep historical-evidence status separate. Test with 2 to 3 maps first.
- Run awpy `Demo` (or any second parser) only as a cross-check harness against round, kill and damage counts; this respects "not on the authoritative path" and would catch A1-A8 style regressions.
- Every new metric: name the denominator, the comparison pair, and a peer baseline before it may be coloured.
- Keep a golden regression set: the corrected B4.5 numbers (250/204 K/D, 45 clutches, 218/33/71 buys, 32-20 openings, 16/37 kill-then-death) and the surrender 1-10 demo.
- When an owner reaction contradicts a number ("that feels wrong"), treat it as a bug report: recompute from raw events before replying (the owner was right on 146, buy types, sub-1 s).
- Persist owner rulings with reasons (OWNER_RULINGS is a good start; get Dawson to confirm it).

## 8. Where to look first (fast index)

- Bug detail: `grok_all.txt` L295-372 (a Grok-authored bug and schema-evolution summary across the Claude/ChatGPT chats), `claude_conv2_text.txt` L204-390.
- Owner voice: `Stage5.txt` L5-12, L50-72, L150-158; `chat_gptCoach2.txt` L1100-1112; `grok_all.txt` L1223, L1322.
- Best coaching examples: `coaching_example.txt` L195-225, L555-565, L960-1020.
- awpy/radar: `DesignV2.1_CURRENT.docx.txt` L366, L607, L615, L1810-1830; device `Stage3_M122_REPLAY_VIEWER/M123_ai_handoff.json`; `V4V1_TEMPORAL_VIEWER2D_FOUNDATION/V4V1_ai_handoff.json`.

## 9. Not verified or not found

- Real AWPy Stage 2 chat (12E to 12J): not in the package.
- Whether `parse_events(["all"])` was ever tried: not found.
- Whether `last_place_name` resolution and `game_time`/`round_start_time` are used in the current extractor v7.7: `game_time`/`round_start_time` appear in the v2 summary; the rest not verified (I did not read `extract_demos_v7dot7.py`).
- Content of `M121_coaching_plan_v1.json`, `M121_player_brief_v1.json`, M130 spatial ablation, Misc stratbook, the DeepSeek and Grok consultant PDFs: not read.
- Line numbers marked with a tilde (L~) are approximate because I re-located quotes through grep of the extracted text rather than opening each spot; the quoted strings themselves were copied from the source.
- Batch-label and metric-definition drift across analyses is indicated in coaching_example.txt L195 (different thresholds) but I did not enumerate every instance.
- The tallies in section 2 are my count of the rows above, against the 26-row KNOWN_PITFALLS.md, not an automatic diff.
