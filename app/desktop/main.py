"""CS2 Toolbox — native Windows utilities for extraction and round review."""
from __future__ import annotations

import csv
import ctypes
import json
import os
import queue
import re
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from jobs import ROOT, STATE, JobRunner, build_extraction, build_viewer_export, dependency_status, python_executable, read_json, save_json, analysis_component
from viewer_service import ViewerService
from credentials import TARGETS, delete_secret, get_secret, write_secret
from downloads import DEFAULT_REPLAYS, INDEX_NAME
from sources import classify_link
from faceit_leagues import season_label
from roster_hint import RosterHint
from report_tools import ReportTools
from skybox_tools import SkyboxTools

BG = '#0c141d'
PANEL = '#121e2a'
FIELD = '#0c1721'
FG = '#e0eaf2'
MUTED = '#8da2b6'
BLUE = '#75c7fb'
LINE = '#273b4c'


class Toolbox(SkyboxTools, ReportTools, tk.Tk):
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
        self.style.configure('TSpinbox', fieldbackground=FIELD, background=LINE, foreground=FG, arrowcolor=BLUE, padding=6)
        self.style.map('TSpinbox', fieldbackground=[('disabled', FIELD)], foreground=[('disabled', MUTED)])
        self.style.configure('Horizontal.TProgressbar', troughcolor=BG, background=BLUE, borderwidth=0, lightcolor=BLUE, darkcolor=BLUE)
        self.style.configure('Treeview', background=FIELD, foreground=FG, fieldbackground=FIELD, rowheight=30, borderwidth=0)
        self.style.configure('Treeview.Heading', background=PANEL, foreground=MUTED, relief='flat')
        self.style.map('Treeview', background=[('selected', '#254b68')])
        self.events = queue.Queue()
        self.runner = JobRunner(self.events)
        self.viewer = ViewerService(self.events)
        self.settings = read_json(STATE / 'settings.json', {})
        self.variables = {}
        self.secret_fields = {name: tk.StringVar() for name in TARGETS}
        self.actions = []
        self.page = ''
        self.closing = False
        self.job_started = None
        self.team_catalog = None
        self.team_scan_pending = None
        self.team_scan_timer = None
        self.team_scan_failed = None
        self._layout()
        self.show_page('download')
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
        sidebar = self.sidebar = tk.Frame(self, bg='#101c27', width=205)
        sidebar.pack(side='left', fill='y')
        sidebar.pack_propagate(False)
        self.text(sidebar, '↗', 30, BLUE).pack(anchor='w', padx=24, pady=(25, 2))
        self.text(sidebar, 'CS2 TOOLBOX', 15, bold=True).pack(anchor='w', padx=24)
        self.text(sidebar, 'Replay utilities', 10, MUTED).pack(anchor='w', padx=24, pady=(4, 28))
        self.text(sidebar, 'WORKSPACE', 8, '#607e96', True).pack(anchor='w', padx=24, pady=(0, 12))
        self.nav = {}
        for key, title in [('download', '01   Download demos'), ('extract', '02   Local analysis'), ('entities', '03   Replay data'), ('viewer', '04   Demo review'), ('reports', '05   HTML reports'), ('activity', '06   Activity'), ('tools', '07   Tools & setup')]:
            b = tk.Button(sidebar, text=title, anchor='w', command=lambda k=key: self.show_page(k),
                          bg='#101c27', fg=MUTED, activebackground='#1d3548', activeforeground=FG,
                          relief='flat', bd=0, padx=18, pady=13, cursor='hand2')
            b.pack(fill='x', padx=10, pady=2)
            self.nav[key] = b
        bottom = tk.Frame(sidebar, bg='#101c27')
        bottom.pack(side='bottom', fill='x', padx=22, pady=24)
        self.dependency_label = self.text(bottom, '●  Checking tools…', 9, MUTED, width=22, anchor='w')
        self.dependency_label.pack(anchor='w')
        self.text(bottom, 'LOCAL ANALYSIS\nDownloads connect to the source.', 8, '#637e92',
                  justify='left', anchor='w', wraplength=155).pack(anchor='w', pady=(13, 0))
        right = self.workspace = tk.Frame(self, bg=BG)
        right.pack(fill='both', expand=True, padx=30, pady=24)
        header = tk.Frame(right, bg=BG)
        header.pack(fill='x')
        self.button(header, 'Open project folder', lambda: self.open_folder(ROOT)).pack(side='right')
        self.text(header, 'REPLAY WORKSPACE', 9, MUTED, True).pack(anchor='w', pady=(5, 6))
        self.heading = self.text(header, '', 24, bold=True)
        self.heading.pack(anchor='w')
        self.subtitle = self.text(right, '', 10, MUTED, anchor='w', justify='left')
        self.subtitle.pack(fill='x', pady=(6, 20))
        content = tk.Frame(right, bg=BG)
        content.pack(fill='both', expand=True)
        self.content_canvas = tk.Canvas(content, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(content, orient='vertical', command=self.content_canvas.yview)
        scrollbar.pack(side='right', fill='y')
        self.content_canvas.pack(side='left', fill='both', expand=True)
        self.content_canvas.configure(yscrollcommand=scrollbar.set)
        self.body = tk.Frame(self.content_canvas, bg=BG)
        window = self.content_canvas.create_window((0, 0), window=self.body, anchor='nw')
        self.body.bind('<Configure>', lambda _: self.content_canvas.configure(scrollregion=self.content_canvas.bbox('all')))
        self.content_canvas.bind('<Configure>', lambda e: self.content_canvas.itemconfigure(window, width=e.width))
        self.bind_all('<MouseWheel>', self.scroll_content, add='+')
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
        self.workspace_chrome=[(widget,widget.pack_info()) for widget in
                               (header,self.subtitle,content,self.jobbar,self.progress,self.log)]
        self.review_host=tk.Frame(right,bg=BG)

    def var(self, key, default=''):
        if key not in self.variables:
            self.variables[key] = tk.StringVar(value=self.settings.get(key, default))
        return self.variables[key]

    def scroll_content(self, event):
        widget = self.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            if widget == self.body or widget == self.content_canvas:
                self.content_canvas.yview_scroll(-int(event.delta / 120), 'units')
                return 'break'
            widget = getattr(widget, 'master', None)

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
        review=getattr(self,'review_workspace',None)
        if review and review.expanded:review.toggle_expanded()
        self.save_settings()
        self.page = page
        for key, button in self.nav.items():
            button.configure(bg='#1d3548' if key == page else '#101c27', fg=BLUE if key == page else MUTED)
        for child in self.body.winfo_children():
            child.destroy()
        self.actions = []
        titles = {'download': ('From a link to your replay library.', 'Paste a FACEIT or HLTV link. Review the selection, download, and optionally analyze.'),
                  'extract': ('Turn demos into analysis.', 'Choose a replay or a folder. V8 runs the analysis and captures replay entity data.'),
                  'entities': ('Capture the finer details.', 'Add recorded item positions, burning fire patches, and raw smoke updates to your replay data.'),
                  'viewer': ('Review your demos.', 'Browse downloaded demos and watch CS2 rendering inside Toolbox.'),
                  'reports': ('Build a report to share.', 'Choose a team or player, select analyzed games, and save an interactive HTML heatmap report.'),
                  'activity': ('Your recent tasks.', 'Completed, failed, and stopped tasks are saved with their full progress logs.'),
                  'tools': ('Keep your tools ready.', 'Check the extraction tools, install missing Python packages, or rebuild the entity helper.')}
        self.heading.configure(text=titles[page][0])
        self.subtitle.configure(text=titles[page][1])
        if page!='viewer':
            self.review_host.pack_forget()
            self.workspace.pack_configure(padx=30,pady=24)
            for widget,options in self.workspace_chrome:widget.pack(**options)
        getattr(self, 'page_' + page)()
        self.content_canvas.yview_moveto(0)

    def auto_output(self, source_key, output_key):
        source = Path(self.var(source_key).get())
        try:
            collection = source.resolve().relative_to((ROOT / 'data/demos').resolve()).parts[0]
        except (ValueError, IndexError):
            collection = source.name if source.is_dir() else source.parent.name
        collection = analysis_component(collection.removesuffix('_demos'), 70)
        suffix = '_entities_v8' if source_key == 'entity_source' else ''
        self.var(output_key).set(str(ROOT / 'data/analysis' / f'Analysis_{collection}{suffix}'))

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
        self.path_field(card, 'Player collection or tournament folder', self.var('extract_output', str(ROOT / 'data/analysis/Analysis_CanadianIQ')),
                        lambda: 'folder')
        self.rate_row(card, 'extract_hz')
        replace = self.check(card, 'Replace this demo’s existing output if it already exists', 'extract_replace')
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill='x', pady=(16, 0))
        self.action(row, 'Run extraction', lambda: self.run_extraction(False))
        self.button(row, 'Open output folder', lambda: self.open_folder(self.var('extract_output').get())).pack(side='left')
        self.text(self.body, 'Analysis is organized into map / Analysis_demo_name folders. Use Analysis_PlayerName or Tournament as the output collection.\n'
                  'Folder mode includes nested folders. One task runs at a time; you can stop it below.', 9, MUTED, justify='left').pack(anchor='w', pady=(3, 0))

    def page_download(self):
        card = self.card('DOWNLOAD DEMOS', 'FACEIT: player, CS2 match, or team league season. HLTV: team, match, or tournament.')
        self.text(card, 'Paste a link', 9, MUTED).pack(anchor='w', pady=(3, 4))
        entry = ttk.Entry(card, textvariable=self.var('download_link'))
        entry.pack(fill='x')
        entry.bind('<KeyRelease>', lambda _: self.update_download_link())
        entry.bind('<<Paste>>', lambda _: self.after_idle(self.download_pasted))
        self.link_detail = self.text(card, '', 9, MUTED, anchor='w', wraplength=790, justify='left')
        self.link_detail.pack(fill='x', pady=(6, 0))
        self.season_row = tk.Frame(card, bg=PANEL)
        self.text(self.season_row, 'League season', 9, MUTED).pack(side='left', padx=(0, 12))
        self.season_combo = ttk.Combobox(self.season_row, textvariable=self.var('download_season'), state='readonly', width=46)
        self.season_combo.pack(side='left', fill='x', expand=True)
        self.season_combo.bind('<<ComboboxSelected>>', lambda _: self.update_download_link())
        self.button(self.season_row, 'Rescan', self.rescan_team).pack(side='left', padx=(8, 0))
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill='x', pady=(7, 0))
        self.count_row = row
        self.text(row, 'Most recent games', 9, MUTED).pack(side='left', padx=(0, 12))
        self.download_count = ttk.Spinbox(row, from_=1, to=1000, width=7, textvariable=self.var('download_count', '10'))
        self.download_count.pack(side='left')
        self.text(row, 'FACEIT players / HLTV teams', 9, MUTED).pack(side='left', padx=12)
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill='x', pady=(7, 0))
        self.text(row, 'Download method', 9, MUTED).pack(side='left', padx=(0, 12))
        ttk.Combobox(row, textvariable=self.var('download_method', 'Automatic'), state='readonly', width=25,
                     values=['Automatic', 'Browser companion', 'API / direct only']).pack(side='left')
        self.button(row, 'Companion script', self.open_companion).pack(side='left', padx=10)
        self.download_button = self.action(row, 'Extract demos', self.review_download)
        self.roster_badge = tk.Label(row, text='', bg=PANEL, fg='#f17474', font=('Segoe UI', 9),
                                    cursor='question_arrow', takefocus=1)
        self.roster_hint = RosterHint(self.roster_badge)
        self.path_field(card, 'Save demos to', self.var('download_root', str(DEFAULT_REPLAYS)), lambda: 'folder', initial=DEFAULT_REPLAYS)
        self.path_field(card, 'Browser downloads folder (used by companion)', self.var('browser_downloads', str(Path.home() / 'Downloads')), lambda: 'folder')
        self.check(card, 'Analyze selected demos after download (keeps existing analysis)', 'download_analyze')
        self.text(card, 'Analysis: ' + str(ROOT / 'data/analysis'), 9, MUTED, anchor='w', wraplength=790).pack(fill='x', pady=(5, 0))
        self.text(card, 'Folders: map → player / selected team / TeamA-vs-TeamB. The replay index links maps to their series.',
                  9, MUTED, wraplength=790, justify='left').pack(anchor='w', pady=(9, 0))
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill='x', pady=(13, 0))
        self.button(row, 'Use default location', lambda: self.var('download_root').set(str(DEFAULT_REPLAYS))).pack(side='left')
        self.button(row, 'Open replays', lambda: self.open_folder(self.var('download_root').get())).pack(side='left', padx=8)
        self.text(self.body, 'The next step reviews match and map counts before any demos are downloaded.\n'
                  'Automatic uses the browser companion when API access is unavailable. Install the companion before starting.\n'
                  'HLTV archive selection is manual; exact-match FACEIT filenames can be detected automatically.',
                  9, MUTED, justify='left', wraplength=830).pack(anchor='w')
        self.update_download_link()

    def update_download_link(self):
        if self.page != 'download':
            return
        try:
            link = classify_link(self.var('download_link').get())
            team_leagues = link['source'] == 'faceit' and link['kind'] == 'team'
            counted = link['kind'] == 'player' or (link['source'] == 'hltv' and link['kind'] == 'team')
            self.download_count.configure(state='normal' if counted else 'disabled')
            self.roster_badge.pack_forget()
            self.roster_hint.set(None)
            if team_leagues:
                self.season_row.pack(fill='x', pady=(7, 0), before=self.count_row)
                if self.team_catalog and self.team_catalog['team_id'] == link['id']:
                    options = {season_label(s): s for s in self.team_catalog['seasons']}
                    self.season_combo.configure(values=list(options), state='readonly')
                    if self.var('download_season').get() not in options:
                        self.var('download_season').set(next(iter(options)))
                    selected = options[self.var('download_season').get()]
                    comparison = selected['comparison']
                    self.roster_hint.set(comparison)
                    if not selected['latest']:
                        if comparison['different']:
                            self.roster_badge.configure(text='● different rosters', fg='#f17474')
                            self.roster_badge.pack(side='left', padx=(8, 0))
                        elif not comparison['complete'] or not comparison['roles_verified']:
                            self.roster_badge.configure(text='● roster not verified', fg='#e2bc78')
                            self.roster_badge.pack(side='left', padx=(8, 0))
                    else:
                        self.roster_badge.configure(text='● roster', fg=MUTED if comparison['roles_verified'] else '#e2bc78')
                        self.roster_badge.pack(side='left', padx=(8, 0))
                    self.link_detail.configure(text=f"{self.team_catalog['team_name']} · {season_label(selected)} · {selected['match_count']} finished matches", fg=BLUE)
                    self.download_button.configure(state='disabled' if self.runner.busy else 'normal')
                else:
                    self.season_combo.configure(values=[], state='disabled')
                    self.var('download_season').set('')
                    self.download_button.configure(state='disabled')
                    failed = self.team_scan_failed == link['id']
                    self.link_detail.configure(text='Season scan failed. See the console, then choose Rescan.' if failed else 'Scanning league seasons and rosters…', fg=MUTED)
                    if not failed and not self.closing and self.team_scan_pending != link['id'] and not self.runner.busy:
                        if self.team_scan_timer:
                            self.after_cancel(self.team_scan_timer)
                        self.team_scan_timer = self.after(650, lambda: self.scan_team(link['id'], link['url']))
                return
            self.season_row.pack_forget()
            detail = f"{link['source'].upper()} {link['kind']} link · " + ('choose the latest X completed games' if counted else 'all published demos for this ' + link['kind'])
            self.link_detail.configure(text=detail, fg=BLUE)
            self.download_button.configure(state='disabled' if self.runner.busy else 'normal')
        except ValueError as exc:
            self.season_row.pack_forget()
            self.roster_badge.pack_forget()
            self.link_detail.configure(text=str(exc), fg=MUTED)
            self.download_count.configure(state='disabled')
            self.download_button.configure(state='disabled')

    def rescan_team(self):
        if self.runner.busy:
            return
        self.team_catalog = None
        self.team_scan_failed = None
        self.update_download_link()

    def download_pasted(self):
        if self.page != 'download':
            return
        try:
            link = classify_link(self.var('download_link').get())
            if link['source'] == 'faceit' and link['kind'] == 'team':
                self.team_catalog = None
                self.team_scan_failed = None
        except ValueError:
            pass
        self.update_download_link()

    def scan_team(self, team_id, url):
        self.team_scan_timer = None
        if self.runner.busy or self.closing or self.page != 'download':
            return
        try:
            current = classify_link(self.var('download_link').get())
            if current['source'] != 'faceit' or current['kind'] != 'team' or current['id'] != team_id:
                return
            path = STATE / 'league-catalogs' / (team_id + '.json')
            self.team_scan_pending = team_id
            self.team_scan_failed = None
            self.launch_job('Scan team league seasons (metadata)',
                            [python_executable(), '-u', str(ROOT / 'app/desktop/downloads.py'), '--scan-team', url, '--catalog', str(path)],
                            str(path.parent), callback='team_scan')
        except (ValueError, RuntimeError) as exc:
            self.team_scan_pending = None
            self.team_scan_failed = team_id
            self.append_log(f'ERROR: Team season scan could not start: {exc}\n')

    def finish_team_scan(self, completed):
        team_id = self.team_scan_pending
        self.team_scan_pending = None
        self.team_scan_failed = None if completed else team_id
        if completed and team_id:
            catalog = read_json(STATE / 'league-catalogs' / (team_id + '.json'), {})
            if catalog.get('team_id') == team_id and catalog.get('seasons'):
                self.team_catalog = catalog
                if self.page == 'download':
                    self.season_combo.configure(state='readonly')
            else:
                self.team_scan_failed = team_id
        self.update_download_link()

    def review_download(self):
        try:
            value = self.var('download_link').get().strip()
            link = classify_link(value)
            is_team_season = link['source'] == 'faceit' and link['kind'] == 'team'
            count = int(self.var('download_count').get()) if link['kind'] in ('player', 'team') and not is_team_season else 1
            if not 1 <= count <= 1000:
                raise ValueError('Choose between 1 and 1000 recent games.')
            output = self.var('download_root').get().strip()
            if not output or not Path(output).is_absolute():
                raise ValueError('Choose an absolute replay folder path.')
            if Path(output).exists() and not Path(output).is_dir():
                raise ValueError('The replay location must be a folder.')
            plan = STATE / 'download-plan.json'
            # Capture the selection before resolving; later edits cannot change the approved job.
            method = {'Automatic': 'auto', 'Browser companion': 'browser', 'API / direct only': 'direct'}[self.var('download_method').get()]
            watch = self.var('browser_downloads').get().strip()
            if method != 'direct' and (not watch or not Path(watch).is_absolute() or not Path(watch).is_dir()):
                raise ValueError('Choose the existing folder where your browser saves downloads.')
            self.download_selection = {'root': output, 'analyze': self.var('download_analyze').get() == '1',
                                       'plan': plan, 'method': method, 'watch': watch}
            cmd = [python_executable(), '-u', str(ROOT / 'app/desktop/downloads.py'), '--resolve', value,
                   '--count', str(count), '--plan', str(plan), '--method', method]
            if is_team_season:
                if not self.team_catalog or self.team_catalog['team_id'] != link['id']:
                    raise ValueError('Wait for this team’s season scan first.')
                selected = next((s for s in self.team_catalog['seasons'] if season_label(s) == self.var('download_season').get()), None)
                if not selected:
                    raise ValueError('Choose a discovered season.')
                cmd += ['--catalog', str(STATE / 'league-catalogs' / (link['id'] + '.json')), '--season', selected['key']]
            self.launch_job('Review download link', cmd, output, callback='download_review')
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror('Check your link', str(exc), parent=self)

    def confirm_download(self):
        selection = self.download_selection
        plan = read_json(selection['plan'], {})
        matches = plan.get('matches', [])
        unavailable = plan.get('unavailable', [])
        if not matches:
            messagebox.showerror('No demos available', 'No downloadable matches were found. See the console for source access or availability errors.', parent=self)
            return
        maps = sum(len(match['maps']) for match in matches)
        text = (f"{len(matches)} matches · {maps} played maps · {len(unavailable)} unavailable matches\n\n"
                f"Demos: {selection['root']}\nLibrary index: {INDEX_NAME}\n\n"
                'Existing demos are kept; indexed downloads are skipped. Unindexed files are compared by checksum after downloading.\n'
                'Downloads run sequentially and may require several GB per match, plus temporary archive space. Download sizes are supplied by the source when available.\n\n')
        if plan.get('league_season'):
            season = plan['league_season']
            text = f"{plan['team_name']} · {season['league_name']} S{season['number']} · {season['division']}\n" + text
            if plan.get('roster_comparison', {}).get('different'):
                text += 'Different rosters from the most recent season. Review the roster warning before continuing.\n\n'
            if season['number'] != plan.get('roster_comparison', {}).get('latest'):
                text += 'Older-season match metadata does not guarantee that the demo files are still available. Transfers check availability.\n\n'
                if not plan.get('roster_comparison', {}).get('roles_verified'):
                    text += 'Historical main/sub roles are unverified for this comparison; promotions and demotions are not assumed.\n\n'
        if selection['method'] != 'direct':
            text += (f"Browser folder: {selection['watch']}\n"
                     'Browser fallback uses the normal demo button. You may need to select completed archives, especially for HLTV and multi-map FACEIT matches. Browser originals are kept.\n\n')
        if selection['analyze']:
            text += (f"Analyze only these selected demos in {ROOT / 'data/analysis'}.\n"
                     'Existing analysis is kept. Analysis can take minutes per demo, use substantial CPU/RAM, and produce several GB of data.\n\n')
        else:
            text += 'Analysis is off.\n\n'
        text += 'Start this job?'
        if not messagebox.askyesno('Review download job', text, parent=self):
            return
        cmd = [python_executable(), '-u', str(ROOT / 'app/desktop/downloads.py'), '--run', str(selection['plan']),
               '--replays', selection['root'], '--method', selection['method'], '--watch', selection['watch']]
        if selection['analyze']:
            cmd.append('--analyze')
        self.launch_job('Download demos' + (' + analyze' if selection['analyze'] else ''), cmd, selection['root'])

    def open_companion(self):
        self.open_folder(ROOT / 'app/desktop/userscripts')
        messagebox.showinfo('Install the Toolbox companion',
                            'In Violentmonkey, import CS2Toolbox.user.js from this folder. Disable the older FACEIT/HLTV Coach Tools collectors.\n\n'
                            'Then start a job from Toolbox. Keep the opened browser tab running and complete any login or site verification yourself.', parent=self)

    def select_browser_archives(self, identity):
        if not re.fullmatch(r'[a-f0-9]{32}', identity):
            self.append_log('ERROR: Invalid archive selection request.\n')
            return
        directory = STATE / 'browser-requests'
        request = read_json(directory / (identity + '.json'), {})
        if not request:
            return
        self.append_log(f"Archive selection for {request.get('match')}: {request.get('reason')}\n")
        files = ()
        if not self.closing and self.runner.busy and not self.runner.cancelled.is_set():
            messagebox.showinfo('Select completed browser downloads',
                                f"{request.get('label', request.get('match', 'Match'))}\n\n{request.get('reason', '')}\n\n"
                                'Select files from this match only. Map-header checks cannot independently prove the teams, date, or score. '
                                'Originals are kept. Cancel stops the job.', parent=self)
            files = filedialog.askopenfilenames(parent=self, title='Select this match’s completed demo archives',
                                               initialdir=request.get('watch') or Path.home() / 'Downloads',
                                               filetypes=[('Demo files and archives', '*.dem *.gz *.zst *.zip *.rar *.7z'), ('All files', '*.*')])
        try:
            save_json(directory / (identity + '.reply.json'), {'files': list(files)})
        except OSError as exc:
            self.append_log(f'ERROR: Could not return archive selection: {exc}\n')
            self.runner.stop()

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
        from demo_review import DemoReview
        for widget,_ in self.workspace_chrome:widget.pack_forget()
        self.workspace.pack_configure(padx=12,pady=8)
        self.review_host.pack(fill='both',expand=True)
        review=getattr(self,'review_workspace',None)
        if review is None or not review.winfo_exists():
            self.review_workspace=DemoReview(self.review_host,self.viewer,expand_changed=self.expand_review)
            self.review_workspace.pack(fill='both',expand=True)

    def expand_review(self,expanded):
        if expanded:
            self.sidebar.pack_forget();self.workspace.pack_configure(padx=0,pady=0)
        else:
            self.sidebar.pack(side='left',fill='y',before=self.workspace)
            self.workspace.pack_configure(padx=12 if self.page=='viewer' else 30,pady=8 if self.page=='viewer' else 24)

    def open_demo_review(self):
        self.show_page('viewer')

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
        self.skybox_card()
        watch = self.card('CS2 REPORT PLAYBACK · PREVIEW', 'Enable Watch in CS2 links in newly built HTML reports for this Windows user.')
        watch_row = tk.Frame(watch, bg=PANEL)
        watch_row.pack(fill='x', pady=(5, 0))
        self.action(watch_row, 'Enable / repair CS2 report links', lambda: self.launch_job(
            'Enable CS2 report links', [python_executable(), '-u', str(ROOT / 'app/desktop/cs2_jump.py'), '--install']))
        card = self.card('ANALYSIS', 'Check missing analysis and shared references, or repair folder names. Review each job before starting it.')
        self.text(card, 'FACEIT player folders use current nicknames verified by account ID or SteamID64.\nGame folders keep the player’s historical nickname. Unresolved games are left for review.',
                  10, MUTED, justify='left').pack(anchor='w', pady=(8, 12))
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill='x')
        self.action(row, 'Fix Directory', self.preview_directory_fix)
        self.action(row, 'Analyze all', self.preview_analysis_all)
        self.action(row, 'Undo last fix', self.undo_directory_fix)
        self.button(row, 'Open analysis folder', lambda: self.open_folder(ROOT / 'data/analysis')).pack(side='left')
        card = self.card('FACEIT CREDENTIALS', 'Saved in Windows Credential Manager for your Windows account. Blank fields keep saved values. Keys never go in project settings or task logs.')
        for name, label in [('FACEIT_API_KEY', 'Data API key'), ('FACEIT_DOWNLOAD_TOKEN', 'Downloads API access token (separate approval from FACEIT)')]:
            self.text(card, label, 9, MUTED).pack(anchor='w', pady=(5, 3))
            ttk.Entry(card, textvariable=self.secret_fields[name], show='●').pack(fill='x')
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill='x', pady=(10, 0))
        self.button(row, 'Save credentials', self.save_credentials).pack(side='left', padx=(0, 9))
        self.button(row, 'Remove saved credentials', self.remove_credentials).pack(side='left', padx=(0, 9))
        self.button(row, 'Downloads access', lambda: webbrowser.open('https://docs.faceit.com/getting-started/Guides/download-api/')).pack(side='left')
        self.credential_detail = self.text(card, '', 9, MUTED, justify='left')
        self.credential_detail.pack(anchor='w', pady=(8, 0))
        self.refresh_credentials()
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

    def preview_directory_fix(self):
        self.launch_job('Preview analysis directory repair',
                        [python_executable(), '-u', str(ROOT / 'app/desktop/directory_fix.py'), '--preview'],
                        str(STATE / 'directory-fixes'), callback='directory_preview')

    def show_directory_preview(self):
        pointer = read_json(STATE / 'directory-fixes/latest-preview.json', {})
        plan_path = Path(pointer.get('plan', ''))
        plan = read_json(plan_path, {}) if plan_path.is_file() else {}
        if not plan or plan.get('root') != str((ROOT / 'data/analysis').resolve()):
            messagebox.showerror('Preview unavailable', 'Run Fix Directory again to create a fresh preview.', parent=self)
            return
        window = tk.Toplevel(self, bg=PANEL)
        window.title('Review analysis directory repair')
        window.geometry('1080x650')
        window.transient(self)
        window.grab_set()
        self.text(window, 'Review the folder changes', 16, FG, True).pack(anchor='w', padx=22, pady=(20, 10))
        detail = (f"{len(plan['moves'])} folders · {plan['files']} files · {plan['bytes']/1024**3:.2f} GiB\n"
                  f"Analysis folder: {plan['root']}\n"
                  'Folders are moved on this drive; analysis files and duplicate versions are retained.\n'
                  'Saved references and the game catalog are updated, with metadata backups and an undo journal.\n'
                  'No demo downloads or analysis will run. Resource use: folder scanning and metadata updates.\n'
                  f"{len(plan['skipped'])} unresolved folders will stay in place. See the full report for reasons.")
        self.text(window, detail, 10, MUTED, justify='left').pack(anchor='w', padx=22, pady=(0, 12))
        frame = tk.Frame(window, bg=PANEL)
        frame.pack(fill='both', expand=True, padx=22)
        tree = ttk.Treeview(frame, columns=('old', 'new'), show='headings')
        for key, label in [('old', 'Current folder'), ('new', 'Proposed folder')]:
            tree.heading(key, text=label)
            tree.column(key, width=800, stretch=False)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky='nsew')
        scroll.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        for item in plan['moves']:
            tree.insert('', 'end', values=(str(Path(item['old']).relative_to(plan['root'])), str(Path(item['new']).relative_to(plan['root']))))
        blocked = bool(plan['errors'] or plan['active_locks'])
        if blocked:
            self.text(window, 'Repair is blocked by an active job or a metadata check. See the report, then create a fresh preview.', 10, '#f1a394', justify='left').pack(anchor='w', padx=22, pady=(10, 0))
        row = tk.Frame(window, bg=PANEL)
        row.pack(fill='x', padx=22, pady=18)
        def apply():
            window.destroy()
            self.viewer.stop()
            self.viewer = ViewerService(self.events)
            self.launch_job('Fix analysis directory',
                            [python_executable(), '-u', str(ROOT / 'app/desktop/directory_fix.py'), '--apply', str(plan_path)],
                            str(plan_path.parent), callback='directory_changed')
        button = self.button(row, 'Apply these changes', apply, primary=True)
        button.pack(side='left', padx=(0, 10))
        if blocked or not plan['moves']:
            button.configure(state='disabled')
        self.button(row, 'Open full report', lambda: webbrowser.open((plan_path.parent / 'preview.html').as_uri())).pack(side='left', padx=(0, 10))
        self.button(row, 'Cancel', window.destroy).pack(side='right')

    def undo_directory_fix(self):
        pointer = read_json(STATE / 'directory-fixes/latest-fix.json', {})
        journal_path = Path(pointer.get('journal', ''))
        journal = read_json(journal_path, {}) if journal_path.is_file() else {}
        if not journal or journal.get('status') == 'undone':
            messagebox.showinfo('No repair to undo', 'There is no directory repair waiting to be undone.', parent=self)
            return
        if not messagebox.askyesno('Undo last directory repair?',
                                  'Restore the folder names and references from the last repair?\n\n'
                                  f"Analysis folder: {journal.get('root')}\n"
                                  'Existing analysis is retained. Changed or occupied folders stop the undo.\n'
                                  'This moves folders and updates metadata; no analysis will run.', parent=self):
            return
        self.viewer.stop()
        self.viewer = ViewerService(self.events)
        self.launch_job('Undo analysis directory repair',
                        [python_executable(), '-u', str(ROOT / 'app/desktop/directory_fix.py'), '--undo', str(journal_path)],
                        str(journal_path.parent), callback='directory_changed')

    def reload_directory_settings(self):
        self.settings = read_json(STATE / 'settings.json', self.settings)
        for key, variable in self.variables.items():
            if key in self.settings:
                variable.set(self.settings[key])

    def refresh_credentials(self):
        try:
            states = [('Data API key' if name == 'FACEIT_API_KEY' else 'Downloads token') + ': ' + ('available' if get_secret(name) else 'not set') for name in TARGETS]
            self.credential_detail.configure(text=' · '.join(states))
        except OSError:
            self.credential_detail.configure(text='Windows Credential Manager is unavailable in this session.')

    def save_credentials(self):
        try:
            for name, field in self.secret_fields.items():
                if field.get().strip():
                    write_secret(name, field.get())
                    field.set('')
            self.refresh_credentials()
            self.append_log('FACEIT credential settings saved in Windows Credential Manager.\n')
        except (OSError, ValueError) as exc:
            messagebox.showerror('Could not save credentials', str(exc), parent=self)

    def remove_credentials(self):
        if not messagebox.askyesno('Remove FACEIT credentials?', 'Remove both CS2 Toolbox credentials from Windows Credential Manager?', parent=self):
            return
        try:
            for name in TARGETS:
                delete_secret(name)
                self.secret_fields[name].set('')
            self.refresh_credentials()
        except OSError as exc:
            messagebox.showerror('Could not remove credentials', str(exc), parent=self)

    def preview_analysis_all(self):
        import uuid
        self.analysis_all_plan = STATE/'analysis-all'/f'{uuid.uuid4().hex}.json'
        self.launch_job('Review all analyses', [python_executable(), '-u', str(ROOT/'app/desktop/analysis_all.py'),
                        '--preview', str(self.analysis_all_plan), '--replays', self.var('download_root', str(DEFAULT_REPLAYS)).get()],
                        str(ROOT/'data/analysis'), callback='analysis_all_review')

    def confirm_analysis_all(self):
        value = read_json(self.analysis_all_plan, {})
        counts = value.get('counts', {})
        detail = (f"{counts.get('recordings', 0)} recordings and {counts.get('references', 0)} reference folders checked.\n"
                  f"{counts.get('analysis_needed', 0)} need analysis; {counts.get('download_needed', 0)} need their source demo downloaded.\n"
                  f"{len(value.get('issues', []))} unresolved items will be reported.\n\n"
                  f"Demos: {value.get('replays')}\nAnalysis: {value.get('analysis')}\n\n"
                  'Completed analysis is reused. Unknown/modified outputs stay intact. Missing demos use the normal download workflow. '
                  'Analysis can take minutes per demo and substantial CPU/RAM/disk space. Start this reviewed job?')
        if messagebox.askyesno('Analyze all — review', detail, parent=self):
            self.launch_job('Analyze all downloaded demos and references', [python_executable(), '-u',
                            str(ROOT/'app/desktop/analysis_all.py'), '--execute', str(self.analysis_all_plan),
                            '--watch', self.var('browser_downloads', str(Path.home()/'Downloads')).get()], value['analysis'])

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
                    if payload.startswith('TOOLBOX_FILES '):
                        self.select_browser_archives(payload.removeprefix('TOOLBOX_FILES ').strip())
                    elif payload.startswith('TOOLBOX_PROGRESS '):
                        try:
                            update = json.loads(payload.removeprefix('TOOLBOX_PROGRESS '))
                            self.progress.stop()
                            self.progress.configure(mode='determinate', value=max(0, min(100, update['percent'])))
                            self.status.configure(text=f"{update['phase']} · {update['percent']:g}% · {update['detail'][:90]}", fg=BLUE)
                            self.append_log(f"{update['phase']}: {update['percent']:g}% — {update['detail']}\n")
                        except (ValueError, KeyError, TypeError):
                            self.append_log(payload)
                    else:
                        self.append_log(payload)
                elif kind == 'started':
                    self.status.configure(text=payload + ' · running', fg=BLUE)
                elif kind == 'finished':
                    record, callback = payload
                    if callback == 'directory_changed':
                        self.reload_directory_settings()
                    self.progress.stop()
                    self.progress.configure(mode='determinate', value=100 if record['status'] == 'Completed' else 0)
                    self.stop_button.configure(state='disabled')
                    self.status.configure(text=f"{record['title']} · {record['status'].lower()} · {record['seconds']:.1f}s",
                                          fg='#8cd5b3' if record['status'] == 'Completed' else '#e2bc78')
                    for b in self.actions:
                        b.configure(state='normal')
                    if callback == 'team_scan':
                        self.finish_team_scan(record['status'] == 'Completed')
                    else:
                        self.update_download_link()
                    self.append_log(f"\n{record['status']} in {record['seconds']:.1f} seconds. Full log saved.\n")
                    if self.page == 'activity':
                        self.show_page('activity')
                    if record['status'] == 'Completed' and not self.closing:
                        if callback == 'viewer':
                            self.viewer.open()
                        if callback == 'tools':
                            self.check_dependencies()
                        if callback == 'download_review':
                            self.confirm_download()
                        if callback == 'directory_preview':
                            self.show_directory_preview()
                        if callback == 'analysis_all_review':
                            self.confirm_analysis_all()
                        if callback == 'report_catalog':
                            self.report_catalog = read_json(STATE / 'report-catalog.json', None)
                            if self.page == 'reports':
                                self.populate_report_targets()
                        if callback == 'html_report':
                            self.var('report_last_file').set(str(self.pending_report))
                            self.save_settings()
                            self.open_last_report()
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
            review=getattr(self,'review_workspace',None)
            if review is not None and review.winfo_exists() and not review.close():
                self.after(70,self.poll);return
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
            if not getattr(self,'close_confirmed',False) and not messagebox.askyesno('A task is still running', 'Stop the current task and close CS2 Toolbox?', parent=self):
                return
            self.close_confirmed=True
            review = getattr(self, 'review_workspace', None)
            if review is not None and review.winfo_exists() and not review.close():
                if review.embedded_view.closing:self.after(80,self.close)
                return
            self.closing = True
            self.runner.stop()
            self.status.configure(text='Stopping before closing…')
        else:
            review = getattr(self, 'review_workspace', None)
            if review is not None and review.winfo_exists() and not review.close():
                if review.embedded_view.closing:self.after(80,self.close)
                return
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
