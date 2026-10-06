"""Launch the local coach-packet window; no scientific packages required to open it."""
from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from cs2di import config  # noqa: E402
from cs2di.packet_jobs import build_packet, discover_batches, export_zip, inspect_batch  # noqa: E402

COACH_INSTRUCTION = "Open PROMPT.md in this folder and follow it. Work only inside this folder."


class PacketWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("CS2 Coach · Packet Builder")
        self.root.geometry("920x750")
        self.root.minsize(780, 650)
        self.events = queue.Queue()
        self.busy = False
        self.batch = None
        self.packet = None
        self.batches = []
        self.custom_batch = None
        self.generation = 0
        self.analysis = tk.StringVar(value=str(config.root() / "02_Analysis"))
        self.destination = tk.StringVar(value=str(config.root() / "06_Handoff_and_Tests/packets"))
        self.batch_name = tk.StringVar()
        self.player_name = tk.StringVar()
        self.kind = tk.StringVar(value="PUG / FACEIT / Premier")
        self.status = tk.StringVar(value="Choose an extracted batch to begin.")
        self.summary = tk.StringVar(value="Raw .dem files must be extracted before using this window.")
        self.selected = tk.StringVar(value="")
        self.location = tk.StringVar(value="")
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("Heading.TLabel", font=("Segoe UI", 11, "bold"))
        root.option_add("*Font", "{Segoe UI} 10")
        page = ttk.Frame(root, padding=24)
        page.pack(fill="both", expand=True)
        page.columnconfigure(1, weight=1)
        ttk.Label(page, text="Build a coach packet", style="Title.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(page, text="Choose a demo batch, prepare its data, then build a packet for a fresh AI coach.",
                  wraplength=840).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 20))
        self.inputs = []
        for row, label, var, browse in ((2, "Analysis folder", self.analysis, self.browse_analysis),
                                        (6, "Save packets in", self.destination, self.browse_destination)):
            ttk.Label(page, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
            entry = ttk.Entry(page, textvariable=var, state="readonly")
            entry.grid(row=row, column=1, sticky="ew", pady=6)
            button = ttk.Button(page, text="Browse…", command=browse)
            button.grid(row=row, column=2, padx=(10, 0))
            self.inputs.append(button)
        for row, label, var, values in ((3, "Demo batch", self.batch_name, []),
                                       (4, "Player", self.player_name, []),
                                       (5, "Match type", self.kind, ["PUG / FACEIT / Premier", "Tournament / pro"])):
            ttk.Label(page, text=label).grid(row=row, column=0, sticky="w", pady=6)
            combo = ttk.Combobox(page, textvariable=var, values=values, state="readonly")
            combo.grid(row=row, column=1, columnspan=1 if row == 3 else 2, sticky="ew", pady=6)
            self.inputs.append(combo)
            if row == 3:
                self.batch_combo = combo
                combo.bind("<<ComboboxSelected>>", lambda e: self.load_batch())
                button = ttk.Button(page, text="Choose folder…", command=self.browse_batch)
                button.grid(row=row, column=2, padx=(10, 0))
                self.inputs.append(button)
            elif row == 4:
                self.player_combo = combo
                combo.bind("<<ComboboxSelected>>", lambda e: self.show_player())
        ttk.Label(page, textvariable=self.summary, wraplength=820).grid(row=7, column=0, columnspan=3, sticky="w", pady=(12, 4))
        ttk.Label(page, textvariable=self.selected, style="Heading.TLabel", wraplength=820).grid(row=8, column=0, columnspan=3, sticky="w")
        controls = ttk.Frame(page)
        controls.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(12, 10))
        self.build_button = ttk.Button(controls, text="Build coach packet", command=self.start_build, state="disabled")
        self.build_button.pack(side="left")
        self.refresh_button = ttk.Button(controls, text="Refresh batches", command=self.refresh)
        self.refresh_button.pack(side="left", padx=12)
        self.inputs.append(self.refresh_button)
        self.progress = ttk.Progressbar(page, mode="indeterminate")
        self.progress.grid(row=10, column=0, columnspan=3, sticky="ew")
        ttk.Label(page, textvariable=self.status, wraplength=820).grid(row=11, column=0, columnspan=3, sticky="w", pady=8)
        details = ttk.LabelFrame(page, text="Progress and excluded matches", padding=8)
        details.grid(row=12, column=0, columnspan=3, sticky="nsew")
        page.rowconfigure(12, weight=1)
        self.log = tk.Text(details, height=8, wrap="word", state="disabled", font=("Consolas", 9))
        scroll = ttk.Scrollbar(details, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        ttk.Label(page, textvariable=self.location, wraplength=820).grid(row=13, column=0, columnspan=3, sticky="w", pady=(10, 4))
        result = ttk.Frame(page)
        result.grid(row=14, column=0, columnspan=3, sticky="w")
        self.result_buttons = []
        for label, action in (("Open packet folder", self.open_packet), ("Copy AI instructions", self.copy_instruction),
                              ("Export ZIP…", self.save_zip)):
            button = ttk.Button(result, text=label, command=action, state="disabled")
            button.pack(side="left", padx=(0, 10))
            self.result_buttons.append(button)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        root.after(100, self.poll)

    def append(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def set_busy(self, busy):
        self.busy = busy
        for widget in self.inputs:
            widget.configure(state="disabled" if busy else "readonly" if isinstance(widget, ttk.Combobox) else "normal")
        self.build_button.configure(state="disabled" if busy or not self.batch or not self.batch.players else "normal")
        for button in self.result_buttons:
            button.configure(state="normal" if self.packet and not busy else "disabled")
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress["value"] = 0

    def background(self, fn, kind, token=None):
        def work():
            try:
                self.events.put((kind, token, fn()))
            except Exception as exc:
                self.events.put(("error", token, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def refresh(self, preferred=None):
        if preferred is None and self.batch and self.batch.path.parent == Path(self.analysis.get()).resolve():
            preferred = self.batch.path
        self.generation += 1
        self.batch = None
        self.packet = None
        self.location.set("")
        for button in self.result_buttons:
            button.configure(state="disabled")
        self.player_combo.configure(values=[])
        self.player_name.set("")
        self.selected.set("")
        self.batches = discover_batches(Path(self.analysis.get()))
        if self.custom_batch and self.custom_batch not in self.batches:
            self.batches.append(self.custom_batch)
        self.batch_combo.configure(values=[p.name for p in self.batches])
        self.build_button.configure(state="disabled")
        if self.batches:
            self.batch_combo.current(self.batches.index(preferred) if preferred in self.batches else 0)
            self.load_batch()
        else:
            self.batch_name.set("")
            self.summary.set("No analysed batches found. Use Choose folder to select an extracted batch directly.")
            self.status.set("Waiting for an analysed batch.")

    def load_batch(self):
        self.generation += 1
        self.batch = None
        self.packet = None
        self.location.set("")
        for button in self.result_buttons:
            button.configure(state="disabled")
        self.player_name.set("")
        self.player_combo.configure(values=[])
        self.selected.set("")
        self.build_button.configure(state="disabled")
        self.clear()
        self.status.set("Reading players and checking match integrity…")
        path = self.batches[self.batch_combo.current()]
        self.summary.set(f"Selected folder: {path}")
        self.background(lambda: inspect_batch(path), "batch", self.generation)

    def show_player(self):
        if self.batch and self.batch.players:
            self.packet = None
            self.location.set("")
            for button in self.result_buttons:
                button.configure(state="disabled")
            p = self.batch.players[self.player_combo.current()]
            self.selected.set(f"Packet will contain {len(p.demos)} usable matches featuring {p.name}.")
            self.status.set("Ready to build. Other players' matches and excluded matches will not be included.")

    def start_build(self):
        if self.busy or not self.batch or not self.batch.players:
            return
        batch, player = self.batch, self.batch.players[self.player_combo.current()]
        destination = Path(self.destination.get())
        kind = "pro" if self.kind.get() == "Tournament / pro" else "pug"
        self.packet = None
        self.location.set("")
        self.set_busy(True)
        self.status.set("Building packet. This window stays responsive; detailed analysis may take several minutes.")
        self.background(lambda: build_packet(REPO, batch, player, destination, kind=kind,
                        on_log=lambda line: self.events.put(("log", None, line))), "packet")

    def poll(self):
        while not self.events.empty():
            kind, token, value = self.events.get_nowait()
            if token is not None and token != self.generation:
                continue
            if kind == "log":
                self.append(value)
            elif kind == "batch":
                self.batch = value
                self.summary.set(f"Selected folder: {value.path}\n{value.accepted} usable matches · {len(value.excluded)} excluded · "
                                 f"{value.ignored} temporary or unrelated folders ignored")
                labels = [f"{p.name} — {len(p.demos)} matches — {p.steamid}" for p in value.players]
                self.player_combo.configure(values=labels)
                for exclusion in value.excluded:
                    self.append("Excluded: " + exclusion)
                if labels:
                    self.player_combo.current(0)
                    self.show_player()
                else:
                    self.status.set("No players with usable matches were found. Check the exclusions below.")
                self.set_busy(False)
            elif kind == "packet":
                self.packet = value
                self.location.set(str(value))
                self.status.set("Packet ready. Start a fresh AI session in this folder, or export it as a ZIP.")
                self.set_busy(False)
            elif kind == "zip":
                self.status.set(f"ZIP saved: {value}")
                self.set_busy(False)
            elif kind == "error":
                self.append(value)
                self.status.set("Could not complete this step. See the details below.")
                self.set_busy(False)
                messagebox.showerror("Packet builder", value, parent=self.root)
        self.root.after(100, self.poll)

    def browse_analysis(self):
        folder = filedialog.askdirectory(title="Choose the folder containing analyzed_* batches", initialdir=self.analysis.get())
        if folder:
            self.custom_batch = None
            self.batch = None
            self.analysis.set(folder)
            self.refresh()

    def browse_batch(self):
        folder = filedialog.askdirectory(
            title="Choose an extracted batch folder containing match folders",
            initialdir=str(self.batch.path) if self.batch else self.analysis.get())
        if folder:
            self.custom_batch = Path(folder).resolve()
            self.analysis.set(str(self.custom_batch.parent))
            self.refresh(preferred=self.custom_batch)

    def browse_destination(self):
        folder = filedialog.askdirectory(title="Choose where packets will be saved", initialdir=self.destination.get())
        if folder:
            self.destination.set(folder)

    def open_packet(self):
        if sys.platform == "win32":
            os.startfile(self.packet)

    def copy_instruction(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(COACH_INSTRUCTION)
        self.status.set("Instructions copied. Use them in a fresh AI session opened inside the packet folder.")

    def save_zip(self):
        destination = filedialog.asksaveasfilename(title="Export coach packet", initialdir=str(self.packet.parent),
                    initialfile=self.packet.name + ".zip", defaultextension=".zip", filetypes=[("ZIP archive", "*.zip")])
        if destination:
            packet = self.packet
            self.set_busy(True)
            self.status.set("Compressing packet…")
            self.background(lambda: export_zip(packet, Path(destination)), "zip")

    def close(self):
        if self.busy:
            messagebox.showinfo("Build in progress", "Please let the current build or export finish before closing.", parent=self.root)
        else:
            self.root.destroy()


def main():
    sys.modules.setdefault("packet_ui", sys.modules[__name__])
    from packet_workflow_ui import WorkflowWindow
    root = tk.Tk()
    WorkflowWindow(root)
    if "--smoke-test" in sys.argv:
        root.update()
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
