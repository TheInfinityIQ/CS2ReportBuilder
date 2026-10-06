# Coach packet window

Double-click **Open_Coach_Packet_Builder.cmd** in the repository root.
No command arguments are needed. The window uses standard Windows Python's
Tkinter; packet calculations run with the repository's `.venv` when it exists.

1. Choose an **extracted** batch from the Demo batch dropdown, or use **Choose
   folder…** to select a specific batch directly, including folders without an
   `analyzed_` prefix. Select the folder containing the individual match folders.
   Browse beside Analysis folder changes the parent folder used for the dropdown
   (normally the local `02_Analysis` folder).
2. Choose the player. The dropdown shows names, match counts and exact SteamIDs.
   The packet contains only usable matches featuring that player. Excluded
   matches and validation reasons are visible; temporary folders are ignored.
   Player names come from match rosters, not demo filenames. Selection stays
   within the displayed batch folder; it never combines batches or searches
   other folders for that player's games. Refresh preserves the selected batch.
3. Choose PUG/FACEIT/Premier or tournament/pro, then click **Build coach packet**.
4. Once ready, open the packet folder and copy the AI instructions. Start a fresh
   AI session in that folder, or export a ZIP for an environment that supports
   uploaded files and Python execution. A text-only chat cannot run the renderer.

The default destination is local `06_Handoff_and_Tests/packets`. Each build has
a unique folder, including when multiple windows run. Prior packets and reports
are preserved. Calculations and rendering checks use the existing packet builder.
Only after a successful build is a complete packet published. Errors retain a
diagnostic log in a hidden `.P_*.building` folder; completed logs are in `.build_logs`.

The window stays responsive during copying, analysis and ZIP creation. Progress
shows copying stages and builder output; it does not invent a percent or ETA
while statistical calculations run. Finish the current operation before closing.

## Scope

This version uses already-extracted analysis, with any positive match count.
Each packet uses one batch folder. Copies of the same match already present
inside that folder are not currently detected as duplicates.
The old CLI default of 30 matches is not an interface requirement. Small samples
still have the software's existing evidence limitations; no useful-finding
threshold is weakened. Raw `.dem` extraction is a separate step.

Source analysis is copied into a private snapshot before calculation, then moved
into the packet. Avoid actively extracting into a batch while building from it.
Failed copies or evidence checks do not produce a ready packet. Discovery here
does not depend on generated navigation catalogs, which can lag new batches.

## Setup and troubleshooting

Standard Windows Python includes Tkinter. If the window cannot open, use an
installation with working Tcl/Tk. Scientific dependencies need only be installed
in the calculation environment. From the repository, the usual one-time setup is:

```powershell
py -m venv .venv
& .venv/Scripts/python.exe -m pip install -e '.[dev]'
```

Do not recreate a working environment. `py build_packet.py` selects the Windows
launcher's default Python, which may lack SciPy; the window deliberately chooses
the repository environment for packet builds. The CLI still requires arguments.

No AI calls, credentials or automatic uploads are involved. Evaluation of the
resulting coaching remains separate from packet/build validation.

## Verification (2026-10-04)

The window opened with installed Windows Python 3.14; batch/player dropdown
callbacks selected CanadianIQ's four matches from the FoxC batch. A real job
computed evidence for 102 rounds, passed the packet's report-rendering smoke
test and exported a ZIP. Test outputs are local in
Downloads/CS2_Packet_UI_Verification_2026-10-04, not in the repository.

The test exposed Pillow as an undeclared dependency of the existing viewer's
map-outline fallback. It is now declared in pyproject.toml and checked before
building. Synthetic job tests cover source preservation, prior-packet preservation,
failed-build isolation, player coverage, example identity and ZIP overwrite refusal.

On 2026-10-06, a Tkinter callback check verified direct selection of a custom
batch name, the displayed source path, selection preservation after refresh,
and passing only that folder's player matches to the build job. Changing the
analysis parent clears the custom selection. This check used a stub build;
the real calculation and rendering verification above remains the build record.
