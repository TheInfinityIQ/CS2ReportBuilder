import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from playback_controls import PlaybackControls


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.geometry('760x200')
        self.bar=PlaybackControls(self.root);self.bar.pack(fill='both',expand=True);self.root.update()
        self.addCleanup(self.cleanup)

    def cleanup(self):self.bar.close();self.root.destroy()

    def ready(self):
        self.bar.session=SimpleNamespace(demo_sha='a'*64)
        self.bar.info={'start_tick':36562,'end':102934,'rate':64}
        self.bar.capabilities={'pause','resume','speed','seek'}
        self.bar.set_enabled(True)

    def test_analysis_ticks_are_translated_only_with_a_valid_engine_origin(self):
        self.ready()
        with patch.object(self.bar,'submit') as submit:
            self.bar.seek_game_tick(36946);submit.assert_called_once_with('game_tick',36946)
            for tick in [36561,200000,'36946',True]:
                with self.assertRaises(ValueError):self.bar.seek_game_tick(tick)
            self.bar.info['start_tick']=None
            with self.assertRaises(ValueError):self.bar.seek_game_tick(36946)

    def test_round_controls_cannot_use_another_downloads_analysis(self):
        self.ready();self.bar.set_rounds('b'*64,[{'number':1,'freeze':36946}])
        self.assertFalse(self.bar.rounds_available())
        self.assertEqual(str(self.bar.round_menu.cget('state')),'disabled')
        self.bar.set_rounds('a'*64,[{'number':1,'freeze':36946}]);self.assertTrue(self.bar.rounds_available())
        with patch.object(self.bar,'seek_analysis_tick') as seek:
            self.bar.round_menu.set('Round 1');self.bar.choose_round();seek.assert_called_once_with(36946,'demo')

    def test_existing_extractor_ticks_are_not_shifted_by_the_server_start_tick(self):
        self.ready()
        with patch.object(self.bar,'submit') as submit:
            self.bar.seek_analysis_tick(6022,'demo');submit.assert_called_once_with('seek',6022)
        self.bar.slider_active=False
        with patch.object(self.bar,'submit') as submit:
            self.bar.seek_slider();submit.assert_not_called()

    def test_old_connection_events_cannot_enable_disconnected_controls(self):
        generation=self.bar.generation;self.bar.disconnect()
        self.bar.messages.put((generation,'ready',{'start_tick':1,'end':100,'rate':64}))
        self.bar.after_cancel(self.bar.timer);self.bar.poll()
        self.assertIsNone(self.bar.info)
        self.assertEqual(str(self.bar.slider.cget('state')),'disabled')

    def test_transport_controls_fit_a_narrow_embedded_page(self):
        self.ready();self.root.update()
        row=self.bar.winfo_children()[0]
        for widget in row.winfo_children():
            self.assertLessEqual(widget.winfo_x()+widget.winfo_width(),row.winfo_width())

    def test_command_acceptance_does_not_enable_unverified_camera_modes_or_tick_steps(self):
        self.ready();self.bar.capabilities.add('camera');self.bar.set_enabled(True)
        for widget,capability in self.bar.widgets:
            if capability in ('camera_mode','precise_step'):
                self.assertEqual(str(widget.cget('state')),'disabled')


if __name__=='__main__':unittest.main()
