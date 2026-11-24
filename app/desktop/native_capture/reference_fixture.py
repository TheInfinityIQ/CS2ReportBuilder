"""Explicit offline CS2 visual references, outside the standalone renderer.

Uses the existing preference lease, process ownership, restricted controller and
Windows Graphics Capture. Captures only the owned game window; MP4s are silent.
"""
import argparse
import json
from pathlib import Path
import sys
import time
import uuid
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jobs import STATE,save_json
from native_controls import LocalGuard,Connection,verify_camera_contract
from native_session import ManagedSession
from native_viewer import Capture,SettingsGuard,configured_game


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay',type=Path,required=True)
    parser.add_argument('--start',type=int,required=True)
    parser.add_argument('--end',type=int,required=True)
    parser.add_argument('--player',required=True)
    args=parser.parse_args()
    if not 0<=args.start<args.end or args.end-args.start>64*180:parser.error('One bounded round only.')
    data=json.loads(args.replay.read_text());player=next(p for p in data['players'] if p['name']==args.player)
    account=int(player['id'])-76561197960265728
    base=STATE/'standalone3d/reference/cs2-anubis-round1';base.mkdir(parents=True,exist_ok=True)
    folder=base/('attempt-'+uuid.uuid4().hex[:10]);folder.mkdir()
    save_json(base/'latest.json',{'folder':str(folder)})
    def publish(value):
        # Status is observational: a Windows replace/read sharing conflict must
        # not abort or corrupt the video being recorded.
        for attempt in range(3):
            try:save_json(folder/'progress.json',value);return
            except PermissionError:time.sleep(.02)
    game=configured_game();baseline=SettingsGuard(game);guard=LocalGuard(game)
    session=ManagedSession(game,allow_unverified=True,experimental_control_guard=guard)
    root=tk.Tk();root.title('CS2 Toolbox · CS2 round reference');root.geometry('1280x840')
    label=tk.Label(root,text='Preparing private reference playback…');label.pack(fill='x')
    viewport=tk.Frame(root,bg='black');viewport.pack(fill='both',expand=True);root.update()
    capture=None;result={'ok':False,'accepted_reference':False,'pov_verification':'pending_visual_review','silent':True,'player':player,'start_tick':args.start,'end_tick':args.end,'videos':[]}
    screen=[root.winfo_screenwidth(),root.winfo_screenheight()]
    def pump(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            root.update()
            if session.process and session.process.poll() is not None:raise ValueError(session.failure_message('engine_exit'))
            if not guard.healthy():raise ValueError('The local control restriction ended.')
            time.sleep(.015)
    try:
        result['camera_contract']=verify_camera_contract(game)
        publish({'phase':'waiting_for_Windows_approval','message':'Accept the Windows administrator prompt for the temporary local control restriction.'})
        guard.start();session.start(Path(data['source']));result['session']=str(session.profile['session'])
        until=time.monotonic()+55
        while time.monotonic()<until:
            pump(.1)
            if not capture:
                window=session.find_window()
                if window:root.update_idletasks();capture=Capture(window['hwnd'],viewport.winfo_id())
            if capture and capture.stats().frames>60 and session.demo_active() and session.redirected():break
        else:raise TimeoutError('CS2 did not reach captured private demo playback within 55 seconds.')
        session.control=Connection(session,guard).connect();control=session.control
        # Startup can rewind once after activation; wait for natural progression.
        control.request('resume');before=control.position();advances=0;deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            pump(.5);after=control.position()
            advances=advances+1 if after['tick']>before['tick'] else 0
            publish({'phase':'waiting_for_advancing_CS2','before':before,'after':after})
            if advances>=3:break
            before=after
        else:raise ValueError('CS2 startup has not reached advancing demo playback within 25 seconds.')
        pump(4)
        control.request('pause');control.request('speed',1.)
        for mode in ['first_person','chase']:
            label.configure(text='Recording SmoodAimder · '+mode+' · round 1');root.update()
            target=args.start
            control.request('seek',target)
            last=None;stable=0;deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                pump(.3);position=control.position()['tick']
                if target-2<=position<=args.start+64:control.request('pause')
                stable=stable+1 if position==last and target-2<=position<=args.start+64 else 0;last=position
                publish({'phase':'settling_CS2_seek','mode':mode,'target':target,'observed':position})
                if stable>=2:break
            else:raise ValueError('CS2 did not settle at the first-round start tick.')
            control.request('lock_account',0);control.request('player_name',args.player)
            control.request('camera',mode);control.request('lock_account',account);pump(.5)
            path=folder/('SmoodAimder_Anubis_Round1_'+mode+'.mp4')
            if path.exists():raise ValueError('Existing reference video retained: '+str(path))
            capture.record_start(path);pump(.3)
            capture.record_snapshot(folder/(mode+'-start.png'))
            control.request('resume');started=time.monotonic();snapshots=set();positions=[]
            duration=(args.end-args.start)/64
            while time.monotonic()-started<duration+20:
                pump(.2);position=control.position()['tick'];positions.append(position)
                frames=capture.record_frames()
                for tick in [4737,5578,6345,6498,7003]:
                    if position>=tick and tick not in snapshots:
                        capture.record_snapshot(folder/(mode+'-'+str(tick)+'.png'));snapshots.add(tick)
                publish({'mode':mode,'tick':position,'frames':frames,'end':args.end})
                if position>=args.end:break
            else:raise TimeoutError('CS2 did not finish the bounded reference round.')
            control.request('pause');frames=capture.record_frames();capture.record_end()
            result['videos'].append({'mode':mode,'path':str(path),'frames':frames,'elapsed':time.monotonic()-started,
                                     'source_size':[capture.stats().width,capture.stats().height],
                                     'observed_start_tick':last,'observed_end_tick':positions[-1]})
            save_json(folder/'result.json',result)
        result['ok']=True
    except Exception as exc:
        result['error']=str(exc)
    finally:
        if capture:capture.close()
        try:session.stop()
        except Exception as exc:result['cleanup_error']=str(exc);result['ok']=False
        if guard.handle and not session.process:guard.close()
        result['original_settings_unchanged']=not baseline.check()
        result['screen_unchanged']=screen==[root.winfo_screenwidth(),root.winfo_screenheight()]
        result['engine_stopped']=not session.process or session.process.poll() is not None
        result['ok']=result['ok'] and result['original_settings_unchanged'] and result['screen_unchanged'] and result['engine_stopped']
        save_json(folder/'result.json',result);root.destroy()
    print(json.dumps(result,indent=2));return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
