"""Task-oriented presentation for the existing demo library and review actions."""
import tkinter as tk
from tkinter import ttk
from review_presentation import demo_label,map_label

BG='#0c141d';PANEL='#121e2a';FG='#e0eaf2';MUTED='#9cb0c2';BLUE='#75c7fb'


class ReviewLayout:
    def layout(self):
        head=self.header=tk.Frame(self,bg=BG);head.pack(fill='x',padx=12,pady=(8,6))
        self.intro=tk.Frame(head,bg=BG);self.intro.pack(fill='x')
        self.label(self.intro,'Demo review',size=17).pack(side='left')
        more=tk.Menubutton(self.intro,text='More options',bg='#21394b',fg=FG,activebackground='#31556d',
            activeforeground='white',relief='flat',padx=12,pady=8,takefocus=True,
            highlightthickness=2,highlightbackground=BG,highlightcolor=BLUE)
        more.pack(side='right')
        self.more_menu=tk.Menu(more,tearoff=False,bg=PANEL,fg=FG,activebackground='#31556d',activeforeground='white')
        more.configure(menu=self.more_menu)
        self.more_menu.add_command(label='Copy demo command',command=self.copy_open_command)
        self.more_menu.add_command(label='Copy selected moment command',command=self.copy_jump)
        self.more_menu.add_command(label='Open selected moment in 2D',command=self.open_companion)
        self.more_menu.add_separator()
        self.more_menu.add_command(label='Legacy playback — uses CS2',command=self.show_legacy)
        self.context_title=tk.StringVar(value='Choose a downloaded demo to begin')
        self.context_meta=tk.StringVar(value='Analysis is optional for watching.')
        self.game_detail=self.label(head,variable=self.context_title,size=11)
        self.game_detail.pack(fill='x',pady=(7,0))
        self.label(head,variable=self.context_meta,color=MUTED,size=9).pack(fill='x',pady=(2,0))
        body=self.review_body=tk.Frame(self,bg=PANEL);body.pack(fill='both',expand=True,padx=12)
        self.tabs=ttk.Notebook(body,style='Review.TNotebook');self.tabs.pack(fill='both',expand=True,padx=10,pady=(8,10))
        self.library_tab=tk.Frame(self.tabs,bg=PANEL)
        self.tabs.add(self.library_tab,text=' Demos ')
        from embedded_replay import EmbeddedReplay
        from native_view_panel import NativeViewPanel
        self.embedded_view=EmbeddedReplay(self.tabs,choose_demo=self.show_downloaded,expand=self.toggle_expanded,
            play_demo=self.play_standalone,replay_demo=self.replay_standalone,search_demo=self.focus_search)
        self.tabs.add(self.embedded_view,text=' Watch ')
        self.analysis_tab=tk.Frame(self.tabs,bg=PANEL);self.tabs.add(self.analysis_tab,text=' Find moments ')
        self.native_view=NativeViewPanel(self.tabs,play_selected=self.play_selected,expand_view=self.toggle_expanded)
        self.tabs.add(self.native_view,text=' Legacy CS2 playback ');self.tabs.hide(self.native_view)
        self.tabs.bind('<<NotebookTabChanged>>',self.review_tab_changed)

        filters=tk.Frame(self.library_tab,bg=PANEL);filters.pack(fill='x',padx=14,pady=(14,8))
        filters.grid_columnconfigure(0,weight=1)
        self.label(filters,'Search demos',color=MUTED,size=9).grid(row=0,column=0,sticky='w',pady=(0,4))
        self.label(filters,'Map',color=MUTED,size=9).grid(row=0,column=1,sticky='w',padx=(10,0),pady=(0,4))
        self.search_entry=ttk.Entry(filters,textvariable=self.search)
        self.search_entry.grid(row=1,column=0,sticky='ew')
        self.search_entry.bind('<KeyRelease>',lambda _:self.filter_games())
        self.map_menu=ttk.Combobox(filters,textvariable=self.map,state='readonly',width=15,values=['All maps'])
        self.map_menu.grid(row=1,column=1,padx=(10,0),sticky='ew')
        self.map_menu.bind('<<ComboboxSelected>>',lambda _:self.filter_games())
        clear=self.button(filters,'Clear filters',self.clear_filters,pack=False);clear.grid(row=1,column=2,padx=(10,0))
        self.refresh_button=self.button(filters,'Refresh',lambda:self.load_library(refresh=True),pack=False)
        self.refresh_button.grid(row=1,column=3,padx=(8,0))
        self.search_hint=self.label(filters,'Search teams, players, tournaments, dates or Steam IDs.',color=MUTED,size=9)
        self.search_hint.grid(row=2,column=0,columnspan=4,sticky='w',pady=(5,0))
        self.library_count=tk.StringVar(value='Finding downloaded demos…')
        self.label(self.library_tab,variable=self.library_count,color=MUTED,size=9).pack(anchor='w',padx=14,pady=(0,6))
        list_area=tk.Frame(self.library_tab,bg=PANEL);list_area.pack(fill='both',expand=True,padx=14)
        self.games=self.tree(list_area,[('date','Date',100),('map','Map',85),('match','Demo',410),('analysis','Analysis',118)],9)
        self.games.bind('<<TreeviewSelect>>',self.choose_game)
        self.games.bind('<Double-1>',self.activate_game);self.games.bind('<Return>',self.activate_game)
        self.library_empty=tk.Frame(list_area,bg=PANEL)
        self.empty_title=tk.StringVar();self.empty_detail=tk.StringVar()
        self.label(self.library_empty,variable=self.empty_title,size=14).pack(anchor='w')
        self.label(self.library_empty,variable=self.empty_detail,color=MUTED).pack(anchor='w',pady=8)
        self.empty_button=self.button(self.library_empty,'Download demos',self.empty_library_action)
        actions=tk.Frame(self.library_tab,bg=PANEL);actions.pack(fill='x',padx=14,pady=14)
        self.standalone_button=self.button(actions,'Watch demo',self.play_standalone,primary=True)
        self.moments_button=self.button(actions,'Find moments',self.show_analysis)
        self.label(actions,'Select a row. Press Enter or double-click to watch.',color=MUTED,size=9).pack(side='left',padx=6)

        self.label(self.analysis_tab,'Rounds, events and saved moments',size=12).pack(anchor='w',padx=14,pady=(12,3))
        self.analysis_summary=tk.StringVar(value='Choose a demo in Demos. Analysis is optional for watching.')
        self.label(self.analysis_tab,variable=self.analysis_summary,color=MUTED,size=9).pack(anchor='w',padx=14,pady=(0,8))
        self.moment_tabs=ttk.Notebook(self.analysis_tab,style='Review.TNotebook');self.moment_tabs.pack(fill='both',expand=True,padx=12)
        self.round_tab=tk.Frame(self.moment_tabs,bg=PANEL);self.event_tab=tk.Frame(self.moment_tabs,bg=PANEL);self.saved_tab=tk.Frame(self.moment_tabs,bg=PANEL)
        for tab,title in [(self.round_tab,'Rounds'),(self.event_tab,'Events'),(self.saved_tab,'Saved moments')]:self.moment_tabs.add(tab,text=' '+title+' ')
        self.review_nav=tk.Frame(self.event_tab,bg=PANEL);self.review_nav.pack(fill='x',padx=8,pady=8)
        def field(title,var,values,width=14):
            frame=tk.Frame(self.review_nav,bg=PANEL);self.label(frame,title,color=MUTED,size=9).pack(anchor='w',pady=(0,3))
            widget=ttk.Combobox(frame,textvariable=var,state='readonly',width=width,values=values);widget.pack()
            widget.bind('<<ComboboxSelected>>',lambda _:self.filter_events());return frame,widget
        groups=[]
        frame,self.round_menu=field('Round',self.round_scope,['All rounds']);groups.append(frame)
        frame,self.kind_menu=field('Event',self.kind,['All events','Kills','Bomb events']);groups.append(frame)
        frame,self.player_menu=field('Player',self.player,['All players'],22);groups.append(frame)
        lead=tk.Frame(self.review_nav,bg=PANEL);self.label(lead,'Lead-in (seconds)',color=MUTED,size=9).pack(anchor='w',pady=(0,3))
        ttk.Spinbox(lead,from_=0,to=30,width=7,textvariable=self.lead).pack();groups.append(lead)
        for column,frame in enumerate(groups):frame.grid(row=0,column=column,sticky='nw',padx=(0,8),pady=2)
        self.review_nav.bind('<Configure>',self.flow_actions)
        self.rounds=self.tree(self.round_tab,[('round','Round',70),('teams','CT / T',360),('score','CT–T at start',128),('result','Winning side',105)],8)
        self.rounds.bind('<<TreeviewSelect>>',self.choose_round)
        self.event_tree=self.tree(self.event_tab,[('round','Round',70),('time','After freeze',100),('text','Event',540)],8)
        self.event_tree.bind('<<TreeviewSelect>>',self.choose_event)
        self.saved_scope=tk.StringVar(value='No saved moments yet. Select a round or event and choose Save moment.')
        self.label(self.saved_tab,variable=self.saved_scope,color=MUTED,size=9).pack(anchor='w',padx=8,pady=8)
        self.saved=self.tree(self.saved_tab,[('date','Date',100),('map','Map',75),('round','Round',60),('match','Demo',220),('note','Saved moment',280)],8)
        self.saved.bind('<<TreeviewSelect>>',self.choose_saved)
        self.analysis_empty=[];self.empty_moment_actions=[]
        self.analysis_empty_title=tk.StringVar(value='Choose a demo to find moments')
        for tab,tree in [(self.round_tab,self.rounds),(self.event_tab,self.event_tree)]:
            frame=tk.Frame(tab,bg=PANEL)
            self.label(frame,variable=self.analysis_empty_title,size=14).pack(anchor='w',padx=18,pady=(24,8))
            self.label(frame,'Watch this demo now, or open Local analysis to add a round and event timeline.',color=MUTED).pack(anchor='w',padx=18,pady=(0,12))
            row=tk.Frame(frame,bg=PANEL);row.pack(anchor='w',padx=18)
            primary=self.button(row,'Watch demo',self.play_standalone,primary=True)
            secondary=self.button(row,'Open analysis setup',self.open_analysis_setup)
            self.empty_moment_actions.append((primary,secondary))
            self.analysis_empty.append((frame,tree.master))
        footer=self.analysis_footer=tk.Frame(self.analysis_tab,bg=PANEL);footer.pack(fill='x',padx=14,pady=12)
        self.label(footer,variable=self.moment_text,color=BLUE).pack(anchor='w')
        ttk.Style(self).configure('Review.Horizontal.TScale',background=PANEL,troughcolor='#21394b',borderwidth=0)
        self.timeline=ttk.Scale(footer,from_=0,to=1,variable=self.position,command=lambda _:self.describe_position(),style='Review.Horizontal.TScale')
        self.timeline.pack(fill='x',pady=(5,10))
        row=tk.Frame(footer,bg=PANEL);row.pack(fill='x')
        self.watch_moment_button=self.button(row,'Watch from here',self.watch_moment,primary=True)
        self.save_button=self.button(row,'Save moment…',self.save_moment)
        self.remove_button=self.button(row,'Remove saved moment',self.remove_saved)
        self.remove_button.pack_forget()
        self.analysis_actions=[self.watch_moment_button,self.save_button]
        self.moment_tabs.bind('<<NotebookTabChanged>>',self.moment_tab_changed)
        self.status_footer=tk.Frame(self,bg=BG);self.status_footer.pack(side='bottom',fill='x',padx=12,pady=(4,7))
        self.library_status=self.label(self.status_footer,variable=self.status,color=MUTED,size=9);self.library_status.pack(fill='x')
        self.library_visible=True;self.tabs.select(self.library_tab)
        self.refresh_saved();self.clear_analysis();self.sync_actions()

    def flow_actions(self,event):
        row=column=used=0
        for child in event.widget.winfo_children():
            width=child.winfo_reqwidth()+8
            if used and used+width>event.width:row+=1;column=used=0
            child.grid_configure(row=row,column=column);used+=width;column+=1

    def review_tab_changed(self,_=None):
        if self.closed:return
        self.library_visible=self.tabs.select()==str(self.library_tab)
        if self.tabs.select()!=str(self.native_view) and self.tabs.tab(self.native_view,'state')!='hidden':self.tabs.hide(self.native_view)
        self.sync_actions()

    def moment_tab_changed(self,_=None):
        if self.closed:return
        saved=self.moment_tabs.select()==str(self.saved_tab)
        self.watch_moment_button.configure(text='Watch saved moment' if saved else 'Watch from here')
        if saved:
            self.save_button.pack_forget();self.remove_button.pack(side='left',padx=(0,8))
            if not self.saved.selection():self.moment_text.set('Select a saved moment to preview.')
        else:
            self.remove_button.pack_forget();self.save_button.pack(side='left',padx=(0,8))
            self.describe_position()
        self.sync_actions()

    def active_entry(self):
        tab=self.tabs.select()
        if tab==str(self.embedded_view) and self.playing_entry:return self.playing_entry
        if tab==str(self.native_view) and self.legacy_entry:return self.legacy_entry
        return self.entry

    def sync_actions(self):
        if not hasattr(self,'more_menu'):return
        selected=bool(self.entry);ready=bool(self.match)
        visible=selected and any(e.get('source')==self.entry.get('source') for e in self.visible)
        self.standalone_button.configure(state='normal' if visible else 'disabled',bg='#245a80' if visible else '#1a2c3d',cursor='hand2' if visible else 'arrow')
        self.moments_button.configure(state='normal' if selected else 'disabled')
        self.embedded_view.set_selection(selected)
        moment_mode=self.tabs.select()==str(self.analysis_tab)
        saved_mode=self.moment_tabs.select()==str(self.saved_tab)
        self.watch_moment_button.configure(state='normal' if ready and (not saved_mode or self.saved.selection()) else 'disabled')
        self.save_button.configure(state='normal' if ready else 'disabled')
        self.remove_button.configure(state='normal' if self.saved.selection() else 'disabled')
        active=self.active_entry()
        self.more_menu.entryconfigure(0,state='normal' if active else 'disabled')
        for index in [1,2]:self.more_menu.entryconfigure(index,state='normal' if moment_mode and ready else 'disabled')
        self.more_menu.entryconfigure(4,state='normal' if active else 'disabled')
        info=demo_label(active)
        self.context_title.set(info['name'] if active else 'Choose a downloaded demo to begin')
        self.context_meta.set(' · '.join(v for v in [info['map'],info['date'],info['source'],
            ('Analysis found' if active.get('folder') else 'Playback available · Analysis optional') if active else 'Analysis is optional for watching.'] if v))
        self.refresh_button.configure(state='disabled' if self.library_busy else 'normal')
        if hasattr(self,'analysis_empty'):
            self.analysis_empty_title.set('Optional analysis is not available' if selected else 'Choose a demo to find moments')
            for primary,secondary in self.empty_moment_actions:
                primary.configure(text='Watch demo' if selected else 'Choose demo',command=self.play_standalone if selected else self.show_downloaded)
                secondary.configure(state='normal' if selected else 'disabled')
            for empty,table in self.analysis_empty:
                if ready or self.analysis_loading:
                    empty.pack_forget();table.pack(fill='both',expand=True)
                else:
                    table.pack_forget();empty.pack(fill='both',expand=True)

    def show_analysis(self):
        self.tabs.select(self.analysis_tab);self.sync_actions()

    def show_legacy(self):
        self.legacy_entry=self.active_entry()
        if self.legacy_entry:
            same=self.entry and self.entry.get('sha')==self.legacy_entry.get('sha')
            self.native_view.playback.set_rounds(self.legacy_entry['sha'],self.match['rounds'] if same and self.match else [])
        self.tabs.tab(self.native_view,state='normal');self.tabs.select(self.native_view);self.sync_actions()

    def open_analysis_setup(self):
        if hasattr(self.host_window,'show_page'):
            if self.entry and hasattr(self.host_window,'var'):
                self.host_window.var('extract_kind').set('Single demo')
                self.host_window.var('extract_source').set(str(self.entry['demo_path']))
            self.host_window.show_page('extract')

    def empty_library_action(self):
        if self.entries:self.clear_filters()
        elif hasattr(self.host_window,'show_page'):self.host_window.show_page('download')

    def clear_filters(self):
        self.search.set('');self.map.set('All maps');self.filter_games();self.search_entry.focus_set()
