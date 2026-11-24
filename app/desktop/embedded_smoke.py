"""Bounded native rendering fixture using Toolbox's own widgets, no CUA."""
import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import time
import tkinter as tk
from unittest.mock import patch

import main
import demo_review
from native_view_panel import NativeViewPanel
from jobs import STATE, read_json


def run(replay, *, raw=False, cancel_loading=False, timeout=90, max_ready_seconds=None, output_dir=None):
    # Match the production Toolbox entry point's per-process DPI policy.
    try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (OSError,AttributeError):pass
    metadata=json.loads(replay.read_text(encoding='utf-8'))
    output=Path(output_dir).resolve() if output_dir else STATE/'standalone3d/embedded-check'
    output.mkdir(parents=True,exist_ok=True)
    report=output/'playback.json';report.unlink(missing_ok=True)
    (output/'viewport.png').unlink(missing_ok=True)
    callback_stalls=[];original_callback=tk.CallWrapper.__call__
    def measured_callback(wrapper,*args):
        started=time.monotonic()
        try:return original_callback(wrapper,*args)
        finally:
            elapsed=time.monotonic()-started
            if elapsed>.1:
                names=[getattr(wrapper.func,'__qualname__',str(wrapper.func))]
                for cell in getattr(wrapper.func,'__closure__',None) or ():
                    try:
                        value=cell.cell_contents
                        if callable(value):names.append(getattr(value,'__qualname__',type(value).__name__))
                    except ValueError:pass
                callback_stalls.append({'milliseconds':round(elapsed*1000,1),'callbacks':names})
    patches=[patch.object(main.Toolbox,'check_dependencies'),patch.object(main.Toolbox,'save_settings'),
             patch.object(main.Toolbox,'page_download'),patch.object(main.Toolbox,'dark_title'),
             patch.object(NativeViewPanel,'check_version'),patch.object(demo_review.DemoReview,'load_library'),
             patch.object(demo_review.model.Moments,'read',return_value=[]),patch.object(tk.CallWrapper,'__call__',measured_callback)]
    for item in patches:item.start()
    app=main.Toolbox();app.show_page('viewer');app.geometry('1180x850');app.update()
    view=app.review_workspace.embedded_view
    entry={'sha':metadata['sha256'],'source':'download:'+metadata['sha256'],'title':metadata['title'],
           'map':metadata['map'],'demo_path':Path(metadata['source']),'folder':None}
    app.review_workspace.entry=entry;app.review_workspace.playing_entry=entry;app.review_workspace.sync_actions()
    app.review_workspace.tabs.select(view);app.update()
    result={'ok':False,'raw_demo':raw};started=previous=time.monotonic();gaps=[];loading_gaps=[]
    phases=set();stage=0;process=None;longest_stage=None;seek_started=0.;resize_started=None
    def finish(error=None):
        if error:result['error']=str(error)
        result['toolbox_max_callback_gap_ms']=round(max(gaps,default=0)*1000,1)
        result['toolbox_loading_max_callback_gap_ms']=round(max(loading_gaps,default=0)*1000,1)
        result['elapsed_seconds']=round(time.monotonic()-started,2)
        result['phases']=sorted(phases)
        view.stop(message=None)
        # This fixture owns its Tk application. Cancel its pending callbacks
        # before destroying it, including Toolbox's job poll, so a later map
        # fixture in this process cannot run deleted Tcl commands.
        for token in app.tk.call('after','info'):
            # Cancel the timer without deleting its callback through the root:
            # the callback may belong to a child widget, whose destroy() owns
            # that command. Tkinter after_cancel() on the wrong widget would
            # leave its owner trying to delete the same command a second time.
            try:app.tk.call('after','cancel',token)
            except tk.TclError:pass
        app.close()
    def inspect():
        nonlocal previous,stage,process,longest_stage,seek_started,resize_started
        now=time.monotonic();gap=now-previous
        if gap>max(gaps,default=0):longest_stage=stage
        gaps.append(gap);previous=now
        if stage==0:loading_gaps.append(gap)
        try:
            if now-started>timeout:raise TimeoutError(view.status.get())
            if view.process:
                process=view.process
                result.setdefault('session',str(view.session))
                state=read_json(view.session/'status.json',{})
                phases.add(state.get('message','Starting').split(' · ')[0])
                if view.ready and 'ready_seconds' not in result:result['ready_seconds']=round(now-started,3)
                if state.get('state')=='error':raise RuntimeError(state['message'])
                cancel_phase=state.get('message','').startswith(('Loading map textures','Loading the prepared map','Loading shared stock'))
                if cancel_loading and stage==0 and cancel_phase:
                    result['cancelled_during_loading']=True
                    view.stop();stage=2
            if stage==2:
                if process.poll() is None:app.after(20,inspect);return
                result['ok']=result.get('cancelled_during_loading',False)
                finish();return
            if not view.process and view.loading_title.get()=='Could not open demo':raise RuntimeError(view.status.get())
            playback=read_json(report,{}) if stage==0 and view.ready else {}
            if playback and stage==0 and view.ready:
                result['playback']=playback;result['parented']=view.child.valid()
                result['runtime_label']=view.version.get()
                result['renderer_pid']=process.pid;result['session']=str(view.session)
                seek_started=time.monotonic()
                view.seek(4321)
                stage=1;app.after(10,inspect);return
            if stage==1:
                if resize_started is None:
                    if state.get('command_ack',0)>=1 and state.get('tick')==4321:
                        result.setdefault('toolbox_seek_seconds',round(now-seek_started,3))
                    drawn=read_json(view.session/'seek-draw.json',{})
                    if (drawn.get('id'),drawn.get('tick'))!=(view.command_sequence,4321):
                        if now-seek_started>=2:raise TimeoutError('Renderer did not confirm drawing the sought tick.')
                        app.after(10,inspect);return
                    result['toolbox_seek_draw_seconds']=round(now-seek_started,3)
                    resize_started=now
                    app.geometry('1040x790')
                    app.after(20,inspect);return
                rect=wintypes.RECT();api=view.child.api
                api.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
                api.GetClientRect(view.child.handle,ctypes.byref(rect))
                result['resize_matches']=(rect.right,rect.bottom)==(view.viewport.winfo_width(),view.viewport.winfo_height())
                result['renderer_client_size']=[rect.right,rect.bottom]
                result['toolbox_viewport_size']=[view.viewport.winfo_width(),view.viewport.winfo_height()]
                # SetWindowPos deliberately posts asynchronously so the host
                # remains responsive. Confirm its acknowledgement, not a fixed
                # 350 ms assumption after an unrelated playback command.
                if not result['resize_matches'] and now-resize_started<2:
                    view.resize();app.after(20,inspect);return
                app.show_page('download');app.update_idletasks()
                api.IsWindowVisible.argtypes=[wintypes.HWND]
                result['hidden_with_page']=not bool(api.IsWindowVisible(view.child.handle))
                app.show_page('viewer');app.update_idletasks()
                visible=[]
                callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
                def top_window(handle,_):
                    pid=wintypes.DWORD();api.GetWindowThreadProcessId(handle,ctypes.byref(pid))
                    if pid.value==process.pid and api.IsWindowVisible(handle):visible.append(int(handle))
                    return True
                api.EnumWindows.argtypes=[callback_type,wintypes.LPARAM]
                api.EnumWindows(callback_type(top_window),0)
                result['external_renderer_windows']=visible
                result['heartbeat']=state
                result['toolbox_seek']=state.get('tick')==4321 and state.get('command_ack',0)>0
                result['ok']=all([result['playback']['ok'],result['parented'],result['resize_matches'],
                                  result['hidden_with_page'],not visible,result['toolbox_seek']])
                finish();return
            app.after(20,inspect)
        except Exception as exc:finish(exc)
    view.start(metadata['source'],replay=None if raw else replay,smoke=report,screenshot=output/'viewport.png')
    app.after(20,inspect)
    try:app.mainloop()
    finally:
        if process:
            try:process.wait(timeout=10)
            except Exception:result['cleanup_failed']=True
            result['renderer_stopped']=process.poll() is not None
        for item in reversed(patches):item.stop()
    result['ok']=result['ok'] and result.get('renderer_stopped',False) and result.get('toolbox_max_callback_gap_ms',10000)<1000
    log=Path(result.get('session',''))/'viewer.log'
    if log.is_file():
        errors=[line for line in log.read_text(encoding='utf-8',errors='replace').splitlines()
                if line.startswith(('ERROR:','SCRIPT ERROR:','SHADER ERROR:'))]
        result['renderer_errors']=errors[:20]
        result['ok']=result['ok'] and not errors
    if max_ready_seconds is not None and not cancel_loading:
        result['ready_budget_seconds']=max_ready_seconds
        result['within_ready_budget']=result.get('ready_seconds',float('inf'))<=max_ready_seconds
        result['ok']=result['ok'] and result['within_ready_budget']
    result['longest_callback_gap_stage']=longest_stage
    result['slow_callbacks']=sorted(callback_stalls,key=lambda item:item['milliseconds'],reverse=True)[:12]
    text=json.dumps(result,indent=2)
    (output/'result.json').write_text(text,encoding='utf-8')
    (output/('cancel-result.json' if cancel_loading else ('raw-result.json' if raw else 'replay-result.json'))).write_text(text,encoding='utf-8')
    print(json.dumps(result,indent=2))
    return 0 if result['ok'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--replay',type=Path,required=True)
    parser.add_argument('--raw',action='store_true');parser.add_argument('--timeout',type=int,default=90)
    parser.add_argument('--cancel-loading',action='store_true')
    parser.add_argument('--max-ready-seconds',type=float)
    parser.add_argument('--output-dir', type=Path, help='Store this run separately from the default evidence.')
    args=parser.parse_args();raise SystemExit(run(args.replay,raw=args.raw,cancel_loading=args.cancel_loading,timeout=args.timeout,max_ready_seconds=args.max_ready_seconds,output_dir=args.output_dir))
