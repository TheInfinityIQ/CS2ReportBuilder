"""Check evidence identity and shared-event accounting at the handoff boundary."""
import copy
import gzip
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from intake import observed_sequence, prepare, sha


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.readiness = self.root / 'readiness.json'
        self.session = self.root / 'session.zip'
        self.manifest = dict(target=dict(steamid='76561198062530225'),
                             selection_sha256='selection',
                             source_membership_hashes={'source': {'data.csv': {'sha256': 'content'}}},
                             artifacts={}, counts=dict(rounds=1, q1_eligible=0, q2_episodes=0,
                                                       q3_attributable_detonations_all=2))
        frozen = dict(player=self.manifest['target'],
                      games=[dict(source='source', game_id='game', archive_path='analysis/0001')],
                      files={'evidence/analysis.json': {'sha256': 'selection'},
                             'analysis/0001/data.csv': {'sha256': 'content'}})
        with zipfile.ZipFile(self.session, 'w') as archive:
            archive.writestr('manifest.json', json.dumps(frozen))
            archive.writestr('session.json', json.dumps(dict(id='session')))
        self.rounds = [dict(round_id='game:1', game='game', source='source', map='map',
                            side='T', team_round_win=True, q1_postplant_advantage=None,
                            q2_last_alive=None, death_sequence=[], objective_events=[],
                            tickrate=64, end_tick=200)]
        flash = dict(flash_id='flash:1', source='source', game='game', round_id='game:1',
                     within_eligible_live_round=True, detonation={'source': {'tick': 100}},
                     blind_effects=[dict(source=dict(csv_data_row=4), user_steamid='opponent')],
                     temporal_teammate_overlaps=[dict(blind_csv_data_row=4,
                        same_tick_order_unresolved=True,
                        event=dict(user_steamid='opponent', source=dict(file='hurt.csv', csv_data_row=9)))])
        self.flashes = [flash, copy.deepcopy(flash)]
        self.flashes[1]['flash_id'] = 'flash:2'

    def write(self):
        for name, rows in [('round_facts.jsonl.gz', self.rounds),
                           ('flash_facts.jsonl.gz', self.flashes), ('blind_facts.jsonl.gz', [])]:
            path = self.root / name
            with gzip.open(path, 'wt') as stream:
                for row in rows:
                    stream.write(json.dumps(row) + '\n')
            self.manifest['artifacts'][name] = dict(rows=len(rows), bytes=path.stat().st_size,
                                                    sha256=sha(path))
        self.readiness.write_text(json.dumps(self.manifest))

    def test_shared_event_is_not_counted_as_two_contacts(self):
        self.write()
        result = prepare(self.readiness, self.session)
        self.assertEqual(result['overlap_accounting']['link_count'], 2)
        self.assertEqual(result['overlap_accounting']['distinct_recorded_contact_events'], 1)
        self.assertEqual(result['overlap_accounting']['same_tick_order_unresolved_links'], 2)

    def test_different_opponent_cannot_support_link(self):
        self.flashes[0]['temporal_teammate_overlaps'][0]['event']['user_steamid'] = 'someone_else'
        self.write()
        with self.assertRaisesRegex(ValueError, 'opponent identity'):
            prepare(self.readiness, self.session)

    def test_same_round_label_cannot_hide_another_game(self):
        self.flashes[0]['game'] = 'other_game'
        self.write()
        with self.assertRaisesRegex(ValueError, 'source/game identity'):
            prepare(self.readiness, self.session)

    def test_different_file_rows_are_distinct_record_types(self):
        self.flashes[1]['temporal_teammate_overlaps'][0]['event']['source']['file'] = 'death.csv'
        self.write()
        result = prepare(self.readiness, self.session)
        self.assertEqual(result['overlap_accounting']['distinct_recorded_contact_events'], 2)

    def test_sequence_uses_entry_time_and_preserves_order_uncertainty(self):
        row = dict(round_id='game:1', tickrate=64, end_tick=300,
                   death_sequence=[dict(tick=164, attacker='a', victim='b')],
                   objective_events=[dict(tick='164', user_steamid='a',
                     source=dict(file='events/bomb_planted.csv.gz', csv_data_row=7)),
                     dict(tick='301', source=dict(file='events/bomb_defused.csv.gz'))])
        events = observed_sequence(row,100)
        self.assertEqual(len(events),2)
        self.assertTrue(all(e['seconds_after_entry']==1 for e in events))
        self.assertTrue(all(e['same_tick_order_unresolved'] for e in events))
        self.assertEqual(events[0]['anchor']['death_sequence_index'],0)
        self.assertEqual(events[1]['anchor']['csv_data_row'],7)


if __name__ == '__main__':
    unittest.main()
