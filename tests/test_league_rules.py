import unittest
from unittest.mock import patch

from fantasy_agent.weekly.league_rules import collect


class LeagueRulesTests(unittest.TestCase):
    def test_raw_codes_and_metadata_preserved(self):
        data = [dict(league_id='1', sport='nfl', settings={'waiver_type': 0},
                     scoring_settings={'rec': 1}, roster_positions=['QB'], total_rosters=1),
                {'user_id': 'u'}, [{'roster_id': 1, 'owner_id': 'u',
                                     'settings': {'waiver_position': 3}}]]
        with patch('fantasy_agent.weekly.league_rules.get_sleeper', side_effect=[
                {'data': d, 'cache_hit': False, 'network_attempts': 1} for d in data]) as get:
            result = collect({'league_id': '1', 'username': 'me', 'user_id': 'u'})
        self.assertEqual(result['settings'], {'waiver_type': 0})
        self.assertEqual(result['our_roster_settings']['waiver_position'], 3)
        self.assertEqual(result['evidence']['league']['network_attempts'], 1)
        self.assertTrue(all(c.kwargs == {'with_metadata': True, 'retries': 0}
                            for c in get.call_args_list))

    def test_wrong_league_stops_collection(self):
        with patch('fantasy_agent.weekly.league_rules.get_sleeper', return_value={'data': {'league_id': 'wrong'}}) as get:
            with self.assertRaises(ValueError):
                collect({'league_id': '1', 'username': 'me', 'user_id': 'u'})
        self.assertEqual(get.call_count, 1)
