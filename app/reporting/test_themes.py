import unittest
from themes import evidence


class ThemeTests(unittest.TestCase):
    def test_recurring_rounds_do_not_inflate_game_or_map_counts(self):
        def rnd(gap):
            return dict(opening='kill',tickrate=64,events=[dict(enemy=True,tick=100)],
                        death=None if gap is None else dict(tick=100+gap*64))
        snapshot=dict(games=[dict(sha='a',map='map_a',rounds=[rnd(1),rnd(4)]),
                             dict(sha='b',map='map_b',rounds=[rnd(None)])])
        result=evidence(snapshot)
        self.assertEqual(result['opening_maps'],2)
        self.assertEqual(result['opening_games'],2)
        self.assertEqual(result['fast_maps'],1)
        self.assertEqual(result['fast_games'],1)
        self.assertEqual(result['by_map']['map_a'],dict(openings=2,within10=2,within2=1))
        self.assertEqual(result['by_map']['map_b']['within10'],0)


if __name__=='__main__':unittest.main()
