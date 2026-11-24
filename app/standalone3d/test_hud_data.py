import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import hud_data
from backend import CACHE

class HudDataTests(unittest.TestCase):
    def test_missing_values_never_invent_scores_or_headshots(self):
        self.assertIsNone(hud_data.number(float('nan')))
        self.assertFalse(hud_data.flag(float('nan')))
        self.assertFalse(hud_data.flag('false'))
        self.assertTrue(hud_data.flag(True))

    def test_match_markers_and_recorded_kill_fields_survive_cache(self):
        root=CACHE/'test-fixtures';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            table=lambda rows:SimpleNamespace(to_dict=lambda _:rows)
            shared={'total_rounds_played':0,'ct_team_rounds_total':0,'t_team_rounds_total':0,'is_warmup_period':False}
            parser=Mock();parser.parse_events.return_value=[
                ('round_end',table([dict(shared,tick=1,winner=float('nan')),dict(shared,tick=120,winner='CT',total_rounds_played=1,ct_team_rounds_total=1)])),
                ('round_freeze_end',table([dict(shared,tick=50)])),
                ('player_death',table([dict(shared,tick=60,user_name='[name]',attacker_name='Shooter',weapon='weapon_ak47',headshot=True,penetrated=1,thrusmoke=False,user_steamid='76561198000000001',attacker_steamid='76561198000000002',user_team_num=2,attacker_team_num=3)]))]
            meta={'sha256':'fixture','parser':{},'rounds':[{'tick':50}],'info':{'ticks':200}}
            data=hud_data.prepare_hud(parser,meta,Path(directory),lambda *a:None)
            self.assertEqual([e['tick'] for e in data['events']],[50,60,120])
            self.assertEqual(data['events'][-1]['round'],1)
            self.assertEqual(data['events'][-1]['ct_score'],1)
            self.assertEqual(data['kills'][0]['victim_id'],'76561198000000001')
            self.assertTrue(data['kills'][0]['headshot']);self.assertTrue(data['kills'][0]['wallbang'])
            self.assertEqual(hud_data.prepare_hud(parser,meta,Path(directory),lambda *a:None),data)
            parser.parse_events.assert_called_once()

if __name__=='__main__':unittest.main()
