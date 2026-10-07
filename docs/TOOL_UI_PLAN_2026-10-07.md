# CS2 Coach Tools: workflow plan and implementation

Goal: let Dawson select the games and player, prepare evidence when needed, then
hand a self-contained packet to a fresh AI. Keep extraction maintenance separate
from packet creation without hiding missing data. Authorized 2026-10-07.

## Decisions and evidence

| Action | Reason and repository evidence |
|---|---|
| Use two full tabs: Packet Builder and Utilities | The previous `WorkflowWindow` appended preparation tabs beneath the base builder, mixing repair actions and packet actions in one tall window. Dedicated pages give each task its own space. |
| Share collection/raw-folder selection and a persistent progress footer | Both `scan_matches` and `start_prepare` use the same included match identities. Separate selections could repair one folder while building another. Busy controls and generation tokens protect asynchronous scans. |
| Builder order: games, player, build/handoff | `inspect_batch` derives eligible players from included valid games; choosing the player before inclusion can give misleading coverage. The preview states the actual player-specific match count. |
| Keep readiness and identity checks in the match list | `build_packet` gates core integrity, hashes and optional validated replay coverage. A disabled build button needs an explanation and a route to Utilities. |
| Clear raw pairing on a collection dropdown change | An original folder belongs to a single analysis collection. Retaining the prior pairing can produce missing or incorrect stem associations. Explicit raw-folder selection still maps to its intended collection. |
| Count hidden included games; add Reset filters | Filters affect visibility, while `included` controls the packet. Without a count, hidden included games can surprise the user. Existing save/load selections retain their version and identity checks. |
| Utilities owns extraction, repair, resources, retries and logs | Existing extraction queue already provides soft CPU/RAM admission, safe cancellation and failure retry. The redesign reuses it; it does not introduce another extraction engine. |
| Disable preparation actions when no selected original needs that operation | Job planning already skips ready files. Reflecting that eligibility in button states avoids a pointless click and ambiguous “nothing to process” message. |
| Allow tab navigation during jobs, lock selection changes | Jobs should remain observable while protecting their captured inputs. Errors open Utilities; cancel remains available for extraction, and active workers finish safely. |
| Make both pages scroll at smaller window sizes | The previous window required 820 pixels of minimum height. Content and build controls must remain reachable at a 900x650 client size. |
| Explain packet contents at the handoff step | `build_packet.py` includes instructions, derived findings, analysis snapshots, renderer/helper source and assets. Raw demos are excluded. Python/file access requirements matter for choosing the receiving AI. |
| Preserve packet format and coaching semantics | UI usability can be checked independently. Prompt correctness, redundant findings retrieval and packet slimming remain a separate review; no evidence files or instructions are removed here. |

## User flow

1. Choose an analyzed collection, or an original player batch/tournament series.
   Custom analysis folders remain available; original-folder matching is scoped
   to one collection. Shared selection is visible on both tabs.
2. In Packet Builder, filter and include games. Choose a roster-derived player
   and match type. Read the actual packet scope and replay readiness.
3. If data is missing, open Utilities. Analyze missing games plus replays, or
   repair replay data. Resource limits, safe cancellation and retries stay here.
4. Return to Packet Builder after the automatic rescan. Build, then open the
   packet, copy AI instructions or export a ZIP. Global status shows progress;
   detailed logs remain in Utilities. Old packets stay unchanged.

## Verification

The real Tk callback smoke check covers two-tab navigation without selection
loss, clearing an old raw pairing on collection change, hidden inclusion counts,
saved-selection relocation, preparation eligibility, busy/cancel controls and a
new raw batch without analysis. Visual checks cover both pages at 1100x900 and
scrolling to build controls at 900x650. Repository checks continue to exercise
packet validation/publication, duplicate detection and extraction scheduling.
