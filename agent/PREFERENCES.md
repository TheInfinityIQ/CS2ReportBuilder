# What Dawson has liked and disliked (append-only, newest at the bottom)

Firm design rulings live in `docs/OWNER_RULINGS.md`; this file is the running sentiment log and how to act on it.
Format: `date | + or − | what | what to do about it`. Add a line whenever he reacts. Never delete a line; supersede it.

## Standing (from OWNER_RULINGS and CRITIQUES, condensed)
| Sign | Preference | Act on it by |
|---|---|---|
| + | Real Counter-Strike coaching voice; lessons taught with real rounds on the map | Teach from findings + replays, never restate stats |
| + | Fixed report shell, changing body; one file, two tabs (Player Study / Analyst Desk) | Do not restructure the shell |
| + | Ask for a feature, get a coherent version with obvious surrounding behaviour | Include paths, defaults, validation, outputs |
| + | Honest confidence; null results recorded | Keep "no detectable difference" results in the Desk |
| − | Hollow coaching ("good job", restated data) | Reject in review |
| − | The AI controlling styling; engineering words in the player view; maths on the surface | Enforced by the validator and theme |
| − | Over-engineering that pushes the useful product off (contracts, gates, falsification for their own sake) | Product first, then rigour (ADR-010) |
| − | Developers/AIs returning to things he asked them not to do; building what he did not mean | Re-read rulings before acting |
| − | Being asked to trust design decisions he never reviewed | Treat unreviewed design choices as weak evidence |

## Log
2026-09-28 | − | Kill feed with no understanding; analysis built without the 2D viewer | Viewer moments replaced the kill list (O-5, O-6)
2026-09-29 | + | Reorganised demoparser folder with a `00_LEGEND.md` and a `00_ORGANIZE_ME/` drop zone ("You the bomb") | Keep the legend true; sort the drop zone on request
2026-09-29 | − | (Folder reorganisation) "Do not run agents" | Do file moves directly, not through sub-agents
2026-09-29 | + | v5 design document, written without assuming earlier layout/context was right ("Amazing") | Re-derive rather than inherit when asked to redo a document
2026-09-29 | − | Teaching Moments hard-coded/hard-prompted to 2–4 | Removed everywhere (prompt, rules, docs, Design v5); ruling in OWNER_RULINGS; test added. Do not reintroduce any count
2026-09-29 | + | Wanted many packets of 30 unique matches per player, with real limits respected ("10 is my estimation… not accurate") | Compute the true maximum and report it (8, not ~10)
2026-09-29 | − | Data folder sat inside a Steam game directory (Steam restrictions) | Moved to `C:\Users\dawso\Developer\CS2ReportBuilder\demoparser`; code default and legend updated
2026-09-29 | + | Wants one agent with a strong start point, legend/maps, a history of regressions and sentiment, and role "hats" (not many agents talking to each other) | This `agent/` system; keep it small and true
2026-09-29 | + | Wants a mandatory pre-work hat (plan the most efficient route) and a post-work hat (review the change log and update the big logs) | Both are in `agent/roles/`; every task is wrapped by them
2026-09-29 | + | Wants a short tail on replies naming the rules or design parts behind judgement calls, so he can change rules; not overwhelming | Max 3 lines, only rules that decided a call, omit if none
