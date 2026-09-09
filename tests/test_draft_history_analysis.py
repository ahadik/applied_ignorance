from datetime import datetime, timezone
import unittest
from draft_history_analysis import (current_depth, historical_features, identity_maps,
                                    metric_summary, regular_rows)


class HistoryTests(unittest.TestCase):
    def test_missing_values_not_zero(self):
        value = metric_summary([{'targets': '2'}, {'targets': ''}], ['targets'])['targets']
        self.assertIsNone(value['total'])
        self.assertIsNone(value['per_recorded_game'])
        self.assertEqual(value['missing_records'], 1)

    def test_missing_ids_are_explicitly_quarantined(self):
        rows = [{'season': '2025', 'week': '18', 'season_type': 'REG', 'player_id': '', 'game_id': 'g'},
                {'season': '2025', 'week': '18', 'season_type': 'REG', 'player_id': 'p', 'game_id': 'g'}]
        excluded = []
        valid = regular_rows(rows, 2025, 'season_type', 'player_id', excluded)
        self.assertEqual(len(valid), 1)
        self.assertEqual(excluded[0]['reason'], 'missing_player_or_game_id')

    def test_postseason_excluded_and_duplicates_rejected(self):
        rows = [{'season': '2025', 'week': '18', 'season_type': 'REG', 'player_id': 'p', 'game_id': 'g'},
                {'season': '2025', 'week': '19', 'season_type': 'POST', 'player_id': 'p', 'game_id': 'h'}]
        self.assertEqual(len(regular_rows(rows, 2025, 'season_type', 'player_id')), 1)
        with self.assertRaises(ValueError):
            regular_rows(rows + [rows[0]], 2025, 'season_type', 'player_id')

    def test_late_usage_is_league_weeks_not_last_appearances(self):
        stats = [{'season': '2025', 'week': str(week), 'season_type': 'REG', 'player_id': pid,
                  'game_id': 'game'+str(week), 'position': 'RB', 'team': 'ARI', 'carries': '10'}
                 for pid, week in [('p', 1), ('p', 2), ('p', 3), ('p', 4), ('other', 18)]]
        snaps = [{'season': '2025', 'week': '18', 'game_type': 'REG', 'pfr_player_id': 'P01',
                  'game_id': 'g', 'position': 'RB', 'team': 'ARI', 'offense_snaps': '30', 'offense_pct': '0.5'}]
        identities, indices = identity_maps([{'gsis_id': 'p', 'pfr_id': 'P01'}])
        players, _, _ = historical_features({2025: stats}, {2025: snaps}, identities, indices)
        self.assertEqual(players['p']['seasons']['2025']['late_stats_recorded_games'], 0)
        self.assertIsNone(players['p']['seasons']['2025']['late_metrics']['carries']['total'])

    def test_latest_team_snapshot_does_not_resurrect_removed_players(self):
        def row(pid, dt, rank):
            return {'dt': dt, 'team': 'ARI', 'gsis_id': pid, 'espn_id': '', 'player_name': pid,
                    'pos_abb': 'RB', 'pos_rank': str(rank), 'pos_slot': '1', 'pos_grp': 'Offense'}
        identities, indices = identity_maps([{'gsis_id': 'old'}, {'gsis_id': 'new'}])
        rows = [row('old', '2026-09-07T00:00:00Z', 1), row('new', '2026-09-08T07:00:00Z', 1)]
        roles, _, _ = current_depth(rows, identities, indices, datetime(2026, 9, 8, 12, tzinfo=timezone.utc))
        self.assertEqual([r['gsis_id'] for r in roles], ['new'])
        self.assertTrue(roles[0]['usable'])
        roles, _, quality = current_depth(rows, identities, indices, datetime(2026, 9, 10, tzinfo=timezone.utc))
        self.assertFalse(roles[0]['usable'])
        self.assertEqual(quality['stale_teams'], ['ARI'])

    def test_ambiguous_ids_not_silently_matched(self):
        identities, indices = identity_maps([{'gsis_id': 'a', 'espn_id': '1'}, {'gsis_id': 'b', 'espn_id': '1'}])
        rows = [{'dt': '2026-09-08T07:00:00Z', 'team': 'ARI', 'gsis_id': '', 'espn_id': '1',
                 'player_name': 'X', 'pos_abb': 'RB', 'pos_rank': '1', 'pos_slot': '1', 'pos_grp': 'Offense'}]
        roles, unmatched, _ = current_depth(rows, identities, indices, datetime(2026, 9, 8, 12, tzinfo=timezone.utc))
        self.assertEqual(roles, [])
        self.assertEqual(len(unmatched), 1)


if __name__ == '__main__':
    unittest.main()
