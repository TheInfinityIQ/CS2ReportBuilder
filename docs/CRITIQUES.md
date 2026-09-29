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
| O-5 | Kill feed is fun but gives no understanding | Replace with 2D viewer moments; timeline only as fallback | OPEN (viewer) |
| O-6 | We need the 2D viewer now; analysis built without it may be wasted | Viewer is the next build; moments must be designed around it | OPEN (priority 1) |
| O-7 | "What this study covers" is far too wordy | Short scannable block: Keep / Work on / Re-check | OPEN |
| O-8 | "Anchor" was not earned: roles come from positional data | Role/position only from positions; state the observation, name the position only when confident | OPEN (position recognition prototype 66% vs 10% baseline) |
| O-9 | The AI coach will only know what is in the package | All lessons go into COACHING_LESSONS.md, later compiled into the coach prompt | ONGOING |
| O-10 | Keep critiques tracked so nothing regresses | This file | DONE |
| O-11 | AI must never control styling; blocks are software | Theme + module registry | DONE (validator rejects styling fields) |
| O-12 | Player Study: no maths without "How is this calculated" | Disclosures | DONE |

## Evidence review of MIMY v2 (E)
| ID | Critique | Decision | Status |
|---|---|---|---|
| E-1 | Dust2 r19 note was wrong: it was a CT retake with the bomb planted, round won by defuse | Moments must show bomb state and round outcome as computed facts; coach may not contradict them | OPEN (observed-facts block) |
| E-2 | Dust2 r1 note was wrong: MIMY traded Greed___ 0.16 s later | Trade detection must consider every teammate death, and moments must list trades as facts | OPEN |
| E-3 | "Deaths while ahead / all deaths" is not the chance of losing an advantage | Build advantage-state denominators: occurrences of each state and what followed | OPEN |
| E-4 | 900 units ignores walls: "potential trade situations", not opportunities | Rename now; geometry/visibility later | OPEN |
| E-5 | Post-round deaths must be separated from live-round conversion | impact.py excludes after_round_end; show it separately in moments | PARTIAL |
| E-6 | Denominators differ (449 vs 447 deaths, 45 vs 44 first deaths) without explanation | "Why counts differ" note on the Desk | OPEN |
| E-7 | Tests treat events as independent; cluster by match | Match-level bootstrap or clustered tests | OPEN |
| E-8 | Split-half agreement is not replication; findings near q=0.08-0.09 are exploratory | Wording tier (see U2-13) | OPEN |
| E-9 | Recommend a practice block with process goals and a re-check | Summary "Re-check next time" + continuous coaching later | PARTIAL |

## UX review v2 (U2)
| ID | Critique | Decision | Status |
|---|---|---|---|
| U2-1 | "Same" is not equivalence | Say "No detectable difference in this sample"; equivalence only with a stated margin | OPEN |
| U2-2 | First-death question vs denominator mismatch (deaths vs rounds) | Per-round rate for "how often do I die first" | OPEN |
| U2-3 | "Free first kills", "a player down for the rest of the round" overstate | Wording rules in COACHING_LESSONS | OPEN |
| U2-4 | Correlation turned into character ("disciplined anchor") | Same as O-8 | OPEN |
| U2-5 | "Reaction and composure" is an unsupported mechanism | Coach may state observed pattern; mechanisms only as a labelled interpretation | OPEN |
| U2-6 | "Stop taking the fight when ahead" too categorical; caveats belong beside the advice | Advice must name its exceptions next to it | OPEN |
| U2-7 | "Cheapest round win" implies an unestimated ranking | No ranking words without an opportunity model | OPEN |
| U2-8 | Trading metric distance-only (see E-4) | | OPEN |
| U2-9 | "Missing it turns one death into a lost round" is causal | Wording rule | OPEN |
| U2-10 | Separate Observed from Coach interpretation in moments | Two labelled parts per moment; observed part generated by software | OPEN |
| U2-11 | Bars scaled to the larger value exaggerate small percentages | Fixed 0-100 scale or dot plot | OPEN |
| U2-12 | Colour encodes both identity and judgement | You/Peers always the same colours; judgement only in verdict text | OPEN |
| U2-13 | "Clear" too strong | "Supported in this sample" | OPEN |
| U2-14 | p = 0.000 | Show "<0.001" | OPEN |
| U2-15 | Explain the statistical method and unit of independence | Desk "Statistical method" section | OPEN |
| U2-16 | Define the halves | Alternating games by date; say so | OPEN |
| U2-17 | Explain differing counts | = E-6 | OPEN |
| U2-18 | Baseline not role-adjusted | Label "same-lobby, all roles"; role-matched peers once positions are recognised | OPEN |
| U2-19 | Player Study too long (10k px mobile); timelines dominate | Show 2-4 relevant events, "Show full round"; viewer replaces most text | OPEN |
| U2-20 | Actionable summary at the bottom | First-screen Keep / Work on / Re-check with links (= O-7) | OPEN |
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
| U2-31 | Contrast: T orange 3.64:1, green badge 4.39:1 | Darken | OPEN |
| U2-32 | "Complete for this study" says nothing | "30/30 demos passed integrity" + date range | OPEN |
| U2-33 | "Player Study" repeated | Use eyebrow for date range / generated date | OPEN |
| U2-34 | Print prints everything; break rules too coarse | Print Player Study vs full; protect modules not sections | OPEN |
| U2-35 | No main landmark | Wrap in main | OPEN |

## Self-found (S)
| ID | Critique | Decision | Status |
|---|---|---|---|
| S-1 | Duplicate matches across batches inflated a finding to "credible" | load_fights dedup, pitfall 28 | DONE |
| S-2 | "Alone" deaths counted clutches (no teammates alive) | Only deaths with living teammates | DONE |
| S-3 | Coach notes written from a kill feed without round state (caused E-1, E-2) | Observed-facts block generated by software under every moment | OPEN |
