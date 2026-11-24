"""Bounded shipping-workspace check, driven by app widget methods, not input.

Only unrelated startup dependency checks/download-page creation/settings writes
are suppressed. The library, analysis, managed session, containment, socket,
playback widgets, engine feedback and GPU capture are real.
"""
import argparse
import ctypes
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import Toolbox
from jobs import STATE,save_json
from native_viewer import SettingsGuard,configured_game


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--demo',type=Path,required=True)
    parser.add_argument('--admin-controls',action='store_true');args=parser.parse_args()
    if not args.admin_controls:parser.error('Explicit permission for --admin-controls is required.')
    baseline=SettingsGuard(configured_game());result={'ok':False}
    patches=[patch.object(Toolbox,'check_dependencies'),patch.object(Toolbox,'page_download'),patch.object(Toolbox,'save_settings')]
    for p in patches:p.start()
    app=Toolbox();app.show_page('viewer');review=app.review_workspace;panel=review.native_view;bar=panel.playback
    begin=time.monotonic();session=None
    screen=[app.winfo_screenwidth(),app.winfo_screenheight()]
    def pump(seconds=.1):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            if time.monotonic()-begin>170:raise TimeoutError('Bounded Toolbox check exceeded 170 seconds, including Windows consent.')
            app.update();time.sleep(.03)
    def wait(predicate,seconds,description):
        until=time.monotonic()+seconds
        while not predicate():
            pump()
            if time.monotonic()>until:raise TimeoutError(description+' · '+panel.status.get()+' · '+bar.note.get())
    try:
        wait(lambda:bool(review.entries) and bool(panel.control_record),15,'Library or validated control profile unavailable')
        index=next(i for i,e in enumerate(review.visible) if Path(e['demo_path']).resolve()==args.demo.resolve())
        review.games.selection_set(str(index));review.choose_game()
        wait(lambda:review.match is not None,10,'Matching analysis did not load')
        review.play_selected()
        wait(lambda:panel.pending_launch or panel.managed is not None,10,'Playback launch was not requested')
        wait(lambda:panel.launch_stage not in ('queued','approval'),120,'Windows approval did not complete')
        wait(lambda:bar.info is not None,40,'Private playback controls did not become ready after engine startup')
        session=panel.managed
        bar.submit('pause');pump(1);before=bar.observed['tick'];pump(.7)
        if bar.observed['tick']!=before:raise ValueError('Pause did not hold the engine tick in the Toolbox UI.')
        target=min(bar.info['end']-2,before+128);bar.submit('seek',target)
        wait(lambda:not bar.seek_pending and abs(bar.observed['tick']-target)<=2,8,'Stable UI seek not confirmed')
        result['precise_tick_step_available']='precise_step' in bar.capabilities
        if not bar.rounds_available():raise ValueError('Round selector did not bind to the playing demo identity.')
        number,game_tick=bar.round_context[1][0]
        bar.round_menu.set(f'Round {number}');bar.choose_round()
        expected=game_tick if bar.round_context[2]=='demo' else game_tick-bar.info['start_tick']
        wait(lambda:not bar.seek_pending and abs(bar.observed['tick']-expected)<=2,8,'Round-to-demo tick mapping not confirmed')
        result['round_jump_tick']=bar.observed['tick']
        bar.submit('seek',0);wait(lambda:not bar.seek_pending and bar.observed['tick']==0,8,'Restart not confirmed')
        review.position.set(game_tick);review.watch_moment()
        wait(lambda:not bar.seek_pending and abs(bar.observed['tick']-expected)<=2,8,'Watch selected moment not confirmed')
        result['analysis_moment_jump']=True
        result['normal_viewport']=[panel.viewport.winfo_width(),panel.viewport.winfo_height()]
        review.toggle_expanded();pump(.5)
        result['expanded_viewport']=[panel.viewport.winfo_width(),panel.viewport.winfo_height()]
        review.toggle_expanded();pump(.3)
        app.show_page('activity');pump(.4);app.show_page('viewer');pump(.4)
        if app.review_workspace is not review or panel.managed is not session or bar.info is None:
            raise ValueError('Changing Toolbox pages discarded the private playback session.')
        bar.submit('resume');old=bar.observed['tick'];wait(lambda:bar.observed['tick']>old,5,'Resume after navigation not confirmed')
        stats=panel.capture.stats();pixel=panel.capture.sample(stats.width//2,stats.height//2)
        if max(pixel[:3])<=.005 or pixel[3]<.9:raise ValueError('No nonblack game picture after navigation.')
        result.update(ok=True,frames=stats.frames,source_size=[stats.width,stats.height],
            private_config_confirmed=session.redirected(),source_input_disabled=session.input_disabled(),
            session=str(session.profile['session']),same_toolbox_window=review.winfo_toplevel() is app)
    except Exception as exc:result['message']=str(exc)
    finally:
        result['actions']=bar.action_history
        result['screen_during']=[app.winfo_screenwidth(),app.winfo_screenheight()]
        session=session or panel.managed
        try:
            if not app.review_workspace.close():raise ValueError('Owned private engine did not stop.')
            app.close()
        except Exception as exc:result['ok']=False;result['close_error']=str(exc)
        result['original_settings_unchanged']=not baseline.check()
        result['owned_process_stopped']=not session or session.process.poll() is not None
        result['guard_stopped']=not session or not session.control_guard or not session.control_guard.healthy()
        result['screen_size_unchanged']=screen==result['screen_during']==[
            ctypes.windll.user32.GetSystemMetrics(0),ctypes.windll.user32.GetSystemMetrics(1)]
        result['ok']=result['ok'] and all(result[k] for k in
            ('original_settings_unchanged','owned_process_stopped','guard_stopped','screen_size_unchanged'))
        save_json(STATE/'native-last-toolbox-smoke.json',result);print(json.dumps(result),flush=True)
        for p in reversed(patches):p.stop()
    return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
