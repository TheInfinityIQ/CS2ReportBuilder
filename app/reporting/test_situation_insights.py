import copy
import unittest
from situation_insights import render


class SituationTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = dict(games=[dict(rounds=[dict(id='a:1', start=0, end=200,
                                                       map='de_inferno', round=1),dict(id='b:1',start=0,end=200,map='de_dust2',round=1)])])
        self.copy = dict(situation_insights=[dict(id='lesson',kind='positive',label='Keep',
            heading='<script>',observation='Observed',meaning='Bounded',cue='Try',limit='Unknown',
            references=[dict(round_id='a:1',anchor_tick=100),dict(round_id='b:1',anchor_tick=100)],
            publication_scope='cross_map_theme',
            review_status='approved_bounded_lesson',review_response='review')])

    def test_copy_and_embedded_evidence_share_canonical_record(self):
        positive, development, records = render(self.snapshot,self.copy)
        self.assertIn('&lt;script&gt;',positive)
        self.assertEqual(development,'')
        self.assertIs(records[0]['references'][0]['record'],self.snapshot['games'][0]['rounds'][0])

    def test_unknown_round_and_invalid_tick_are_rejected(self):
        for ref in [dict(round_id='other',anchor_tick=100),dict(round_id='a:1',anchor_tick=201)]:
            c=copy.deepcopy(self.copy);c['situation_insights'][0]['references']=[ref]
            with self.assertRaises(ValueError):render(self.snapshot,c)

    def test_unreviewed_copy_cannot_publish(self):
        self.copy['situation_insights'][0]['review_status']='unreviewed'
        with self.assertRaisesRegex(ValueError,'approval'):render(self.snapshot,self.copy)

    def test_single_map_approval_is_not_a_cross_map_theme(self):
        self.copy['situation_insights'][0]['references']=[dict(round_id='a:1',anchor_tick=100)]
        with self.assertRaisesRegex(ValueError,'different maps'):render(self.snapshot,self.copy)


if __name__=='__main__':unittest.main()
