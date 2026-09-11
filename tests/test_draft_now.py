"""Offline manual fallback checks with synthetic Sleeper responses."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fantasy_agent.drafting.draft_now import main, recommend_now, render
from tests.test_draft_strategy import fixture


class DraftNowTests(unittest.TestCase):
    def setUp(self):
        self.board, self.policy = fixture()
        self.draft = {'draft_id': '456', 'league_id': '123', 'type': 'snake',
                      'status': 'drafting', 'draft_order': {'u': 1},
                      'settings': {'teams': 2, 'rounds': 8, 'slots_qb': 1,
                                   'slots_rb': 1, 'slots_wr': 1, 'slots_te': 1,
                                   'slots_flex': 1, 'slots_k': 1, 'slots_def': 1,
                                   'slots_bn': 1}}

    def run_advice(self, picks=None, *, mock=False, draft_id='456'):
        with tempfile.TemporaryDirectory() as directory:
            board = Path(directory) / 'board.json'
            board.write_text(json.dumps(self.board))
            with patch('fantasy_agent.drafting.draft_data.get_sleeper', side_effect=[self.draft, [], picks or []]) as provider:
                with patch('fantasy_agent.drafting.draft_now.load_policy', return_value=self.policy):
                    result = recommend_now(board, draft_id, 'u', mock=mock)
            self.assertEqual([call.args[0] for call in provider.call_args_list],
                             [f'draft/{draft_id}', f'draft/{draft_id}/traded_picks', f'draft/{draft_id}/picks'])
            self.assertTrue(all(call.kwargs == {'retries': 0} for call in provider.call_args_list))
            self.assertEqual(list(Path(directory).iterdir()), [board])
            return result

    def test_fresh_on_turn_advice_without_browser(self):
        advice = self.run_advice()
        self.assertEqual(len(advice['players']), 3)
        self.assertTrue(render(advice).startswith('DRAFT NOW:'))

    def test_new_pick_changes_turn_and_removes_selected_player(self):
        first = self.run_advice()['players'][0]
        pick = {'draft_id': '456', 'pick_no': 1, 'draft_slot': 1,
                'player_id': first['player_id'], 'metadata': {'position': first['position']}}
        advice = self.run_advice([pick])
        self.assertFalse(advice['state']['our_turn'])
        self.assertNotIn(first['player_id'], [p['player_id'] for p in advice['players']])
        self.assertTrue(render(advice).startswith('PREVIEW ONLY'))

    def test_pre_draft_and_complete(self):
        self.draft['status'] = 'pre_draft'
        self.assertIn('NOT YOUR TURN', render(self.run_advice()))
        self.draft['status'] = 'complete'
        self.assertTrue(self.run_advice()['finished'])

    def test_expired_inputs_and_wrong_identity_fail_closed(self):
        self.board['sources'][0]['fetched_at'] = '2000-01-01T00:00:00+00:00'
        with self.assertRaises(ValueError):
            self.run_advice()
        self.draft['league_id'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self.run_advice()

    def test_slow_collection_refuses_recommendation(self):
        with patch('fantasy_agent.drafting.draft_now.monotonic', side_effect=[0, 21]):
            with self.assertRaisesRegex(ValueError, '20 seconds'):
                self.run_advice()

    def test_cli_failure_never_prints_old_name(self):
        out, err = StringIO(), StringIO()
        with patch('fantasy_agent.drafting.draft_now.recommend_now', side_effect=OSError('Sleeper unavailable')):
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main([]), 1)
        self.assertEqual(out.getvalue(), '')
        self.assertIn('NO RECOMMENDATION', err.getvalue())

    def test_name_only_requires_our_turn(self):
        advice = self.run_advice()
        for our_turn, expected_code in [(True, 0), (False, 2)]:
            advice['state']['our_turn'] = our_turn
            out, err = StringIO(), StringIO()
            with patch('fantasy_agent.drafting.draft_now.recommend_now', return_value=advice):
                with redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(main(['--name-only']), expected_code)
            self.assertEqual(out.getvalue(), advice['players'][0]['name']+'\n' if our_turn else '')

    def test_explicit_mock_uses_actual_mock_state(self):
        self.draft.update(draft_id='789', league_id=None)
        advice = self.run_advice(mock=True, draft_id='789')
        self.assertEqual(advice['state']['draft_id'], '789')
        self.assertTrue(advice['state']['our_turn'])
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self.run_advice(draft_id='789')

    def test_mock_rejects_real_league_and_wrong_format(self):
        with self.assertRaisesRegex(ValueError, 'league-less'):
            self.run_advice(mock=True)
        self.draft['league_id'] = None
        self.draft['settings']['slots_flex'] = 2
        with self.assertRaises(ValueError):
            self.run_advice(mock=True)

    def test_cli_routes_mock_id_and_displays_target(self):
        advice = self.run_advice()
        out, err = StringIO(), StringIO()
        with patch('fantasy_agent.drafting.draft_now.recommend_now', return_value=advice) as recommend:
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(['--mock', '789']), 0)
            recommend.assert_called_once_with(draft_id='789', mock=True)
        self.assertIn('MOCK https://sleeper.com/draft/nfl/789', err.getvalue())


if __name__ == '__main__':
    unittest.main()
