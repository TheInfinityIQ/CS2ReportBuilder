"""Two task-oriented tabs; shared selection and progress, no extraction logic."""

import os
import tkinter as tk
from tkinter import ttk


def scroll_page(tabs, title):
    page = ttk.Frame(tabs)
    tabs.add(page, text=title)
    canvas = tk.Canvas(page, highlightthickness=0, background="#f0f0f0")
    bar = ttk.Scrollbar(page, command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set)
    canvas.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")
    body = ttk.Frame(canvas, padding=12)
    item = canvas.create_window(0, 0, window=body, anchor="nw")

    def resize(event=None):
        canvas.itemconfigure(
            item, width=canvas.winfo_width(), height=max(body.winfo_reqheight(), canvas.winfo_height())
        )
        canvas.configure(scrollregion=canvas.bbox("all"))

    canvas.bind("<Configure>", resize)
    body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    return page, body, canvas


def build_layout(w):
    root = w.root
    root.title("CS2 Coach Tools")
    root.geometry(f"1100x{min(900, max(650, root.winfo_screenheight() - 100))}")
    root.minsize(900, 650)
    w.inputs = []
    shell = ttk.Frame(root, padding=16)
    shell.pack(fill="both", expand=True)
    ttk.Label(shell, text="CS2 Coach Tools", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    ttk.Label(
        shell, text="Choose games, prepare their data when needed, and build a packet for your AI coach."
    ).pack(anchor="w", pady=(2, 8))

    source = ttk.LabelFrame(shell, text="Selected demo collection · shared by both tabs", padding=8)
    source.pack(fill="x", pady=(0, 8))
    source.columnconfigure(1, weight=1)
    ttk.Label(source, text="Analyzed collection").grid(row=0, column=0, sticky="w", padx=(0, 8))
    w.batch_combo = ttk.Combobox(source, textvariable=w.batch_name, state="readonly")
    w.batch_combo.grid(row=0, column=1, sticky="ew", pady=3)
    w.batch_combo.bind("<<ComboboxSelected>>", lambda e: w.select_collection())
    w.inputs.append(w.batch_combo)
    w.control(source, "Choose analyzed folder…", w.browse_batch).grid(row=0, column=2, padx=(8, 0))
    w.refresh_button = w.control(source, "Refresh", w.refresh)
    w.refresh_button.grid(row=0, column=3, padx=(8, 0))
    ttk.Label(source, text="Original demo folder").grid(row=1, column=0, sticky="w", padx=(0, 8))
    ttk.Entry(source, textvariable=w.raw, state="readonly").grid(row=1, column=1, sticky="ew", pady=3)
    w.control(source, "Choose demo batch…", w.browse_raw).grid(row=1, column=2, padx=(8, 0))
    w.control(source, "Clear", w.clear_raw).grid(row=1, column=3, padx=(8, 0))

    w.tabs = ttk.Notebook(shell)
    w.tabs.pack(fill="both", expand=True)
    w.packet_tab, packet, packet_canvas = scroll_page(w.tabs, "Packet Builder")
    w.utilities_tab, utilities, utility_canvas = scroll_page(w.tabs, "Utilities")
    packet.columnconfigure(0, weight=1)
    packet.rowconfigure(0, weight=1)

    matches = ttk.LabelFrame(packet, text="1 · Choose games", padding=8)
    matches.grid(row=0, column=0, sticky="nsew")
    matches.columnconfigure(0, weight=1)
    matches.rowconfigure(1, weight=1)
    filters = ttk.Frame(matches)
    filters.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
    ttk.Label(filters, text="Map").pack(side="left")
    w.map_combo = ttk.Combobox(
        filters, textvariable=w.map_filter, values=["All maps"], state="readonly", width=16
    )
    w.map_combo.pack(side="left", padx=6)
    w.inputs.append(w.map_combo)
    ttk.Label(filters, text="Name / date").pack(side="left", padx=(8, 4))
    search = ttk.Entry(filters, textvariable=w.name_filter, width=24)
    search.pack(side="left")
    w.inputs.append(search)
    w.control(filters, "Reset filters", w.reset_filters).pack(side="left", padx=8)
    w.map_filter.trace_add("write", lambda *a: w.render_matches())
    w.name_filter.trace_add("write", lambda *a: w.render_matches())
    w.tree = ttk.Treeview(
        matches,
        columns=("use", "match", "map", "core", "viewer", "identity"),
        show="headings",
        selectmode="extended",
        height=6,
    )
    for col, title, width in (
        ("use", "Use", 36),
        ("match", "Game", 250),
        ("map", "Map", 80),
        ("core", "Analysis", 90),
        ("viewer", "Replay readiness", 195),
        ("identity", "Duplicate / identity check", 160),
    ):
        w.tree.heading(col, text=title)
        w.tree.column(col, width=width, minwidth=35)
    w.tree.grid(row=1, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(matches, command=w.tree.yview)
    scroll.grid(row=1, column=1, sticky="ns")
    w.tree.configure(yscrollcommand=scroll.set)
    w.tree.bind("<Double-1>", lambda e: w.toggle_rows())
    w.tree.bind("<space>", lambda e: w.toggle_rows())
    selection = ttk.Frame(matches)
    selection.grid(row=2, column=0, columnspan=2, sticky="w", pady=6)
    for label, action in (
        ("Toggle highlighted", w.toggle_rows),
        ("Include visible", lambda: w.set_visible(True)),
        ("Exclude visible", lambda: w.set_visible(False)),
        ("Save selection…", w.save_selection),
        ("Load selection…", w.load_selection),
    ):
        w.control(selection, label, action).pack(side="left", padx=(0, 6))
    w.visible_summary = tk.StringVar(root)
    ttk.Label(matches, textvariable=w.visible_summary).grid(row=3, column=0, columnspan=2, sticky="w")
    ttk.Label(
        matches,
        text="Double-click or press Space to toggle games. Filters hide rows; they do not exclude games.",
    ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 0))
    w.match_details = tk.StringVar(root, value="Highlight a game to see its validation details.")
    ttk.Label(matches, textvariable=w.match_details, wraplength=940).grid(
        row=5, column=0, columnspan=2, sticky="w", pady=(4, 0)
    )

    player = ttk.LabelFrame(packet, text="2 · Choose the player", padding=8)
    player.grid(row=1, column=0, sticky="ew", pady=8)
    player.columnconfigure(1, weight=1)
    ttk.Label(player, text="Player").grid(row=0, column=0, padx=(0, 8))
    w.player_combo = ttk.Combobox(player, textvariable=w.player_name, state="readonly")
    w.player_combo.grid(row=0, column=1, sticky="ew")
    w.player_combo.bind("<<ComboboxSelected>>", lambda e: w.show_player())
    w.inputs.append(w.player_combo)
    ttk.Label(player, text="Match type").grid(row=0, column=2, padx=(12, 8))
    kind = ttk.Combobox(
        player,
        textvariable=w.kind,
        values=["PUG / FACEIT / Premier", "Tournament / pro"],
        state="readonly",
        width=23,
    )
    kind.grid(row=0, column=3)
    w.inputs.append(kind)
    ttk.Label(player, textvariable=w.selected, wraplength=940).grid(
        row=1, column=0, columnspan=4, sticky="w", pady=(6, 0)
    )

    output = ttk.LabelFrame(packet, text="3 · Build and hand off", padding=8)
    output.grid(row=2, column=0, sticky="ew")
    output.columnconfigure(1, weight=1)
    ttk.Label(output, text="Save packets in").grid(row=0, column=0, padx=(0, 8))
    ttk.Entry(output, textvariable=w.destination, state="readonly").grid(row=0, column=1, sticky="ew")
    w.control(output, "Change…", w.browse_destination).grid(row=0, column=2, padx=(8, 0))
    actions = ttk.Frame(output)
    actions.grid(row=1, column=0, columnspan=3, sticky="w", pady=8)
    w.build_button = ttk.Button(actions, text="Build coach packet", command=w.start_build, state="disabled")
    w.build_button.pack(side="left", padx=(0, 8))
    w.utilities_button = ttk.Button(actions, text="Open Utilities / logs", command=w.open_utilities)
    w.utilities_button.pack(side="left", padx=(0, 8))
    w.result_buttons = []
    for label, action in (
        ("Open packet", w.open_packet),
        ("Copy AI instructions", w.copy_instruction),
        ("Export ZIP…", w.save_zip),
    ):
        button = ttk.Button(actions, text=label, command=action, state="disabled")
        button.pack(side="left", padx=(0, 8))
        w.result_buttons.append(button)
    ttk.Label(
        output,
        text="Includes coaching instructions, computed findings, selected analysis and replays, and report software/assets.\nRaw .dem files are excluded. Use a fresh AI session with file access and Python.",
        wraplength=940,
    ).grid(row=2, column=0, columnspan=3, sticky="w")
    ttk.Label(output, textvariable=w.location, wraplength=940).grid(
        row=3, column=0, columnspan=3, sticky="w", pady=(4, 0)
    )

    utilities.columnconfigure(0, weight=1)
    utilities.rowconfigure(3, weight=1)
    selection_info = ttk.LabelFrame(utilities, text="Working on the same selected games", padding=8)
    selection_info.grid(row=0, column=0, sticky="ew")
    ttk.Label(selection_info, textvariable=w.summary, wraplength=940).pack(anchor="w")
    ttk.Label(
        selection_info,
        text="Change game inclusion in Packet Builder. Preparation uses included games with available originals.",
    ).pack(anchor="w", pady=4)
    ttk.Button(selection_info, text="Back to Packet Builder", command=w.open_builder).pack(anchor="w")
    w.control(selection_info, "Refresh catalog for selected collection", w.refresh_catalog).pack(
        anchor="w", pady=4
    )
    preparation = ttk.LabelFrame(utilities, text="Prepare or repair data", padding=8)
    preparation.grid(row=1, column=0, sticky="ew", pady=8)
    ttk.Label(
        preparation,
        text="Analyze missing / invalid games and add 16 Hz replays, or repair only replay data. Valid analysis is reused.",
        wraplength=940,
    ).pack(anchor="w")
    buttons = ttk.Frame(preparation)
    buttons.pack(anchor="w", pady=6)
    w.prepare_button = w.control(
        buttons, "Analyze missing games + replays", lambda: w.start_prepare("prepare")
    )
    w.repair_button = w.control(buttons, "Repair replay data", lambda: w.start_prepare("viewer"))
    w.retry_button = w.control(buttons, "Retry failed", lambda: w.start_prepare("prepare", retry=True))
    for b in (w.prepare_button, w.repair_button, w.retry_button):
        b.pack(side="left", padx=(0, 8))
    w.cancel_button = ttk.Button(buttons, text="Cancel queued jobs", command=w.cancel, state="disabled")
    w.cancel_button.pack(side="left")
    resources = ttk.Frame(preparation)
    resources.pack(anchor="w", pady=4)
    for label, var, lo, hi in (
        ("CPU target %", w.cpu_target, 10, 95),
        ("RAM limit %", w.memory_target, 20, 95),
        ("Max jobs", w.workers, 1, max(8, os.cpu_count() or 1)),
    ):
        ttk.Label(resources, text=label).pack(side="left", padx=(0, 4))
        spin = ttk.Spinbox(resources, textvariable=var, from_=lo, to=hi, width=5)
        spin.pack(side="left", padx=(0, 12))
        w.inputs.append(spin)
    ttk.Label(
        preparation,
        text="Limits guide when new jobs start; active jobs finish safely. Cancel stops queued jobs, then waits for active jobs.",
        wraplength=940,
    ).pack(anchor="w")
    settings = ttk.LabelFrame(utilities, text="Paths and packet options", padding=8)
    settings.grid(row=2, column=0, sticky="ew", pady=(0, 8))
    settings.columnconfigure(1, weight=1)
    ttk.Label(settings, text="Analysis root").grid(row=0, column=0, padx=(0, 8))
    ttk.Entry(settings, textvariable=w.analysis, state="readonly").grid(row=0, column=1, sticky="ew")
    w.control(settings, "Change…", w.browse_analysis).grid(row=0, column=2, padx=(8, 0))
    check = ttk.Checkbutton(
        settings,
        text="Require validated 16 Hz replays in packets (recommended)",
        variable=w.require_viewer,
        command=w.show_player,
    )
    check.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
    w.inputs.append(check)
    ttk.Label(
        settings, text="Turn this off only to intentionally build a packet with limited replay evidence."
    ).grid(row=2, column=0, columnspan=3, sticky="w")
    logs = ttk.LabelFrame(utilities, text="Progress and errors", padding=8)
    logs.grid(row=3, column=0, sticky="nsew")
    w.log = tk.Text(logs, height=10, wrap="word", state="disabled", font=("Consolas", 9))
    scroll = ttk.Scrollbar(logs, command=w.log.yview)
    w.log.configure(yscrollcommand=scroll.set)
    w.log.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")

    w.progress = ttk.Progressbar(shell, mode="indeterminate")
    w.progress.pack(fill="x", pady=(8, 0))
    ttk.Label(shell, textvariable=w.status, wraplength=1020).pack(fill="x", pady=(4, 0))

    def wheel(event):
        if isinstance(event.widget, (ttk.Treeview, tk.Text, ttk.Combobox, ttk.Spinbox)):
            return
        canvas = packet_canvas if w.tabs.select() == str(w.packet_tab) else utility_canvas
        canvas.yview_scroll(-int(event.delta / 120), "units")

    root.bind("<MouseWheel>", wheel, add="+")

    def wrap_labels(parent):
        for child in parent.winfo_children():
            if isinstance(child, ttk.Label) and str(child.cget("wraplength")) not in {"", "0"}:
                if child.winfo_manager() == "grid":
                    child.grid_configure(sticky="ew")
                elif child.winfo_manager() == "pack":
                    child.pack_configure(fill="x")
                child.bind("<Configure>", lambda e: e.widget.configure(wraplength=max(100, e.width - 8)))
            wrap_labels(child)

    wrap_labels(shell)
