import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from fantasy_agent.automation.automation_store import utc
from fantasy_agent.notifications.team_notifications import Notices


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'config.json').write_text('{"username":"owner"}')
        (self.root / '.env').write_text('SLEEPER_LEAGUE_ID=123\nSLEEPER_USER_ID=u\n')
        self.now = 1800000000
        self.n = Notices(self.root, clock=lambda: self.now)
        self.n.enable()
        self.game = {'id': '2027_01_A_B', 'home': 'B', 'away': 'A', 'week': 1, 'season': 2027,
                     'kickoff': self.now + 1700, 'roster_id': 1, 'players': {'1': 'Player One', '2': 'Player Two'}}
        with self.n.db() as db:
            db.execute('INSERT INTO games VALUES (?,?)', (self.game['id'], json.dumps(self.game)))
        self.roster = {'owner_id': 'u', 'roster_id': 1, 'players': ['1', '2'], 'starters': ['1']}
        self.match = {'roster_id': 1, 'starters': ['1'], 'players_points': {'1': 12.5, '2': 25}}
        self.client = Mock()
        self.client.send.return_value = {'state': 'queued', 'network_attempts': 1}

    def provider(self, endpoint, **kwargs):
        if endpoint.endswith('/rosters'):
            return [self.roster]
        if '/matchups/' in endpoint:
            return [self.match]
        return {'1': {'full_name': 'Player One', 'team': 'A'}, '2': {'full_name': 'Player Two', 'team': 'B'}}

    def test_pregame_uses_current_roster_and_restart_does_not_duplicate(self):
        with patch('fantasy_agent.notifications.team_notifications.get_sleeper', side_effect=self.provider), patch('fantasy_agent.notifications.team_notifications.get_pushover', return_value=self.client):
            self.n.tick()
            Notices(self.root, clock=lambda: self.now).tick()
        self.client.send.assert_called_once()
        message = self.client.send.call_args.args[1]
        self.assertIn('Starting: Player One', message)
        self.assertIn('Bench: Player Two', message)

    def test_unknown_delivery_is_not_blindly_replayed(self):
        self.n.enqueue('change', 'Changed lineup.')
        self.client.send.return_value = {'state': 'unknown'}
        with patch('fantasy_agent.notifications.team_notifications.get_pushover', return_value=self.client):
            self.n.flush()
            self.n.flush()
        self.client.send.assert_called_once()
        self.assertEqual(self.n.status()['delivery_attention'][0]['state'], 'unknown')

    def test_cooldown_keeps_pending_for_next_wake(self):
        self.n.enqueue('change', 'Changed lineup.')
        self.client.send.side_effect = [ValueError('Notification cooldown is active'), {'state': 'queued'}]
        with patch('fantasy_agent.notifications.team_notifications.get_pushover', return_value=self.client):
            self.n.flush()
            self.assertEqual(self.n.status()['notice_counts'], {'pending': 1})
            self.n.flush()
        self.assertEqual(self.n.status()['notice_counts'], {'queued': 1})

    def test_elapsed_time_only_requests_final_check(self):
        self.now += 12000
        with patch('fantasy_agent.notifications.team_notifications.get_sleeper') as api, patch('fantasy_agent.notifications.team_notifications.get_pushover') as push:
            result = self.n.tick()
        self.assertEqual(len(result['final_checks']), 1)
        api.assert_not_called()
        push.assert_not_called()

    def test_final_requires_fresh_explicit_evidence_and_counts_only_starters(self):
        self.now += 12000
        proof = {'game_id': self.game['id'], 'home': 'B', 'away': 'A', 'home_score': 21, 'away_score': 14,
                 'status': 'Q4', 'observed_at': utc(self.now), 'source_url': 'https://example.test/game'}
        path = self.root / 'final.json'
        path.write_text(json.dumps(proof))
        with self.assertRaises(ValueError):
            self.n.final(path)
        proof['status'] = 'Final'
        proof['observed_at'] = utc(self.now - 301)
        path.write_text(json.dumps(proof))
        with self.assertRaises(ValueError):
            self.n.final(path)
        proof['observed_at'] = utc(self.now)
        path.write_text(json.dumps(proof))
        with patch('fantasy_agent.notifications.team_notifications.get_sleeper', side_effect=self.provider), patch('fantasy_agent.notifications.team_notifications.get_pushover', return_value=self.client):
            self.n.final(path)
            self.n.final(path)
        self.client.send.assert_called_once()
        self.assertIn('12.5 pts', self.client.send.call_args.args[1])

    def test_confirmed_change_survives_restart_and_is_deduplicated(self):
        from fantasy_agent.execution.lineup_execution import Execution
        engine = Execution(self.root, clock=lambda: self.now)
        with engine.db() as db:
            db.execute('INSERT INTO actions VALUES (?,?,?,?)', ('a', 'e', 'confirmed', json.dumps({'incoming': '1', 'outgoing': '2'})))
            engine.event(db, 'reconciled', {'action_id': 'a', 'outcome': 'confirmed'})
        self.n.capture_changes()
        with patch.object(Notices, 'enqueue', side_effect=AssertionError('Old event was processed again')):
            Notices(self.root, clock=lambda: self.now).capture_changes()
        self.assertEqual(self.n.status()['notice_counts'], {'pending': 1})

    def test_wrong_account_is_blocked(self):
        self.roster['owner_id'] = 'other'
        with patch('fantasy_agent.notifications.team_notifications.get_sleeper', side_effect=self.provider), patch('fantasy_agent.notifications.team_notifications.get_pushover') as push:
            with self.assertRaises(ValueError):
                self.n.tick()
        push.assert_not_called()
