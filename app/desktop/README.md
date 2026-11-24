# CS2 Toolbox

A native desktop utility app for this project. It launches scripts in the background, captures their output, and saves task logs. No terminal is needed for normal use.

## Open

Double-click **CS2 Toolbox** on the Windows desktop, or **Open CS2 Toolbox.vbs** in the project folder. Keep the project folder in its current location so the shortcut remains valid. To recreate the shortcut after moving the project, run `install_shortcut.ps1` from this folder.

The app uses the installed Python runtime and standard Tkinter. On this computer the shortcut points to the bundled Python runtime. It is not a self-contained executable installer; if that runtime is removed, recreate the shortcut using another Python installation that includes Tkinter.

## Utilities

- **Download demos:** paste a FACEIT player/CS2 match or HLTV team/match/event link. Recent-game count is enabled only for player/team links. **Extract demos** first resolves a review with match/map counts and unavailable matches; confirmation starts downloads. A tournament follows every results page. A series downloads all published archives and checks that every played map is represented. Missing/expired demos or failed analysis mark the job failed even when other demos succeed.
- **Local analysis:** choose a single `.dem` or a folder, select an output folder and position sample rate, then run the v8 extractor. Folder mode includes nested folders. Existing outputs are protected unless replacement is checked deliberately.
- **Replay data:** capture item positions, burning fire patches, and raw smoke updates. Select an existing analysis folder and round number to capture one round; leave Round empty for the whole match. With no existing analysis selected, this exports the full demo including warmup.
- **2D viewer:** select an analysis folder and round, then prepare/open it. This updates the viewer's saved example JSON and opens the local viewer in the default browser. The viewer is browser-based; the utility interface is native. The viewer's current v8 entity-data integration limitations still apply.
- **HTML reports:** choose Team or Player, search by name/Steam ID, select maps and games, then **Build HTML report…** and choose where to save. **Refresh analyzed games** rescans the library. Each self-contained `.html` includes full round playback, maps/icons, and adjustable heatmaps; it opens automatically and works offline in current Chrome/Edge. Player reports permit only the selected Steam ID as a heat contributor. Team reports include both rosters and opponent filters. Heatmaps start at 40 seconds, stop the entire round at its first death by default, average CT/T separately including overtime, and average only included games on the current map. The report can switch between all included games and one game.
- **Activity:** open saved task logs and output folders. The live log shows recent output; the full log is retained on disk.
- **Tools & setup:** check Python packages and .NET 9, install/repair extraction packages in `app/extractor/.deps`, or build the entity helper. A .NET download link is provided if the SDK is missing. Downloads require internet access.

One utility job runs at a time. **Stop task** stops the job's process tree, including its .NET helper. The original extractors' staging/validation rules govern output publication. Closing during a job offers to stop it first. A viewer server started by this app is stopped on close; an already-running viewer server is reused and left running.

Preferences, the latest 100 task records, download review, and full logs are saved under ignored `data/.desktop/`. Utility commands use argument lists rather than a shell. Paths with spaces are supported. Downloads connect to their providers; analysis runs locally, with no telemetry.

Reports use existing analysis; they do not download demos or rerun extraction. The builder runs in a separate worker with progress and **Stop task**. An incomplete build does not replace the selected output. Invalid analyses are omitted; missing movement windows remain visible as exclusions in the report. Identical demo copies are deduplicated; distinct recording segments remain available, and their canonical rounds are deduplicated for heat averages. Players are grouped by Steam ID, with recorded nickname aliases available in search. Teams use verified provider identity when present, or exact recorded clan labels for organized competition; historical team renames stay separate. Saved provider download facts can recover older league imports when their complete canonical name and recorded rosters agree. No identity metadata is rewritten.

Report size grows with full replay data, especially decoded smoke. Selections exceeding 256 MB of compressed embedded data stop with a request to select fewer games or one map. Save reports outside `data/analysis`. A named existing file requires the save dialog's overwrite confirmation; the builder checks it did not change during the job. Report files contain the included players' names, Steam IDs and recorded matches, so sharing the HTML shares those included data.

## Demo review application

Open **Demo review → Open demo review** for the review workspace. **Choose a match** opens the collapsible watch library, which lists only actual `.dem` files under `C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\replays` and its map/player/team subfolders. **Refresh library** rescans that folder; it does not rebuild the analysis catalog or run extraction. Deleted files and analysis-only recordings are excluded. Unindexed downloaded files are discovered automatically, duplicate content is shown once, and unchanged file hashes are cached in Toolbox's own data folder. Playback verifies the file's content and never asks the user to locate a missing original or falls back to a file outside replays.

Downloaded demos can be watched without analysis. Where matching analysis exists, search also includes its player names/Steam IDs/team metadata, and rounds, events, the 2D companion and saved moments become available. Without analysis, the demo is ready for 3D playback and those analysis controls stay disabled. Saved moments use demo SHA-256 plus the exact tick; notes for unavailable downloads are hidden from the watch workspace and preserved in `data/.desktop/review-moments.json`. A corrupt notes file is reported and preserved. Missing event streams never prevent watching a downloaded demo.

**3D view · Preview → Play selected demo** starts a private CS2 engine and displays its real rendering inside the application. CS2 does not need to be open first; Steam must be running and signed in. Toolbox verifies the original demo, copies the active user's preferences into `data/.desktop/native-sessions/<session>/profile/cfg`, and sets the engine's process-only `USRLOCAL` override. Existing normal configuration files are held open with read-only sharing to prevent writes, replacement and deletion during playback. No preferences are restored or copied back afterward. New configuration entries are checked separately. Exclusive-fullscreen profiles currently fail preflight rather than being switched to another display mode.

The private engine runs stock Valve binaries with `-insecure` for demo-only playback, without scripts, plugins, injected DLLs or game-file edits. Only its positively identified owned window is made almost transparent, non-activating and input-disabled. Windows Graphics Capture receives its full-color pixels before window opacity is applied. D3D11/DirectComposition display the frames in our viewport; resizing Toolbox scales only our presentation surface. **Stop view**, closing review, and closing Toolbox stop the owned engine. An already-running normal CS2 process is never closed or restarted. **Attach to existing CS2** is an optional read-only capture mode that leaves the user's existing window alone.

Managed rendering passed an actual ESEA Mirage demo on CS2 **1.41.9.6 / Steam build 26445667**: the selected demo became active, the panel received hundreds of non-black frames at **1920×1080**, its own process stopped, screen dimensions stayed unchanged before/during/after, and all **70** monitored original configuration files stayed unchanged. This is one representative game/build/configuration, not a claim that every historical demo or HDR setup is supported. On this PC, Windows denied private startup while FACEIT anti-cheat was running; startup succeeded after the user closed it. Toolbox never stops or reconfigures anti-cheat.

The 3D tab hides analysis-only controls to enlarge playback. **Expand view / F11** fills the Toolbox review window; **Restore view / Escape** returns to the library layout. This changes only the application viewport and preserves the game image's aspect ratio and source resolution. Engine crashes are reported separately from capture failures, with evidence in the session's `playback-failure.json`. Reconnection targets only the same owned process and is bounded; crashed demos are never automatically restarted.

The November 5 Dust2 and Ancient FACEIT startup crashes were traced to late CChicken baseline setup data, rather than established blanket version incompatibility. `native_demo_compat.py` checks the selected download and, only for the supported pattern and validated engine, prepares a private copy under `data/.desktop/playback-compat/`. The pinned MIT-licensed [repair core](https://github.com/NewTanachot/cs2-faceit-demo-fixer/tree/6627fbce1d6ea3f94f604576720602d41006337b) runs locally in the existing Node runtime. No demo is uploaded, no original replay/game file is edited, and no analysis is rebuilt. Text sanitization is disabled. The adapter verifies unchanged frame identities/timing and gameplay network messages, hashes the copy, and retains the original SHA as the library/notes identity. Normal demos use their original file. Unsupported repair patterns fail before launching; a copy that itself crashes is blocked for that exact demo/build/adapter. Changed engines or repair code require revalidation.

Both previously crashing recordings passed 30 seconds beyond startup at 1920x1080 using compatibility copies, with originals and all monitored game preferences unchanged. Dust2 preserved 118,226 frame identities and Ancient 142,389; only four setup/table frames changed in each. This proves the tested startup workaround, not every moment of every historical recording. `native_capture/compat_fixture.py --demo "<downloaded.dem>"` performs a bounded private-copy check without external controls or administrator network changes.

Demo review is embedded directly in the Toolbox page; it no longer opens a separate review window. Changing Toolbox pages retains the same review/session. **Stop view** or closing Toolbox stops the private engine. Expand/F11 hides the Toolbox sidebar; Restore/Escape brings it back.

For a validated engine/control adapter, **More → Enable demo controls (Windows approval)** enables the private local control connection. Windows asks for administrator consent for the separate application control guard. It holds temporary, executable/port-specific WFP filters blocking non-loopback access to Valve's otherwise unauthenticated listener, with no persistent firewall rule or game-file edits. The restriction starts before CS2, is monitored during playback, and closes after the owned engine stops. Cancelling consent leaves playback stopped; uncheck the option to watch without external controls.

The control bar provides pause/resume, a seek timeline, ±10 seconds, restart and speed. Matching analysis adds the round selector and **Watch selected moment**. Existing extractor event ticks are demo-relative and pass through directly; only analysis explicitly marked with server ticks uses the engine's `server_start_tick` offset. Round controls require matching demo SHA-256. Position comes from engine feedback, not a wall-clock estimate or the selected analysis cursor; seeking waits for a stable paused position. Controls wait for natural advancing playback before enabling, so CS2's delayed startup rewind/resume cannot overwrite an early request. Rendered frames can lag position feedback. Previous/next-player requests are supported. Camera modes, observed POV identity, selection by player identity and free-camera mouse input remain unavailable; accepting a camera command does not prove the resulting mode. The engine's native `demo_step_tick 1` advanced two ticks in testing; precise stepping stays disabled until separately verified. **2D companion** still opens the selected analyzed round in the browser.

Build the separate guard with `app/desktop/native_capture/build_guard.cmd`. Control validation is independent of capture validation and pins the game fingerprint plus the control code/helper digest in `data/.desktop/native-control-compatibility.json`. A changed build/adapter disables controls pending a new bounded test. `control_fixture.py --admin-guard --demo "<downloaded.dem>"` checks actual engine tick/speed/seek feedback under containment; `toolbox_fixture.py --admin-controls --demo "<downloaded.dem>"` exercises the integrated page. Both require explicit approval for the Windows administrator prompt. No historical runtime is downloaded and no bulk extraction is launched. Stop private playback before opening CS2 to play a match.

Read-only hashes monitor known game and Steam-user configuration locations; a detected change stops the view and never restores or overwrites settings. These hashes alone do not certify every effective runtime setting. Version checks run on opening the workspace, manually, and once per minute while open. Selected binary fingerprints/depot manifests are retained in `data/.desktop/native-runtime-profiles.json`. Production managed launch requires a successful rendering check matching the exact runtime fingerprint, native capture-library digest, video-preferences digest and adapter version in `native-playback-compatibility.json`. Changed builds/components/preferences fail closed before launching. No game versions are downloaded and no background monitoring service is installed.

Build the capture library with `app/desktop/native_capture/build.cmd` using the existing Visual Studio 2022 Community C++ tools and Windows SDK. Versioned output stays in its ignored `build/` directory; an atomically published `current.json` selects the build, and existing views retain their loaded version. No extra Python/.NET runtime or downloaded dependencies are needed. Run `python app/desktop/native_capture/fixture.py --self-test --masked-source` from a normal desktop process for the bounded GPU/pixel test; a restricted AppContainer can deny Windows capture. This fixture uses only its own windows and never starts/finds CS2. Entirely off-screen source capture did not deliver sufficient frames and is not the selected implementation.

For an explicitly authorized game-facing compatibility check, run `python app/desktop/native_capture/integrated_fixture.py --demo "<original.dem>" --seconds 45`. This uses the shipping panel, private profile, configuration leases and owned engine; only a fully successful check publishes a compatibility record. Add `--require-verified` to exercise the normal production gate. It stops its own engine and records results in `data/.desktop/native-last-integrated-smoke.json`, including actual pixels, demo activation, private configuration routing, input-disabled source, original-setting hashes, screen sizes and process cleanup. UI tests use application-owned Tk methods and layout/state assertions, without Computer Use, desktop clicks/typing, or a pre-existing game session.

The full capability gates and historical-runtime design are in [NATIVE_VIEWER_PLAN.md](NATIVE_VIEWER_PLAN.md). All application code, notes and bookmarks stay outside CS2; no generated game scripts, injected plugins or configuration files are installed.

## Watch in CS2

Enable **Tools & setup → Enable / repair CS2 report links** once per Windows user, then build a new HTML report. **Watch in CS2** uses the current report timeline tick, including moments reached by selecting a round or event. The browser opens the registered `cs2toolbox:` helper. Links contain only a registered SHA-256 identity and an integer tick; the helper locates the matching download automatically inside replays and verifies its checksum. A different demo or a file outside replays is rejected without opening a file picker.

The helper finds and verifies the requested demo only within replays, then provides **Copy open command** and **Copy jump command** for manual use. If it is not downloaded there, it reports that state without opening a file picker. The legacy HTML helper's automatic launcher remains disabled; use the review workspace's managed playback instead. Its application code stays outside CS2; no generated cfg files or DLLs are installed in the game. A custom engine installation can be set as `cs2_game_directory` in Toolbox settings; the watch library still uses the central replays folder above.

An existing CS2 session is left untouched; the helper does not start, close or restart it. Game/demo compatibility still applies; the initial 1.41.9.5 playback tests crashed inside CS2 and their cause remains unresolved. Existing HTML reports must be rebuilt to gain the action.

## Download library

The initial demo destination is `C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\replays`. Browse to override it; the selection is remembered, and **Use default location** restores the Steam path. The Toolbox needs write permission to the chosen folder; it does not elevate automatically.

Downloaded files go under `<map>/<player or selected team>/`. For match/event links without a selected player/team, the owner folder is `TeamA-vs-TeamB`. Names use each map's round score, source match date in UTC, and tournament name (HLTV) or `FaceIt`:

```text
anubis/G2/[13-9]_G2-vs-Vitality_Oct-31-2026_anubis_Test Cup.dem
anubis/CanadianIQ/[13-vs-9]_CanadianIQ_Oct-31-2026_anubis_FaceIt.dem
```

For a FACEIT player download, the score is `[PlayersTeamScore-vs-OpponentsTeamScore]`, including losses (for example, `[7-vs-13]`). The profile's stable player ID identifies the correct roster even after a nickname change; missing or ambiguous membership is reported rather than guessing. FACEIT match links without a selected player use `[TeamAScore-vs-TeamBScore]` in the displayed team order. Names are made Windows-safe and long labels are shortened. Split demos retain all parts, with `-part1`, `-part2`, etc. in the map component and original archive member names in the index. A short checksum suffix resolves a filename collision without overwriting either file. Premier links are not supported by this downloader; local Premier demos can still be analyzed.

`replay-library.json` in the replay root connects stable provider match IDs to all map/segment files, scores, teams, dates, player/team contexts, SHA-256 checksums, download receipts, and analysis status. Paths are relative to the replay root. Its previous version is retained as `replay-library.json.bak`. Keep the index with the demos when moving/backing up the library. A corrupt index is reported, never silently reset.

Indexed download receipts are checked before fetching demo bytes. Missing/changed files cause a retry. Files downloaded before this index existed cannot reliably be identified from arbitrary filenames: after download, size-matching existing `.dem` files are compared by checksum and adopted instead of copied. Selecting another player/team for the same match reuses the indexed files and records another context. It does not make a second physical copy under the other owner.

Downloads and decompression use `.toolbox-staging` in the replay root. Only validated CS2 demo headers with unambiguous source map/score metadata are published. Archives cannot choose output paths; final publication is atomic and never overwrites another file. Stop/crash may leave temporary staging folders; remove these only when no download job is running. An OS-managed library lock prevents simultaneous writers. Downloads retry transient network/rate-limit errors, but interrupted transfers restart rather than resume byte ranges.

ZIP/gzip use Python's standard library. Zstandard (`.dem.zst`) streams through the existing `pyarrow` extraction dependency. RAR/7z archives use an existing 7-Zip installation or Windows `tar`; nothing is installed automatically. Some archive variants require 7-Zip. Header metadata uses the existing `demoparser2` extraction dependency, without running analysis. Each download/unpacked file has a 32 GiB ceiling and a 512 MiB free-space reserve. Analysis can require substantially more free space.

**Analyze selected demos after download** is off initially. When checked, only the selected downloads (including already-downloaded selected demos) are analyzed, one at a time. New outputs use these collection layouts, with the actual map name as the map folder:

```text
data/analysis/Tournament_Name/inferno/Analysis_[demo_name]/
data/analysis/Analysis_PlayerName/anubis/Analysis_[demo_name]/
```

Tournament and team identities come from the selected download job, including when the raw demo was already indexed under a player or another team. FACEIT league collections include league/season/division in the tournament component. Team selection stays in metadata; both teams share one tournament/map/match analysis folder. Whitespace becomes underscores in every new analysis path component; hyphens and score brackets are retained. Windows-invalid/reserved names are sanitized, and long components retain a short identifying hash. Analysis output paths containing spaces are rejected. Raw demo paths/names may contain spaces and are not renamed or copied just to name analysis output. A content suffix disambiguates an existing named result owned by another demo.

`Analysis_[demo_name]` is a **folder**, not a ZIP or a new file format. It retains the extractor's CSV/JSON/compressed replay files so the 2D viewer can open it directly. `analysis_run.json` is a per-demo completion/integrity receipt; shared map-level batch summaries cannot make another demo appear complete. Source hashes are checked against viewer metadata before success is recorded. Matching completed results at the same layout and sample rate are skipped. Existing results and their history are preserved; this change does not rename/migrate old content-ID folders. Creating the new layout for a previously analyzed demo can run a fresh analysis and consume additional disk space. Other existing output at the new target requires review rather than being replaced.

**Local analysis** uses the same whitespace-free map / `Analysis_demo_name` layout beneath the selected output collection. Choose `Analysis_PlayerName` or a `Tournament` collection folder; the local-file page cannot infer absent tournament/player metadata from an arbitrary legacy filename. Its automatic player collection suggestion replaces spaces with underscores. Replay entity exports launched through Toolbox also use organized names. Existing standalone extractor/rebuild scripts keep their legacy defaults unless `--organized-output` or the single-demo `--analysis-name` option is explicitly supplied.

The console reports each download, byte percentage when a size is supplied, and analysis percentage as demos processed / selected demos. This is not an estimated percentage within an individual demo. Full extractor output is streamed into the same log. Failed integrity or viewer checks cannot report successful analysis.

### CPU execution

The Tkinter interface, download worker, Python analysis process, and .NET entity helper are separate processes. Toolbox handles one demo at a time. It does not set CPU affinity, reserve a core, or restrict worker threads to one core. Windows schedules their threads across available logical CPUs; native parser/library work may use additional threads. A separate background process keeps the interface independent but still competes for CPU, memory, and disk bandwidth with CS2 or other applications. No processor priority/affinity settings were changed for the folder-layout update. No real analysis was run to benchmark core usage.

## FACEIT credentials and provider access

### Team league seasons

Paste a FACEIT `/teams/<team-uuid>/leagues` link. Toolbox automatically scans the team's CS2 league registrations, discovers season numbers/division/region, and lists seasons newest first. It selects the newest season initially; **Rescan** or pasting again refreshes the catalog. Recent-game count is disabled for FACEIT team links. Choosing a season resolves all finished team matches from its regular-season and playoff championships, with pagination and ID/filter checks. Scheduled matches are reported separately. Transfer, indexing, folder naming and optional analysis use the same pipeline as other demos. The selected team's ID fixes score order, and files go under `<map>/<team>/` with the league, season and division in their source label. Older demo files may have expired even while match metadata remains accessible.

Every selected season is compared to the highest discovered season number **within the same league**, never to the previously selected season or a hard-coded S59. A red **● different rosters** indicator sits to the right of **Extract demos**. Hover it for changes **from the selected season to the latest season**:

| Mark/colour | Meaning |
| --- | --- |
| Green `+` | Added to the latest roster |
| Red `−` | Removed from the latest roster |
| Blue `+` | Moved from subs to main roster |
| Blue `−` | Moved from main roster to subs |
| Grey `•` | Same account in both rosters |

The list has **Main Roster** then **Subs** headings. Hover each name for its specific explanation, full FACEIT account UUID, and SteamID64 when available. UUIDs are the comparison keys; nickname changes remain the same account. Historical names/unknown roles have their own clearly labelled group when role evidence is unavailable. Incomplete comparisons use an amber **roster not verified** indicator rather than an all-clear. The latest-season grey roster indicator also exposes its roster and IDs.

**Historical evidence limitation:** the linked team's summary returned the same ten `team_members` for S57, S58, and S59, while S58 match records listed players outside that set. Consequently, old summary members are not accepted as a complete historical roster. The scan reconstructs older match-listed players from finished match records. It uses the current registered players/substitutes only when the separate current-registration response matches the newest league/season ID. Such dated observations are retained in `data/.desktop/league-roster-snapshots/` for future season comparisons. Saved older observations can establish main/sub movements; absent historical role records stay unverified. Match-lineup comparisons describe observed additions/removals in each name's tooltip and do not prove membership of unplayed substitutes or past registration roles. Blue movement markers require known roles in both seasons. Missing match data suppresses definitive change markers. This avoids inventing historical roles while still showing differences in the available season lineups.

Catalogs under `data/.desktop/league-catalogs/` retain team, league, season, championship and account IDs plus comparison provenance; `replay-library.json` retains selected season metadata on each imported match. Discovery reads only team/league/match metadata and never starts demo transfers or analysis. The supplied team was checked live: **S59 Open9-10: 8 finished matches; S58 Open9-10: 17; S57 Open1-8: 17**, including playoffs where listed. A representative S58 Bo3's per-map score ordering was also checked against FACEIT's Data API. No real demos were downloaded. These web metadata endpoints are not part of FACEIT's documented v4 Data API and may change; malformed or mismatched filters fail visibly. UI state transitions and blue-marker logic are fixture-tested; the native hover layout was not visually verified in this run. Historical main/sub roles for this team's older seasons remain unverified.

**Tools & setup → FACEIT credentials** saves masked input in Windows Credential Manager for the current Windows user on this computer. Blank fields leave saved values unchanged; input is cleared after saving. Secrets are not stored in project settings, plans, logs, or command arguments. To add them manually, use **Windows Credentials → Generic Credentials → Add a generic credential** (not **Add a Windows Credential**):

| Internet or network address | Username | Password |
| --- | --- | --- |
| `CS2Toolbox/FACEIT/DataAPI` | `FaceItAPI` (label only) | FACEIT Data API key |
| `CS2Toolbox/FACEIT/DownloadsAPI` | `FaceItAPI` (label only) | Separate Downloads API access token |

The Data API key alone does not grant demo downloads. [FACEIT requires separately approved Downloads API access](https://docs.faceit.com/getting-started/Guides/download-api/). Resource URLs are exchanged for short-lived signed URLs at download time; signed URLs are not written to the replay index. For non-Windows/managed environments, `FACEIT_API_KEY` and `FACEIT_DOWNLOAD_TOKEN` environment variables override the vault. Removing vault credentials does not remove environment variables.

HLTV may refuse direct automated access or require a browser challenge. **Automatic** switches to the companion for blocked HLTV metadata, missing FACEIT Downloads access, and signing/direct-transfer access failures. **Browser companion** explicitly uses that route; **API / direct only** fails rather than switching. FACEIT metadata still requires the Data API key even when the browser handles downloads. Direct transfer interruptions or corrupt archives are reported for retry, rather than treated as evidence of expiry. An HTTP 403 and a separate successful browser inspection of HLTV's match/results/team markup were observed on this machine. No real demo download or analysis has been run to validate either route end to end.

## Browser companion setup and limits

1. Reopen Toolbox. On **Download demos**, use **Companion script** to open `app/desktop/userscripts/`.
2. Import `CS2Toolbox.user.js` through the existing Violentmonkey dashboard. Disable the older FACEIT Verified Downloader and CS2 Coach Tools HLTV collectors, then reload their pages. The new companion pauses if their panels are present.
3. Set **Browser downloads folder** to the folder your normal browser actually uses. This is separate from the final Steam replay destination. Leave the method at **Automatic**, or select **Browser companion** explicitly.
4. Start from Toolbox, review the resolved match/map counts, and confirm the download job. Keep the opened browser tab running. Complete login, verification, and browser download prompts yourself; the companion does not bypass them.
5. Let each download finish. FACEIT filenames carrying the exact match ID are detected after their size/time remain stable for three seconds, with partial sibling files excluded. Other names and all HLTV archives require explicit file selection in Toolbox. Select only that match's completed archives. Browser originals are copied for import and retained.

The helper binds only `127.0.0.1` on an available port; it does not reserve the old viewer/helper ports 8765/8766. Each job gets a fresh pairing value delivered in a transient browser fragment and retained in that tab's session storage. No FACEIT key, browser cookies, or login tokens cross this connection. Messages carry public match/result elements, not complete pages or embedded page scripts. Version, token, host, task ID, expected URL/filter set, and tab lease are checked. A claimed download cannot be clicked again after a refresh or a lost reply. Closing or stopping the job closes its helper; start again from Toolbox to reconnect.

This is a new, protocol-compatible companion, not a drop-in patch for the supplied scripts' missing Coach Tools helpers. Review of those originals found:

| Supplied script | What it actually handles | Gaps for this Toolbox workflow |
| --- | --- | --- |
| FACEIT Verified Demo Downloader 2.6.5 | Player-history collection, saved browser queue, normal Watch Demo clicks, polling a separate helper for completion | Starts only from player history; helper on 8765 is absent here; requires rating/date/player result labels for the old filename format; assumes an age-based expiry cutoff; no demonstrated full multi-map series support |
| CS2 Coach Tools HLTV Downloads 1.0.0 | Event-result scans, match inspection, normal demo-button clicks, helper polling | Event-only state/filter model; helper on 8766 is absent here and that port may serve the viewer; embedded pairing value belongs to the old helper; map names collected without per-map round scores; team and standalone-match workflows absent |

The replacement uses the Data API for FACEIT player/match metadata and the same scoped HLTV parser for event, team, and single-match pages. HLTV results are requested by explicit offsets until an empty recognized results page, rather than trusting whichever future-page link appears first. Page changes, extra filters, auth errors, missing buttons, and timeouts are errors, never silent expiry/completion. Browser login, verification, and connection errors stop the batch for attention; restart from Toolbox after resolving them. No demo is skipped merely because it is older than an assumed retention window.

After import, all source-reported played maps must be represented. If a FACEIT button returns only one map or an HLTV series is split across archives, Toolbox asks for the remaining files. The index records `download_complete` only after coverage checks. This confirms file receipt and map coverage, not full replay duration or every round: only analysis can investigate those contents. Manually selected archives are explicitly recorded with `archive_provenance: user_selected`; map headers cannot independently prove the source teams, date, or final score. Arbitrary HLTV filenames are never associated by newest-file timing. Complete indexed matches are reused across direct/browser modes.

**FACEIT retries (companion 1.1.4):** Toolbox watches the configured browser download folder after the actual click acknowledgement. If no new download activity appears within three seconds, it issues a new attempt identity. The companion refreshes once for that attempt, waits at least three seconds after returning, then rechecks the enabled button before clicking. At most three total attempts are allowed before manual assistance. Match-ID-bearing partial/final files stop automatic retries; an unidentified new browser partial also suppresses retries conservatively, without being imported or attributed to the match. A final server check before a retry click catches late starts. File completion still requires the existing identity/stability and import checks; activity alone is not download completion. Browser save prompts or unusually delayed responses can still require manual help.

Re-import `userscripts/CS2Toolbox.user.js` into Violentmonkey and reload FACEIT to update the installed copy. Retry capability is negotiated: older companions keep their single-click behavior. The backend changes take effect for a new download job; an already-running job does not hot-load them. No browser download-history API or extra browser permission is used.

**Validation:** automated fixtures cover helper authentication/host checks, competing tabs, duplicate claims, stale IDs, exact filters, missing companion timeout, partial/unstable/unrelated files, bounded no-start retries, late-start vetoes, original-file retention, missing series maps, cancelled imports, shared duplicate receipts, streaming Zstandard, and automatic versus direct-only routing. Script checks cover pairing/URL validation, click acknowledgement, refresh timing and one-click-per-attempt behavior without reading cookies. These do not prove that current provider buttons, browser settings, localization, popups, archive formats, interrupted transfers, or all series variants work live. A representative real download from each source remains required before treating the integration as end-to-end verified. Installing the companion or starting real jobs is left to the user.

## Shared demos and analysis references

The replay library reuses provider match/resource IDs before asking for a download,
then verifies imported demo content with SHA-256. Different names, player
collections, and team collections do not require another physical `.dem`.
Unknown identical content can only be recognized after receiving it; the importer
still publishes one canonical demo. Existing browser archives and old duplicate
files are not automatically deleted.

When a second collection requests an already validated analysis, Toolbox creates
its correctly named, whitespace-free analysis folder containing only
`analysis_reference.json`. This portable data file records the demo hash, a target
relative to the analysis root, collection identity and sampling rate. It does not
copy the analysis or contain credentials. The 2D replay reader follows references;
reports continue to read canonical data once rather than double-counting aliases.

**Tools & setup → Analysis → Analyze all** first previews indexed recordings and
reference folders. Starting the reviewed job validates existing analysis, heals
moved targets using their demo hash, and prepares missing analysis once per demo.
If a required source demo is absent, it uses the normal authenticated download
workflow and requires the exact expected hash before analyzing it. A complete
analysis does not trigger an unnecessary source download.

Cycles, outside-library targets, changed identities/schemas, conflicting sampling
rates, incomplete or modified outputs, and unavailable downloads are reported and
preserved for review. Unknown/unindexed raw demos require source verification;
filenames are not guessed into player identities. Existing physical duplicates
are not migrated by this feature. No bulk job starts from preview alone.

## Analysis directory repair

**Tools & setup → Analysis → Fix Directory** creates a read-only preview of `data/analysis`. The review shows the exact current/proposed paths, file count and size, unresolved folders, and blocking checks. **Apply these changes** is the explicit confirmation to perform the repair; the preview alone moves nothing.

The console and progress bar identify the folder scan, destination checks, saved-reference checks (including file counts/current file), and report creation. Folder mappings are compiled once into a prefix lookup shared across reference files; replay labels do not rescan every folder mapping.

The repair uses `Tournament/map/Analysis_<demo>` or `Analysis_<current_FACEIT_nickname>/map/Analysis_<demo>`, with whitespace-free folder components. FACEIT identities are verified using a stored account UUID or a SteamID64 matched to the recorded player roster, then looked up using the saved Data API key. Nickname searches are not used to identify renamed accounts. Each game keeps its recorded historical nickname. Legacy FACEIT names can be rebuilt from recorded dates and complete, clan-aligned final scores; unknown scores, dates, identities or tournament context are reported and left in place.

Folders are renamed on the same drive; CSV and compressed replay evidence are not decoded or regenerated. Existing duplicate versions remain separate, with a stable suffix when needed. Empty legacy containers are removed, and their collection-level reports are retained under `data/.desktop/directory-fixes/<repair_id>/collection-reports/`. Stored JSON paths, replay-library analysis receipts, viewer exports, desktop selections/history and affected game-catalog entries are updated. Catalog validation is invalidated, never replaced with an unverified success claim. Outside analysis datasets and raw demo paths remain unchanged.

Metadata/catalog backups, the full preview and an operation journal are kept under `data/.desktop/directory-fixes/<repair_id>/`. **Undo last fix** restores the last repair after checking that its analysis has not changed and original names are available. New unrelated preferences/history are preserved. Interrupted repairs keep their journal and must be undone before another repair. Ambiguous recovery or modified analysis requires manual review using those backups. V8 CLI extraction and repair share an exclusive maintenance lock; repair also reports existing per-output extraction locks.

## Developer checks

The **Play demo** button in Demo Review loads the selected physical download in
the embedded **3D viewer** tab using the installed Steam Godot 4.7 runtime. Loading
has a cancellable screen and background resource reads. No separate player window
or CS2 process is opened. The old game-powered tab remains explicitly labelled
**CS2 engine · Legacy**. The historical `Open Standalone CS2 Viewer.vbs` shortcut
now enters Toolbox. See [viewer capabilities and limits](../standalone3d/README.md).

```powershell
python -m unittest discover -s app/desktop -p 'test_*.py'
node --test app/desktop/userscripts/test_companion.cjs
```

To run directly: `python app/desktop/main.py`. For a console-free launch use `pythonw app/desktop/main.py`.
