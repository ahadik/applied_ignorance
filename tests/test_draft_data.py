import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import call, patch

from draft import sync
from draft_data import read_draft_context, read_live_draft
from storage import save_atomic


class DraftDataTests(unittest.TestCase):
    def setUp(self):
        self.config = {'league_id': '123', 'username': 'user'}
        self.league = {'league_id': '123', 'draft_id': '456'}
        self.draft = {'draft_id': '456', 'league_id': '123'}

    def test_context_composes_shared_reads_and_preserves_snapshot_shape(self):
        with patch('draft_data.get_sleeper', side_effect=[self.league, self.draft,
                                                        {'user_id': 'u'}, [], []]) as get:
            result = read_draft_context(self.config)
        self.assertEqual(set(result), {'fetched_at', 'league', 'draft', 'user_id', 'picks', 'rosters'})
        self.assertEqual(result['user_id'], 'u')
        self.assertEqual(get.call_args_list, [call('league/123'), call('draft/456'),
                         call('user/user'), call('draft/456/picks'), call('league/123/rosters')])

    def test_wrong_draft_fails_before_downstream_reads(self):
        with patch('draft_data.get_sleeper', side_effect=[self.league, {'draft_id': '999'}]) as get:
            with self.assertRaisesRegex(ValueError, 'mismatched'):
                read_draft_context(self.config)
        self.assertEqual(get.call_count, 2)

    def test_failed_sync_preserves_existing_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'snapshot.json'
            save_atomic(destination, {'last_good': True})
            with patch('draft.SNAPSHOT', destination), patch('draft_data.get_sleeper',
                       side_effect=[self.league, self.draft, {'user_id': 'u'}, [], None]):
                with self.assertRaises(ValueError):
                    sync(self.config)
            self.assertEqual(json.loads(destination.read_text()), {'last_good': True})

    def test_live_board_requires_known_untraded_ownership(self):
        for trades in (None, {}, [{'roster_id': 2}]):
            with patch('draft_data.get_sleeper', side_effect=[self.draft, trades]) as get:
                with self.assertRaises(ValueError):
                    read_live_draft('456')
            self.assertEqual(get.call_count, 2)

    def test_live_board_disables_retries_on_all_reads(self):
        with patch('draft_data.get_sleeper', side_effect=[self.draft, [], []]) as get:
            self.assertEqual(read_live_draft('456'), (self.draft, []))
        self.assertEqual(get.call_args_list, [call('draft/456', retries=0),
                         call('draft/456/traded_picks', retries=0),
                         call('draft/456/picks', retries=0)])

    def test_successful_sync_writes_collected_context(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'snapshot.json'
            with patch('draft.SNAPSHOT', destination), patch('draft_data.get_sleeper',
                       side_effect=[self.league, self.draft, {'user_id': 'u'}, [], []]):
                result = sync(self.config)
            self.assertEqual(json.loads(destination.read_text()), result)


if __name__ == '__main__':
    unittest.main()
