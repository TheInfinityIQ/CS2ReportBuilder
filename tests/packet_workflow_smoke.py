"""Exercise actual Tk callbacks with a normal Windows Python (no parser required)."""

import json
from dataclasses import replace
import os
import sys
import time
import tkinter as tk
from pathlib import Path
from tempfile import mkdtemp

ROOT = Path(mkdtemp(prefix="cs2_gui_", dir=Path.home() / "Downloads"))
os.environ["CS2DI_ROOT"] = str(ROOT)
os.environ["CS2DI_DEMOS_ROOT"] = str(ROOT / "replays")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import packet_ui  # noqa: E402
from packet_workflow_ui import WorkflowWindow  # noqa: E402
from cs2di.batch_selection import ReplayQuality  # noqa: E402

analysis = ROOT / "02_Analysis/analyzed_test"
folder = analysis / "one"
folder.mkdir(parents=True)
(folder / "match_summary.json").write_text(
    json.dumps(
        {
            "integrity_hard_failure_count": 0,
            "schema_version": "3.8",
            "valid": True,
            "coaching_valid": True,
            "map_name": "de_ancient",
        }
    )
)
(folder / "integrity_checks.json").write_text('{"integrity_ok":true,"errors":[],"warnings":[]}')
(folder / "rounds.csv").write_text("round\n1\n")
(folder / "player_rounds.csv").write_text("round\n1\n")
(folder / "players.csv").write_text("steamid,name,team_number\n76561198062530225,CanadianIQ,3\n")
raw = ROOT / "replays/test/batch_001"
raw.mkdir(parents=True)
(raw / "one.dem").write_bytes(b"demo")
(raw / "duplicate.dem").write_bytes(b"demo")
(raw / "new.dem").write_bytes(b"new demo")

root = tk.Tk()
root.withdraw()
window = WorkflowWindow(root)


def settle():
    deadline = time.monotonic() + 20
    while window.busy and time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)
    assert not window.busy, "Scan failed to complete"
    root.update()


settle()
assert [window.tabs.tab(t, "text") for t in window.tabs.tabs()] == ["Packet Builder", "Utilities"]
initial = (window.batch.path, window.matches, set(window.included))
window.open_utilities()
assert window.tabs.select() == str(window.utilities_tab)
window.open_builder()
assert window.tabs.select() == str(window.packet_tab)
assert initial == (window.batch.path, window.matches, set(window.included))
assert len(window.matches) == 1 and window.batch.accepted == 1
assert str(window.build_button["state"]) == "disabled"
original_matches = window.matches
window.matches = (
    replace(
        window.matches[0],
        replay=ReplayQuality(True, 16, "Validated tracks", unobserved_players=("76561198062530225",)),
    ),
)
window.show_player()
assert str(window.build_button["state"]) == "disabled"
assert "No recorded viewer positions" in window.status.get()
window.matches = original_matches
window.require_viewer.set(False)
window.show_player()
assert str(window.build_button["state"]) == "normal"
window.require_viewer.set(True)

packet_ui.filedialog.askdirectory = lambda **kwargs: str(raw)
window.browse_raw()
settle()
assert len(window.matches) == 3
assert sum(bool(m.problem) for m in window.matches) == 1
assert len(window.included) == 2
assert window.batch.accepted == 1, "Keep canonical analysis when a renamed duplicate is present"
assert str(window.prepare_button["state"]) == "normal"
raw_matches = window.matches
window.matches = tuple(replace(m, replay=ReplayQuality(True, 16, "Validated tracks")) for m in window.matches)
window.show_player()
assert str(window.build_button["state"]) == "normal"
assert str(window.repair_button["state"]) == "disabled", "Ready replay data should not offer a no-op repair"
assert str(window.prepare_button["state"]) == "normal", "Missing core data still needs preparation"
window.matches = raw_matches
window.show_player()
window.name_filter.set("new")
assert len(window.tree.get_children()) == 1
assert "1 included games hidden" in window.visible_summary.get()
window.set_visible(False)
assert len(window.included) == 1
saved = ROOT / "selection.json"
packet_ui.filedialog.asksaveasfilename = lambda **kwargs: str(saved)
window.save_selection()
assert len(json.loads(saved.read_text())["included"]) == 1
# Metadata directories still exist after relocation; translate even when present.
legacy = ROOT / "01_Demos/test/batch_001"
legacy.mkdir(parents=True)
record = json.loads(saved.read_text())
record["raw"] = str(legacy)
saved.write_text(json.dumps(record))
window.name_filter.set("")
window.set_visible(False)
packet_ui.filedialog.askopenfilename = lambda **kwargs: str(saved)
window.load_selection()
settle()
assert Path(window.raw.get()) == raw
assert len(window.included) == 1
window.operation = "prepare"
window.cancel_path = ROOT / "cancel"
window.set_busy(True)
window.open_utilities()
assert window.tabs.select() == str(window.utilities_tab)
window.open_builder()
assert str(window.batch_combo["state"]) == "disabled"
previous_raw = window.raw.get()
window.select_collection()
assert window.raw.get() == previous_raw
window.cancel()
assert window.cancel_path.exists()
window.set_busy(False)

window.select_collection()
settle()
assert not window.raw.get(), "A changed collection must clear its previous raw-folder pairing"

# A completely new raw batch must appear even before its analysis directory exists.
new_raw = ROOT / "replays/new_batch/batch_001"
new_raw.mkdir(parents=True)
(new_raw / "fresh.dem").write_bytes(b"fresh")
packet_ui.filedialog.askdirectory = lambda **kwargs: str(new_raw)
window.browse_raw()
settle()
assert window.batch.path.name == "analyzed_new_batch" and not window.batch.path.exists()
assert len(window.matches) == 1 and not window.matches[0].core_ready
assert str(window.prepare_button["state"]) == "normal"
# Valid-looking replay metadata must not prevent missing core analysis preparation.

window.matches = (replace(window.matches[0], replay=ReplayQuality(True, 16, "Validated tracks")),)
started = []
window.background = lambda fn, kind, token=None: started.append(kind)
window.start_prepare("prepare")
assert started == ["prepared"]
assert len(json.loads(next((ROOT / ".extraction_jobs").glob("ui_*/jobs.json")).read_text())) == 1
window.set_busy(False)
if "--screenshot" in sys.argv:
    import subprocess

    root.deiconify()
    root.attributes("-topmost", True)
    root.lift()
    root.update()
    print("Screen:", root.winfo_screenwidth(), root.winfo_screenheight(), "Window:", root.winfo_geometry())
    time.sleep(0.3)
    python = Path(__file__).resolve().parents[1] / ".venv/Scripts/python.exe"
    window.operation = None
    window.show_batch()
    for tab, name in [(window.packet_tab, "packet_builder"), (window.utilities_tab, "utilities")]:
        window.tabs.select(tab)
        root.update()
        time.sleep(0.15)
        box = (
            root.winfo_rootx(),
            root.winfo_rooty(),
            root.winfo_rootx() + root.winfo_width(),
            root.winfo_rooty() + root.winfo_height(),
        )
        destination = ROOT / (name + ".png")
        subprocess.run(
            [
                str(python),
                "-c",
                "from PIL import ImageGrab; ImageGrab.grab(bbox="
                + repr(box)
                + ").save("
                + repr(str(destination))
                + ")",
            ],
            check=True,
        )
        print("Screenshot:", destination)
    root.geometry("900x650")
    window.open_builder()
    root.update()
    # Content must remain reachable at the supported minimum size.
    canvas = window.packet_tab.winfo_children()[0]
    canvas.yview_moveto(1)
    root.update()
    assert window.build_button.winfo_ismapped()
    assert (
        window.build_button.winfo_rooty() + window.build_button.winfo_height()
        < root.winfo_rooty() + root.winfo_height()
    )
    destination = ROOT / "packet_builder_small.png"
    box = (
        root.winfo_rootx(),
        root.winfo_rooty(),
        root.winfo_rootx() + root.winfo_width(),
        root.winfo_rooty() + root.winfo_height(),
    )
    subprocess.run(
        [
            str(python),
            "-c",
            "from PIL import ImageGrab; ImageGrab.grab(bbox="
            + repr(box)
            + ").save("
            + repr(str(destination))
            + ")",
        ],
        check=True,
    )
    print("Screenshot:", destination)
root.destroy()
print("Tk workflow callbacks passed: inclusion, filters, save/load, cancellation, new batch mapping.")
