"""Task flow, stable playback context, discovery, and honest empty states."""
from pathlib import Path
from unittest.mock import patch
import unittest

from test_review_integration import ReviewFixture
from review_presentation import demo_label


def entry(letter,name,map_name='de_dust2'):
    return {'sha':letter*64,'source':'download:'+letter*64,'title':name,'map':map_name,'date':'2026-11-05',
            'demo_path':Path(name+'.dem'),'folder':None,'players':{},'search':name.casefold()}


class ReviewFlowTests(ReviewFixture):
    def seed(self):
        self.a=entry('a','[16-vs-12]_Player_A_Nov-05-2026_dust2_FaceIt')
        self.b=entry('b','[13-vs-8]_Team_B-vs-Team_C_Nov-05-2026_anubis_Event','de_anubis')
        review=self.app.review_workspace;review.events.put(('library',None,[self.a,self.b]));review.poll();self.app.update();return review

    def select(self,review,index):
        review.games.selection_set(str(index));review.choose_game();self.app.update()

    def test_library_is_visible_without_an_idle_loading_indicator(self):
        review=self.seed()
        self.assertEqual(review.tabs.select(),str(review.library_tab))
        self.assertTrue(review.games.winfo_ismapped())
        self.assertEqual(review.standalone_button.cget('state'),'disabled')
        self.assertFalse(review.embedded_view.progress.winfo_manager())
        self.assertEqual(review.embedded_view.stop_button.cget('state'),'disabled')
        self.assertEqual(review.tabs.tab(review.native_view,'state'),'hidden')

    def test_selecting_a_demo_keeps_the_library_and_does_not_start_playback(self):
        review=self.seed()
        with patch.object(review.embedded_view,'start') as start:
            self.select(review,0)
            self.assertEqual(review.tabs.select(),str(review.library_tab))
            self.assertTrue(review.games.winfo_ismapped());start.assert_not_called()
            self.assertEqual(review.standalone_button.cget('state'),'normal')
            self.assertIn('16–12',review.context_title.get())

    def test_browsing_a_new_demo_does_not_relabel_the_one_being_watched(self):
        review=self.seed();self.select(review,0)
        review.playing_entry=self.a;review.embedded_view.last_demo=str(self.a['demo_path'])
        self.select(review,1)
        self.assertIn('Team B',review.context_title.get())
        review.tabs.select(review.embedded_view);self.app.update()
        self.assertIn('Player A',review.context_title.get())
        self.assertEqual(review.active_entry(),self.a)

    def test_filters_preserve_selection_but_disable_watching_a_hidden_row(self):
        review=self.seed();self.select(review,0)
        review.search.set('not-present');review.filter_games();self.app.update()
        self.assertIn('match your filters',review.empty_title.get())
        self.assertEqual(review.standalone_button.cget('state'),'disabled')
        self.assertEqual(review.entry['sha'],self.a['sha'])
        review.clear_filters();self.app.update()
        self.assertEqual(review.entry['sha'],self.a['sha'])
        self.assertEqual(len(review.visible),2)
        self.assertEqual(review.standalone_button.cget('state'),'normal')

    def test_empty_library_and_empty_filter_results_have_different_next_steps(self):
        review=self.seed();review.entries=[];review.filter_games();self.app.update()
        self.assertIn('No downloaded demos',review.empty_title.get())
        self.assertEqual(review.empty_button.cget('text'),'Download demos')
        review=self.seed();review.search.set('none');review.filter_games();self.app.update()
        self.assertEqual(review.empty_button.cget('text'),'Clear filters')

    def test_optional_analysis_does_not_block_watching(self):
        review=self.seed();self.select(review,0);review.show_analysis();self.app.update()
        self.assertTrue(review.analysis_empty[0][0].winfo_ismapped())
        self.assertIn('ready to watch',review.analysis_summary.get())
        self.assertEqual(review.watch_moment_button.cget('state'),'disabled')
        with patch.object(review,'work') as work:
            review.play_standalone();self.assertEqual(work.call_args.args[0],'standalone_demo')

    def test_refresh_retains_the_current_timeline_position(self):
        review=self.seed();self.select(review,0);review.match={'rounds':[]};review.position.set(4321)
        review.events.put(('library',None,[dict(self.a),dict(self.b)]));review.poll();self.app.update()
        self.assertEqual(review.entry['sha'],self.a['sha'])
        self.assertEqual(review.position.get(),4321)
        self.assertIsNotNone(review.match)

    def test_advanced_navigation_never_launches_cs2(self):
        review=self.seed();self.select(review,0)
        with patch.object(review.native_view,'start_private') as engine:
            review.show_legacy();self.app.update();engine.assert_not_called()
            self.assertEqual(review.tabs.select(),str(review.native_view))
            review.show_downloaded();self.app.update()
            self.assertEqual(review.tabs.tab(review.native_view,'state'),'hidden')

    def test_return_activation_uses_the_explicit_watch_action(self):
        review=self.seed();self.select(review,0)
        with patch.object(review,'play_standalone') as watch:review.activate_game();watch.assert_called_once()

    def test_fullscreen_does_not_change_the_current_task(self):
        review=self.seed();review.toggle_expanded();self.app.update()
        self.assertEqual(review.tabs.select(),str(review.library_tab))
        review.toggle_expanded();self.app.update()

    def test_retry_revalidates_the_played_demo_instead_of_using_a_new_library_selection(self):
        review=self.seed();self.select(review,1);review.playing_entry=self.a
        with patch.object(review,'work') as work,patch('demo_review.replays.resolve_entry',return_value='verified.dem') as resolve:
            review.replay_standalone()
            self.assertEqual(work.call_args.args[0],'standalone_retry')
            self.assertEqual(work.call_args.args[1](),(self.a,'verified.dem'))
            resolve.assert_called_once_with(self.a)

    def test_changed_analysis_is_reloaded_without_losing_the_target_position(self):
        review=self.seed();self.select(review,0)
        review.entry['folder']=Path('virtual-analysis');review.match={'rounds':[]};review.match_stamp=(1,10);review.position.set(321)
        with patch('demo_review.model.analysis_stamp',return_value=(2,10)),patch.object(review,'work'):
            review.events.put(('library',None,[dict(self.a),dict(self.b)]));review.poll();self.app.update()
            self.assertTrue(review.analysis_loading)
            self.assertEqual(review.pending,{'sha':self.a['sha'],'tick':321})

    def test_saving_a_moment_selects_it_and_preserves_its_exact_tick(self):
        review=self.seed();self.select(review,0)
        review.show_match({'start':0,'end':1000,'rate':64,'rounds':[{'number':1,'start':0,'freeze':0,'end':1000,
            'ct':'CT team','t':'T team','score':'0–0','winner':'T'}],'events':[],'missing':[]})
        review.position.set(487)
        saved={'id':'note','sha':self.a['sha'],'source':self.a['source'],'title':self.a['title'],'map':'de_dust2',
               'round':1,'tick':487,'note':'Check utility','saved':'2026-11-06T00:00:00Z'}
        with patch('demo_review.simpledialog.askstring',return_value='Check utility'), \
             patch.object(review.moments,'save',return_value=saved),patch.object(review.moments,'read',return_value=[saved]):
            review.save_moment();self.app.update()
            self.assertEqual(review.saved.selection(),('note',))
            self.assertEqual(review.position.get(),487)
            self.assertEqual(review.watch_moment_button.cget('state'),'normal')
            self.assertEqual(review.moment_tabs.select(),str(review.saved_tab))


class PresentationTests(unittest.TestCase):
    def test_player_score_order_and_current_filename_are_preserved(self):
        value=entry('a','[16-vs-12]_Player_A_Nov-05-2026_dust2_FaceIt')
        info=demo_label(value)
        self.assertEqual(info['name'],'[16–12] Player A');self.assertEqual(info['source'],'FACEIT')
        self.assertEqual(value['demo_path'].name,'[16-vs-12]_Player_A_Nov-05-2026_dust2_FaceIt.dem')

    def test_unrecognized_filename_keeps_its_original_title(self):
        self.assertEqual(demo_label({'title':'A useful recording name'})['name'],'A useful recording name')

    def test_date_shaped_player_name_is_not_mistaken_for_the_match_date(self):
        value=entry('a','[16-vs-12]_Nov-04-2026_Nov-05-2026_dust2_FaceIt')
        self.assertEqual(demo_label(value)['name'],'[16–12] Nov-04-2026')


if __name__=='__main__':unittest.main()
