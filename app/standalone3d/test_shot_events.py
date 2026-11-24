import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import shot_events
from backend import CACHE

class ShotEventsTests(unittest.TestCase):
    def setUp(self):
        self.base=CACHE/'test-fixtures';self.base.mkdir(parents=True,exist_ok=True)
    def test_only_recorded_finite_impacts_for_known_players_are_retained(self):
        with tempfile.TemporaryDirectory(dir=self.base) as directory:
            rows=[{'tick':20,'user_steamid':'7','x':1,'y':2,'z':3},
                  {'tick':21,'user_steamid':'8','x':1,'y':2,'z':3},
                  {'tick':22,'user_steamid':'7','x':float('nan'),'y':2,'z':3},
                  {'tick':101,'user_steamid':'7','x':1,'y':2,'z':3}]
            parser=Mock();parser.parse_events.return_value=[('bullet_impact',SimpleNamespace(to_dict=lambda _:rows))]
            meta={'sha256':'demo','parser':{'version':'fixture'},'players':[{'id':'7'}],'info':{'ticks':100}}
            result=shot_events.prepare_shots(parser,meta,Path(directory),lambda *args:None)
            self.assertEqual(result['impacts'],[{'tick':20,'player':0,'position':[1.,2.,3.]}])
            self.assertEqual(shot_events.prepare_shots(parser,meta,Path(directory),lambda *args:None),result)
            parser.parse_events.assert_called_once()

    def test_missing_network_impacts_remain_empty(self):
        with tempfile.TemporaryDirectory(dir=self.base) as directory:
            parser=Mock();parser.parse_events.return_value=[]
            meta={'sha256':'demo','parser':{},'players':[],'info':{'ticks':100}}
            result=shot_events.prepare_shots(parser,meta,Path(directory),lambda *args:None)
            self.assertEqual(result['impacts'],[])

    def test_damage_groups_invalid_fields_and_no_invented_impacts(self):
        with tempfile.TemporaryDirectory(dir=self.base) as directory:
            good={'tick':20,'user_steamid':'7','attacker_steamid':'8','user_X':1,'user_Y':2,'user_Z':3,'hitgroup':'head','dmg_health':40}
            rows=[good,dict(good,tick=None),dict(good,user_X=None),dict(good,dmg_health=float('nan')),dict(good,user_Z=1e8)]
            parser=Mock();parser.parse_events.return_value=[('player_hurt',SimpleNamespace(to_dict=lambda _:rows))]
            meta={'sha256':'demo','parser':{},'players':[{'id':'7'},{'id':'8'}],'info':{'ticks':100}}
            result=shot_events.prepare_shots(parser,meta,Path(directory),lambda *args:None)
            self.assertEqual(result['impacts'],[])
            self.assertEqual(result['damage'],[{'tick':20,'victim':0,'attacker':1,'position':[1.,2.,3.],'hitgroup':1,'amount':40}])

if __name__=='__main__':unittest.main()
