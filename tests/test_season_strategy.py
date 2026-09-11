import copy
import unittest

from automation_store import InvalidContract
from season_strategy import roster_value, compare, chronological_evaluation


def pool_fixture():
    def player(sid, pos, points, unavailable=False, exact=True):
        return {'id': sid, 'positions': [pos], 'points': points, 'owned': False,
                'locked': False, 'unavailable': unavailable, 'availability_review': False,
                'game': {'kickoff': '2026-09-13T17:00:00Z'}, 'scoring': {'exact_league_total': exact}}
    players = {'a': player('a', 'QB', 20), 'b': player('b', 'QB', 15),
               'c': player('c', 'QB', 22), 'k': player('k', 'K', 10, exact=False)}
    return {'schema_version': 1, 'kind': 'roster_forecast_pool', 'created_at': '2026-09-11T12:00:00+00:00',
            'weeks': [{'week': 1, 'slots': ['QB'], 'players': players}]}


class SeasonTests(unittest.TestCase):
    def test_current_week_locked_starter_cannot_create_fictional_upgrade(self):
        pool = pool_fixture()
        pool['weeks'][0]['current_starters'] = ['a']
        pool['weeks'][0]['players']['a']['locked'] = True
        result = compare(pool, ['a', 'b'], ['c'], ['b'])
        self.assertEqual(result['modeled_gain'], 0)
        self.assertEqual(result['after']['weeks'][0]['lineup']['starters'], ['a'])
        self.assertEqual(compare(pool, ['a', 'b'], ['c'], ['a'])['status'], 'blocked')
    def test_full_roster_value_counts_bench_and_priority_cost(self):
        pool = pool_fixture()
        result = compare(pool, ['a', 'b'], ['c'], ['b'], priority_cost=1)
        self.assertAlmostEqual(result['modeled_gain'], 2.5)
        self.assertAlmostEqual(result['net_policy_value'], 1.5)
        self.assertEqual(result['status'], 'review_required')

    def test_missing_future_data_never_becomes_zero(self):
        pool = pool_fixture()
        second = copy.deepcopy(pool['weeks'][0])
        second['week'] = 2
        del second['players']['b']
        pool['weeks'].append(second)
        self.assertIsNone(roster_value(pool, ['a', 'b'])['value'])
        self.assertEqual(compare(pool, ['a', 'b'], ['c'], ['b'])['status'], 'blocked')

    def test_bye_coverage_and_specialist_missing_categories(self):
        pool = pool_fixture()
        pool['weeks'][0]['players']['a']['unavailable'] = True
        self.assertEqual(roster_value(pool, ['a'])['weeks'][0]['unfilled_slots'], ['QB'])
        self.assertFalse(compare(pool, ['a'], ['k'], ['a'])['specialist_streaming_eligible'])

    def test_chronological_evaluation_rejects_hindsight(self):
        record = {'predicted_at': '2026-09-13T16:00:00Z', 'kickoff': '2026-09-13T17:00:00Z',
                  'outcome_observed_at': '2026-09-14T01:00:00Z', 'source_observed_at': ['2026-09-13T15:00:00Z'],
                  'selected_actual_points': 20, 'baseline_actual_points': 18}
        self.assertEqual(chronological_evaluation([record])['paired_actual_difference'], 2)
        record['source_observed_at'] = ['2026-09-13T18:00:00Z']
        with self.assertRaises(InvalidContract):
            chronological_evaluation([record])
