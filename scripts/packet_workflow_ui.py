"""Batch workflow controls layered on the packet window's existing build/export UI."""

from __future__ import annotations
import json
import os
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from uuid import uuid4
from packet_ui import PacketWindow, REPO
from cs2di import config
from cs2di.evidence import check_demo
from cs2di.batch_selection import scan_matches, selection_record
from cs2di.packet_jobs import build_packet, inspect_batch, process_options, python_for


class WorkflowWindow(PacketWindow):
    def __init__(self, root):
        self.raw = tk.StringVar(root)
        self.require_viewer = tk.BooleanVar(root, value=True)
        self.map_filter = tk.StringVar(root, value="All maps")
        self.name_filter = tk.StringVar(root)
        self.cpu_target = tk.StringVar(root, value="80")
        self.memory_target = tk.StringVar(root, value="90")
        self.workers = tk.StringVar(root, value=str(min(8, os.cpu_count() or 1)))
        self.matches = ()
        self.included = set()
        self.last_source = None
        self.pending_record = None
        self.failed_jobs = []
        self.retry_phase = "prepare"
        self.cancel_path = None
        self.operation = None
        self.cache_path = config.root() / ".extraction_jobs" / ("hashes_" + uuid4().hex + ".json")
        super().__init__(root)

    def build_layout(self):
        from packet_layout import build_layout

        build_layout(self)

    def open_utilities(self):
        self.tabs.select(self.utilities_tab)

    def open_builder(self):
        self.tabs.select(self.packet_tab)

    def select_collection(self):
        if self.busy:
            return
        # A raw-folder pairing belongs to one collection, never another dropdown choice.
        self.raw.set("")
        self.load_batch()

    def reset_filters(self):
        self.map_filter.set("All maps")
        self.name_filter.set("")

    def control(self, parent, label, command):
        button = ttk.Button(parent, text=label, command=command)
        self.inputs.append(button)
        return button

    def current_player(self):
        index = self.player_combo.current()
        return self.batch.players[index] if self.batch and 0 <= index < len(self.batch.players) else None

    def update_actions(self):
        player = self.current_player()
        quality = {m.analysis: m.replay for m in self.matches}
        ready = player and (
            not self.require_viewer.get()
            or all(
                (
                    quality[p].ready and player.steamid not in quality[p].unobserved_players
                    for p in player.demos
                )
            )
        )
        self.build_button.configure(state="normal" if ready and (not self.busy) else "disabled")
        if hasattr(self, "prepare_button"):
            raw_matches = [
                m for i, m in enumerate(self.matches) if str(i) in self.included and m.raw and not m.problem
            ]
            prepare_needed = any(not m.core_ready or not m.replay.ready for m in raw_matches)
            repair_needed = any(m.core_ready and not m.replay.ready for m in raw_matches)
            self.prepare_button.configure(state="normal" if prepare_needed and not self.busy else "disabled")
            self.repair_button.configure(state="normal" if repair_needed and not self.busy else "disabled")
            self.retry_button.configure(
                state="normal" if self.failed_jobs and (not self.busy) else "disabled"
            )

    def set_busy(self, busy):
        super().set_busy(busy)
        self.update_actions()
        if hasattr(self, "cancel_button"):
            self.cancel_button.configure(
                state="normal" if busy and self.operation == "prepare" else "disabled"
            )

    def refresh(self, preferred=None):
        if self.busy:
            return
        super().refresh(preferred)
        index = self.batch_combo.current()
        self.batch_combo.configure(
            values=[p.name.removeprefix("analyzed_").removesuffix("_demos") for p in self.batches]
        )
        if index >= 0:
            self.batch_combo.current(index)

    def browse_analysis(self):
        if self.busy:
            return
        folder = filedialog.askdirectory(
            title="Choose the analysis collections folder", initialdir=self.analysis.get()
        )
        if folder:
            self.raw.set("")
            self.custom_batch = None
            self.analysis.set(folder)
            self.refresh()

    def browse_batch(self):
        if self.busy:
            return
        folder = filedialog.askdirectory(
            title="Choose an analysis collection", initialdir=self.analysis.get()
        )
        if folder:
            self.raw.set("")
            self.custom_batch = Path(folder).resolve()
            self.analysis.set(str(self.custom_batch.parent))
            self.refresh(preferred=self.custom_batch)

    def load_batch(self):
        if self.busy:
            return
        index = self.batch_combo.current()
        if index < 0:
            return
        path = self.batches[index]
        raw = Path(self.raw.get()) if self.raw.get() else None
        same = self.last_source == (path, raw)
        previous = {self.matches[int(i)].analysis for i in self.included} if same else None
        self.last_source = (path, raw)
        if not same:
            self.failed_jobs = []
            self.reset_filters()
        record = self.pending_record
        self.pending_record = None
        old_sid = self.current_player().steamid if self.current_player() else None
        self.generation += 1
        self.batch = None
        self.packet = None
        self.location.set("")
        self.match_details.set("Highlight a game to see its validation details.")
        self.operation = "scan"
        self.set_busy(True)
        self.status.set("Mapping demos and checking duplicate identities, integrity and viewer coverage…")

        def scan():
            matches = scan_matches(path, raw, self.cache_path)
            if record:
                names, identities = (set(record["included"]), record.get("identities", {}))
                included = {
                    str(i)
                    for i, m in enumerate(matches)
                    if m.analysis.name in names
                    and (not m.problem)
                    and (m.analysis.name not in identities or identities[m.analysis.name] == m.sha256)
                }
            else:
                included = {
                    str(i)
                    for i, m in enumerate(matches)
                    if not m.problem and (previous is None or m.analysis in previous)
                }
            batch = inspect_batch(
                path,
                [m.analysis for i, m in enumerate(matches) if str(i) in included and m.core_ready],
                matches,
            )
            return (matches, included, batch, old_sid)

        self.background(scan, "scan", self.generation)

    def render_matches(self):
        if not hasattr(self, "tree"):
            return
        self.tree.delete(*self.tree.get_children())
        for i, m in enumerate(self.matches):
            if self.name_filter.get().casefold() not in m.analysis.name.casefold():
                continue
            if self.map_filter.get() != "All maps" and self.map_filter.get() != m.map_name:
                continue
            identity = m.problem or (
                "Raw SHA verified"
                if m.raw
                else "Recorded SHA"
                if m.sha256
                else "Original identity unavailable"
            )
            self.tree.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    "✓" if str(i) in self.included else "",
                    m.analysis.name,
                    m.map_name,
                    "Ready" if m.core_ready else "Missing / invalid",
                    f"{m.replay.hz:g} Hz · {m.replay.reason}",
                    identity,
                ),
            )

        if hasattr(self, "visible_summary"):
            visible = set(self.tree.get_children())
            hidden = len(self.included - visible)
            self.visible_summary.set(
                f"{len(visible)} of {len(self.matches)} games visible · {len(self.included)} included · {hidden} included games hidden by filters"
            )

    def describe_row(self, event=None):
        rows = self.tree.selection()
        if not rows:
            self.match_details.set("Highlight a match for its full name and validation details.")
            return
        match = self.matches[int(rows[0])]
        reasons = ", ".join(check_demo(match.analysis).reasons)
        self.match_details.set(
            f"{match.analysis.name} · {match.problem or reasons or 'Core integrity passed'}\nViewer: {match.replay.reason}; {match.replay.paths} recorded grenade paths"
        )

    def toggle_rows(self):
        if self.busy:
            return
        for i in self.tree.selection():
            if not self.matches[int(i)].problem:
                self.included.symmetric_difference_update({i})
        self.recount()

    def set_visible(self, use):
        if self.busy:
            return
        for i in self.tree.get_children():
            if self.matches[int(i)].problem:
                continue
            self.included.add(i) if use else self.included.discard(i)
        self.recount()

    def recount(self):
        self.packet = None
        self.location.set("")
        self.render_matches()
        if self.batch:
            old_sid = self.current_player().steamid if self.current_player() else None
            self.batch = inspect_batch(
                self.batch.path,
                [m.analysis for i, m in enumerate(self.matches) if str(i) in self.included and m.core_ready],
                self.matches,
            )
            self.show_batch(old_sid)

    def show_batch(self, old_sid=None):
        labels = [f"{p.name} — {len(p.demos)} matches — {p.steamid}" for p in self.batch.players]
        self.player_combo.configure(values=labels)
        if labels:
            self.player_combo.current(
                next((i for i, p in enumerate(self.batch.players) if p.steamid == old_sid), 0)
            )
        else:
            self.player_name.set("")
        self.summary.set(
            f"{self.batch.path}\n{len(self.matches)} candidates · {len(self.included)} included · {self.batch.accepted} valid analysis · {sum((bool(m.problem) for m in self.matches))} blocked/duplicates"
        )
        self.show_player()

    def show_player(self):
        player = self.current_player()
        self.packet = None
        self.location.set("")
        for b in self.result_buttons:
            b.configure(state="disabled")
        if player:
            selected = [m for m in self.matches if m.analysis in player.demos]
            ready = sum(
                (m.replay.ready and player.steamid not in m.replay.unobserved_players for m in selected)
            )
            self.selected.set(
                f"Packet: {len(player.demos)} included matches featuring {player.name}; {ready}/{len(selected)} have validated 16 Hz viewer data."
            )
            self.status.set(
                "Ready to build."
                if ready == len(selected) or not self.require_viewer.get()
                else "Replay data needs attention. Open Utilities to prepare or repair it."
            )
            missing_player = sum(player.steamid in m.replay.unobserved_players for m in selected)
            if missing_player and self.require_viewer.get():
                self.status.set(
                    f"No recorded viewer positions for this player in {missing_player} included matches. Exclude those games or allow limited replays."
                )
        else:
            self.selected.set(
                "No player with usable included analysis yet. Prepare missing analysis or change inclusion."
            )
            self.status.set(
                "Include at least one usable game."
                if not self.included
                else "Selected games need analysis. Open Utilities to analyze them."
                if self.raw.get()
                else "Choose an analyzed collection or an original demo batch to begin."
            )
        self.utilities_button.configure(
            text="Open Utilities / logs"
            if player and (ready == len(selected) or not self.require_viewer.get())
            else "Prepare data in Utilities"
        )
        self.update_actions()

    def start_build(self):
        player = self.current_player()
        if self.busy or not player:
            return
        batch, output, required = (self.batch, Path(self.destination.get()), self.require_viewer.get())
        kind = "pro" if self.kind.get() == "Tournament / pro" else "pug"
        self.packet = None
        self.location.set("")
        self.operation = "build"
        self.status.set("Building and validating the packet. Progress is available in Utilities.")
        self.set_busy(True)
        self.background(
            lambda: build_packet(
                REPO,
                batch,
                player,
                output,
                kind=kind,
                require_viewer=required,
                on_log=lambda s: self.events.put(("log", None, s)),
            ),
            "packet",
        )

    def start_prepare(self, phase, retry=False):
        if self.busy:
            return
        phase = self.retry_phase if retry else phase
        self.retry_phase = phase
        try:
            cpu, memory, workers = (
                int(self.cpu_target.get()),
                int(self.memory_target.get()),
                int(self.workers.get()),
            )
            if not 10 <= cpu <= 95 or not 20 <= memory <= 95 or workers < 1:
                raise ValueError()
        except ValueError:
            messagebox.showerror(
                "Resource settings", "CPU 10–95%, RAM 20–95%, at least one job.", parent=self.root
            )
            return
        allowed = {
            m.analysis for i, m in enumerate(self.matches) if str(i) in self.included and not m.problem
        }
        jobs = (
            [j for j in self.failed_jobs if Path(j["analysis"]) in allowed]
            if retry
            else [
                {"demo": str(m.raw), "analysis": str(m.analysis), "sha256": m.sha256}
                for i, m in enumerate(self.matches)
                if str(i) in self.included
                and m.raw
                and (not m.problem)
                and (not m.replay.ready or (phase == "prepare" and not m.core_ready))
                and (phase == "prepare" or m.core_ready)
            ]
        )
        if not jobs:
            self.status.set("Nothing to process. Selected games are ready, or need an original demo folder.")
            return
        work = config.root() / ".extraction_jobs" / ("ui_" + uuid4().hex)
        work.mkdir(parents=True)
        spec, report = (work / "jobs.json", work / "summary.json")
        self.cancel_path = work / "cancel"
        cancel = self.cancel_path
        spec.write_text(json.dumps(jobs), encoding="utf-8")
        self.packet = None
        self.location.set("")
        self.operation = "prepare"
        self.open_utilities()
        self.set_busy(True)
        self.status.set("Preparing selected matches. Cancel stops queued jobs; active jobs finish safely.")

        def run():
            python = python_for(REPO)
            check = subprocess.run(
                [str(python), "-c", "import demoparser2, psutil"],
                capture_output=True,
                text=True,
                **process_options(),
            )
            if check.returncode:
                raise RuntimeError(
                    f'From the repository, install extraction dependencies:\n& "{python}" -m pip install -e ".[parse]"'
                )
            command = [
                str(python),
                "-u",
                str(REPO / "scripts/fix_viewer_data.py"),
                "--root",
                str(config.root()),
                "--jobs",
                str(spec),
                "--report",
                str(report),
                "--cancel",
                str(cancel),
                "--phase",
                phase,
                "--cpu-target",
                str(cpu),
                "--memory-target",
                str(memory),
                "--max-workers",
                str(workers),
            ]
            with subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "PYTHONUTF8": "1"},
                **process_options(),
            ) as process:
                for line in process.stdout:
                    self.events.put(("log", None, line.rstrip()))
                code = process.wait()
            if not report.exists():
                raise RuntimeError(f"Preparation exited {code}. See the Utilities log.")
            return json.loads(report.read_text(encoding="utf-8"))

        self.background(run, "prepared")

    def cancel(self):
        if self.cancel_path and self.operation == "prepare":
            self.cancel_path.touch()
            self.cancel_button.configure(state="disabled")
            self.status.set("Cancellation requested; waiting for active jobs to finish.")

    def poll(self):
        while not self.events.empty():
            kind, token, value = self.events.get_nowait()
            if token is not None and token != self.generation:
                continue
            if kind == "log":
                self.append(value)
            elif kind == "scan":
                self.matches, self.included, self.batch, sid = value
                self.map_combo.configure(values=["All maps"] + sorted({m.map_name for m in self.matches}))
                self.map_filter.set("All maps")
                self.render_matches()
                self.set_busy(False)
                self.show_batch(sid)
                for exclusion in self.batch.excluded:
                    self.append("Excluded: " + exclusion)
                for m in self.matches:
                    if m.problem:
                        self.append(f"Excluded {m.analysis.name}: {m.problem}")
            elif kind == "prepared":
                self.failed_jobs = [r["job"] for r in value["results"] if r["status"] == "failed"]
                self.append(
                    f"Preparation finished: {len(self.failed_jobs)} failed. Logs: {value['run_folder']}"
                )
                self.set_busy(False)
                self.load_batch()
            elif kind == "packet":
                self.packet = value
                self.location.set(str(value))
                self.set_busy(False)
                self.status.set("Packet ready. Open the folder or export a ZIP for a fresh AI.")
            elif kind == "zip":
                self.set_busy(False)
                self.status.set(f"ZIP saved: {value}")
            elif kind == "error":
                self.open_utilities()
                self.append(value)
                self.set_busy(False)
                self.status.set("Step failed. See the Utilities log for details.")
                messagebox.showerror("Packet builder", value, parent=self.root)
        self.root.after(100, self.poll)

    def browse_raw(self):
        if self.busy:
            return
        folder = filedialog.askdirectory(
            title="Choose raw demo batch or subfolder", initialdir=str(config.demos_root())
        )
        if folder:
            raw = Path(folder).resolve()
            self.raw.set(str(raw))
            base = (config.demos_root()).resolve()
            if raw.is_relative_to(base) and raw != base:
                self.custom_batch = Path(self.analysis.get()) / (
                    "analyzed_"
                    + config.collection_name(base / raw.relative_to(base).parts[0], Path(self.analysis.get()))
                )
                self.refresh(preferred=self.custom_batch)
            elif self.batches:
                self.load_batch()
            else:
                self.status.set("Choose an analysis collection to pair with this raw folder.")

    def clear_raw(self):
        self.raw.set("")
        self.load_batch()

    def save_selection(self):
        if not self.batch:
            return
        path = filedialog.asksaveasfilename(
            title="Save batch selection", defaultextension=".json", filetypes=[("JSON", "*.json")]
        )
        if path:
            record = selection_record(
                self.batch.path,
                Path(self.raw.get()) if self.raw.get() else None,
                [m.analysis for i, m in enumerate(self.matches) if str(i) in self.included],
                self.matches,
            )
            Path(path).write_text(json.dumps(record, indent=2), encoding="utf-8")

    def load_selection(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(title="Load batch selection", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            record = json.loads(Path(path).read_text(encoding="utf-8"))
            if record["version"] != 1 or not isinstance(record["included"], list):
                raise ValueError("Unsupported selection file")
            analysis, raw = (Path(record["analysis"]).resolve(), record.get("raw"))
            if raw:
                relocated = config.relocated_selection(Path(raw))
                if relocated.is_dir():
                    raw = str(relocated)
            if raw and (not Path(raw).is_dir()):
                raise ValueError("Saved raw folder is missing")
            self.custom_batch = analysis
            self.analysis.set(str(analysis.parent))
            self.raw.set(raw or "")
            self.pending_record = record
            self.refresh(preferred=analysis)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("Selection", str(exc), parent=self.root)
