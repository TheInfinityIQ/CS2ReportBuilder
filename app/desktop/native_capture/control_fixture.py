"""Explicit, bounded control acceptance gate. Requires administrator consent.

Run only after the user approves the temporary app/port restriction. No game
file changes, desktop input, existing-game attachment or bulk extraction.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import time
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jobs import STATE,save_json
from native_controls import LocalGuard,Connection,record_validation
from native_session import ManagedSession
from native_viewer import Capture,SettingsGuard,configured_game


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--demo',required=True,type=Path)
    parser.add_argument('--admin-guard',action='store_true',help='Explicitly permit the Windows administrator consent prompt.')
    args=parser.parse_args()
    if not args.admin_guard:parser.error('This diagnostic requires explicit approval for --admin-guard.')
    game=configured_game();baseline=SettingsGuard(game);guard=LocalGuard(game)
    session=ManagedSession(allow_unverified=True,experimental_control_guard=guard)
    root=tk.Tk();root.title('CS2 Toolbox · Private playback control check');root.geometry('1280x860+20+20')
    label=tk.Label(root,text='Preparing the temporary local control restriction…');label.pack(fill='x')
    viewport=tk.Frame(root,bg='black');viewport.pack(fill='both',expand=True)
    capture=None;result={'ok':False,'capabilities':[],'observations':[],'guard_folder':str(guard.folder)}
    screen=[root.winfo_screenwidth(),root.winfo_screenheight()]
    def pump(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            root.update()
            if session.process and session.process.poll() is not None:raise ValueError(session.failure_message('engine_exit'))
            if not guard.healthy():raise ValueError('The local control restriction ended; stopping the private engine.')
            time.sleep(.05)
    try:
        guard.start();result['guard']=json.loads((guard.folder/'guard-result.json').read_text())
        label.configure(text='Loading one known-working demo with original preferences protected…');root.update()
        session.start(args.demo);until=time.monotonic()+40
        while time.monotonic()<until:
            pump(.1)
            if not capture:
                window=session.find_window()
                if window:viewport.update_idletasks();capture=Capture(window['hwnd'],viewport.winfo_id());root.lift()
            if capture and capture.stats().frames>=60 and session.demo_active() and session.redirected():break
        else:raise TimeoutError('The demo did not reach stable playback within 40 seconds.')
        session.control=Connection(session,guard).connect();control=session.control
        result['handshake']=True
        result['demo_info']=control.request('info')
        label.configure(text='Checking pause, resume, speed and seeks using engine-reported ticks…');root.update()
        control.request('pause');pump(.3);a=control.position();pump(.5);b=control.position()
        if a['tick']!=b['tick']:raise ValueError('Pause did not hold the engine-reported tick.')
        result['capabilities'].append('pause');result['observations'].append({'paused':b})
        control.request('resume');pump(.8);advanced=control.position()
        if advanced['tick']<=b['tick']:raise ValueError('Resume did not advance the engine-reported tick.')
        result['capabilities'].append('resume')
        def measure_speed(speed):
            control.request('speed',speed);control.request('resume');pump(.3)
            begin=control.position();stamp=time.monotonic();pump(2)
            end=control.position();elapsed=time.monotonic()-stamp;control.request('pause')
            return (end['tick']-begin['tick'])/elapsed
        normal=measure_speed(1.);half=measure_speed(.5)
        result['observations'].append({'ticks_per_second_at_1x':normal,'ticks_per_second_at_half':half})
        if normal<=0 or not .2<half/normal<.8:raise ValueError('Half-speed playback did not produce the expected tick progression.')
        control.request('speed',1.);result['capabilities'].append('speed')
        control.request('pause');current=control.position()
        for name,target in [('seek_forward',min(current['end']-1,current['tick']+128)),
                            ('seek_backward',max(0,current['tick']-64))]:
            control.request('seek',target);pump(.5);observed=control.position()
            result['observations'].append({'action':name,'requested_tick':target,'observed':observed})
            if abs(observed['tick']-target)>2:raise ValueError(name+' did not reach the requested tick.')
            result['capabilities'].append(name)
        before=control.position();control.request('step');pump(.3);after=control.position()
        result['observations'].append({'step_before':before,'step_after':after})
        if after['tick']==before['tick']+1:result['capabilities'].append('step')
        else:result['limitations']=['Single-tick advance was not confirmed; leave that control disabled.']
        # Command acceptance is distinct from observed camera/POV state.
        try:
            for action,value in [('camera','first_person'),('next_player',None),('previous_player',None),('camera','chase')]:
                control.request(action,value);pump(.2)
            result['camera_commands_accepted']=True
        except ValueError as exc:result['camera_commands_accepted']=False;result['camera_limitation']=str(exc)
        control.request('resume');frames=capture.stats().frames;pump(2)
        if capture.stats().frames<=frames:raise ValueError('Rendering stopped after the control actions.')
        result.update(ok=True,frames=capture.stats().frames,source_size=[capture.stats().width,capture.stats().height],
                      private_config_confirmed=session.redirected(),session=str(session.profile['session']),
                      runtime_fingerprint=session.before_runtime['fingerprint'])
    except Exception as exc:result['message']=str(exc)
    finally:
        if capture:capture.close()
        try:session.stop()
        except Exception as exc:result['ok']=False;result['stop_error']=str(exc)
        try:guard.close()
        except Exception as exc:result['ok']=False;result['guard_stop_error']=str(exc)
        result['original_settings_unchanged']=not baseline.check()
        result['owned_process_stopped']=not session.process or session.process.poll() is not None
        result['screen_size_unchanged']=screen==[root.winfo_screenwidth(),root.winfo_screenheight()]
        result['guard_stopped']=not guard.healthy()
        result['ok']=result['ok'] and all(result.get(k) for k in
            ('original_settings_unchanged','owned_process_stopped','screen_size_unchanged','guard_stopped'))
        if result['ok']:
            try:record_validation(result)
            except Exception as exc:result['ok']=False;result['validation_error']=str(exc)
        save_json(STATE/'native-last-control-smoke.json',result)
        print(json.dumps(result),flush=True);root.destroy()
    return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
