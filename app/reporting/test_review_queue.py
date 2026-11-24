import copy
import unittest

from review_queue import build


def example(identity, win, game='game', question='postplant'):
    return dict(id=identity, round_id=identity, game=game, map='map', side='T',
                question=question, state='eligible_interpretation_unresolved',
                team_round_win=win, context=dict(plant_site_id_recorded='42',
                    state_at_plant=dict(own=3, enemy=2), entry_enemy_count=2,
                    bomb_planted_at_entry=True, interpretation_unresolved=['equipment unknown']))


class QueueTests(unittest.TestCase):
    def test_raw_site_id_does_not_match_between_games(self):
        result = build(dict(session_id='session', readiness_sha256='receipt',
                            candidates=[example('a', True), example('b', False, game='other')]))
        self.assertEqual(result['comparisons'], [])

    def test_last_alive_objective_phase_must_match(self):
        a = example('a', True, question='lastalive')
        b = example('b', False, question='lastalive')
        b['context']['bomb_planted_at_entry'] = False
        result = build(dict(session_id='session', readiness_sha256='receipt', candidates=[a,b]))
        self.assertEqual(result['comparisons'], [])

    def test_matched_outcomes_stay_unreviewed_and_do_not_mutate_evidence(self):
        index = dict(session_id='session', readiness_sha256='receipt',
                     candidates=[example('a', True), example('b', False)])
        original = copy.deepcopy(index)
        result = build(index)
        card = result['comparisons'][0]
        self.assertEqual(card['status'], 'unreviewed')
        self.assertIsNone(card['review']['supported_positive_example'])
        self.assertIsNone(card['review']['practice_cue'])
        self.assertEqual(index, original)

    def test_same_outcome_is_not_filtered_out(self):
        index = dict(session_id='session', readiness_sha256='receipt',
                     candidates=[example('a', True), example('b', True), example('c', False)])
        card = build(index)['comparisons'][0]
        self.assertEqual(card['candidate_ids'], ['a', 'b'])
        self.assertEqual(card['team_round_outcomes'], [True, True])


if __name__ == '__main__':
    unittest.main()
