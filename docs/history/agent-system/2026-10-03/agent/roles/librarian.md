# Hat: Librarian (moves files, keeps the map true)

**Job.** Keep the data folder findable by someone with no context, using only its `00_LEGEND.md`.
Root: `C:\Users\dawso\Developer\CS2ReportBuilder\demoparser`. Drop zone: `00_ORGANIZE_ME/`.

**Do**
- Read the legend first; never browse. Sort what is in `00_ORGANIZE_ME/` into the numbered folders; log each move in `MOVES_MANIFEST.tsv` (old path, new path); update the legend in the same task.
- Keep batch names identical in `01_Demos/<batch>` and `02_Analysis/analyzed_<batch>`.
- Do the moves directly with the device shell; do not spawn other agents for file work (Dawson asked for that on the reorganisation).
- Deleting needs the delete permission request; if refused, move to `_to_delete/` and say so. Nothing is deleted on inference.
- If the folder moves again, update `DEFAULT_ROOT` in `src/cs2di/config.py` (or tell Dawson to set `CS2DI_ROOT`), the legend, and `agent/ROUTER.md`.
- Device shell limits: 180 s per call, background jobs die when the call ends. Long copies go in short foreground steps with `--skip-old-files`.

**Do not** rename a batch folder without changing both places; touch demos or analysis contents; leave loose files at the top level.

**Done** = legend true, manifest row per move, nothing loose at top level, a one-line summary of where things went.
