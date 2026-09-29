# What coaches actually coach, and what a demo can show

Source: all 1,540 transcripts from 5 creators (austincs, HOLMESO, isk, pienix, Grashog), of which 161 are
demo reviews or coaching sessions. About 62,000 coaching-style sentences ("you should...", "the mistake
is...") were tagged by topic. Counts are mentions in reviews / elsewhere; they show emphasis, not truth.
One full review (austincs, "Why Top Fragging Doesn't Mean You're Carrying") was read end to end for how
feedback is structured. Mining script: Development/Outputs/repair_tool (device), output creator_concepts.json.

## How a human review works (the pattern to imitate)
1. State a hypothesis up front ("kills don't translate into round wins").
2. Walk rounds; at a moment, name what happened, why it matters, and the better alternative.
3. Praise what was right in the same breath (credibility; "the idea is there").
4. Tie it to level and context ("in a higher-ELO lobby this gets punished").
5. Close with one takeaway ("detach from the scoreboard: are your kills serving the round?").
Coaches judge **decisions in context**, not averages. Our equivalent: a finding (pattern with counts)
plus the specific rounds that show it, each with what happened and what the alternative was.

## Catalog: concept -> what the data can measure -> status
Mentions: review / other. Status: HAVE = computable from current output; BUILD = computable, not built;
PARTIAL = only a proxy; NO = needs video/voice/intent.

| Concept (mentions) | Measurable signal in the demo | Status |
|---|---|---|
| Utility use (3180/4680) | throws per round, type, time, where; followed by a fight/entry within N s by self or team; flashes that blind enemies vs teammates; unused utility at death; smokes with no following action ("no goal") | BUILD (grenade + blind + position data present; blind events missing on tournament demos) |
| Positioning / angles (1069/1534) | where fights start, how many enemies could see you (spotted mask), distance to nearest teammate, repeated same-spot deaths | PARTIAL (place + spacing HAVE; true sightlines need map geometry) |
| Aggression vs passivity, over-peeking (688/794) | pushing into enemies after contact, re-peeking the same angle, fights taken while team is ahead | BUILD |
| Timing / patience (521/703) | round time of first contact and death, fights taken early vs late, speed on entry | HAVE (fight table) |
| Information / sound (469/999) | footsteps near enemies before contact (pugs only), spotted-before-damage | PARTIAL |
| Peek type (435/548) | speed and movement direction at first damage, re-peeks, initiative | PARTIAL (speed HAVE; jiggle needs 64-tick deep sample) |
| Economy (393/881) | buy vs team, save/force choices, weapon value lost on death, eco kills | HAVE (economy tables) |
| Decision-making (287/615) | only via the concrete items in this table | via others |
| Mentality / tilt (273/622) | performance after a lost round / bad streak vs baseline | BUILD (proxy only) |
| Trading / spacing / baiting (221/651) | traded within 5 s, was tradeable (teammate within reach), traded a teammate, bait deaths that got traded | BUILD (positions 2 Hz HAVE) |
| Map control / mid-round (217/377) | early-round space taken, contact timing per area, rotations | BUILD |
| Spray / aim (211/522, 210/598) | hits per fight, headshot share, damage before dying, time to kill from first damage | PARTIAL |
| Role (188/370) | profile from habits: where and when fights happen, weapon | HAVE (habit findings) |
| Crosshair placement (165/715) | horizontal aim error at first damage | PARTIAL (horizontal only) |
| Value of a death / meaningful kills (143/222) | kill's effect on round (man-advantage state before/after, round already decided?), "exit" kills, dying first with no trade | BUILD (high value; directly the austincs theme) |
| Rotations (138/227) | time to reach other site after info, over-rotation | BUILD |
| Post-plant / retake (123/345) | positions and fights after plant, utility on bomb, conversion | BUILD |
| Communication (94/122) | not in demo (voice not parsed) | NO |
| Numbers advantage (89/130) | conversion of 5v4/4v3 etc., who died breaking an advantage | BUILD |
| Reload / knife out (74/117) | weapon in hand at first damage, reloading when engaged | HAVE (knife in 1-2% of fights) |
| Clutch (50/98) | 1vX situations: approach, time used, outcome | BUILD |
| Counter-strafe (37/148) | speed at shot; true counter-strafe needs 64-tick input data | PARTIAL |

## Priority for the next analyses (value x feasibility)
1. Value of kills and deaths (meaningful kills, dying first, advantage thrown).
2. Trading and spacing (traded / tradeable / traded a teammate).
3. Utility with purpose (what follows each grenade).
4. Advantage and clutch conversion.
5. Economy decisions.
All judged against lobby peers and the player's own level (ADR-013).
