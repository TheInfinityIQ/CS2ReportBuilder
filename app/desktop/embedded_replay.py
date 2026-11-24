"""Toolbox-owned Godot child window, asynchronous startup and cancellation."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk
import uuid

from jobs import STATE, WindowsProcessGroup, read_json, save_json
from standalone3d import launcher, map_setup


class ChildWindow:
    """Only operate on the renderer PID's existing child of our own host."""
    def __init__(self, parent, pid):
        self.parent=int(parent);self.pid=pid;self.handle=0
        self.last_display=None
        self.attaching=False;self.cancelled=threading.Event()
        self.api=ctypes.WinDLL('user32',use_last_error=True)
        self.api.GetParent.argtypes=[wintypes.HWND];self.api.GetParent.restype=wintypes.HWND
        self.api.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT];self.api.GetAncestor.restype=wintypes.HWND
        self.api.SetParent.argtypes=[wintypes.HWND,wintypes.HWND];self.api.SetParent.restype=wintypes.HWND
        self.api.GetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int];self.api.GetWindowLongPtrW.restype=ctypes.c_ssize_t
        self.api.SetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_ssize_t];self.api.SetWindowLongPtrW.restype=ctypes.c_ssize_t
        self.api.AttachThreadInput.argtypes=[wintypes.DWORD,wintypes.DWORD,wintypes.BOOL]
        self.api.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
        self.api.IsWindow.argtypes=[wintypes.HWND]
        self.api.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
        self.api.ShowWindowAsync.argtypes=[wintypes.HWND,ctypes.c_int]
        self.api.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_uint]
        self.callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
        self.api.EnumChildWindows.argtypes=[wintypes.HWND,self.callback_type,wintypes.LPARAM]
        self.api.EnumWindows.argtypes=[self.callback_type,wintypes.LPARAM]

    def valid(self):
        # SetParent holds Windows' cross-thread window lock while delivering
        # ownership messages. Querying that same HWND on Tk's thread during
        # attachment can block the host until the renderer releases the lock.
        if self.attaching:return False
        if not self.handle or not self.api.IsWindow(self.handle):return False
        pid=wintypes.DWORD();self.api.GetWindowThreadProcessId(self.handle,ctypes.byref(pid))
        return pid.value==self.pid and self.api.GetParent(self.handle)==self.parent and bool(self.api.GetWindowLongPtrW(self.handle,-16)&0x40000000)

    def find(self):
        if self.valid():return True
        if self.attaching or self.cancelled.is_set():return False
        def visit(handle,_):
            pid=wintypes.DWORD();self.api.GetWindowThreadProcessId(handle,ctypes.byref(pid))
            owner=self.api.GetParent(handle)
            if pid.value==self.pid and owner in (self.parent,self.api.GetAncestor(self.parent,2)):
                self.handle=handle;return False
            return True
        callback=self.callback_type(visit);self.api.EnumChildWindows(self.parent,callback,0)
        if not self.handle:
            # Godot 4.7 --wid creates an owned popup on Windows. Convert only
            # our renderer's popup, already owned by this exact host, to a real
            # child so clipping, page visibility and movement belong to Toolbox.
            self.api.EnumWindows(callback,0)
            if self.handle:
                self.attaching=True
                def attach():
                    try:
                        if self.cancelled.is_set():return
                        pid=wintypes.DWORD();child_thread=self.api.GetWindowThreadProcessId(self.handle,ctypes.byref(pid))
                        if pid.value!=self.pid:return
                        self.api.ShowWindowAsync(self.handle,0)
                        style=self.api.GetWindowLongPtrW(self.handle,-16)
                        self.api.SetWindowLongPtrW(self.handle,-16,(style&~0x80cf0000)|0x46000000)
                        if self.cancelled.is_set():return
                        self.api.SetParent(self.handle,self.parent)
                        parent_thread=self.api.GetWindowThreadProcessId(self.parent,None)
                        self.api.AttachThreadInput(child_thread,parent_thread,False)
                        self.last_display=None
                    finally:self.attaching=False
                threading.Thread(target=attach,daemon=True,name='toolbox-renderer-attach').start()
        return self.valid()

    def display(self,width,height,visible):
        if not self.valid():return
        width,height=max(1,width),max(1,height)
        if self.last_display==(width,height,visible):
            # An asynchronous Windows resize can be overtaken by Godot's own
            # pending size event. A posted request is not an acknowledgement.
            rect=wintypes.RECT()
            if self.api.GetClientRect(self.handle,ctypes.byref(rect)) and (rect.right,rect.bottom)==(width,height):return
        if not self.api.SetWindowPos(self.handle,None,0,0,width,height,0x4034):
            self.last_display=None;return
        self.api.ShowWindowAsync(self.handle,4 if visible else 0)
        self.last_display=(width,height,visible)


class EmbeddedReplay(tk.Frame):
    def __init__(self,master,*,choose_demo=None,expand=None,play_demo=None,replay_demo=None,search_demo=None):
        super().__init__(master,bg='#0c141d')
        self.choose_demo=choose_demo;self.expand=expand;self.messages=queue.Queue()
        self.search_demo=search_demo or choose_demo
        self.play_demo=play_demo;self.replay_demo=replay_demo;self.last_demo=None;self.has_selection=False
        self.pending_pause=False;self.command_ack=0
        self.launch_lock=threading.Lock()
        self.process=None;self.group=None;self.child=None;self.cancelled=threading.Event()
        self.closed=False;self.generation=0;self.session=None;self.ready=False;self.request_id=0
        self.retiring=[];self.closing=False
        self.started=0.;self.last_heartbeat=0.;self.last_sequence=-1;self.timer=None
        self.demo=None;self.demo_sha=None;self.pending_tick=None;self.command_sequence=0
        self.waiting_command=0
        row=tk.Frame(self,bg='#0c141d');row.pack(fill='x',padx=8,pady=6)
        for text,command in [('Back to demos',choose_demo),('Stop playback',self.stop),('Full screen',expand)]:
            button=tk.Button(row,text=text,command=command,bg='#21394b',fg='#e0eaf2',relief='flat',padx=10,pady=6,
                takefocus=True,highlightthickness=2,highlightbackground='#0c141d',highlightcolor='#75c7fb')
            button.pack(side='left',padx=(0,8))
            if command==self.stop:self.stop_button=button;button.configure(state='disabled')
        self.version=tk.StringVar(value='Godot · Inside Toolbox')
        self.viewport=tk.Frame(self,bg='#080e15',takefocus=True);self.viewport.pack(fill='both',expand=True)
        self.loading=tk.Frame(self.viewport,bg='#101d2b');self.loading.place(relx=.5,rely=.5,anchor='center',relwidth=.86)
        self.status=tk.StringVar(value='Choose a downloaded demo to watch inside Toolbox.')
        self.loading_title=tk.StringVar(value='No demo playing')
        tk.Label(self.loading,textvariable=self.loading_title,font=('Segoe UI',17),fg='#75c7fb',bg='#101d2b').pack(pady=(24,12))
        self.message=tk.Label(self.loading,textvariable=self.status,wraplength=650,fg='#e0eaf2',bg='#101d2b',font=('Segoe UI',11))
        self.message.pack(padx=16,pady=8)
        self.map_setup_request=None
        self.map_warning=tk.Frame(self.loading,bg='#101d2b')
        tk.Label(self.map_warning,text='MAP SETUP REQUIRES YOUR PERMISSION',fg='#ff9b86',bg='#101d2b',font=('Segoe UI',10,'bold')).pack(pady=6)
        actions=tk.Frame(self.map_warning,bg='#101d2b');actions.pack()
        self.map_prepare_button=tk.Button(actions,text='Prepare this map',command=self.approve_map_setup,
            bg='#24485a',fg='#ffffff',relief='flat',padx=16,pady=8)
        self.map_prepare_button.pack(side='left',padx=6)
        tk.Button(actions,text='Cancel',command=self.stop,bg='#21394b',fg='#e0eaf2',relief='flat',padx=16,pady=8).pack(side='left',padx=6)
        self.progress=ttk.Progressbar(self.loading,mode='indeterminate')
        self.watch_start=tk.Button(self.loading,text='Watch demo',command=self.restart_demo,bg='#245a80',fg='white',
            relief='flat',padx=18,pady=9,takefocus=True,highlightthickness=2,highlightbackground='#101d2b',highlightcolor='#75c7fb')
        self.watch_start.pack(pady=(8,24));self.watch_start.configure(state='disabled')
        self.viewport.bind('<Configure>',self.resize)
        self.bind('<Unmap>',lambda _:self.pause_when_hidden())
        self.timer=self.after(50,self.poll)

    def start(self,demo,*,tick=None,replay=None,smoke=None,screenshot=None,demo_sha=None):
        self.last_demo=str(Path(demo).resolve())
        self.pending_pause=False
        if self.process and self.process.poll() is None and self.ready and not any((replay,smoke,screenshot)):
            if self.demo==self.last_demo and self.demo_sha==demo_sha:
                if tick is not None:self.seek(tick)
                return
            self.demo=self.last_demo;self.demo_sha=demo_sha;self.pending_tick=tick;self.ready=False
            self.status.set('Preparing the selected demo…');self.progress.pack(fill='x',padx=30,pady=12);self.progress.start(12)
            self.loading_title.set('Opening demo');self.watch_start.pack_forget();self.stop_button.configure(text='Cancel loading',state='normal')
            self.loading.place(relx=.5,rely=.5,anchor='center',relwidth=.86)
            self.command_sequence+=1;self.waiting_command=self.command_sequence
            save_json(self.session/'command.json',{'id':self.command_sequence,'action':'load','demo':self.demo})
            self.last_heartbeat=time.monotonic();self.resize()
            return
        self.stop(message=None)
        if os.name!='nt':self.fail('Embedded 3D playback currently requires Windows.');return
        self.generation+=1;generation=self.generation;self.cancelled=threading.Event();cancelled=self.cancelled
        self.session=STATE/'standalone3d/sessions'/uuid.uuid4().hex
        self.session.mkdir(parents=True,exist_ok=True)
        self.demo=self.last_demo;self.demo_sha=demo_sha;self.pending_tick=tick;self.command_sequence=0;self.waiting_command=0
        self.ready=False;self.started=self.last_heartbeat=time.monotonic();self.last_sequence=-1;self.request_id=0
        self.attach_started=None
        self.status.set('Starting the 3D viewer inside Toolbox…')
        self.loading_title.set('Opening demo');self.watch_start.pack_forget();self.progress.pack(fill='x',padx=30,pady=12)
        self.stop_button.configure(text='Cancel loading',state='normal')
        self.loading.place(relx=.5,rely=.5,anchor='center',relwidth=.86);self.progress.start(12)
        parent=self.viewport.winfo_id();size=(self.viewport.winfo_width(),self.viewport.winfo_height());session=self.session
        messages=self.messages;launch_lock=self.launch_lock
        retiring=list(self.retiring)
        def prepare():
            process=group=None
            try:
                for finished in retiring:
                    finished.wait(5)
                    if cancelled.is_set():return
                executable=launcher.find_godot();version=launcher.runtime_version(executable)
                if cancelled.is_set():return
                process=launcher.launch(demo,parent=parent,session=session,size=size,replay=replay,smoke=smoke,screenshot=screenshot)
                group=WindowsProcessGroup(process)
                if not group.handle:raise RuntimeError('Could not supervise the embedded renderer.')
                with launch_lock:
                    abandoned=cancelled.is_set()
                    if not abandoned:messages.put((generation,'started',(process,group,version)))
                if abandoned:group.terminate();group.close();process.wait(timeout=10);return
            except Exception as exc:
                if group:group.terminate();group.close()
                elif process:process.terminate()
                messages.put((generation,'error',str(exc)))
        threading.Thread(target=prepare,daemon=True,name='toolbox-replay-start').start()

    def resize(self,_=None):
        self.message.configure(wraplength=max(150,min(650,self.viewport.winfo_width()-80)))
        if self.child:self.child.display(self.viewport.winfo_width(),self.viewport.winfo_height(),self.ready)

    def fail(self,message):
        self.stop(message=None);self.status.set(message)
        self.loading_title.set('Could not open demo');self.watch_start.configure(text='Try again')
        self.loading.place(relx=.5,rely=.5,anchor='center',relwidth=.86)

    def stop(self,message='Playback stopped. Choose a downloaded demo to continue.'):
        was_ready=self.ready
        stop_id=max(self.command_sequence,self.command_ack)+1
        stop_session=self.session
        abandoned=[]
        with self.launch_lock:
            self.generation+=1;self.cancelled.set()
            try:
                while True:
                    _,kind,value=self.messages.get_nowait()
                    if kind=='started':abandoned.append(value)
            except queue.Empty:pass
        for process,group,_ in abandoned:group.terminate();group.close()
        self.ready=False;self.progress.stop();self.progress.pack_forget()
        self.pending_pause=False;self.command_ack=0
        self.stop_button.configure(text='Stop playback',state='disabled')
        self.loading_title.set('Playback stopped' if self.last_demo else 'No demo playing')
        self.watch_start.configure(text='Watch again' if self.last_demo else 'Watch demo',state='normal' if self.last_demo or self.has_selection else 'disabled')
        self.watch_start.pack(pady=(8,24))
        self.map_setup_request=None;self.map_warning.pack_forget()
        process,group=self.process,self.group
        if self.child:
            if self.child.valid():self.child.display(self.viewport.winfo_width(),self.viewport.winfo_height(),False)
            self.child.cancelled.set()
        self.process=self.group=self.child=None
        self.demo=None;self.demo_sha=None;self.pending_tick=None
        self.retiring=[finished for finished in self.retiring if not finished.is_set()]
        if process and was_ready and stop_session and process.poll() is None:
            finished=threading.Event();self.retiring.append(finished)
            def finish_renderer():
                try:
                    # Allow Godot to commit compiled graphics caches on exit.
                    # Closing its job immediately discards that preparation.
                    save_json(stop_session/'command.json',{'id':stop_id,'action':'quit'})
                    process.wait(timeout=4)
                except (OSError,subprocess.TimeoutExpired):
                    if group:group.terminate()
                    else:process.terminate()
                    try:process.wait(timeout=2)
                    except (OSError,subprocess.TimeoutExpired):pass
                finally:
                    if group:group.close()
                    finished.set()
            threading.Thread(target=finish_renderer,daemon=True,name='toolbox-renderer-close').start()
        else:
            if group:group.terminate();group.close()
            elif process and process.poll() is None:process.terminate()
            if process:threading.Thread(target=process.wait,daemon=True).start()
        if message is not None:
            self.status.set(message);self.loading.place(relx=.5,rely=.5,anchor='center',relwidth=.86)

    def poll(self):
        if self.closed:return
        try:
            while True:
                generation,kind,value=self.messages.get_nowait()
                if generation!=self.generation:
                    if kind=='started':value[1].terminate();value[1].close()
                    continue
                if kind=='error':self.fail('Unable to open the 3D viewer: '+value)
                elif kind=='map_approved':
                    self.map_setup_request=None;self.map_warning.pack_forget()
                    self.status.set('Preparing the approved map…');self.progress.pack(fill='x',padx=30,pady=12);self.progress.start(12)
                    self.loading_title.set('Preparing demo')
                    self.command_sequence+=1;self.waiting_command=self.command_sequence
                    save_json(self.session/'command.json',{'id':self.command_sequence,'action':'load','demo':self.demo})
                    self.last_heartbeat=time.monotonic()
                elif kind=='map_approval_error':
                    self.status.set(str(value));self.map_prepare_button.configure(state='normal')
                else:
                    self.process,self.group,version=value
                    self.version.set('Godot '+version.split('.')[0]+'.'+version.split('.')[1]+' · Inside Toolbox')
                    self.child=ChildWindow(self.viewport.winfo_id(),self.process.pid)
        except queue.Empty:pass
        if self.process:
            state=read_json(self.session/'status.json',{})
            # Reparenting joins Windows input queues. Keep the owned, offscreen
            # renderer independent while imports/shaders can stall its window
            # thread, and attach only when its loading work has completed.
            attached=self.child.valid()
            if attached or state.get('state')=='ready':
                attached=self.child.find()
                if attached:self.resize()
            self.command_ack=max(self.command_ack,int(state.get('command_ack',0)))
            if self.pending_pause and self.command_ack>=self.command_sequence:
                self.pending_pause=False;self._send_pause()
            sequence=state.get('sequence',-1)
            if sequence!=self.last_sequence and state.get('command_ack',0)>=self.waiting_command:
                self.last_sequence=sequence;self.last_heartbeat=time.monotonic()
                phase=state.get('state')
                if phase=='error':self.fail(state.get('message','The renderer could not load this demo.'))
                elif phase=='ready':
                    if not attached:
                        # Attachment runs in a worker; retry the same heartbeat
                        # rather than treating an in-progress attachment as failure.
                        self.last_sequence=-1
                        self.status.set('Finishing the view inside Toolbox…')
                        if getattr(self,'attach_started',None) is None:self.attach_started=time.monotonic()
                        elif time.monotonic()-self.attach_started>10:
                            self.fail('The renderer could not attach to Toolbox. You can retry this demo.')
                            self.timer=self.after(50,self.poll);return
                    else:
                        self.ready=True;self.progress.stop();self.loading.place_forget();self.resize()
                        self.stop_button.configure(text='Stop playback',state='normal')
                        if self.pending_tick is not None:
                            self.seek(self.pending_tick);self.pending_tick=None
                elif phase!='permission_required':
                    self.status.set(state.get('message','Preparing the 3D view…'))
            request=read_json(self.session/'request.json',{})
            if request.get('id',0)>self.request_id:
                self.request_id=request['id']
                if request.get('action')=='map_setup':self.show_map_setup(request.get('map_setup',{}))
                callback={'expand':self.expand,'library':self.choose_demo,'search':self.search_demo,'stop':self.stop}.get(request.get('action'))
                if callback:callback()
            if self.process and self.process.poll() is not None:
                self.fail('The 3D viewer stopped. You can retry this demo. Details: '+str(self.session/'viewer.log'))
            elif self.process and not self.ready and self.map_setup_request is None and time.monotonic()-self.last_heartbeat>60:
                self.fail('Loading stopped responding. The renderer was stopped; you can retry. Details: '+str(self.session/'viewer.log'))
        self.timer=self.after(50,self.poll)

    def show_map_setup(self,details):
        self.ready=False;self.progress.stop()
        self.progress.pack_forget();self.watch_start.pack_forget();self.loading_title.set('Map setup needed')
        self.map_setup_request=details
        outside=' is outside your selected seven-map pool and' if not details.get('in_pool') else ''
        self.status.set(f"{details.get('label','This map')}{outside} needs preparation for the current game and viewer versions. "
            'Preparing it may take several minutes and use up to 8 GB of cache space. '
            'Your installed game files and settings will stay unchanged. Prepare this map?')
        self.map_prepare_button.configure(state='normal')
        if not details.get('installed',True):
            self.status.set(f"{details.get('label','This map')} is not installed. Install its map assets through Steam, then reopen this demo. Toolbox will ask before preparing the map.")
            self.map_prepare_button.configure(state='disabled')
        self.loading.place(relx=.5,rely=.5,anchor='center',relwidth=.86)
        self.map_warning.pack(fill='x',pady=8)
        self.resize()

    def approve_map_setup(self):
        if not self.map_setup_request:return
        if not self.map_setup_request.get('installed',True):return
        request=dict(self.map_setup_request);generation=self.generation
        self.map_prepare_button.configure(state='disabled')
        self.status.set('Checking the map version before starting the approved preparation…')
        messages=self.messages
        def approve():
            try:
                map_setup.approve(map_setup.configured_game(),request)
                messages.put((generation,'map_approved',None))
            except Exception as exc:messages.put((generation,'map_approval_error',str(exc)))
        threading.Thread(target=approve,daemon=True,name='toolbox-map-approval').start()

    def set_selection(self,available):
        self.has_selection=available
        if self.demo is None and self.last_demo is None:
            self.watch_start.configure(state='normal' if available else 'disabled')
            self.loading_title.set('Ready to watch' if available else 'No demo playing')
            self.status.set('Choose Watch demo to open your selection.' if available else 'Open Demos and select a downloaded demo to begin.')

    def restart_demo(self):
        if self.last_demo and self.replay_demo:self.replay_demo()
        elif self.last_demo:self.start(self.last_demo)
        elif self.play_demo:self.play_demo()

    def pause_when_hidden(self):
        if not self.ready or not self.session:return
        if self.command_ack<self.command_sequence:self.pending_pause=True
        else:self._send_pause()

    def _send_pause(self):
        self.command_sequence+=1
        save_json(self.session/'command.json',{'id':self.command_sequence,'action':'pause'})

    def seek(self,tick):
        if not self.session:return
        if not self.ready:self.pending_tick=tick;return
        self.command_sequence+=1
        save_json(self.session/'command.json',{'id':self.command_sequence,'action':'seek','tick':max(0,int(tick))})

    def close(self):
        self.closing=True
        if not self.closed:self.closed=True;self.stop(message=None)
        if self.timer:self.after_cancel(self.timer);self.timer=None
        # Keep the parent window alive until the owned renderer exits normally.
        return all(finished.is_set() for finished in self.retiring)
