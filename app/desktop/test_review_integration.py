"""Toolbox-owned layout and lifecycle checks; no desktop automation."""
import tkinter as tk
import unittest
from unittest.mock import patch

import main
import demo_review
from native_view_panel import NativeViewPanel


class ReviewFixture(unittest.TestCase):
    def setUp(self):
        self.patches=[patch.object(main.Toolbox,'check_dependencies'),patch.object(main.Toolbox,'save_settings'),
                      patch.object(main.Toolbox,'page_download'),patch.object(main.Toolbox,'dark_title'),
                      patch.object(NativeViewPanel,'check_version'),patch.object(demo_review.DemoReview,'load_library'),
                      patch.object(demo_review.model.Moments,'read',return_value=[])]
        for p in self.patches:p.start()
        self.app=main.Toolbox();self.app.show_page('viewer');self.app.update()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        import gc
        self.app.update_idletasks()
        for timer in self.app.tk.call('after','info'):self.app.tk.call('after','cancel',timer)
        self.app.close()
        self.app=None
        for p in reversed(self.patches):p.stop()
        gc.collect()

class ToolboxReviewTests(ReviewFixture):
    def test_review_is_a_page_in_the_same_window_and_gets_the_available_height(self):
        review=self.app.review_workspace
        self.assertIsInstance(review,tk.Frame)
        self.assertIs(review.winfo_toplevel(),self.app)
        self.assertFalse(any(isinstance(w,tk.Toplevel) for w in self.app.winfo_children()))
        self.assertTrue(review.winfo_ismapped())
        self.assertFalse(self.app.content_canvas.winfo_ismapped())
        self.assertEqual(review.tabs.select(),str(review.library_tab))
        review.tabs.select(review.embedded_view);self.app.update()
        for width,height in [(1040,790),(1180,850)]:
            self.app.geometry(f'{width}x{height}');self.app.update()
            panel=review.embedded_view
            self.assertGreater(panel.viewport.winfo_height(),height-400)
            for button in panel.winfo_children()[0].winfo_children():
                self.assertLessEqual(button.winfo_x()+button.winfo_width(),button.master.winfo_width())

    def test_standalone_launch_stays_separate_from_the_engine_adapter(self):
        review=self.app.review_workspace;review.entry={'sha':'a'*64}
        with patch.object(review,'work') as work, patch.object(review.native_view,'start_private') as engine:
            review.play_standalone()
            self.assertEqual(work.call_args.args[0],'standalone_demo')
            with patch.object(demo_review.replays,'resolve_entry',return_value='downloaded.dem'):
                self.assertEqual(work.call_args.args[1](),'downloaded.dem')
            engine.assert_not_called()
        review.events.put(('standalone_demo',review.generation,'downloaded.dem'))
        with patch.object(review.embedded_view,'start') as launch, patch.object(review.native_view,'start_private') as engine:
            review.poll()
            launch.assert_called_once_with('downloaded.dem',demo_sha=review.entry['sha'])
            self.assertEqual(review.tabs.select(),str(review.embedded_view))
            engine.assert_not_called()

    def test_standalone_button_fits_the_toolbox_header(self):
        review=self.app.review_workspace
        for width in [1040,1280]:
            self.app.geometry(f'{width}x790');self.app.update()
            button=review.standalone_button
            self.assertLessEqual(button.winfo_x()+button.winfo_width(),button.master.winfo_width())

    def test_navigation_keeps_the_same_review_and_restores_other_pages(self):
        review=self.app.review_workspace;review.detail.set('Selected demo stays selected')
        self.app.show_page('download');self.app.update()
        self.assertFalse(review.winfo_ismapped())
        self.assertTrue(self.app.content_canvas.winfo_ismapped())
        self.app.open_demo_review();self.app.update()
        self.assertIs(self.app.review_workspace,review)
        self.assertEqual(review.detail.get(),'Selected demo stays selected')
        self.assertTrue(review.winfo_ismapped())

    def test_analysis_controls_wrap_inside_the_toolbox_page(self):
        self.app.geometry('1040x790');review=self.app.review_workspace
        review.tabs.select(review.analysis_tab);review.moment_tabs.select(review.event_tab);self.app.update()
        for child in review.review_nav.winfo_children():
            self.assertLessEqual(child.winfo_x()+child.winfo_width(),review.review_nav.winfo_width())

    def test_expand_and_restore_affect_only_the_toolbox_window(self):
        review=self.app.review_workspace;original=self.app.geometry()
        review.tabs.select(review.embedded_view);self.app.update()
        review.toggle_expanded();self.app.update()
        self.assertFalse(self.app.sidebar.winfo_ismapped())
        self.assertGreaterEqual(review.embedded_view.viewport.winfo_height(),self.app.winfo_height()-120)
        review.toggle_expanded();self.app.update()
        self.assertTrue(self.app.sidebar.winfo_ismapped())
        self.assertEqual(self.app.geometry(),original)


if __name__=='__main__':unittest.main()
