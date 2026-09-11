from concurrent.futures import ThreadPoolExecutor
from email.message import Message
from email.utils import formatdate
from io import BytesIO
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from sleeper import (Sleeper, SleeperError, SleeperConnectionError,
                     SleeperRateLimited, cache_policy, transport)


class Clock:
    def __init__(self):
        self.value = 1800000000.0
    def time(self):
        return self.value
    def sleep(self, seconds):
        self.value += seconds


class SleeperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = Clock()
        self.calls = []
        self.responses = []
        def send(path):
            self.calls.append(path)
            response = self.responses.pop(0) if self.responses else (200, {}, {'user_id': 'u'})
            if isinstance(response, Exception):
                raise response
            return response
        self.send = send
        self.client = self.new_client()

    def new_client(self):
        return Sleeper(self.temp.name, self.send, self.clock.time, self.clock.sleep)

    def test_general_resource_transport_uses_fixed_host_and_timeout(self):
        opener = MagicMock()
        body = BytesIO(b'{"week": 1}')
        body.headers = Message()
        opener.open.return_value = body
        with patch('sleeper.build_opener', return_value=opener):
            self.assertEqual(transport('state/nfl'), (200, {}, {'week': 1}))
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.sleeper.app/v1/state/nfl')
        self.assertEqual(request.get_method(), 'GET')
        self.assertEqual(request.get_header('Cache-control'), 'no-cache')
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 5)

    def test_malformed_json_not_retried_or_cached(self):
        opener = MagicMock()
        body = BytesIO(b'<html>error</html>')
        body.headers = Message()
        opener.open.return_value = body
        client = Sleeper(self.temp.name, transport, self.clock.time, self.clock.sleep)
        with patch('sleeper.build_opener', return_value=opener):
            with self.assertRaises(SleeperError):
                client.get('user/u')
        self.assertEqual(opener.open.call_count, 1)
        with client.locked() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM cache').fetchone()[0], 0)

    def test_invalid_paths_and_cache_policy_overrides_rejected(self):
        for path in ('https://other.test', '//other.test', '../state/nfl',
                     'state/nfl?token=secret', 'state/%2e%2e', '', None):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.client.get(path)
        for path, age in [('draft/123/picks', 1), ('user/u', 301), ('user/u', float('nan'))]:
            with self.assertRaises(ValueError):
                self.client.get(path, max_age=age)
        self.assertEqual(self.calls, [])

    def test_transport_errors_safe(self):
        opener = MagicMock()
        opener.open.side_effect = URLError('sensitive text')
        with patch('sleeper.build_opener', return_value=opener):
            with self.assertRaises(SleeperConnectionError) as caught:
                transport('players/nfl')
        self.assertNotIn('sensitive', str(caught.exception))
        opener.open.side_effect = HTTPError('sensitive-url', 429, 'sensitive text', {}, None)
        with patch('sleeper.build_opener', return_value=opener):
            self.assertEqual(transport('players/nfl'), (429, {}, None))

    def test_profile_cache_survives_restart_and_expires_at_boundary(self):
        first = self.client.get('user/u', with_metadata=True)
        self.clock.sleep(299)
        second = self.new_client().get('user/u', with_metadata=True)
        self.assertTrue(second['cache_hit'])
        self.assertEqual(second['fetched_at'], first['fetched_at'])
        self.assertEqual(second['cache_age_seconds'], 299)
        self.assertEqual(second['network_attempts'], 0)
        self.clock.sleep(1)
        self.assertFalse(self.client.get('user/u', with_metadata=True)['cache_hit'])
        self.assertEqual(len(self.calls), 2)

    def test_mutable_and_unknown_resources_always_live(self):
        for path in ('draft/1', 'draft/1/picks', 'draft/1/traded_picks', 'league/1',
                     'league/1/rosters', 'league/1/matchups/1', 'league/1/transactions/1',
                     'state/nfl', 'players/nfl', 'players/nfl/trending', 'new/resource',
                     'user/u/leagues/nfl/2026'):
            self.assertEqual(cache_policy(path), 0)
            self.responses = [(200, {}, {'version': 1}), (200, {}, {'version': 2})]
            self.assertEqual(self.client.get(path)['version'], 1)
            self.assertEqual(self.client.get(path)['version'], 2)

    def test_shortened_age_refresh_and_invalidation(self):
        self.client.get('user/u')
        self.clock.sleep(11)
        self.assertFalse(self.client.get('user/u', max_age=10, with_metadata=True)['cache_hit'])
        self.assertFalse(self.client.get('user/u', refresh=True, with_metadata=True)['cache_hit'])
        self.new_client().invalidate('user/u')
        self.assertFalse(self.client.get('user/u', with_metadata=True)['cache_hit'])
        self.assertEqual(len(self.calls), 4)

    def test_no_negative_caching(self):
        for payload in (None, [], {}):
            self.responses = [(200, {}, payload), (200, {}, {'user_id': 'new'})]
            self.assertEqual(self.client.get('user/new'), payload)
            self.assertEqual(self.client.get('user/new'), {'user_id': 'new'})
            self.client.invalidate()

    def test_retry_success_and_limits_and_usage(self):
        self.responses = [SleeperConnectionError('offline'), (502, {}, None), (200, {}, [])]
        result = self.client.get('league/1/rosters', with_metadata=True)
        self.assertEqual(result['network_attempts'], 3)
        self.assertEqual(self.client.usage()['attempts_last_24h'], 3)
        self.responses = [(503, {}, None)] * 3
        with self.assertRaises(SleeperError):
            self.client.get('draft/1/picks')
        self.assertEqual(len(self.calls), 6)
        self.responses = [(503, {}, None)]
        with self.assertRaises(SleeperError):
            self.client.get('draft/1/picks', retries=0)
        self.assertEqual(len(self.calls), 7)

    def test_nontransient_failures_not_retried(self):
        for status in (400, 401, 403, 404):
            self.responses = [(status, {}, None)]
            with self.assertRaises(SleeperError):
                self.client.get('user/u')
        self.assertEqual(len(self.calls), 4)

    def test_diagnostics_distinguish_connection_http_and_cooldown(self):
        self.responses = [SleeperConnectionError('private transport text')]
        with self.assertRaises(SleeperConnectionError) as caught:
            self.client.get('league/1', retries=0)
        self.assertEqual(caught.exception.diagnostic(), {
            'category': 'connection', 'http_status': None,
            'network_attempts': 1, 'cache_hit': False})
        self.assertNotIn('private', str(caught.exception))
        self.responses = [(503, {}, None)]
        with self.assertRaises(SleeperError) as caught:
            self.client.get('league/1', retries=0)
        self.assertEqual(caught.exception.diagnostic()['http_status'], 503)
        self.assertEqual(caught.exception.diagnostic()['category'], 'http')
        self.responses = [(429, {'Retry-After': '60'}, None)]
        with self.assertRaises(SleeperRateLimited):
            self.client.get('league/1', retries=0)
        with self.assertRaises(SleeperRateLimited) as caught:
            self.new_client().get('league/1', retries=0)
        self.assertEqual(caught.exception.diagnostic()['category'], 'cooldown')
        self.assertEqual(caught.exception.diagnostic()['network_attempts'], 0)

    def test_rate_limit_persists_and_invalidation_cannot_bypass(self):
        self.responses = [(429, {'Retry-After': '120'}, None)]
        with self.assertRaises(SleeperRateLimited):
            self.client.get('draft/1/picks')
        self.client.invalidate()
        with self.assertRaises(SleeperRateLimited):
            self.new_client().get('league/1')
        self.assertEqual(len(self.calls), 1)
        self.clock.sleep(121)
        self.client.get('league/1')
        self.assertEqual(len(self.calls), 2)

    def test_retry_after_http_date_on_503(self):
        self.responses = [(503, {'Retry-After': formatdate(self.clock.time()+60, usegmt=True)}, None)]
        with self.assertRaises(SleeperRateLimited):
            self.client.get('state/nfl')
        self.clock.sleep(59)
        with self.assertRaises(SleeperRateLimited):
            self.client.get('state/nfl')
        self.clock.sleep(2)
        self.client.get('state/nfl')
        self.assertEqual(len(self.calls), 2)

    def test_failed_refresh_never_returns_expired_cache(self):
        self.client.get('user/u')
        self.clock.sleep(301)
        self.responses = [(503, {}, None)]
        with self.assertRaises(SleeperError):
            self.client.get('user/u', retries=0)
        with self.client.locked() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM cache').fetchone()[0], 1)

    def test_invalid_response_and_validator_preserve_good_cache(self):
        self.client.get('user/u')
        for bad in (42, {'error': 'failed'}):
            self.responses = [(200, {}, bad)]
            with self.assertRaises(SleeperError):
                self.client.get('user/u', refresh=True)
        def reject(data):
            raise ValueError('Wrong identity')
        with self.assertRaises(ValueError):
            self.client.get('user/u', validator=reject)
        self.assertEqual(self.client.get('user/u'), {'user_id': 'u'})
        self.assertEqual(len(self.calls), 3)

    def test_server_cache_directives_only_shorten_policy(self):
        for directive in ('no-store', 'no-cache', 'max-age=0'):
            self.responses = [(200, {'Cache-Control': directive}, {'user_id': 'u'})]
            self.client.get('user/u', refresh=True)
            self.assertFalse(self.client.get('user/u', with_metadata=True)['cache_hit'])
        self.responses = [(200, {'Cache-Control': 'max-age=30', 'Age': '20'}, {'user_id': 'u'})]
        self.client.get('user/u', refresh=True)
        self.clock.sleep(10)
        self.assertFalse(self.client.get('user/u', with_metadata=True)['cache_hit'])

    def test_concurrent_profile_reads_coalesce(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.new_client().get('user/u', with_metadata=True), range(4)))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(sum(r['cache_hit'] for r in results), 3)


if __name__ == '__main__':
    unittest.main()
