import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fantasy_agent.core.project_config import load_config, check_user


class ConfigTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'config.json').write_text(json.dumps({'league_id': 'legacy', 'username': 'owner'}))
        self.env = patch.dict(os.environ, {'SLEEPER_USER_ID': 'owner'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_missing_or_blank_never_uses_json_default(self):
        for value in (None, '', 'SLEEPER_LEAGUE_ID=\n', 'SLEEPER_LEAGUE_ID=""\n'):
            if value is not None:
                (self.root / '.env').write_text(value)
            with self.assertRaisesRegex(ValueError, 'Set SLEEPER_LEAGUE_ID'):
                load_config(self.root)

    def test_env_file_ignores_credentials_and_preserves_other_settings(self):
        (self.root / '.env').write_text('FANTASYPROS_API_KEY=secret\nexport SLEEPER_LEAGUE_ID="123"\n')
        self.assertEqual(load_config(self.root), {'league_id': '123', 'user_id': 'owner', 'username': 'owner'})

    def test_process_environment_takes_precedence_including_invalid_empty(self):
        (self.root / '.env').write_text('SLEEPER_LEAGUE_ID=123\n')
        with patch.dict(os.environ, {'SLEEPER_LEAGUE_ID': '456'}):
            self.assertEqual(load_config(self.root)['league_id'], '456')
        with patch.dict(os.environ, {'SLEEPER_LEAGUE_ID': ''}):
            with self.assertRaises(ValueError):
                load_config(self.root)

    def test_custom_config_reads_adjacent_env_without_parent_fallback(self):
        (self.root / '.env').write_text('SLEEPER_LEAGUE_ID=123\n')
        other = self.root / 'other'
        other.mkdir()
        (other / 'custom.json').write_text('{}')
        with self.assertRaises(ValueError):
            load_config(path=other / 'custom.json')
        (other / '.env').write_text('SLEEPER_LEAGUE_ID=456\n')
        self.assertEqual(load_config(path=other / 'custom.json')['league_id'], '456')

    def test_url_is_not_a_league_id_and_error_does_not_echo_input(self):
        (self.root / '.env').write_text('SLEEPER_LEAGUE_ID=https://example.com/private\n')
        with self.assertRaisesRegex(ValueError, 'not a URL') as error:
            load_config(self.root)
        self.assertNotIn('private', str(error.exception))

    def test_user_id_required_even_if_legacy_json_contains_one(self):
        (self.root / 'config.json').write_text('{"user_id":"legacy"}')
        (self.root / '.env').write_text('SLEEPER_LEAGUE_ID=123\n')
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'Set SLEEPER_USER_ID'):
                load_config(self.root)
        with patch.dict(os.environ, {'SLEEPER_USER_ID': ''}):
            with self.assertRaisesRegex(ValueError, 'Set SLEEPER_USER_ID'):
                load_config(self.root)

    def test_profile_id_must_match_even_when_username_matches(self):
        for user in (None, {}, {'user_id': 'different', 'username': 'owner'}):
            with self.assertRaises(ValueError):
                check_user({'user_id': 'expected', 'username': 'owner'}, user)
        check_user({'user_id': 'expected'}, {'user_id': 'expected'})
