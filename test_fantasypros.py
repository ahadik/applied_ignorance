from concurrent.futures import ThreadPoolExecutor
import tempfile
import unittest
from fantasypros import FantasyPros, APIError, InvalidData, BudgetExceeded, RateLimited


class Clock:
    def __init__(self):
        self.value = 1800000000.0
    def time(self):
        return self.value
    def sleep(self, seconds):
        self.value += seconds


class FantasyProsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = Clock()
        self.calls = []
        self.responses = []
        def send(path, params, key):
            self.calls.append((path, params, self.clock.time()))
            return self.responses.pop(0) if self.responses else (200, {}, {'sport': 'NFL', 'players': [{'player_id': 1}]})
        self.send = send
        self.client = self.new_client()

    def new_client(self):
        return FantasyPros(self.temp.name, lambda: 'test-secret', self.send, self.clock.time, self.clock.sleep)

    def test_normalized_cache_survives_restart(self):
        self.client.get('nfl/players', {'show': 'pos_rank', 'ecr': 'included'})
        result = self.new_client().get('/nfl/players', {'ecr': 'included', 'show': 'pos_rank'})
        self.assertTrue(result['cache_hit'])
        self.assertEqual(len(self.calls), 1)

    def test_expiry_and_request_spacing(self):
        self.client.get('nfl/players', max_age=0)
        self.client.get('nfl/players', max_age=0)
        self.assertGreaterEqual(self.calls[1][2] - self.calls[0][2], 1)

    def test_retries_count_and_auth_errors_do_not_retry(self):
        self.responses = [(503, {}, None), (200, {}, {'players': [{'player_id': 1}]})]
        self.client.get('nfl/players')
        self.assertEqual(self.client.usage()['attempts_last_24h'], 2)
        self.responses = [(401, {}, None)]
        with self.assertRaises(APIError):
            self.client.get('nfl/players', max_age=0)
        with self.assertRaises(RateLimited):
            self.client.get('nfl/players', max_age=0)
        self.assertEqual(len(self.calls), 3)

    def test_quota_blocks_but_cache_still_works(self):
        self.client.get('nfl/players')
        with self.client.locked() as db:
            db.executemany('INSERT INTO attempts VALUES (?)', [(self.clock.time(),)] * 79)
            db.commit()
        self.assertTrue(self.client.get('nfl/players')['cache_hit'])
        with self.assertRaises(BudgetExceeded):
            self.client.get('nfl/players', {'ecr': 'included'})
        self.assertEqual(len(self.calls), 1)

    def test_hard_retry_budget(self):
        with self.client.locked() as db:
            db.executemany('INSERT INTO attempts VALUES (?)', [(self.clock.time(),)] * 100)
            db.commit()
        with self.assertRaises(BudgetExceeded):
            self.client.get('nfl/players')
        self.assertEqual(len(self.calls), 0)

    def test_rate_limit_cooldown_persists(self):
        self.responses = [(429, {'Retry-After': '120'}, None)]
        with self.assertRaises(RateLimited):
            self.client.get('nfl/players')
        with self.assertRaises(RateLimited):
            self.new_client().get('nfl/players')
        self.clock.sleep(121)
        self.assertFalse(self.new_client().get('nfl/players')['cache_hit'])
        self.assertEqual(len(self.calls), 2)

    def test_invalid_data_preserves_cache(self):
        self.client.get('nfl/players')
        for bad in ({'players': []}, {'players': [{'player_id': 1}], 'sample': True}, {'error': 'bad'}):
            self.responses = [(200, {}, bad)]
            with self.assertRaises(InvalidData):
                self.client.get('nfl/players', max_age=0)
        self.assertTrue(self.client.get('nfl/players')['cache_hit'])

    def test_validators_run_on_cache_hits(self):
        self.client.get('nfl/players')
        def reject(data):
            raise InvalidData('Rejected by domain checks')
        with self.assertRaises(InvalidData):
            self.client.get('nfl/players', validator=reject)
        self.assertEqual(len(self.calls), 1)

    def test_images_removed_and_wrong_season_rejected(self):
        self.responses = [(200, {}, {'players': [{'image_url': 'private-image', 'player_id': 1}]})]
        result = self.client.get('nfl/players')
        self.assertNotIn('image_url', result['data']['players'][0])
        self.responses = [(200, {}, {'season': '2025', 'players': [{'player_id': 1}]})]
        with self.assertRaises(InvalidData):
            self.client.get('nfl/2026/projections', {'position': 'RB', 'week': 0})

    def test_untrusted_paths_and_secret_query_rejected_before_call(self):
        for path, params in [('https://evil.example', {}), ('nfl/players', {'api_key': 'secret'}),
                             ('nfl/2025/player-points', {})]:
            with self.assertRaises(ValueError):
                self.client.get(path, params)
        self.assertEqual(len(self.calls), 0)

    def test_concurrent_requests_share_single_fetch(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.new_client().get('nfl/players'), range(4)))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(sum(not r['cache_hit'] for r in results), 1)


if __name__ == '__main__':
    unittest.main()
