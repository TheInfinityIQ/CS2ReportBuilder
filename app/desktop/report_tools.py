"""Native report-builder controls, using the Toolbox's background job runner."""
import tkinter as tk
import webbrowser
from collections import defaultdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from jobs import ROOT, STATE, analysis_component, python_executable, read_json, save_json

PANEL, MUTED = '#121e2a', '#8da2b6'


class ReportTools:
    def page_reports(self):
        card=self.card('HTML HEATMAP REPORT', 'Choose a team or a player from your analyzed games. The report includes round playback and works offline.')
        row=tk.Frame(card,bg=PANEL);row.pack(fill='x',pady=(4,10))
        self.text(row,'Report for',9,MUTED).pack(side='left',padx=(0,10))
        mode=ttk.Combobox(row,textvariable=self.var('report_mode','Player'),values=['Player','Team'],state='readonly',width=10)
        mode.pack(side='left');mode.bind('<<ComboboxSelected>>',lambda _:self.populate_report_targets())
        self.button(row,'Refresh analyzed games',self.refresh_report_library).pack(side='right')
        self.text(card,'Search by name or Steam ID, then choose from the list',9,MUTED).pack(anchor='w')
        self.report_target_combo=ttk.Combobox(card,textvariable=self.var('report_target_label'),state='normal')
        self.report_target_combo.pack(fill='x',pady=(5,10))
        self.report_target_combo.bind('<KeyRelease>',self.search_report_targets)
        self.report_target_combo.bind('<<ComboboxSelected>>',lambda _:self.select_report_target())
        row=tk.Frame(card,bg=PANEL);row.pack(fill='x',pady=(0,10))
        self.text(row,'Map',9,MUTED).pack(side='left',padx=(0,10))
        self.report_map_combo=ttk.Combobox(row,textvariable=self.var('report_map','All maps'),state='readonly',width=18)
        self.report_map_combo.pack(side='left');self.report_map_combo.bind('<<ComboboxSelected>>',lambda _:self.populate_report_games())
        self.button(row,'Select all games',lambda:self.report_games.selection_set(self.report_games.get_children())).pack(side='right')
        self.report_games=ttk.Treeview(card,columns=('map','match','rounds','heat'),show='headings',height=7,selectmode='extended')
        for col,title,width in [('map','Map',85),('match','Game',480),('rounds','Rounds',65),('heat','Heatmap',100)]:
            self.report_games.heading(col,text=title);self.report_games.column(col,width=width,stretch=col=='match')
        self.report_games.pack(fill='x');self.report_games.bind('<<TreeviewSelect>>',lambda _:self.report_selection_status())
        self.report_hint=self.text(card,'Refresh the library to find available teams and players.',9,MUTED,wraplength=790,justify='left')
        self.report_hint.pack(anchor='w',pady=(9,3))
        self.text(card,'Use Ctrl or Shift to select games. Player reports track only the chosen player. Team reports let you filter players and opponents. Heatmaps average games on the selected map.',9,MUTED,wraplength=790,justify='left').pack(anchor='w',pady=(7,10))
        row=tk.Frame(card,bg=PANEL);row.pack(fill='x',pady=(5,0))
        self.action(row,'Build HTML report…',self.build_html_report)
        self.button(row,'Open last report',self.open_last_report).pack(side='left')
        self.text(card,'Starts at 40 seconds with first-kill cutoff on. The report includes all rounds of the selected games, embedded map images, and adjustable heatmap controls. Larger selections take longer and create larger files.',9,MUTED,wraplength=790,justify='left').pack(anchor='w',pady=(12,0))
        self.report_catalog=getattr(self,'report_catalog',None) or read_json(STATE/'report-catalog.json',None)
        if self.report_catalog and self.report_catalog.get('version') != 3:self.report_catalog=None
        self.populate_report_targets()
        if not self.report_catalog and not self.runner.busy:
            self.after_idle(self.refresh_report_library)

    def refresh_report_library(self):
        if self.runner.busy:
            messagebox.showinfo('Task running','Wait for the current task to finish, or stop it first.',parent=self);return
        self.launch_job('Find report teams and players',[python_executable(),'-u',str(ROOT/'app/desktop/reports.py'),
                        'catalog','--output',str(STATE/'report-catalog.json')],callback='report_catalog')

    def populate_report_targets(self):
        catalog=getattr(self,'report_catalog',None) or {}
        mode=self.var('report_mode','Player').get().lower()
        targets=[t for t in catalog.get('targets',[]) if t['mode']==mode]
        counts=defaultdict(int)
        for t in targets:counts[t['name']]+=1
        self.report_targets={}
        for t in targets:
            label=t['name']+(' · '+t['steamid'] if mode=='player' else ' · '+t['id'][-8:] if counts[t['name']]>1 else '')
            self.report_targets[label]=t
        selected=next((label for label,t in self.report_targets.items() if t['id']==self.var('report_target_id').get()),'')
        self.var('report_target_label').set(selected)
        self.report_target_combo.configure(values=list(self.report_targets))
        self.select_report_target()

    def search_report_targets(self,event=None):
        if event and event.keysym in ('Up','Down','Return','Escape','Tab'):return
        term=self.var('report_target_label').get().casefold()
        self.report_target_combo.configure(values=[label for label,t in self.report_targets.items()
            if term in (label+' '+' '.join(t['aliases'])).casefold()])
        self.select_report_target()

    def select_report_target(self):
        target=self.report_targets.get(self.var('report_target_label').get())
        self.var('report_target_id').set(target['id'] if target else '')
        catalog=getattr(self,'report_catalog',None) or {}
        maps=sorted({e['map'] for e in catalog.get('entries',[]) if target and e['source'] in target['games']})
        self.report_maps={'All maps':None,**{m.removeprefix('de_'):m for m in maps}}
        self.report_map_combo.configure(values=list(self.report_maps))
        if self.var('report_map').get() not in self.report_maps:self.var('report_map').set('All maps')
        self.populate_report_games()

    def populate_report_games(self):
        self.report_games.delete(*self.report_games.get_children())
        self.report_rows={}
        target=self.report_targets.get(self.var('report_target_label').get())
        if target:
            catalog=self.report_catalog or {};groups={}
            selected_map=self.report_maps.get(self.var('report_map').get())
            for e in catalog.get('entries',[]):
                if e['source'] not in target['games'] or (selected_map and e['map']!=selected_map):continue
                groups.setdefault(e['game'],[]).append(e)
            for i,entries in enumerate(groups.values()):
                key=str(i);self.report_rows[key]=entries
                e=entries[0]
                state='Ready' if all(e.get('heat_ready') for e in entries) else 'Partial' if any(e.get('heat_ready') for e in entries) else 'Replay only'
                self.report_games.insert('', 'end',iid=key,values=(e['map'].removeprefix('de_'),e['name'],sum(e['rounds'] for e in entries),state))
            self.report_games.selection_set(self.report_games.get_children())
        self.report_selection_status()

    def report_selection_status(self):
        selected=self.report_games.selection()
        entries=[e for key in selected for e in self.report_rows.get(key,[])]
        catalog=getattr(self,'report_catalog',None) or {}
        text=f'{len(selected)} games selected · {len(entries)} recordings · {len({e["map"] for e in entries})} maps'
        target=self.report_targets.get(self.var('report_target_label').get())
        if not target:text='Choose a team or player from the list.'
        elif target['mode']=='team' and any((e.get('team') or {}).get('recorded_names') for e in entries):
            text+=' · Grouped by recorded team names; historical team renames stay separate.'
        if catalog.get('skipped'):text+=f' · {len(catalog["skipped"])} unavailable analyses omitted.'
        missing=sum(not e.get('heat_ready') for e in entries)
        if missing:text+=f' · {missing} recordings lack validated death data; excluded from heat averages.'
        self.report_hint.configure(text=text)

    def build_html_report(self):
        if self.runner.busy:return
        target=self.report_targets.get(self.var('report_target_label').get())
        entries=[e for key in self.report_games.selection() for e in self.report_rows.get(key,[])]
        if not target or not entries:
            messagebox.showinfo('Choose report games','Choose a team or player from the list and select at least one game.',parent=self);return
        last=Path(self.var('report_last_file',str(ROOT/'data/reports/report.html')).get())
        directory=last.parent if last.parent.is_dir() else ROOT/'data'
        filename=filedialog.asksaveasfilename(parent=self,title='Save HTML heatmap report',initialdir=directory,
            initialfile='Heatmap_'+analysis_component(target['name'],70)+'.html',defaultextension='.html',
            filetypes=[('HTML heatmap report','*.html')])
        if not filename:return
        path=Path(filename)
        if path.resolve().is_relative_to((ROOT/'data/analysis').resolve()):
            messagebox.showerror('Choose another location','Save reports outside the analysis library.',parent=self);return
        request=dict(target=target['id'],sources=[e['source'] for e in entries],output=str(path))
        if path.exists():request['replace_stamp']=[path.stat().st_size,path.stat().st_mtime_ns]
        save_json(STATE/'report-request.json',request)
        self.pending_report=path
        self.launch_job('Build HTML heatmap report',[python_executable(),'-u',str(ROOT/'app/desktop/reports.py'),
                        'build','--request',str(STATE/'report-request.json')],str(path.parent),callback='html_report')

    def open_last_report(self):
        path=Path(self.var('report_last_file').get())
        if path.is_file():webbrowser.open(path.resolve().as_uri())
        else:messagebox.showinfo('No saved report','Build an HTML report first.',parent=self)
