# Hat: Packet builder (builds test data)

**Job.** Produce report packets: self-contained folders a fresh, context-free AI coach can turn into a `plan.json` and a report.

**Facts to keep straight**
- A packet = PROMPT.md, RULES.md, MODULES.md, an example plan for a *different* player, `data/` (digest, findings, findings_index, batch), `src/`, `assets/`, `tools/moment_facts.py`, MANIFEST.json. Generator: `scripts/build_packet.py`.
- Unit = a match (pugs) or a map (tournaments: `-p1/-p2` are one map). Sample = exactly 30 units per player; a unit is used in only one packet.
- Match identity is a fingerprint (map + sorted 10 steamids + per-round start/end/winner), not a folder name; one match can sit in several batches (pitfall 28).
- Only `map_complete` and `full_match` maps are eligible. The focal player must be in every unit.
- Assignment is an exact b-matching (MILP, scipy) — the achievable number of packets is computed, never guessed.
- Pipeline: gate (`scan_batch`) -> `build_digest` -> `analyse_batch` -> smoke build. `assert_all_mapped` fails on an unknown weapon/item name: add it to `report/weapons.py`.

**Do**
- Compute the real maximum, tell Dawson if it differs from his estimate, and say why.
- Deliver to `06_Handoff_and_Tests/packets/<id>/` in the data folder; update that folder's README index and the legend.
- Verify from the delivered copy: 30 folders each, manifests match, no unit shared across packets.

**Do not** hard-code counts the evidence decides; put coaching content in a packet; edit demo or analysis files.

**Done** = every packet passes the gate and smoke build, is delivered and verified on the device, and the index is updated.
