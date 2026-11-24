"""One bounded repaired-copy rendering check. Original demo stays untouched."""
import argparse
import json
from pathlib import Path
import sys
import time
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jobs import STATE,save_json
from native_session import ManagedSession
from native_viewer import Capture,SettingsGuard
from native_demo_compat import checksum,record_validation


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--demo',type=Path,required=True)
    parser.add_argument('--stable-seconds',type=int,default=30);args=parser.parse_args()
    if not 25<=args.stable_seconds<=60:parser.error('Use a bounded 25–60 seconds of loaded playback.')
    original_sha=checksum(args.demo)
    session=ManagedSession(allow_unverified=True);baseline=SettingsGuard(session.game)
    root=tk.Tk();root.title('CS2 Toolbox · Playback compatibility check');root.geometry('1280x860+20+20')
    label=tk.Label(root,text='Preparing a private compatibility copy. Original demo and game settings stay unchanged.');label.pack(fill='x')
    viewport=tk.Frame(root,bg='black');viewport.pack(fill='both',expand=True)
    screen=[root.winfo_screenwidth(),root.winfo_screenheight()]
    state={'capture':None,'ready':None,'frames_ready':0,'started':time.monotonic(),'finished':False}

    def finish(ok,message):
        if state['finished']:return
        state['finished']=True;capture=state['capture'];stats=capture.stats() if capture else None
        compat={k:str(v) if isinstance(v,Path) else v for k,v in (session.demo_compat or {}).items()}
        result={'ok':ok,'message':message,'frames':stats.frames if stats else 0,
            'source_size':[stats.width,stats.height] if stats else None,'frames_after_ready':stats.frames-state['frames_ready'] if stats else 0,
            'stable_playback_seconds':round(time.monotonic()-state['ready'],1) if state['ready'] else 0,
            'compatibility':compat,'demo_active':session.demo_active() if session.profile else False,
            'private_config_confirmed':session.redirected() if session.profile else False,
            'runtime_fingerprint':(session.before_runtime or {}).get('fingerprint'),
            'session':str(session.profile['session']) if session.profile else None}
        if capture:capture.close()
        try:session.stop()
        except Exception as exc:result['ok']=False;result['stop_error']=str(exc)
        result['original_settings_unchanged']=not baseline.check()
        result['original_demo_unchanged']=checksum(args.demo)==original_sha
        result['owned_process_stopped']=not session.process or session.process.poll() is not None
        result['screen_size_unchanged']=screen==[root.winfo_screenwidth(),root.winfo_screenheight()]
        if not all(result[k] for k in ('original_settings_unchanged','original_demo_unchanged','owned_process_stopped','screen_size_unchanged')):result['ok']=False
        if result['ok']:
            try:record_validation(result)
            except Exception as exc:result['ok']=False;result['validation_error']=str(exc)
        save_json(STATE/'native-last-demo-compat-smoke.json',result)
        print(json.dumps(result),flush=True);root.destroy()
        if not result['ok']:raise SystemExit(1)

    def poll():
        try:
            if session.process.poll() is not None:raise ValueError(session.failure_message('engine_exit'))
            if session.changes():raise ValueError('An original settings path changed.')
            if not state['capture']:
                window=session.find_window()
                if window:
                    viewport.update_idletasks();state['capture']=Capture(window['hwnd'],viewport.winfo_id());root.lift()
            if state['capture']:
                stats=state['capture'].stats()
                if stats.state in (3,4):raise ValueError('The private playback picture stopped.')
                if state['ready'] is None and stats.frames>=60 and session.demo_active() and session.redirected() and 'Demo Skipping:' in session.logs():
                    state['ready']=time.monotonic();state['frames_ready']=stats.frames
                stable=time.monotonic()-state['ready'] if state['ready'] else 0
                label.configure(text=f'Compatibility playback · {stats.frames} frames · {stable:.0f} seconds after startup · Original protected')
                if stable>=args.stable_seconds:
                    pixel=state['capture'].sample(stats.width//2,stats.height//2)
                    if stats.frames-state['frames_ready']<60 or max(pixel[:3])<=.005 or pixel[3]<.9:
                        raise ValueError('Continuous nonblack playback was not confirmed.')
                    finish(True,'The previously crashing demo rendered beyond startup using its verified private compatibility copy.');return
            if time.monotonic()-state['started']>100:raise TimeoutError('The bounded compatibility check timed out.')
            root.after(200,poll)
        except Exception as exc:finish(False,str(exc))

    def start():
        try:session.start(args.demo);poll()
        except Exception as exc:finish(False,str(exc))
    viewport.bind('<Configure>',lambda _:state['capture'].resize() if state['capture'] else None)
    root.protocol('WM_DELETE_WINDOW',lambda:finish(False,'Compatibility check was closed.'))
    root.after(150,start);root.mainloop()


if __name__=='__main__':main()
