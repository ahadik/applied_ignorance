import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from fantasy_agent.drafting.controller import assess, build, now, rank, validate, refresh, read, apply_reviewed_choice
from fantasy_agent.core.storage import save_atomic


class ControllerTests(unittest.TestCase):
    def test_reviewed_specialist_preserves_legality_and_reason(self):
        state = {'draft_id':'123','our_turn':True,'next_pick':10,'drafted_ids':[],
                 'remaining_slots':4,'needs':{'DEF':1,'K':1}}
        choice = {'draft_id':'123','pick_no':10,'player_id':'PIT','reason':'Reviewed timing'}
        candidates = {'players':[{'player_id':'WR1','position':'WR','priority':1},
                                {'player_id':'PIT','position':'DEF','priority':2}]}
        apply_reviewed_choice(state,candidates,choice)
        self.assertEqual(candidates['players'][0]['player_id'],'PIT')
        self.assertNotIn('score',candidates['players'][0]['rationale'])
        self.assertEqual(candidates['players'][0]['rationale']['reason'],'Reviewed timing')
        for changes in ({'drafted_ids':['PIT']},{'remaining_slots':5},
                        {'needs':{'DEF':0}},{'our_turn':False},{'next_pick':11}):
            with self.assertRaises(ValueError):
                apply_reviewed_choice(dict(state,**changes),candidates,choice)

    def setUp(self):
        self.draft = {'draft_id': '123', 'type': 'snake', 'status': 'drafting',
                      'draft_order': {'u': 1}, 'settings': {'teams': 2, 'rounds': 3,
                      'slots_qb': 1, 'slots_rb': 1, 'slots_flex': 1}}
        self.state = build(self.draft, [], 'u')
        self.candidates = {'draft_id': '123', 'observed_at': now(), 'source': 'test fixture',
                           'players': [{'player_id': 'a', 'position': 'RB', 'priority': 1},
                                       {'player_id': 'b', 'position': 'QB', 'priority': 2}]}
        self.ui = {'draft_id': '123', 'observed_at': now(), 'auto_pick': False,
                   'last_pick': 0, 'queue': ['a', 'b']}

    def test_ready_and_pending_block(self):
        self.assertTrue(assess(self.state, self.ui, self.candidates)['ready'])
        self.assertFalse(assess(self.state, self.ui, self.candidates, {'player_id': 'a'})['ready'])

    def test_timeout_auto_pick_and_empty_queue_block(self):
        self.ui.update(auto_pick=True, queue=[])
        result = assess(self.state, self.ui, self.candidates)
        self.assertFalse(result['ready'])
        self.assertEqual(len(result['blockers']), 2)

    def test_stale_wrong_room_and_board_race(self):
        for update in ({'observed_at': (datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat()},
                       {'draft_id': '456'}, {'last_pick': 1}):
            self.assertFalse(assess(self.state, dict(self.ui, **update), self.candidates)['ready'])

    def test_unavailable_removed_and_last_slot_reserved(self):
        self.state.update(drafted_ids=['a'], remaining_slots=1, needs={'QB': 1, 'RB': 0, 'FLEX': 0})
        self.assertEqual([p['player_id'] for p in rank(self.state, self.candidates)], ['b'])

    def test_mock_autopick_ownership_and_snake(self):
        picks = [{'draft_id': '123', 'pick_no': 1, 'draft_slot': 1, 'player_id': 'a',
                  'picked_by': '', 'roster_id': None, 'metadata': {'position': 'RB'}}]
        state = build(self.draft, picks, 'u')
        self.assertEqual(state['roster'][0]['player_id'], 'a')
        self.assertEqual(state['next_pick'], 4)
        self.assertFalse(state['our_turn'])
        self.assertEqual(state['needs'], {'QB': 1, 'RB': 0, 'WR': 0, 'TE': 0, 'K': 0, 'DEF': 0, 'FLEX': 1})

    def test_invalid_pick_sequences_rejected(self):
        with self.assertRaises(ValueError):
            validate(self.draft, [{'pick_no': 2}], '123')

    def test_stale_candidates_rejected(self):
        self.candidates['observed_at'] = '2020-01-01T00:00:00+00:00'
        with self.assertRaises(ValueError):
            rank(self.state, self.candidates)

    def test_submission_reconciles_match_and_preserves_mismatch(self):
        pick = {'draft_id': '123', 'pick_no': 1, 'draft_slot': 1, 'player_id': 'a',
                'roster_id': None, 'metadata': {'position': 'RB'}}
        for expected, matched in [('a', True), ('b', False)]:
            with tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                save_atomic(folder / 'pending.json', {'pick_no': 1, 'player_id': expected})
                with patch('fantasy_agent.drafting.draft_data.get_sleeper', side_effect=[self.draft, [], [pick]]):
                    refresh(folder, '123', 'u')
                self.assertEqual(read(folder / 'last_submission.json')['matched'], matched)
                self.assertEqual(read(folder / 'pending.json') is None, matched)

    def test_bad_refresh_preserves_last_good_state(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            save_atomic(folder / 'state.json', self.state)
            with patch('fantasy_agent.drafting.draft_data.get_sleeper', side_effect=[self.draft, [], [{'pick_no': 2}]]):
                with self.assertRaises(ValueError):
                    refresh(folder, '123', 'u')
            self.assertEqual(read(folder / 'state.json'), self.state)


if __name__ == '__main__':
    unittest.main()
