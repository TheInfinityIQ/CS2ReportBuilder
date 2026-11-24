from unittest import TestCase

from replay_audio import pickup_sound, timeline


class Table:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, format):
        assert format == 'records'
        return self.rows


class ReplayAudioTests(TestCase):
    def test_pickup_routes_only_known_audible_items(self):
        self.assertEqual(pickup_sound({'item':'glock'}),'pickup_pistol')
        self.assertEqual(pickup_sound({'item':'smokegrenade'}),'pickup_grenade')
        self.assertIsNone(pickup_sound({'item':'glock','silent':True}))
        self.assertIsNone(pickup_sound({'item':'unrecognized'}))

    def test_cues_anchor_bomb_outcome_to_plant_and_ignore_stale_positions(self):
        class Parser:
            def parse_events(self, names, player):
                yield 'bomb_exploded', Table([{'tick':60},{'tick':120}])
                yield 'round_start', Table([{'tick':10},{'tick':100}])
                yield 'bomb_planted', Table([{'tick':20,'user_X':10,'user_Y':20,'user_Z':30}])
                yield 'player_hurt', Table([{'tick':30,'user_X':float('nan'),'user_Y':20,'user_Z':30}])
        cues = timeline(Parser(), {'info':{'ticks':150,'tickrate':20}})
        self.assertEqual([(c['tick'],c['sound'],c['position']) for c in cues],
                         [(20,'plant',[10,20,30]),(40,'bomb_beep',[10,20,30]),(60,'explode',[10,20,30])])
