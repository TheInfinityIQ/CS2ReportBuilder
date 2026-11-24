"""CS2 review workspace with an in-app, read-only native game viewport."""
from __future__ import annotations
import queue
from pathlib import Path
import threading
import tkinter as tk
from tkinter import simpledialog, ttk

import cs2_jump
import review_model as model
import replay_inventory as replays
from native_view_panel import NativeViewPanel
from embedded_replay import EmbeddedReplay
from review_layout import ReviewLayout
from review_presentation import demo_label,map_label

BG='#0c141d';PANEL='#121e2a';FG='#e0eaf2';MUTED='#8da2b6';BLUE='#75c7fb'


class DemoReview(ReviewLayout,tk.Frame):
    def __init__(self,master,viewer,expand_changed=None):
        super().__init__(master)
        self.viewer=viewer;self.host_window=self.winfo_toplevel();self.expand_changed=expand_changed
        self.configure(bg=BG);self.events=queue.Queue();self.closed=False
        style=ttk.Style(self)
        style.configure('Review.TNotebook',background=PANEL,borderwidth=0)
        style.configure('Review.TNotebook.Tab',background='#21394b',foreground=FG,padding=(12,6))
        style.map('Review.TNotebook.Tab',background=[('selected','#31556d')],foreground=[('selected','#ffffff')])
        style.configure('Review.Treeview',background=PANEL,fieldbackground=PANEL,foreground=FG,rowheight=32,font=('Segoe UI',10))
        style.configure('Review.Treeview.Heading',font=('Segoe UI',10,'bold'),padding=(8,9))
        style.map('Review.Treeview',background=[('selected','#245a80')],foreground=[('selected','#ffffff')])
        self.entries=[];self.visible=[];self.entry=None;self.match=None;self.generation=0;self.pending=None
        self.pending_watch=None
        self.playing_entry=None;self.legacy_entry=None;self.analysis_loading=False;self.map_options={};self.match_stamp=None
        self.moments=model.Moments();self.library_busy=False
        self.search=tk.StringVar();self.map=tk.StringVar(value='All maps');self.kind=tk.StringVar(value='All events')
        self.round_scope=tk.StringVar(value='All rounds');self.lead=tk.StringVar(value='3');self.position=tk.DoubleVar(value=0)
        self.status=tk.StringVar(value='Finding downloaded demos…');self.detail=tk.StringVar(value='Choose a downloaded demo to begin.')
        self.moment_text=tk.StringVar(value='No moment selected');self.player=tk.StringVar(value='All players')
        self.expanded=False;self.restore_geometry=None
        self.layout();self.poll_timer=self.after(80,self.poll);self.load_library()
        self.key_bindings=[('<F11>',self.host_window.bind('<F11>',self.expand_key,add='+')),
                           ('<Escape>',self.host_window.bind('<Escape>',self.restore_key,add='+')),
                           ('<Control-f>',self.host_window.bind('<Control-f>',self.focus_search,add='+')),
                           ('<Alt-Left>',self.host_window.bind('<Alt-Left>',self.back_to_demos,add='+'))]

    def expand_key(self,_=None):
        if self.winfo_ismapped():self.toggle_expanded();return 'break'

    def restore_key(self,_=None):
        if self.expanded:self.toggle_expanded();return 'break'

    def label(self,parent,text='',variable=None,color=FG,size=10):
        label=tk.Label(parent,text=text,textvariable=variable,fg=color,bg=parent.cget('bg'),font=('Segoe UI',size),anchor='w',justify='left',wraplength=1100)
        parent.bind('<Configure>',lambda e,w=label:w.configure(wraplength=max(100,min(1100,e.width-24))),add='+')
        return label

    def button(self,parent,text,command,primary=False,pack=True):
        b=tk.Button(parent,text=text,command=command,bg='#245a80' if primary else '#21394b',fg=FG,activebackground='#31556d',activeforeground=FG,
                    disabledforeground='#9aaabd',relief='flat',padx=12,pady=8,cursor='hand2',takefocus=True,
                    highlightthickness=2,highlightbackground=parent.cget('bg'),highlightcolor=BLUE)
        if pack:b.pack(side='left',padx=(0,8))
        return b

    def tree(self,parent,columns,height):
        frame=tk.Frame(parent,bg=PANEL);frame.pack(fill='both',expand=True)
        tree=ttk.Treeview(frame,columns=[c[0] for c in columns],show='headings',height=height,selectmode='browse',style='Review.Treeview')
        scroll=ttk.Scrollbar(frame,orient='vertical',command=tree.yview);tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        for key,title,width in columns:
            tree.heading(key,text=title,anchor='w');tree.column(key,width=width,minwidth=50,stretch=key in ('match','text','note','teams'))
        return tree

    def focus_search(self,_=None):
        if self.winfo_ismapped():
            self.show_downloaded();self.search_entry.focus_set();self.search_entry.selection_range(0,tk.END);return 'break'

    def back_to_demos(self,_=None):
        if self.winfo_ismapped():self.show_downloaded();return 'break'

    def activate_game(self,event=None):
        if event is not None and getattr(event,'num',None) in (1,'1') and not self.games.identify_row(event.y):return 'break'
        if self.games.selection():self.choose_game();self.play_standalone()
        return 'break'

    def toggle_expanded(self):
        # Fullscreen belongs to this review window only; CS2 is never resized.
        if self.expanded:
            self.host_window.attributes('-fullscreen',False)
            if self.restore_geometry:self.host_window.geometry(self.restore_geometry)
            if self.expand_changed:self.expand_changed(False)
            self.header.pack(fill='x',padx=12,pady=8,before=self.review_body)
            self.review_body.pack_configure(padx=12)
            self.tabs.pack_configure(padx=12,pady=(0,12))
            self.tabs.configure(style='Review.TNotebook')
            self.status_footer.pack(side='bottom',fill='x',padx=12,pady=(4,7))
        else:
            self.restore_geometry=self.host_window.geometry()
            self.review_tab_changed();self.header.pack_forget()
            self.status_footer.pack_forget()
            self.review_body.pack_configure(padx=0);self.tabs.pack_configure(padx=0,pady=0)
            style=ttk.Style(self);style.layout('Review.Expanded.TNotebook.Tab',[])
            self.tabs.configure(style='Review.Expanded.TNotebook')
            if self.expand_changed:self.expand_changed(True)
            self.host_window.attributes('-fullscreen',True)
        self.expanded=not self.expanded;self.native_view.set_expanded(self.expanded)

    def work(self,tag,fn,generation=None):
        events=self.events
        def run():
            try:events.put((tag,generation,fn()))
            except Exception as exc:events.put(('error',generation,(tag,str(exc))))
        threading.Thread(target=run,daemon=True).start()

    def toggle_library(self):
        self.tabs.select(self.embedded_view if self.library_visible else self.library_tab)

    def load_library(self,refresh=False):
        if self.library_busy:return
        self.library_busy=True;self.status.set('Finding downloaded demos in replays…')
        self.sync_actions()
        self.work('library',model.library)

    def filter_games(self):
        selected=self.entry['source'] if self.entry else None
        self.visible=model.filter_library(self.entries,self.search.get(),None if self.map.get()=='All maps' else self.map_options.get(self.map.get()))
        self.games.delete(*self.games.get_children())
        for i,e in enumerate(self.visible):
            info=demo_label(e)
            self.games.insert('','end',iid=str(i),values=(info['date'],info['map'],info['name'],'Found' if e.get('folder') else 'Not analyzed'))
        self.library_count.set(f'{len(self.visible)} of {len(self.entries)} downloaded demos · Newest first')
        index=next((i for i,e in enumerate(self.visible) if e['source']==selected),None)
        if index is not None:self.games.selection_set(str(index));self.games.see(str(index))
        if self.visible:self.library_empty.place_forget()
        else:
            self.empty_title.set('No demos match your filters' if self.entries else 'No downloaded demos yet')
            self.empty_detail.set('Try another search or clear the map filter.' if self.entries else 'Download a demo first. It will appear here when the download finishes.')
            self.empty_button.configure(text='Clear filters' if self.entries else 'Download demos')
            self.empty_button.configure(command=self.empty_library_action)
            self.library_empty.place(relx=.5,rely=.5,anchor='center',relwidth=.9)
        self.sync_actions()

    def choose_game(self,_=None):
        selection=self.games.selection()
        if not selection:return
        entry=self.visible[int(selection[0])]
        if self.entry and entry['source']==self.entry['source']:return
        self.entry=entry;self.match=None;self.generation+=1;generation=self.generation
        self.native_view.playback.set_rounds(entry['sha'],[])
        self.pending_watch=None
        if self.pending and self.pending['sha']!=entry['sha']:self.pending=None
        self.clear_analysis();self.detail.set(entry['title'])
        if getattr(self,'load_timer',None):self.after_cancel(self.load_timer)
        if not entry.get('folder'):
            self.moment_text.set('Downloaded and ready to watch · Round and event analysis is not available yet.')
            self.analysis_summary.set('This demo is ready to watch. Optional round and event analysis is not available yet.')
            self.status.set('Demo selected. Choose Watch demo, or press Enter.');self.sync_actions()
            return
        self.analysis_loading=True;self.sync_actions()
        self.analysis_summary.set('Loading rounds and events…')
        self.moment_text.set('Loading match timeline…')
        self.load_timer=self.after(180,lambda:self.work('match',lambda:model.load_match(entry),generation))

    def clear_analysis(self):
        self.match=None;self.analysis_loading=False;self.rounds.delete(*self.rounds.get_children());self.event_tree.delete(*self.event_tree.get_children())
        self.timeline.configure(state='disabled');self.round_menu.configure(values=['All rounds'],state='disabled')
        self.round_scope.set('All rounds');self.player_menu.configure(values=['All players'],state='disabled');self.player.set('All players')
        for button in self.analysis_actions:button.configure(state='disabled')
        self.kind_menu.configure(state='disabled')
        self.analysis_summary.set('Choose a demo in Demos. Analysis is optional for watching.')
        self.sync_actions()

    def show_match(self,match):
        self.analysis_loading=False
        self.match_stamp=model.analysis_stamp(self.entry)
        self.native_view.playback.set_rounds(self.entry['sha'],match['rounds'],match.get('tick_space','demo'))
        self.timeline.configure(state='normal');self.round_menu.configure(state='readonly');self.player_menu.configure(state='readonly')
        for button in self.analysis_actions:button.configure(state='normal')
        self.match=match;self.timeline.configure(from_=match['start'],to=match['end'])
        self.round_menu.configure(values=['All rounds']+[f'Round {r["number"]}' for r in match['rounds']]);self.round_scope.set('All rounds')
        self.player_ids={'All players':None}
        for sid,names in self.entry.get('players',{}).items():self.player_ids[' / '.join(names)+' · '+sid[-6:]]=sid
        self.player_menu.configure(values=list(self.player_ids));self.player.set('All players')
        for r in match['rounds']:
            self.rounds.insert('','end',iid=str(r['number']),values=(r['number'],f'{r["ct"]} / {r["t"]}',r['score'],r['winner']))
        self.position.set(match['rounds'][0]['freeze']);self.filter_events();self.describe_position()
        self.status.set(f'{len(match["rounds"])} rounds · {len(match["events"])} events'+
                        (f' · {len(match["missing"])} event streams unavailable' if match['missing'] else ''))
        self.analysis_summary.set(self.status.get());self.kind_menu.configure(state='readonly');self.sync_actions()
        if self.pending and self.pending['sha']==self.entry['sha']:
            saved=self.pending;self.pending=None;self.position.set(max(match['start'],min(match['end'],saved['tick'])));self.describe_position()

    def filter_events(self):
        self.event_tree.delete(*self.event_tree.get_children())
        if not self.match:return
        rnd=None if self.round_scope.get()=='All rounds' else int(self.round_scope.get().split()[-1])
        self.visible_events=model.event_filter(self.match['events'],rnd,self.kind.get(),self.player_ids.get(self.player.get()))
        for i,e in enumerate(self.visible_events):
            r=next(r for r in self.match['rounds'] if r['number']==e['round']);seconds=max(0,int((e['tick']-r['freeze'])/self.match['rate']))
            self.event_tree.insert('','end',iid=str(i),values=(e['round'],f'{seconds//60}:{seconds%60:02}',e['text']))

    def choose_round(self,_=None):
        if not self.match or not self.rounds.selection():return
        number=int(self.rounds.selection()[0]);rnd=next(r for r in self.match['rounds'] if r['number']==number)
        self.position.set(rnd['freeze']);self.round_scope.set(f'Round {number}');self.filter_events();self.describe_position()

    def choose_event(self,_=None):
        if not self.match or not self.event_tree.selection():return
        try:self.position.set(model.event_target(self.match,self.visible_events[int(self.event_tree.selection()[0])],self.lead.get()));self.describe_position()
        except ValueError as exc:self.status.set(str(exc))

    def current(self):
        if not self.entry or not self.match:raise ValueError('Choose a match and a round or event first.')
        tick=max(self.match['start'],min(self.match['end'],int(self.position.get())))
        rnd=next((r for r in self.match['rounds'] if r['start']<=tick<=r['end']),None)
        if not rnd:rnd=min(self.match['rounds'],key=lambda r:abs(r['freeze']-tick));tick=rnd['freeze']
        return self.entry,rnd,tick

    def describe_position(self):
        if not self.match:return
        _,rnd,tick=self.current();seconds=max(0,int((tick-rnd['freeze'])/self.match['rate']))
        self.moment_text.set(f'Round {rnd["number"]} · {seconds//60}:{seconds%60:02} after freeze time')

    def copy_jump(self):
        try:
            _,_,tick=self.current();self.clipboard_clear();self.clipboard_append(cs2_jump.jump_command(tick).replace('\n','; ').rstrip('; '));self.update()
            self.status.set('Jump copied. After the demo loads in CS2, open its console and paste this command.')
        except ValueError as exc:self.status.set(str(exc))

    def open_companion(self):
        try:entry,rnd,tick=self.current();self.viewer.open(source=entry['source'],round_number=rnd['number'],tick=tick)
        except ValueError as exc:self.status.set(str(exc))

    def copy_open_command(self):
        entry=self.active_entry()
        if not entry:self.status.set('Choose a downloaded demo first.');return
        def resolve():
            path=replays.resolve_entry(entry)
            return 'playdemo '+cs2_jump.console_path(path)
        self.status.set('Finding and verifying the original demo…')
        self.work('copy_demo',resolve,self.generation)

    def play_standalone(self):
        if not self.entry:
            self.show_downloaded();self.status.set('Select a demo, then choose Watch demo.');return
        entry=self.entry
        self.tabs.select(self.embedded_view)
        self.status.set('Verifying the downloaded demo for playback inside Toolbox…')
        self.embedded_view.status.set(self.status.get())
        self.work('standalone_demo',lambda:replays.resolve_entry(entry),self.generation)

    def show_downloaded(self):
        if self.expanded:self.toggle_expanded()
        self.tabs.select(self.library_tab);self.games.focus_set()

    def replay_standalone(self):
        entry=self.playing_entry or self.entry
        if not entry:self.show_downloaded();return
        self.work('standalone_retry',lambda:(entry,replays.resolve_entry(entry)),self.generation)

    def play_selected(self):
        if self.native_view.pending_launch:return
        entry=self.legacy_entry or self.entry
        if not entry:
            if self.expanded:self.toggle_expanded()
            if not self.library_visible:self.toggle_library()
            self.status.set('Choose a downloaded demo first.');self.native_view.status.set(self.status.get());return
        self.status.set('Finding and verifying the original demo for private playback…')
        self.native_view.status.set(self.status.get())
        def resolve():
            return replays.resolve_entry(entry)
        self.work('play_demo',resolve,self.generation)

    def watch_moment(self):
        try:
            entry,_,tick=self.current();panel=self.embedded_view
            self.tabs.select(panel)
            if self.match.get('tick_space','demo')!='demo':raise ValueError('This analysis uses an unsupported tick reference. Open its downloaded demo instead.')
            if panel.demo==str(Path(entry['demo_path']).resolve()) and panel.demo_sha==entry['sha'] and panel.ready:
                panel.seek(tick)
            else:
                self.work('standalone_moment',lambda:(replays.resolve_entry(entry),tick),self.generation)
        except ValueError as exc:self.status.set(str(exc));self.embedded_view.status.set(str(exc))

    def refresh_saved(self):
        self.saved.delete(*self.saved.get_children())
        try:
            available={e['sha'] for e in self.entries}
            self.saved_values=[v for v in self.moments.read() if v['sha'] in available]
            for v in self.saved_values:
                info=demo_label(v)
                self.saved.insert('','end',iid=v['id'],values=(info['date'],info['map'],v['round'],info['name'],v['note']))
            self.saved_scope.set(f'{len(self.saved_values)} saved moments across your downloaded demos.' if self.saved_values else 'No saved moments for downloaded demos yet. Select a round or event and choose Save moment.')
        except (OSError,ValueError) as exc:
            self.saved_values=[];self.status.set(str(exc));self.saved_scope.set('Saved moments could not be read. Your existing notes were left unchanged.')

    def save_moment(self):
        try:entry,rnd,tick=self.current()
        except ValueError as exc:self.status.set(str(exc));return
        note=simpledialog.askstring('Save moment','Name or coaching note:',parent=self,initialvalue=f'Round {rnd["number"]}')
        if note is None:return
        try:
            saved=self.moments.save(entry,tick,rnd['number'],note);self.refresh_saved()
            self.saved.selection_set(saved['id']);self.saved.see(saved['id'])
            self.status.set('Moment saved.');self.tabs.select(self.analysis_tab);self.moment_tabs.select(self.saved_tab)
        except (OSError,ValueError) as exc:self.status.set(str(exc))

    def remove_saved(self):
        if self.moment_tabs.select()!=str(self.saved_tab) or not self.saved.selection():self.status.set('Select a saved moment to remove.');return
        try:self.moments.remove(self.saved.selection()[0]);self.refresh_saved();self.status.set('Saved moment removed.');self.sync_actions()
        except (OSError,ValueError) as exc:self.status.set(str(exc))

    def choose_saved(self,_=None):
        if not self.saved.selection():return
        saved=next(v for v in self.saved_values if v['id']==self.saved.selection()[0])
        if self.entry and self.match and self.entry['sha']==saved['sha']:
            self.position.set(max(self.match['start'],min(self.match['end'],saved['tick'])));self.describe_position();self.sync_actions();return
        entry=next((e for e in self.entries if e['sha']==saved['sha']),None)
        if not entry:self.status.set('This saved moment’s demo is not downloaded in replays.');return
        self.pending=saved;self.search.set('');self.map.set('All maps');self.filter_games()
        index=self.visible.index(entry);self.games.selection_set(str(index));self.games.see(str(index));self.choose_game()

    def poll(self):
        if self.closed:return
        try:
            while True:
                kind,generation,value=self.events.get_nowait()
                if generation is not None and generation!=self.generation:continue
                if kind=='library':
                    self.library_busy=False;self.entries=value
                    sha=self.entry['sha'] if self.entry else None
                    old=self.entry;new=next((e for e in value if e['sha']==sha),None)
                    preserve=bool(old and new and old.get('folder')==new.get('folder') and
                        (not new.get('folder') or self.match or self.analysis_loading) and
                        (not self.match or model.analysis_stamp(new)==self.match_stamp))
                    if not preserve:
                        if old and new and self.match:self.pending={'sha':sha,'tick':int(self.position.get())}
                        self.entry=None;self.generation+=1;self.clear_analysis()
                        self.moment_text.set('Choose a downloaded demo to begin.');self.detail.set('No demo selected')
                    else:self.entry=new
                    self.map_options={map_label(e['map']):e['map'] for e in value}
                    self.map_menu.configure(values=['All maps']+sorted(self.map_options));self.filter_games()
                    if self.map.get() not in self.map_menu.cget('values'):self.map.set('All maps');self.filter_games()
                    selected=next((i for i,e in enumerate(self.visible) if e['sha']==sha),None)
                    if selected is not None:
                        self.games.selection_set(str(selected))
                        if not preserve:self.choose_game()
                    self.refresh_saved();self.sync_actions()
                    self.status.set('Demo library refreshed.' if preserve else 'Select a demo, then choose Watch demo. Analysis is optional.')
                elif kind=='match':self.show_match(value)
                elif kind=='copy_demo':
                    self.clipboard_clear();self.clipboard_append(value)
                    self.status.set('Verified demo command copied. Paste it manually into CS2’s console to load the selected recording.')
                elif kind=='standalone_demo':
                    self.playing_entry=dict(self.entry) if self.entry else None
                    self.tabs.select(self.embedded_view)
                    self.embedded_view.start(value,demo_sha=self.playing_entry['sha'] if self.playing_entry else None)
                    self.status.set('Preparation and playback controls are shown in Watch. F11 opens full screen.')
                    self.sync_actions()
                elif kind=='standalone_moment':
                    self.playing_entry=dict(self.entry) if self.entry else None
                    self.tabs.select(self.embedded_view)
                    self.embedded_view.start(value[0],tick=value[1],demo_sha=self.playing_entry['sha'] if self.playing_entry else None)
                    self.sync_actions()
                elif kind=='standalone_retry':
                    self.playing_entry=dict(value[0]);self.tabs.select(self.embedded_view)
                    self.embedded_view.start(value[1],demo_sha=self.playing_entry['sha']);self.sync_actions()
                elif kind=='play_demo':
                    self.tabs.select(self.native_view)
                    if self.pending_watch and self.entry and self.pending_watch[0]==self.entry['sha']:
                        _,tick,tick_space=self.pending_watch;self.pending_watch=None
                        self.native_view.start_private(value,analysis_tick=tick,tick_space=tick_space)
                    else:self.native_view.start_private(value)
                    self.status.set('Private playback requested. Engine playback controls are available when enabled.')
                elif kind=='progress':self.status.set(value)
                elif kind=='error':
                    origin,message=value
                    if origin=='library':
                        self.library_busy=False;self.sync_actions()
                        self.library_count.set('Could not refresh demos. Choose Refresh to try again.')
                        if not self.entries:
                            self.empty_title.set('Could not load your demos');self.empty_detail.set('Choose Try again to refresh the download library.')
                            self.empty_button.configure(text='Try again',command=lambda:self.load_library(refresh=True))
                            self.library_empty.place(relx=.5,rely=.5,anchor='center',relwidth=.9)
                    self.status.set(message)
                    if origin in ('standalone_demo','standalone_moment','standalone_retry'):self.embedded_view.status.set(message)
                    if origin=='play_demo':self.native_view.status.set(message)
                    if origin in ('copy_demo','play_demo'):self.load_library()
                    if origin=='match':
                        self.clear_analysis();self.moment_text.set('Downloaded demo is ready to watch. Its analysis could not be loaded.')
                        self.analysis_summary.set('Analysis could not be loaded. You can still watch the demo.')
        except queue.Empty:pass
        self.poll_timer=self.after(80,self.poll)

    def close(self):
        if not self.native_view.close():
            self.status.set('The private engine has not stopped. Use Stop view again before closing.')
            self.native_view.status.set(self.status.get());return False
        if not self.embedded_view.close():
            self.status.set('Closing the demo viewer…');return False
        self.closed=True;self.generation+=1
        if self.expanded:self.toggle_expanded()
        for key,binding in self.key_bindings:self.host_window.unbind(key,binding)
        for timer in (getattr(self,'poll_timer',None),getattr(self,'load_timer',None)):
            if timer:self.after_cancel(timer)
        self.destroy()
        return True


if __name__=='__main__':
    from main import Toolbox
    toolbox=Toolbox();toolbox.show_page('viewer')
    toolbox.mainloop()
