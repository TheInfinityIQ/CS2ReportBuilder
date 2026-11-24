"""Ownership and exact-identity regressions for the memory-saving path."""
import unittest
import pandas as pd
from pandas.testing import assert_frame_equal
import extract_demos_v8 as e
from analysis_resources import configure_native_threads


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.old = e.ROSTER
        e.ROSTER = [76561198062530225, 76561198149119669]
        self.addCleanup(setattr, e, 'ROSTER', self.old)

    def test_owned_and_borrowed_filter_keep_identical_values_without_mutating_borrower(self):
        for ids in [[str(x) for x in e.ROSTER], [str(e.ROSTER[0]), None, '0', str(e.ROSTER[1])]]:
            with self.subTest(ids=ids):
                source = pd.DataFrame({'steamid': ids, 'X': [1.23456789012345] * len(ids)})
                original = source.copy(deep=True)
                borrowed = e.filter_competitive_rows(source)
                owned = e.filter_competitive_rows(source.copy(), owned=True)
                assert_frame_equal(borrowed, owned)
                assert_frame_equal(source, original)
                self.assertEqual(borrowed.steamid.tolist(), e.ROSTER)

    def test_exact_ids_nullable_rows_and_duplicate_first_observation(self):
        for dtype in ['Int64', 'object']:
            with self.subTest(dtype=dtype):
                rows = pd.DataFrame({'steamid': pd.Series([e.ROSTER[0], None, e.ROSTER[1], e.ROSTER[0]], dtype=dtype),
                                     'value': [10, 99, 20, 30]})
                self.assertEqual(e._row_for_sid(rows, e.ROSTER[0])['value'], 10)
                self.assertEqual(e._row_for_sid(rows, e.ROSTER[1])['value'], 20)
                self.assertIsNone(e._row_for_sid(rows, 76561198000000000))
                if dtype == 'Int64':
                    self.assertIsNone(e._row_for_sid(rows, 76561198149119668))

    def test_event_cleanup_does_not_modify_source_frames(self):
        events = {'round_end': pd.DataFrame({'tick': [3, 3, 4], 'winner': ['CT', 'CT', None]}),
                  'player_death': pd.DataFrame({'tick': [1], 'weapon': ['glock']})}
        original = {k: v.copy(deep=True) for k, v in events.items()}
        cleaned = e.sanitize_clipped_events(events, {})
        self.assertEqual(cleaned['round_end'].tick.tolist(), [3])
        for name in events:
            assert_frame_equal(events[name], original[name])

    def test_pool_defaults_fit_cpu_count_and_preserve_explicit_overrides(self):
        small = configure_native_threads({}, cpus=2)
        self.assertEqual(small['RAYON_NUM_THREADS'], '2')
        self.assertEqual(small['POLARS_MAX_THREADS'], '2')
        normal = configure_native_threads({}, cpus=24)
        self.assertEqual(normal['RAYON_NUM_THREADS'], '8')
        self.assertEqual(normal['POLARS_MAX_THREADS'], '4')
        self.assertEqual(normal['OPENBLAS_NUM_THREADS'], '1')
        custom = configure_native_threads({'RAYON_NUM_THREADS': '3', 'OPENBLAS_NUM_THREADS': '6'}, cpus=24)
        self.assertEqual(custom['RAYON_NUM_THREADS'], '3')
        self.assertEqual(custom['OPENBLAS_NUM_THREADS'], '6')


if __name__ == '__main__':
    unittest.main()
