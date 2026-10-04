# CS2ReportBuilder workspace (pointer only; the rules live in the repo)

- **Code and rules:** git repo `TheInfinityIQ/cs2-demo-intelligence`. Its `CLAUDE.md` is the start-here file for any AI session (task router, role hats, logs). Read it first, then `agent/STATE.md`.
  No checkout here yet? Clone it next to the data: `git clone https://github.com/TheInfinityIQ/cs2-demo-intelligence repo` (run inside this folder), then start the AI from `repo\`.
- **Data:** `demoparser\` (demos, analysis, reports, coach packets). Its map is `demoparser\00_LEGEND.md`. Drop unsorted files in `demoparser\00_ORGANIZE_ME\`.
- **Find files cheaply:** use `repo\00_INDEX.md` or `demoparser\00_INDEX.md`, then the relevant folder map. Maintenance and catalog commands live in `repo\docs\NAVIGATION.md`; indexes do not replace source authority.
- **Coach test runs:** start the fresh AI inside a packet folder (`demoparser\06_Handoff_and_Tests\packets\<packet>\`), never from `repo\`. See `demoparser\06_Handoff_and_Tests\PASTE_TO_FRESH_AI.md`.
- The same start-here text is in the Claude Project "CS2 Demo Reviewer" as `claude/START_HERE.md`.
