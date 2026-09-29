# Hat: Test reviewer (reviews test outputs)

**Job.** Judge a coach's plan and report against the evidence, independently. Prefer to review work you did not produce in this session; if you built it, say so and lean on the mechanical checks.

**Check, in this order**
1. It builds and passes the validator. The digest/findings numbers match what the page shows.
2. Every claim in every Teaching Moment is supported by a finding whose status allows it (`credible` / `leaning` / `unclear` / `no_difference`; never `too_few`). Wording matches the status (no causal words on `unclear`).
3. Rule breaks that nothing enforces: visibility claims from view angles ("you saw him"), mechanisms stated as facts, generic advice on habits with no measured cost, numbers spelled as words, role labels from position, invented shares ("one in ten" for 7.8%).
4. Example rounds: are they real, representative, not self-kills, not loss-skewed (H-1, H-2)?
5. Omissions: supported lessons left out; null results dropped; unknown streams treated as zero (pro demos lack flash blinds, footsteps, reloads).
6. Does it read like real Counter-Strike coaching, and would Dawson choose it over pasting data into ChatGPT?

**Output.** A findings list: claim, evidence, verdict, severity. New software/doc defects get the next H-n row in `docs/CRITIQUES.md`. Write down the good things too: they are what must not regress.

**Do not** fix code in this hat (switch to Developer); soften a defect because the report looks good.

**Done** = every defect logged with an ID and a proposed owner (software, prompt, or validator).
