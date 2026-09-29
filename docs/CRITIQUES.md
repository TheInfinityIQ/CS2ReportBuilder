# Critique log (regression guard)

Every critique of the product, who raised it, what we decided, and whether it is done. Read this
before changing the report, the analyst or the coach. A "done" item that breaks again is a
regression. Sources: **O** = Dawson (owner), **U1/U2** = outside UX reviews (v1 in
UX_REVIEW_2026-09-28.md, v2 2026-09-28 evening), **E** = outside evidence review of MIMY v2
(2026-09-28), **S** = self-found.

Status: OPEN, DONE (with how it is enforced), REJECTED (with reason).

## The idea of the product (never lose this)
- A player uploads a batch of their demos and gets coaching they would choose over pasting stats
  into ChatGPT: where and why they win or lose, shown on the map, with honest confidence. (O)
- Two audiences in one file: Player Study (no maths on the surface) and Analyst Desk (everything).
- Coaching judges decisions in context, like a human demo review; it never just restates stats.
- Only the submitted batch is used as a baseline (ADR-013). Later: continuous coaching across batches.

## Owner critiques
| ID | Critique | Decision | Status |
|---|---|---|---|
| O-1 | Coaching was hollow: restated data, "good job" | Analyst finds patterns, coach teaches from them with real rounds | DONE v2 (analyst.py, KeyMoments); keep testing |
| O-2 | Need an analyst stage that lists everything it finds, interesting or not | Analyst Desk findings tables incl. null results | DONE v2 |
| O-3 | "Normal" needs a baseline | ADR-012/013; verdict words tied to tests | DONE |
| O-4 | Never compare to a database; batch only (lobby peers, own level, own history) | ADR-013 | DONE (findings.py baseline = same matches) |
| O-5 | Kill feed is fun but gives no understanding | Replace with 2D viewer moments; timeline only as fallback | DONE v3: KeyMoments show a map replay; kill list collapsed under it |
| O-6 | We need the 2D viewer now; analysis built without it may be wasted | Viewer is the next build; moments must be designed around it | DONE v3.3: radar images installed (11 maps); viewer rebuilt around real demo data (see V-1..V-12) |
| O-7 | "What this study covers" is far too wordy | Short scannable block: Keep / Work on / Re-check | DONE v3: three lines, Keep / Work on / Re-check (plan rule in COACHING_LESSONS) |
| O-8 | "Anchor" was not earned: roles come from positional data | Role/position only from positions; state the observation, name the position only when confident | PARTIAL v3: role label removed, described as where fights happen; position recognition not yet in product |
| O-9 | The AI coach will only know what is in the package | All lessons go into COACHING_LESSONS.md, later compiled into the coach prompt | ONGOING |
| O-10 | Keep critiques tracked so nothing regresses | This file | DONE |
| O-11 | AI must never control styling; blocks are software | Theme + module registry | DONE (validator rejects styling fields) |
| O-12 | Player Study: no maths without "How is this calculated" | Disclosures | DONE |

## Evidence review of MIMY v2 (E)
| ID | Critique | Decision | Status |
|---|---|---|---|
| E-1 | Dust2 r19 note was wrong: it was a CT retake with the bomb planted, round won by defuse | Moments must show bomb state and round outcome as computed facts; coach may not contradict them | DONE v3: software "What happened" facts (side, result and how, bomb state, numbers, kills ±5 s) above every coach note |
| E-2 | Dust2 r1 note was wrong: MIMY traded Greed___ 0.16 s later | Trade detection must consider every teammate death, and moments must list trades as facts | DONE v3: kills within 5 s listed as facts; example note rewritten |
| E-3 | "Deaths while ahead / all deaths" is not the chance of losing an advantage | Build advantage-state denominators: occurrences of each state and what followed | OPEN |
| E-4 | 900 units ignores walls: "potential trade situations", not opportunities | Rename now; geometry/visibility later | DONE v3: renamed "potential trade situations"; geometry still OPEN |
| E-5 | Post-round deaths must be separated from live-round conversion | impact.py excludes after_round_end; show it separately in moments | PARTIAL |
| E-6 | Denominators differ (449 vs 447 deaths, 45 vs 44 first deaths) without explanation | "Why counts differ" note on the Desk | PARTIAL v3: Desk explains why counts differ; per-metric eligibility table OPEN |
| E-7 | Tests treat events as independent; cluster by match | Match-level bootstrap or clustered tests | OPEN |
| E-8 | Split-half agreement is not replication; findings near q=0.08-0.09 are exploratory | Wording tier (see U2-13) | OPEN |
| E-9 | Recommend a practice block with process goals and a re-check | Summary "Re-check next time" + continuous coaching later | PARTIAL |

## UX review v2 (U2)
| ID | Critique | Decision | Status |
|---|---|---|---|
| U2-1 | "Same" is not equivalence | Say "No detectable difference in this sample"; equivalence only with a stated margin | DONE v3: "No detectable difference in this sample"; test guards the old word |
| U2-2 | First-death question vs denominator mismatch (deaths vs rounds) | Per-round rate for "how often do I die first" | DONE v3: value.first_death_rounds (first deaths / rounds played) |
| U2-3 | "Free first kills", "a player down for the rest of the round" overstate | Wording rules in COACHING_LESSONS | DONE v3 (plan wording; rule in COACHING_LESSONS) |
| U2-4 | Correlation turned into character ("disciplined anchor") | Same as O-8 | PARTIAL v3 (= O-8) |
| U2-5 | "Reaction and composure" is an unsupported mechanism | Coach may state observed pattern; mechanisms only as a labelled interpretation | DONE v3 (plan says the data does not say why) |
| U2-6 | "Stop taking the fight when ahead" too categorical; caveats belong beside the advice | Advice must name its exceptions next to it | DONE v3 (exceptions in the takeaway) |
| U2-7 | "Cheapest round win" implies an unestimated ranking | No ranking words without an opportunity model | DONE v3 (removed) |
| U2-8 | Trading metric distance-only (see E-4) | | OPEN |
| U2-9 | "Missing it turns one death into a lost round" is causal | Wording rule | DONE v3 |
| U2-10 | Separate Observed from Coach interpretation in moments | Two labelled parts per moment; observed part generated by software | DONE v3: "What happened (from the demo)" vs "Coach's read"; test guards it |
| U2-11 | Bars scaled to the larger value exaggerate small percentages | Fixed 0-100 scale or dot plot | DONE v3: 0-100% scale with axis labels |
| U2-12 | Colour encodes both identity and judgement | You/Peers always the same colours; judgement only in verdict text | DONE v3: You always dark, peers always grey; judgement only in verdict text |
| U2-13 | "Clear" too strong | "Supported in this sample" | DONE v3: "Supported in this sample" |
| U2-14 | p = 0.000 | Show "<0.001" | DONE v3: <0.001 |
| U2-15 | Explain the statistical method and unit of independence | Desk "Statistical method" section | PARTIAL v3: method paragraph states event-level independence; clustered tests OPEN (E-7) |
| U2-16 | Define the halves | Alternating games by date; say so | DONE v3: alternate games in date order |
| U2-17 | Explain differing counts | = E-6 | PARTIAL v3 (= E-6) |
| U2-18 | Baseline not role-adjusted | Label "same-lobby, all roles"; role-matched peers once positions are recognised | OPEN |
| U2-19 | Player Study too long (10k px mobile); timelines dominate | Show 2-4 relevant events, "Show full round"; viewer replaces most text | PARTIAL v3: full kill list collapsed; page still ~12k px on phones |
| U2-20 | Actionable summary at the bottom | First-screen Keep / Work on / Re-check with links (= O-7) | PARTIAL v3: first-screen Keep / Work on / Re-check; links to sections OPEN |
| U2-21 | No in-page navigation | Compact section nav | OPEN |
| U2-22 | 9-column tables on phones | Card rows on mobile, IDs out, swipe hint | OPEN |
| U2-23 | Analyst Desk ~17-20k px; needs filters | Filter by topic/verdict/map/side; collapse "no difference" and "too few" | OPEN |
| U2-24 | Developer IDs take table width | Move to row details | OPEN |
| U2-25 | "All figures" schema awkward | Result / Sample / Definition / Scope; N/A explicit | OPEN |
| U2-26 | Game list uses UUIDs | Date, map, score first | OPEN |
| U2-27 | Tabs lack full ARIA pattern | aria-controls, tabpanel, arrow keys | OPEN |
| U2-28 | Tab switch resets scroll | Keep per-tab scroll | OPEN |
| U2-29 | Tabs fail without JS | Anchor links enhanced into tabs | OPEN |
| U2-30 | Text too small (11.5-12.5 px) | Minimum 13-14 px | OPEN |
| U2-31 | Contrast: T orange 3.64:1, green badge 4.39:1 | Darken | PARTIAL v3: T orange darkened to #8f560a; badge green OPEN |
| U2-32 | "Complete for this study" says nothing | "30/30 demos passed integrity" + date range | PARTIAL v3: "30/30 demos passed the integrity check"; date range OPEN |
| U2-33 | "Player Study" repeated | Use eyebrow for date range / generated date | OPEN |
| U2-34 | Print prints everything; break rules too coarse | Print Player Study vs full; protect modules not sections | OPEN |
| U2-35 | No main landmark | Wrap in main | OPEN |

## 2D viewer review v3.1-v3.3 (V) - owner comparison against a reference viewer
| ID | Critique | Decision | Status |
|---|---|---|---|
| V-1 | Show all player names, not only the subject | Team-tinted name pills on every pin; nudged apart so they do not stack | DONE v3.3 |
| V-2 | Equipped weapon on each player | `active_weapon_name` IS in `player_positions` per frame (earlier note saying it was not was wrong). Icon by category on the name pill and in the kill feed | DONE v3.3 |
| V-3 | Facing cone / pointer | Continuous view angle is NOT in the export. Yaw exists only at events (shots, hits, kills). Pin points at the last recorded aim (<=1.5 s) else direction of travel; a shaded cone shows recorded aim only; legend says so. Yaw convention checked against 175 kills (median error 0.4 deg) | DONE v3.3; continuous facing needs the usercmd view-angle capture (`usercmd_availability.json` says the props exist) - OPEN |
| V-4 | Pointer too small / disappears | Pin marker with a 1.7 R nose; heading falls back to last known instead of vanishing; direction computed in pixel space (v3.1 mixed world and pixel units) | DONE v3.3 |
| V-5 | Nade arcs looked invented | Removed the bezier. Throw spot and time now come from `weapon_fire` (v3.1 wrongly used the thrower position at detonation). A straight dashed line joins throw spot to landing spot only while in flight; legend states the flight path is not recorded | DONE v3.3; true arcs/bounces need projectile positions - not in the data, OPEN |
| V-6 | Nades should look better | Smoke at its in-game radius (144 units), duration from the real `smokegrenade_expired` event, dashed rim in the thrower's team colour, cloud/flame/burst icons | DONE v3.3 |
| V-7 | Health / weapons / team panel like the reference | Roster under the viewer: HP bar, armour, equipped weapon, alive count, dead struck through. Money and utility inventory not shown yet | PARTIAL v3.3 |
| V-8 | Kill feed | On-canvas feed (killer, weapon icon, headshot mark, victim); text feed kept for screen readers only | DONE v3.3 |
| V-9 | Flashed players | White ring while `flash_duration` > 0.3 s | DONE v3.3 |
| V-10 | Win vs loss distinction across viewers | Green/red left border, Won/Lost tag, filter bar by outcome and map | DONE v3.1 |
| V-11 | Many viewers are messy | One drawer per round, first open, opening one closes the others; filter bar applies to drawers | DONE v3.1 |
| V-12 | Coach limited to 4 teaching moments | Not a builder cap (the plan had 4). KeyMoments now allows 1-6 rounds per block | DONE v3.1 |
| V-13 | Every moment has a 2D viewer and no charts | Dashboard of per-map, side and trend charts (owner likes graphs); design once the statistical layer (E-3, E-7) is fixed | OPEN (planned, see ROADMAP) |

## External review of v3.3 (R) - full product pass, 2026-09-29
Verified against the code before logging. "Agree" means the claim was checked and is true.

| ID | Critique | Decision | Status |
|---|---|---|---|
| R-1 | HE grenade shows a rifle icon (Dust2, 0:48): `wcat()` regex misses "High Explosive Grenade" and defaults to rifle; kill feed also falls back to rifle | Agree (a real bug of mine). Replace regex with an explicit map from every raw item name to one canonical id; add an `unknown` icon; the report build FAILS on an unmapped name. The 58 distinct names in the 30 MIMY games are the starting table | DONE v3.4 (`report/weapons.py`: 57 names + kill codes mapped, `unknown` icon, build fails on unmapped; `tests/test_weapons.py`) |
| R-2 | Category glyphs look crude; AK = M4, AWP = Scout; blur when the canvas is scaled to 350 px | Agree. Interim: canonical ids + text chips (AK, M4A1-S) and no glyph below a minimum displayed map width. Real per-weapon silhouettes need an icon set with a licence the owner approves; I will not hand-draw 58 inaccurate ones | PARTIAL v3.4 (exact weapon name as text in the kill feed and roster; icons are labelled as item kind; no glyph below 460 px; real silhouettes still need an approved icon set) |
| R-3 | "Equipped weapon" is the wrong term (it is the active item: HE, knife, bomb) | Agree; use "active item" in the legend and roster | DONE v3.4 (legend says the icon is the kind of item held; roster shows the exact active item) |
| R-4 | The pin mixes three meanings (recorded aim, movement, last known) | Agree. With 8 Hz tracks the pin becomes real facing always; without them, pin only for recorded aim, a short tail for movement, neutral dot when unknown | DONE v3.4 (real 8 Hz yaw when the sidecar exists; else recorded aim pin, movement trail, neutral dot) |
| R-5 | Heading cached on `p._th` survives scrubbing backwards (replay state depends on how you arrived) | Agree. Make heading stateless: derive only from data at or before t | DONE v3.4 (stateless `facing()`; no cached heading) |
| R-6 | Cone shows 1.2 s but the pin and legend say 1.5 s | Agree; one constant | DONE v3.4 (single `AIM_HOLD` = 1.5 s) |
| R-7 | Labels are canvas text scaled down (microscopic on phones); need full-screen mobile viewer | Agree. Render labels and kill feed as DOM/SVG at fixed CSS size; add "Expand replay" | DONE v3.4 differently (canvas labels are scaled to a fixed on-screen size instead of DOM/SVG; "Expand replay" full-screen mode added; checked at 390 px) |
| R-8 | Timeline needs markers (focus moment, plant, kills, round end); step and prev/next-event controls; two-row mobile toolbar | Agree | DONE v3.4 (timeline markers, prev/next event, ±0.5 s step, two-row toolbar; step buttons hidden under 560 px) |
| R-9 | Layer toggles (Players / Aim / Utility / Feed); default to the smallest set that explains the moment | Agree | DONE v3.4 (Names / Facing / Utility / Feed toggles, `aria-pressed`; all on by default because the owner asked for each of them) |
| R-10 | Legend paragraph repeats under every replay | Agree; move behind a "How to read" control | DONE v3.4 ("How to read this replay") |
| R-11 | Roster: dead rows too faint (opacity .45), need an amber mid-HP state, compact rows on mobile | Agree | DONE v3.4 (amber mid-HP, dead rows at .72 opacity with red "dead", 2-column roster on phones) |
| R-12 | Filter bar sits under "What this study covers" so it looks global but only filters the replay drawers; contradicts "five maps" | Agree (my placement error). Make filters local to each replay set, labelled "Filter example replays", with an empty state and `aria-pressed`; keep label with its buttons on mobile | DONE v3.4 (each replay set has its own "Filter example replays" bar with counts, empty state, reset; global bar removed) |
| R-13 | Drawer header repeats inside the open drawer; consider all drawers closed on mobile; initialise viewers lazily on first open | Agree | PARTIAL v3.4 (duplicated header removed, viewers start lazily on first open; first drawer stays open by owner request, mobile-collapsed default not done) |
| R-14 | Summary rows (Maintain / Practice / Measure next), date-range eyebrow instead of "Player Study" | Agree | OPEN (= U2-20, U2-33) |
| R-15 | 7% vs 10% bars vanish on a 0-100% axis; use a dumbbell / dot plot with the difference | Agree; do with the planned dashboard work | OPEN |
| R-16 | "Both halves" are interleaved games (`i % 2` over sorted demo ids in `analyst._half_map`), not early vs late | Agree, verified in code. Say "both interleaved splits agree", or compare games 1-15 with 16-30 | DONE v3.4 (wording: "interleaved splits (alternate games), not early versus late") |
| R-17 | Headline "win more than most" and "worst way to start a fight" are unsupported rankings | Agree (= P0 in the v3 review); reword to the pooled same-lobby baseline / "a difficult way to start a fight" | DONE for the MIMY v3 plan (reworded); the rule still applies to every new plan |
| R-18 | Analyst Desk on phones is a wide table; needs metric cards, filters, sticky nav; ARIA tab pattern; per-tab scroll; contrast of the green badge; badge size; print; `<main>` | Agree | OPEN (= U2-22, 23, 27, 28, 30, 31, 34, 35) |

## Self-found (S)
| ID | Critique | Decision | Status |
|---|---|---|---|
| S-1 | Duplicate matches across batches inflated a finding to "credible" | load_fights dedup, pitfall 28 | DONE |
| S-2 | "Alone" deaths counted clutches (no teammates alive) | Only deaths with living teammates | DONE |
| S-3 | Coach notes written from a kill feed without round state (caused E-1, E-2) | Observed-facts block generated by software under every moment | DONE v3 (= E-1) |
