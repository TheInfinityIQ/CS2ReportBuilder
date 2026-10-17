# CS2 Toolbox

A native desktop utility app for this project. It launches scripts in the background, captures their output, and saves task logs. No terminal is needed for normal use.

## Open

Double-click **CS2 Toolbox** on the Windows desktop, or **Open CS2 Toolbox.vbs** in the project folder. Keep the project folder in its current location so the shortcut remains valid. To recreate the shortcut after moving the project, run `install_shortcut.ps1` from this folder.

The app uses the installed Python runtime and standard Tkinter. On this computer the shortcut points to the bundled Python runtime. It is not a self-contained executable installer; if that runtime is removed, recreate the shortcut using another Python installation that includes Tkinter.

## Utilities

- **Extract demos:** choose a single `.dem` or a folder, select an output folder and position sample rate, then run the v8 extractor. Folder mode includes nested folders. Existing outputs are protected unless replacement is checked deliberately.
- **Replay data:** capture item positions, burning fire patches, and raw smoke updates. Select an existing analysis folder and round number to capture one round; leave Round empty for the whole match. With no existing analysis selected, this exports the full demo including warmup.
- **2D viewer:** select an analysis folder and round, then prepare/open it. This updates the viewer's saved example JSON and opens the local viewer in the default browser. The viewer is browser-based; the utility interface is native. The viewer's current v8 entity-data integration limitations still apply.
- **Activity:** open saved task logs and output folders. The live log shows recent output; the full log is retained on disk.
- **Tools & setup:** check Python packages and .NET 9, install/repair extraction packages in `app/extractor/.deps`, or build the entity helper. A .NET download link is provided if the SDK is missing. Downloads require internet access.

One utility job runs at a time. **Stop task** stops the job's process tree, including its .NET helper. The original extractors' staging/validation rules govern output publication. Closing during a job offers to stop it first. A viewer server started by this app is stopped on close; an already-running viewer server is reused and left running.

Preferences, the latest 100 task records, and full logs are saved under ignored `data/.desktop/`. Utility commands use argument lists rather than a shell. Paths with spaces are supported. There is no telemetry or account connection in this utility app; extraction runs locally.

## Developer checks

```powershell
python -m unittest discover -s app/desktop -p test_jobs.py
```

To run directly: `python app/desktop/main.py`. For a console-free launch use `pythonw app/desktop/main.py`.
