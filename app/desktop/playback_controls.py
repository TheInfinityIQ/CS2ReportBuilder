"""Toolbox playback controls; socket I/O stays off Tk's UI thread."""
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from native_controls import Connection,SPEEDS,playback_info

BG='#080d13';FG='#e0eaf2';MUTED='#8da2b6'


class PlaybackControls(tk.Frame):
    def __init__(self,master):
        super().__init__(master,bg=BG)
        self.session=None;self.info=None;self.observed=None;self.generation=0;self.closed=False
        self.requests=queue.Queue();self.messages=queue.Queue();self.cancel=threading.Event()
        self.widgets=[];self.capabilities=set();self.slider_active=False
        self.camera_notice=False
        self.round_context=None
        self.seek_pending=False
        self.action_history=[]
        self.note=tk.StringVar(value='Connecting playback controls…');self.position=tk.DoubleVar(value=0)
        row=tk.Frame(self,bg=BG);row.pack(fill='x');row.bind('<Configure>',self.flow)
        for label,action,value in [('Resume','resume',None),('Pause','pause',None),('−10 s','skip',-10),
                                   ('+10 s','skip',10),('Restart','seek',0),('Tick +1','step',None)]:
            self.add_button(row,label,lambda a=action,v=value:self.submit(a,v))
        speed=ttk.Combobox(row,state='disabled',values=[f'{s:g}×' for s in SPEEDS],width=5)
        speed.set('1×');speed.bind('<<ComboboxSelected>>',lambda _:self.submit('speed',float(speed.get().removesuffix('×'))))
        speed.grid(row=0,column=len(row.winfo_children())-1,padx=3);self.widgets.append((speed,'speed'))
        self.add_button(row,'Previous player',lambda:self.submit('previous_player'))
        self.add_button(row,'Next player',lambda:self.submit('next_player'))
        camera=ttk.Combobox(row,state='disabled',values=['First person','Chase'],width=12)
        camera.set('Camera modes')
        camera.bind('<<ComboboxSelected>>',lambda _:self.submit('camera','first_person' if camera.get()=='First person' else 'chase'))
        # Console acceptance alone does not verify which rendered observer mode
        # these numeric values select in a particular game build.
        camera.grid(row=0,column=len(row.winfo_children())-1,padx=3);self.widgets.append((camera,'camera_mode'))
        self.round_menu=ttk.Combobox(row,state='disabled',values=[],width=9)
        self.round_menu.set('Round')
        self.round_menu.bind('<<ComboboxSelected>>',self.choose_round)
        self.round_menu.grid(row=0,column=len(row.winfo_children())-1,padx=3)
        self.widgets.append((self.round_menu,'round'))
        self.slider=ttk.Scale(self,variable=self.position,from_=0,to=1,state='disabled')
        self.slider.pack(fill='x',pady=3)
        self.slider.bind('<ButtonPress-1>',lambda _:setattr(self,'slider_active',True))
        self.slider.bind('<ButtonRelease-1>',self.seek_slider)
        for key in ('Left','Right','Home','End','Prior','Next'):
            self.slider.bind(f'<KeyRelease-{key}>',lambda _:self.submit('seek',int(self.position.get())))
        tk.Label(self,textvariable=self.note,bg=BG,fg=MUTED,anchor='w',justify='left',wraplength=950).pack(fill='x')
        self.bind('<Configure>',lambda e:self.wrap(e))
        self.timer=self.after(100,self.poll)

    def wrap(self,event):
        if event.widget is self:
            for child in self.winfo_children():
                if isinstance(child,tk.Label):child.configure(wraplength=max(100,event.width))

    def add_button(self,row,text,action):
        button=tk.Button(row,text=text,command=action,bg='#21394b',fg=FG,relief='flat',padx=8,pady=4,state='disabled')
        button.grid(row=0,column=len(row.winfo_children())-1,padx=3,pady=2)
        key={'Resume':'resume','Pause':'pause','−10 s':'seek','+10 s':'seek','Restart':'seek','Tick +1':'precise_step',
             'Previous player':'camera','Next player':'camera'}[text]
        self.widgets.append((button,key));return button

    def flow(self,event):
        row=column=used=0
        for widget in event.widget.winfo_children():
            width=widget.winfo_reqwidth()+6
            if used and used+width>event.width:row+=1;column=used=0
            widget.grid_configure(row=row,column=column);column+=1;used+=width

    def set_enabled(self,enabled):
        for widget,capability in self.widgets:
            allow=enabled and capability in self.capabilities
            if capability=='round':allow=enabled and self.rounds_available()
            widget.configure(state=('readonly' if isinstance(widget,ttk.Combobox) else 'normal') if allow else 'disabled')
        self.slider.configure(state='normal' if enabled and 'seek' in self.capabilities else 'disabled')

    def connect(self,session,record):
        self.disconnect();self.session=session;generation=self.generation;cancel=self.cancel
        self.capabilities=set(record['capabilities'])
        if {'seek_forward','seek_backward'}<=self.capabilities:self.capabilities.add('seek')
        if record.get('camera_requests'):self.capabilities.add('camera')
        requests=self.requests
        def run():
            connection=None
            try:
                connection=Connection(session,session.control_guard).connect()
                if cancel.is_set():return
                session.control=connection
                info=playback_info(''.join(connection.request('info')))
                # File/header availability precedes the engine's final startup
                # seek. Commands issued in that interval can be overwritten by
                # startup's own rewind/resume. Observe natural playback first.
                self.messages.put((generation,'loading','Waiting for the demo to finish starting…'))
                initial=connection.position()['tick'];until=time.monotonic()+25
                while not cancel.is_set():
                    time.sleep(.25);observed=connection.position()['tick']
                    if observed>initial:
                        time.sleep(.25)
                        if connection.position()['tick']>observed:break
                    initial=observed
                    if time.monotonic()>until:raise ValueError('The demo did not reach advancing playback during startup.')
                if cancel.is_set():return
                self.messages.put((generation,'ready',info))
                while not cancel.is_set():
                    try:action,value=requests.get(timeout=.5)
                    except queue.Empty:action=value=None
                    if cancel.is_set():break
                    if action:
                        if action=='game_tick':
                            if info['start_tick'] is None:raise ValueError('This demo did not provide a server tick origin.')
                            value-=info['start_tick'];action='seek'
                        if action=='skip':
                            value=connection.position()['tick']+round(value*info['rate']);action='seek'
                        if action=='step':
                            value=connection.position()['tick']+1;action='seek'
                        if action=='seek':
                            value=max(0,min(info['end']-1,int(value)))
                            connection.request(action,value)
                            time.sleep(.5)
                            until=time.monotonic()+5
                            while not cancel.is_set():
                                observed=connection.position()
                                if abs(observed['tick']-value)<=2:
                                    time.sleep(.2)
                                    stable=connection.position()
                                    if stable['tick']==observed['tick']:break
                                if time.monotonic()>until:raise ValueError('The engine did not confirm the requested seek.')
                                time.sleep(.1)
                        else:connection.request(action,value)
                        if action in ('camera','next_player','previous_player'):
                            self.messages.put((generation,'notice','Camera request accepted; player identity is not confirmed.'))
                        self.messages.put((generation,'done',None))
                    observed=connection.position()
                    self.messages.put((generation,'position',observed))
            except Exception as exc:
                if not cancel.is_set():self.messages.put((generation,'error',str(exc)))
            finally:
                if connection:connection.close()
        threading.Thread(target=run,daemon=True).start()

    def submit(self,action,value=None):
        self.action_history.append({'time':time.monotonic(),'action':action,'value':value})
        self.action_history=self.action_history[-100:]
        if self.info is None:return
        capability={'skip':'seek','game_tick':'seek','step':'precise_step','next_player':'camera','previous_player':'camera'}.get(action,action)
        if capability not in self.capabilities:
            self.note.set('This control has not been verified for the current engine.');return
        if self.seek_pending:return
        if action in ('seek','skip','game_tick','step'):
            self.seek_pending=True;self.set_enabled(False)
        self.note.set('Seeking…' if action in ('seek','skip','game_tick') else 'Sending playback request…')
        self.requests.put((action,value))

    def seek_slider(self,_=None):
        if not self.slider_active:return
        self.slider_active=False;self.submit('seek',int(self.position.get()))

    def poll(self):
        if self.closed:return
        try:
            while True:
                generation,kind,value=self.messages.get_nowait()
                if generation!=self.generation:continue
                if kind=='ready':
                    self.info=value;self.slider.configure(to=value['end']);self.set_enabled(True)
                elif kind=='loading':self.note.set(value)
                elif kind=='position':
                    self.observed=value
                    if not self.slider_active:self.position.set(value['tick'])
                    seconds=int(value['tick']/self.info['rate'])
                    self.note.set(f'Engine position {seconds//60}:{seconds%60:02} · Demo tick {value["tick"]:,} / {value["end"]:,}'
                                  + (' · Camera requested; POV identity unconfirmed' if self.camera_notice else ''))
                elif kind=='notice':self.camera_notice=True;self.note.set(value)
                elif kind=='done':self.seek_pending=False;self.set_enabled(True)
                elif kind=='error':self.seek_pending=False;self.set_enabled(False);self.info=None;self.note.set('Playback controls unavailable: '+value)
        except queue.Empty:pass
        self.timer=self.after(100,self.poll)

    def disconnect(self):
        self.cancel.set();self.generation+=1;self.cancel=threading.Event();self.requests=queue.Queue()
        self.session=None;self.info=None;self.observed=None;self.camera_notice=False;self.seek_pending=False;self.set_enabled(False)

    def seek_analysis_tick(self,tick,tick_space='demo'):
        if tick_space=='server':return self.seek_game_tick(tick)
        if tick_space!='demo' or not self.info or type(tick) is not int or not 0<=tick<self.info['end']:
            raise ValueError('This analysis moment is outside the engine-reported demo timeline.')
        self.submit('seek',tick)

    def seek_game_tick(self,tick):
        if not self.info or 'seek' not in self.capabilities:raise ValueError('Start this demo with playback controls before watching an analysis moment.')
        origin=self.info.get('start_tick')
        if origin is None or type(tick) is not int or not 0<=tick-origin<self.info['end']:
            raise ValueError('This analysis moment is outside the engine-reported demo timeline.')
        self.submit('game_tick',tick)

    def set_rounds(self,sha,rounds,tick_space='demo'):
        self.round_context=(sha,[(r['number'],r['freeze']) for r in rounds],tick_space)
        self.round_menu.configure(values=[f'Round {n}' for n,_ in self.round_context[1]])
        self.round_menu.set('Round');self.set_enabled(self.info is not None)

    def rounds_available(self):
        return bool(self.info and self.session and self.round_context
                    and self.session.demo_sha==self.round_context[0] and self.round_context[1])

    def choose_round(self,_=None):
        if not self.rounds_available():return
        try:
            number=int(self.round_menu.get().split()[-1])
            tick=next(t for n,t in self.round_context[1] if n==number)
            self.seek_analysis_tick(tick,self.round_context[2])
        except (ValueError,StopIteration) as exc:self.note.set(str(exc))

    def close(self):
        self.disconnect();self.closed=True;self.after_cancel(self.timer)
