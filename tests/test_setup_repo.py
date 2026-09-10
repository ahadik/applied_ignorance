import unittest
from unittest.mock import patch

import setup_repo


class SetupRepoTests(unittest.TestCase):
    @patch('setup_repo.collect')
    def test_explicit_season_and_normal_cache_policy(self, collect):
        collect.return_value = {'complete': True}
        self.assertEqual(setup_repo.main(['--season', '2027']), 0)
        collect.assert_called_once_with(2027, [2025, 2026])

    @patch('setup_repo.collect')
    def test_incomplete_collection_is_failure(self, collect):
        collect.return_value = {'complete': False}
        self.assertEqual(setup_repo.main([]), 1)
