"""CS2 Toolbox — native Windows utilities for extraction and round review."""
from __future__ import annotations

import csv
import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from jobs import ROOT, STATE, JobRunner, build_extraction, build_viewer_export, dependency_status, python_executable, read_json, save_json
from viewer_service import ViewerService

BG = '#0c141d'
PANEL = '#121e2a'
FIELD = '#0c1721'
FG = '#e0eaf2'
MUTED = '#8da2b6'
BLUE = '#75c7fb'
LINE = '#273b4c'


class Toolbox(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('CS2 Toolbox')
        self.geometry('1180x850')
        self.minsize(1040, 790)
        self.configure(bg=BG)
        try:
            self.iconbitmap(str(Path(__file__).with_name('toolbox.ico')))
        except tk.TclError:
            pass
        self.option_add('*Font', '{Segoe UI} 10')
        self.option_add('*TCombobox*Listbox.background', PANEL)
        self.option_add('*TCombobox*Listbox.foreground', FG)
        self.option_add('*TCombobox*Listbox.selectBackground', '#245174')
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.style.configure('TCombobox', fieldbackground=FIELD, background=LINE, foreground=FG, arrowcolor=BLUE, bordercolor=LINE, padding=7)
        self.style.map('TCombobox', fieldbackground=[('readonly', FIELD)], foreground=[('readonly', FG)], selectbackground=[('readonly', FIELD)])
        self.style.configure('TEntry', fieldbackground=FIELD, foreground=FG, insertcolor=FG, bordercolor=LINE, padding=8)
        self.style.configure('Horizontal.TProgressbar', troughcolor=BG, background=BLUE, borderwidth=0, lightcolor=BLUE, darkcolor=BLUE)
        self.style.configure('Treeview', background=FIELD, foreground=FG, fieldbackground=FIELD, rowheight=30, borderwidth=0)
        self.style.configure('Treeview.Heading', background=PANEL, foreground=MUTED, relief='flat')
        self.style.map('Treeview', background=[('selected', '#254b68')])
        self.events = queue.Queue()
        self.runner = JobRunner(self.events)
        self.viewer = ViewerService(self.events)
        self.settings = read_json(STATE / 'settings.json', {})
        self.variables = {}
        self.actions = []
        self.page = ''
        self.closing = False
        self.job_started = None
        self._layout()
        self.show_page('extract')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(70, self.poll)
        self.check_dependencies()
        self.after(150, self.dark_title)

    def dark_title(self):
        if os.name == 'nt':
            try:
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)
            except (OSError, AttributeError):
                pass

    def text(self, parent, text='', size=10, color=FG, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color, font=('Segoe UI', size, 'bold' if bold else 'normal'), **kwargs)

    def button(self, parent, text, command, primary=False, **kwargs):
        button = tk.Button(parent, text=text, command=command, bg='#245a80' if primary else '#1a2c3d', fg=FG,
                           activebackground='#346d96', activeforeground='white', relief='flat', bd=0,
                           cursor='hand2', padx=15, pady=9, disabledforeground='#617586', **kwargs)
        return button

    def _layout(self):
        sidebar = tk.Frame(self, bg='#101c27', width=205)
        sidebar.pack(side='left', fill='y')
        sidebar.pack_propagate(False)
        self.text(sidebar, '↗', 30, BLUE).pack(anchor='w', padx=24, pady=(25, 2))
        self.text(sidebar, 'CS2 TOOLBOX', 15, bold=True).pack(anchor='w', padx=24)
        self.text(sidebar, 'Replay utilities', 10, MUTED).pack(anchor='w', padx=24, pady=(4, 28))
        self.text(sidebar, 'WORKSPACE', 8, '#607e96', True).pack(anchor='w', padx=24, pady=(0, 12))
        self.nav = {}
        for key, title in [('extract', '01   Extract demos'), ('entities', '02   Replay data'), ('viewer', '03   2D viewer'), ('activity', '04   Activity'), ('tools', '05   Tools & setup')]:
            b = tk.Button(sidebar, text=title, anchor='w', command=lambda k=key: self.show_page(k),
                          bg='#101c27', fg=MUTED, activebackground='#1d3548', activeforeground=FG,
                          relief='flat', bd=0, padx=18, pady=13, cursor='hand2')
            b.pack(fill='x', padx=10, pady=2)
            self.nav[key] = b
        bottom = tk.Frame(sidebar, bg='#101c27')
        bottom.pack(side='bottom', fill='x', padx=22, pady=24)
        self.dependency_label = self.text(bottom, '●  Checking tools…', 9, MUTED, width=22, anchor='w')
        self.dependency_label.pack(anchor='w')
        self.text(bottom, 'LOCAL WORKSPACE\nYour files stay on this computer.', 8, '#637e92', justify='left').pack(anchor='w', pady=(13, 0))
        right = tk.Frame(self, bg=BG)
        right.pack(fill='both', expand=True, padx=30, pady=24)
        header = tk.Frame(right, bg=BG)
        header.pack(fill='x')
        self.button(header, 'Open project folder', lambda: self.open_folder(ROOT)).pack(side='right')
        self.text(header, 'REPLAY WORKSPACE', 9, MUTED, True).pack(anchor='w', pady=(5, 6))
        self.heading = self.text(header, '', 24, bold=True)
        self.heading.pack(anchor='w')
        self.subtitle = self.text(right, '', 10, MUTED, anchor='w', justify='left')
        self.subtitle.pack(fill='x', pady=(6, 20))
        self.body = tk.Frame(right, bg=BG)
        self.body.pack(fill='both', expand=True)
        self.jobbar = tk.Frame(right, bg=BG)
        self.jobbar.pack(fill='x', pady=(15, 7))
        self.status = self.text(self.jobbar, 'Ready when you are.', 10, MUTED)
        self.status.pack(side='left')
        self.stop_button = self.button(self.jobbar, 'Stop task', self.stop_job)
        self.stop_button.pack(side='right')
        self.stop_button.configure(state='disabled')
        self.progress = ttk.Progressbar(right, mode='determinate', value=0)
        self.progress.pack(fill='x', pady=(0, 9))
        self.log = ScrolledText(right, height=7, bg='#08111a', fg='#afc4d4', insertbackground=FG, relief='flat', bd=0,
                                padx=12, pady=10, font=('Consolas', 9), wrap='word', state='disabled')
        self.log.pack(fill='x')
        self.log.tag_configure('error', foreground='#f1a394')
        self.append_log('Choose a utility on the left. Progress and saved task logs will appear here.\n')

    def var(self, key, default=''):
        if key not in self.variables:
            self.variables[key] = tk.StringVar(value=self.settings.get(key, default))
        return self.variables[key]

    def save_settings(self):
        self.settings.update({k: v.get() for k, v in self.variables.items()})
        try:
            save_json(STATE / 'settings.json', self.settings)
        except OSError as exc:
            self.append_log(f'Could not save preferences: {exc}\n')

    def card(self, title, subtitle=''):
        frame = tk.Frame(self.body, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        frame.pack(fill='x', pady=(0, 12))
        inner = tk.Frame(frame, bg=PANEL)
        inner.pack(fill='both', expand=True, padx=20, pady=17)
        self.text(inner, title, 12, bold=True).pack(anchor='w', pady=(0, 4))
        if subtitle:
            self.text(inner, subtitle, 9, MUTED, justify='left', wraplength=790).pack(anchor='w', pady=(0, 9))
        return inner

    def path_field(self, parent, label, variable, picker, initial=None, after=None):
        self.text(parent, label, 9, MUTED).pack(anchor='w', pady=(7, 4))
        row = tk.Frame(parent, bg=parent.cget('bg'))
        row.pack(fill='x', pady=(0, 3))
        entry = ttk.Entry(row, textvariable=variable)
        entry.pack(side='left', fill='x', expand=True)

        def choose():
            current = Path(variable.get()) if variable.get() else Path(initial or ROOT)
            directory = current if current.is_dir() else current.parent
            if not directory.is_dir():
                directory = ROOT
            if picker() == 'file':
                value = filedialog.askopenfilename(parent=self, title=label, initialdir=directory,
                                                   filetypes=[('Counter-Strike replay', '*.dem'), ('All files', '*.*')])
            else:
                value = filedialog.askdirectory(parent=self, title=label, initialdir=directory)
            if value:
                variable.set(value)
                if after:
                    after()
                self.save_settings()
        self.button(row, 'Browse…', choose).pack(side='left', padx=(9, 0))
        return entry

    def check(self, parent, label, key):
        var = self.var(key, '0')
        tk.Checkbutton(parent, text=label, variable=var, onvalue='1', offvalue='0', bg=PANEL,
                       fg=MUTED, activebackground=PANEL, activeforeground=FG, selectcolor=FIELD,
                       bd=0, highlightthickness=0, anchor='w').pack(anchor='w', pady=(8, 0))
        return var

    def action(self, parent, title, command):
        b = self.button(parent, title, command, primary=True)
        b.pack(side='left', padx=(0, 10))
        self.actions.append(b)
        if self.runner.busy:
            b.configure(state='disabled')
        return b

    def show_page(self, page):
        self.save_settings()
        self.page = page
        for key, button in self.nav.items():
            button.configure(bg='#1d3548' if key == page else '#101c27', fg=BLUE if key == page else MUTED)
        for child in self.body.winfo_children():
            child.destroy()
        self.actions = []
        titles = {'extract': ('Turn demos into analysis.', 'Choose a replay or a folder. V8 runs the analysis and captures replay entity data.'),
                  'entities': ('Capture the finer details.', 'Add recorded item positions, burning fire patches, and raw smoke updates to your replay data.'),
                  'viewer': ('Review a round.', 'Prepare a real round, then open the interactive 2D viewer in your browser.'),
                  'activity': ('Your recent tasks.', 'Completed, failed, and stopped tasks are saved with their full progress logs.'),
                  'tools': ('Keep your tools ready.', 'Check the extraction tools, install missing Python packages, or rebuild the entity helper.')}
        self.heading.configure(text=titles[page][0])
        self.subtitle.configure(text=titles[page][1])
        getattr(self, 'page_' + page)()

    def auto_output(self, source_key, output_key):
        source = Path(self.var(source_key).get())
        try:
            collection = source.resolve().relative_to((ROOT / 'data/demos').resolve()).parts[0]
        except (ValueError, IndexError):
            collection = source.name if source.is_dir() else source.parent.name
        suffix = '_entities_v8' if source_key == 'entity_source' else '_v8'
        self.var(output_key).set(str(ROOT / 'data/analysis' / f'analyzed_{collection}{suffix}'))

    def rate_row(self, parent, key, round_key=None):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill='x', pady=(10, 3))
        self.text(row, 'Position detail', 9, MUTED).pack(side='left', padx=(0, 9))
        ttk.Combobox(row, textvariable=self.var(key, '16'), state='readonly', width=7,
                     values=['1', '2', '4', '8', '16', '32', '64']).pack(side='left')
        self.text(row, 'samples / second', 9, MUTED).pack(side='left', padx=8)
        if round_key:
            self.text(row, 'Round', 9, MUTED).pack(side='left', padx=(24, 8))
            tk.Entry(row, textvariable=self.var(round_key), width=7, bg=FIELD, fg=FG,
                     insertbackground=FG, relief='flat').pack(side='left', ipady=7)
            self.text(row, 'empty = whole match', 9, MUTED).pack(side='left', padx=8)

    def page_extract(self):
        card = self.card('EXTRACTOR V8', 'New output is saved in its own folder. Your previous analysis is kept unless you enable replacement.')
        kind = self.var('extract_kind', 'Folder of demos')
        select = tk.Frame(card, bg=PANEL)
        select.pack(fill='x', pady=(6, 3))
        self.text(select, 'Input type', 9, MUTED).pack(side='left', padx=(0, 12))
        combo = ttk.Combobox(select, values=['Folder of demos', 'Single demo'], textvariable=kind, state='readonly', width=22)
        combo.pack(side='left')
        default = ROOT / 'data/demos/CanadianIQ_demos'
        self.path_field(card, 'Demo file or folder', self.var('extract_source', str(default if default.exists() else ROOT / 'data/demos')),
                        lambda: 'folder' if kind.get() == 'Folder of demos' else 'file', after=lambda: self.auto_output('extract_source', 'extract_output'))
        self.path_field(card, 'Save analysis to', self.var('extract_output', str(ROOT / 'data/analysis/analyzed_CanadianIQ_demos_v8')),
                        lambda: 'folder')
        self.rate_row(card, 'extract_hz')
        replace = self.check(card, 'Replace this demo’s existing output if it already exists', 'extract_replace')
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill='x', pady=(16, 0))
        self.action(row, 'Run extraction', lambda: self.run_extraction(False))
        self.button(row, 'Open output folder', lambda: self.open_folder(self.var('extract_output').get())).pack(side='left')
        self.text(self.body, 'Folder mode includes nested folders. One task runs at a time; you can stop it below.', 9, MUTED).pack(anchor='w', pady=(3, 0))

    def page_entities(self):
        card = self.card('REPLAY ENTITY DATA', 'Records ground items and fire patches, and attempts experimental smoke decoding. Exact smoke boundaries and HE holes are not verified.')
        self.path_field(card, 'Original demo file', self.var('entity_source'), lambda: 'file', initial=ROOT / 'data/demos',
                        after=lambda: self.auto_output('entity_source', 'entity_output'))
        self.path_field(card, 'Existing analysis folder (optional, required for one round)', self.var('entity_analysis'),
                        lambda: 'folder', initial=ROOT / 'data/analysis')
        self.path_field(card, 'Save replay data to', self.var('entity_output', str(ROOT / 'data/analysis/v8_entities')), lambda: 'folder')
        self.rate_row(card, 'entity_hz', 'entity_round')
        self.check(card, 'Replace existing entity data for this demo', 'entity_replace')
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill='x', pady=(15, 0))
        self.action(row, 'Capture replay data', lambda: self.run_extraction(True))
        self.button(row, 'Open output folder', lambda: self.open_folder(self.var('entity_output').get())).pack(side='left')

    def page_viewer(self):
        default = ROOT / 'data/analysis/analyzed_CanadianIQ_demos/CanadianIQ_09-17-2026_0dot78_Ancient_LOSS'
        card = self.card('2D ROUND VIEWER', 'Playback, scrubbing, round navigation, and player tracking. The viewer opens in your browser; these utilities stay in the desktop app.')
        self.path_field(card, 'Analysis folder', self.var('viewer_analysis', str(default) if default.exists() else ''),
                        lambda: 'folder', initial=ROOT / 'data/analysis', after=self.refresh_rounds)
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill='x', pady=(14, 15))
        self.text(row, 'Round to prepare', 9, MUTED).pack(side='left', padx=(0, 12))
        self.round_combo = ttk.Combobox(row, textvariable=self.var('viewer_round', '24'), values=[], state='readonly', width=8)
        self.round_combo.pack(side='left')
        self.refresh_rounds()
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill='x', pady=(3, 0))
        self.action(row, 'Prepare & open round', self.prepare_viewer)
        self.button(row, 'Open current viewer', self.viewer.open).pack(side='left')
        self.text(card, 'Preparing a round updates the viewer’s saved example. Original analysis files are unchanged.', 9, MUTED,
                  wraplength=780, justify='left').pack(anchor='w', pady=(15, 0))
        self.text(self.body, 'The current viewer uses its original effects. Reading the new v8 entity tracks is a separate integration.', 9,
                  MUTED, wraplength=800, justify='left').pack(anchor='w', pady=(4, 0))

    def refresh_rounds(self):
        try:
            folder = Path(self.var('viewer_analysis').get())
            with (folder / 'rounds.csv').open(encoding='utf-8-sig', newline='') as f:
                rounds = [r['round'] for r in csv.DictReader(f)]
            self.round_combo.configure(values=rounds)
            if self.var('viewer_round').get() not in rounds:
                self.var('viewer_round').set(rounds[0] if rounds else '')
        except (OSError, KeyError, ValueError):
            self.round_combo.configure(values=[])
            self.var('viewer_round').set('')

    def page_activity(self):
        card = self.card('TASK HISTORY', 'Select a task to open its saved log or output folder.')
        self.history = read_json(STATE / 'history.json', [])
        tree = ttk.Treeview(card, columns=('task', 'date', 'result', 'duration'), show='headings', height=7, selectmode='browse')
        for key, title, width in [('task', 'Task', 240), ('date', 'Started', 180), ('result', 'Result', 100), ('duration', 'Time', 70)]:
            tree.heading(key, text=title)
            tree.column(key, width=width, stretch=key == 'task')
        for index, record in enumerate(self.history):
            tree.insert('', 'end', iid=str(index), values=(record['title'], record['started'][:19].replace('T', ' '),
                                                         record['status'], f"{record['seconds']:.1f}s"))
        tree.pack(fill='x', pady=(9, 14))
        def selected(key):
            if not tree.selection():
                messagebox.showinfo('Select a task', 'Select a task from the list first.', parent=self)
                return
            value = self.history[int(tree.selection()[0])].get(key)
            if value:
                self.open_folder(value, file=key == 'log')
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill='x')
        self.button(row, 'Open selected log', lambda: selected('log')).pack(side='left', padx=(0, 9))
        self.button(row, 'Open selected output', lambda: selected('output')).pack(side='left', padx=(0, 9))
        self.button(row, 'All logs', lambda: self.open_folder(STATE / 'logs')).pack(side='left')

    def page_tools(self):
        card = self.card('EXTRACTION TOOLS', 'Setup installs Python packages into this project and builds the v8 entity helper. Internet access is needed for downloads.')
        self.tools_detail = self.text(card, 'Checking installed tools…', 10, MUTED, justify='left')
        self.tools_detail.pack(anchor='w', pady=(12, 18))
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill='x')
        self.action(row, 'Install / repair tools', self.setup_tools)
        self.button(row, 'Check tools', self.check_dependencies).pack(side='left', padx=(0, 9))
        self.button(row, '.NET 9 download', lambda: webbrowser.open('https://dotnet.microsoft.com/en-us/download/dotnet/9.0')).pack(side='left')
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill='x', pady=(13, 0))
        self.button(row, 'Extraction guide', lambda: self.open_folder(ROOT / 'app/extractor/README_v8.md', file=True)).pack(side='left', padx=(0, 9))
        self.button(row, 'Viewer guide', lambda: self.open_folder(ROOT / 'app/modules/viewer2d/README.md', file=True)).pack(side='left')
        self.text(self.body, 'This desktop app uses the Python runtime installed on this computer.\nUtility tasks run in the background without terminal windows.',
                  9, MUTED, justify='left').pack(anchor='w', pady=4)
        self.check_dependencies()

    def run_extraction(self, entities):
        prefix = 'entity' if entities else 'extract'
        try:
            cmd = build_extraction(source=self.var(prefix + '_source').get(), output=self.var(prefix + '_output').get(),
                                   folder=not entities and self.var('extract_kind').get() == 'Folder of demos', entities=entities,
                                   analysis=self.var('entity_analysis').get() if entities else '',
                                   round_number=self.var('entity_round').get() if entities else '',
                                   hz=self.var(prefix + '_hz').get(), replace=self.var(prefix + '_replace').get() == '1')
            self.launch_job('Capture replay data' if entities else 'V8 demo extraction', cmd, self.var(prefix + '_output').get())
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror('Check your selection', str(exc), parent=self)

    def prepare_viewer(self):
        try:
            cmd = build_viewer_export(self.var('viewer_analysis').get(), self.var('viewer_round').get())
            self.launch_job('Prepare viewer round', cmd, str(ROOT / 'app/modules/viewer2d'), callback='viewer')
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror('Check your selection', str(exc), parent=self)

    def setup_tools(self):
        self.launch_job('Set up extraction tools', [python_executable(), '-u', str(ROOT / 'app/desktop/setup_tools.py')], callback='tools')

    def launch_job(self, title, command, output='', callback=None):
        self.save_settings()
        self.runner.start(title, command, output, callback)
        self.append_log('\n' + '─' * 62 + '\n' + title + '\n')
        self.status.configure(text=title + ' · starting…', fg=BLUE)
        self.progress.configure(mode='indeterminate')
        self.progress.start(16)
        self.stop_button.configure(state='normal')
        for b in self.actions:
            b.configure(state='disabled')

    def stop_job(self):
        self.status.configure(text='Stopping the current task…', fg='#e2bc78')
        self.stop_button.configure(state='disabled')
        self.runner.stop()

    def append_log(self, line):
        self.log.configure(state='normal')
        self.log.insert('end', line, 'error' if 'ERROR' in line or 'Traceback' in line else '')
        if int(self.log.index('end-1c').split('.')[0]) > 2000:
            self.log.delete('1.0', '300.0')
        self.log.see('end')
        self.log.configure(state='disabled')

    def check_dependencies(self):
        def check():
            try:
                self.events.put(('dependencies', dependency_status()))
            except Exception as exc:
                self.events.put(('dependencies', {'ready': False, 'modules': {}, 'sdk': '', 'error': str(exc)}))
        threading.Thread(target=check, daemon=True).start()

    def poll(self):
        try:
            for _ in range(150):
                kind, payload = self.events.get_nowait()
                if kind == 'line':
                    self.append_log(payload)
                elif kind == 'started':
                    self.status.configure(text=payload + ' · running', fg=BLUE)
                elif kind == 'finished':
                    record, callback = payload
                    self.progress.stop()
                    self.progress.configure(mode='determinate', value=100 if record['status'] == 'Completed' else 0)
                    self.stop_button.configure(state='disabled')
                    self.status.configure(text=f"{record['title']} · {record['status'].lower()} · {record['seconds']:.1f}s",
                                          fg='#8cd5b3' if record['status'] == 'Completed' else '#e2bc78')
                    for b in self.actions:
                        b.configure(state='normal')
                    self.append_log(f"\n{record['status']} in {record['seconds']:.1f} seconds. Full log saved.\n")
                    if self.page == 'activity':
                        self.show_page('activity')
                    if record['status'] == 'Completed' and not self.closing:
                        if callback == 'viewer':
                            self.viewer.open()
                        if callback == 'tools':
                            self.check_dependencies()
                elif kind == 'dependencies':
                    self.dependency_label.configure(text='●  Tools ready' if payload['ready'] else '●  Setup needed',
                                                    fg='#8cd5b3' if payload['ready'] else '#e2bc78')
                    if self.page == 'tools':
                        modules = payload['modules']
                        self.tools_detail.configure(text='Python extraction packages: ' + ('Ready' if len(modules) == 5 and all(modules.values()) else 'Missing packages') +
                                                    '\n.NET 9 SDK: ' + (payload['sdk'] or 'Not found') +
                                                    '\nEntity helper: Built automatically when needed')
                elif kind == 'viewer_ready':
                    if not self.closing:
                        self.append_log('Viewer ready: ' + payload + '\n')
                        webbrowser.open(payload)
                elif kind == 'error':
                    messagebox.showerror('Unable to open viewer', payload, parent=self)
        except queue.Empty:
            pass
        if self.closing and not self.runner.busy:
            self.viewer.stop()
            self.destroy()
            return
        self.after(70, self.poll)

    def open_folder(self, value, file=False):
        path = Path(value)
        if not path.exists():
            messagebox.showinfo('Folder not created yet', 'This location will be created when the task runs.', parent=self)
            return
        if os.name == 'nt':
            os.startfile(str(path.resolve()))
        else:
            webbrowser.open(path.resolve().as_uri())

    def close(self):
        if self.runner.busy:
            if not messagebox.askyesno('A task is still running', 'Stop the current task and close CS2 Toolbox?', parent=self):
                return
            self.closing = True
            self.runner.stop()
            self.status.configure(text='Stopping before closing…')
        else:
            self.viewer.stop()
            self.save_settings()
            self.destroy()


if __name__ == '__main__':
    if os.name == 'nt':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (OSError, AttributeError):
            pass
    app = Toolbox()
    app.mainloop()
