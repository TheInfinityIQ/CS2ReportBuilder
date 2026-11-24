# Demo Review usability review — 2026-11-06

This is a heuristic review of the implemented desktop screen, supported by source
inspection, application-owned window captures and task/state tests. It is not a
moderated user study or a claim of complete assistive-technology conformance.

## Research and responsibilities

NN/g's [State of UX 2026](https://www.nngroup.com/articles/state-of-ux-2026/)
emphasizes the whole experience, including system behavior, consistency, control
and recovery. A polished surface alone does not establish usability. For this
tool, that means keeping the selected recording, playback target and analysis
context accurate, and making progress and consent understandable.

UX owns the task sequence, information architecture, state transitions, error
recovery and user control. UI owns the hierarchy, wording, spacing, grouping,
contrast, focus indicators and adaptation to available space. Both must be checked
against real tasks rather than a style trend alone.

Microsoft's [command-bar guidance](https://learn.microsoft.com/en-us/windows/apps/develop/ui/controls/command-bar)
separates common actions from secondary commands and supports overflow when space
is limited. NN/g's established [progressive-disclosure guidance](https://www.nngroup.com/articles/progressive-disclosure/)
supports deferring specialist controls until requested. Neither principle requires
removing useful expert features.

[W3C's WCAG 2.2 guidance](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/)
informs visible focus, usable targets and predictable help. These principles are
applied to the desktop controls without claiming that web criteria alone certify
a Tk/Godot application. New buttons have visible keyboard focus, fields have
persistent labels, and important states use text as well as color. Selected-tab
text changed to white: computed contrast against its background increased from
4.27:1 to 7.92:1. Primary button text is 6.04:1; secondary panel text is 7.55:1.

## What already worked

- The catalog uses physical downloaded demos in replays, with no original-demo
  file picker. Watching does not depend on analysis.
- Team/player/date/identity search and map filtering are useful for a large library.
- Loading runs outside the UI thread and can be cancelled.
- Existing event-to-tick links, saved moments and stable demo/player identities
  provide useful continuity between analysis and playback.
- Playback is embedded in Toolbox and respects the user's game-file/settings rules.

## Problems and implemented corrections

| Observed problem | Resulting behavior |
| --- | --- |
| The list began hidden; selecting a row hid it again. | Demos is the default page. Row selection keeps the list visible; Watch, double-click or Enter explicitly opens playback. |
| An unlabeled search box remained while its hint and page title disappeared. | Search demos and Map labels remain with their controls in Demos; the current recording has a persistent header. |
| Rounds, events, saved moments, standalone viewing and legacy CS2 playback competed at the same level. | Three task modes: Demos, Watch, Find moments. Round/event/saved views live inside Find moments; legacy access is under More options. |
| Two choose-demo controls, two cancel controls and specialist commands competed with playback. | Watch has Back to demos, a state-specific stop/cancel action and Full screen. Command copying and the 2D companion are secondary options. |
| The idle viewer displayed a progress bar and Cancel loading. | Idle, ready, loading, stopped, failed and map-permission states have distinct titles/actions. A progress indicator appears only during real preparation. |
| Browsing another recording could change the header while the old demo was still in the renderer. | Library selection and the opened playback entry are tracked separately. The Watch header and advanced copy command use the opened recording. |
| Hidden playback could continue to produce audio. | Leaving Watch pauses playback without dropping the position or engine cache. Pause waits for an outstanding seek acknowledgement. |
| “Starting score” and “Round time” did not explain their basis. | Round tables identify CT/T score order and winning side; event times are labelled After freeze. |
| Missing analysis left empty controls without a clear next step. | An explanatory state offers Watch demo and Open analysis setup. Analysis setup preselects the current single demo and does not run extraction. |
| Saved moments did not identify the recording/date clearly. | Saved rows include date, map, round, demo and note. Save selects the new item; removal is scoped to the saved view. |
| Refresh discarded position and context. | Unchanged analysis retains its current position. Changed analysis is reloaded while retaining the bounded target tick. |

Ctrl+F opens/focuses demo search, including from the renderer; Alt+Left returns
to Demos. F11 expands the current task and Escape restores the window. Camera
labels follow keyboard mode changes; roster rows identify T/CT in text as well
as color. No acquisition, extraction, map-consent or bookmark schemas were rebuilt.

## Verification artifacts

Application-owned captures are in `data/.desktop/review-ui-check/`, including the
before screen and the revised library, moments, events, missing-analysis and
no-results states at desktop sizes. `review_ui_check.py` captures only Toolbox's
own window using PrintWindow; it does not use Computer Use or capture the desktop.

Relevant regression suites: `test_review_integration.py`, `test_review_ux.py`,
`test_embedded_replay.py`, `test_review_model.py`; the native request/keyboard/pause
fixture is `app/standalone3d/test_map_prompt.gd`. Live rendering uses the bounded
`embedded_smoke.py --raw --max-ready-seconds 10` fixture with the existing Dust2 demo.

Final validation on 2026-11-06:

- All 36 affected desktop regression tests passed. The headless native fixture
  passed map-permission, pause and search-request checks without importing assets.
- Own-window captures were inspected at 1180×850 and 1040×790, including filters,
  event controls, empty results and missing optional analysis. No clipping was
  observed at those sizes. This does not cover every display scaling setting.
- Live native playback passed embedded parenting, resizing, hidden-page behavior,
  exact seeking, models/animation/audio/utility checks and renderer shutdown on
  both runs. No external renderer window or CS2 process was required.
- The first prepared Dust2 opening took 12.359 seconds, exceeding the 10-second
  loading target; the immediate repeat took 7.282 seconds and passed the budget.
  Seek acknowledgement took 0.375 and 0.360 seconds respectively. Loading UI
  callback gaps remained below 50 ms on the first run. These measurements support
  responsive UI and fast repeat opening, not a universal sub-10-second guarantee.
- Results are retained in
  `data/.desktop/standalone3d/embedded-check/review-ux-first-result.json` and
  `review-ux-repeat-result.json`. A whitespace check of all 13 affected source,
  fixture and assessment files passed, including untracked files.

The subsequent bounded startup follow-up removed repeated runtime-version probes
and deferred decoding-only library imports. The prepared backend profile improved
from 2.734 to 0.969 seconds; the full embedded fixture then passed at 6.656 seconds,
with 0.359-second seeking. Its 27 focused tests included runtime-update invalidation,
recorded data and map-consent behavior. See `app/standalone3d/README.md` and
`data/.desktop/standalone3d/embedded-check/latency-fix-result.json`. This does not
establish a cold-filesystem guarantee or explain all earlier loading variance.

Remaining follow-up: characterize first-opening variance if it recurs, and observe
a real user choosing a demo and returning to a saved moment. Neither a heuristic
review nor automated tests substitutes for that usability observation.
