import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pushover import Pushover, PushoverError


class PushoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'PUSHOVER_APP_TOKEN': 'a'*30, 'PUSHOVER_USER_KEY': 'b'*30})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.now = 1000
        self.calls = []
        def request(payload):
            self.calls.append(payload)
            return 200, {}, b'{"status":1,"request":"request-id"}'
        self.client = Pushover(self.root, request=request, clock=lambda: self.now, sleep=lambda n: None)

    def test_queued_is_not_phone_delivery_and_duplicate_is_suppressed(self):
        result = self.client.send('incident', 'Test')
        self.assertEqual(result['state'], 'queued')
        self.assertFalse(result['phone_delivery_confirmed'])
        self.assertTrue(self.client.send('incident', 'Test')['deduplicated'])
        self.assertEqual(len(self.calls), 1)
        with self.assertRaises(PushoverError):
            self.client.send('incident', 'Different')
        (self.root / 'confirmation.json').write_text('{"owner":"received on phone"}')
        self.client.confirm('incident', 'confirmation.json')
        self.assertTrue(self.client.status()['phone_delivery_confirmed'])

    def test_no_credentials_or_tokens_in_status_and_history(self):
        self.client.send('incident', 'Test')
        self.assertNotIn('a'*30, json.dumps(self.client.status()))
        self.assertNotIn(b'b'*30, self.client.path.read_bytes())
        with patch.dict(os.environ, {'PUSHOVER_APP_TOKEN': '', 'PUSHOVER_USER_KEY': ''}):
            self.assertFalse(self.client.status()['configured'])
            with self.assertRaises(PushoverError):
                self.client.send('other', 'Test')

    def test_transport_unknown_is_not_retried_after_restart(self):
        self.client.request = lambda payload: (_ for _ in ()).throw(PushoverError('private transport text'))
        result = self.client.send('incident', 'Test')
        self.assertEqual(result['state'], 'unknown')
        self.assertEqual(result['network_attempts'], 1)
        restarted = Pushover(self.root, request=lambda _: self.fail('Must not resend'))
        self.assertTrue(restarted.send('incident', 'Test')['deduplicated'])
        self.assertNotIn(b'private transport text', self.client.path.read_bytes())

    def test_explicit_server_rejection_has_one_bounded_retry(self):
        responses = iter([(500, {}, b'{"status":0}'), (200, {}, b'{"status":1}')])
        self.client.request = lambda _: next(responses)
        sleeps = []
        self.client.sleep = sleeps.append
        result = self.client.send('incident', 'Test')
        self.assertEqual(result['state'], 'queued')
        self.assertEqual(result['network_attempts'], 2)
        self.assertEqual(sleeps, [5])

    def test_client_rejection_and_cooldown(self):
        self.client.request = lambda _: (400, {}, b'{"status":0,"errors":["private"]}')
        self.assertEqual(self.client.send('incident', 'Test')['network_attempts'], 1)
        with self.assertRaises(PushoverError):
            self.client.send('another', 'Test')
        self.assertNotIn(b'private', self.client.path.read_bytes())

    def test_interrupted_send_remains_sending_and_never_replays(self):
        self.client.request = lambda _: (_ for _ in ()).throw(KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            self.client.send('incident', 'Test')
        self.assertEqual(self.client.send('incident', 'Test')['state'], 'sending')

    def test_retry_cannot_exceed_daily_attempt_budget(self):
        with self.client.database() as db:
            db.executemany('INSERT INTO attempts VALUES (?,?,?,?)', [(900, 'old', 500, 'rejected')] * 49)
        self.client.request = lambda _: (500, {}, b'{"status":0}')
        result = self.client.send('incident', 'Test')
        self.assertEqual(result['network_attempts'], 1)
        self.assertEqual(result['state'], 'rejected')
        with self.client.database() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 50)
