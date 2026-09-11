import hashlib
import json
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from fantasy_agent.providers.nflverse import (API, NFLVerse, NFLVerseError, Cooldown, BudgetExceeded,
                      parse_csv, cooldown_delay, metadata_cache_age, transport)


class NFLVerseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1788880000.0
        self.calls = []
        self.revision = '2026-09-08T07:00:00Z'
        self.body = b'gsis_id,pfr_id\n00-1,Test01\n'
        self.fail = None
        self.client = NFLVerse(self.temp.name, self.send, lambda: self.now, self.sleep)
    def sleep(self, seconds):
        self.now += seconds
    def send(self, url, headers):
        self.calls.append((url, headers))
        if self.fail:
            return self.fail
        if 'api.github.com' in url:
            data = {'tag_name': 'players', 'assets': [{'id': 1, 'name': 'players.csv', 'size': len(self.body),
                    'updated_at': self.revision, 'browser_download_url': 'https://github.com/nflverse/nflverse-data/releases/download/players/players.csv',
                    'digest': 'sha256:'+hashlib.sha256(self.body).hexdigest()}]}
            return 200, {'ETag': 'revision'}, json.dumps(data).encode()
        return 200, {}, self.body
    def test_cache_revalidates_and_revision_change_downloads(self):
        first = self.client.get('players')
        second = self.client.get('players')
        self.assertFalse(first['provenance']['cache_hit'])
        self.assertTrue(second['provenance']['cache_hit'])
        self.assertEqual(len(self.calls), 3)
        self.body = b'gsis_id,pfr_id\n00-2,Test02\n'
        self.revision = '2026-09-08T08:00:00Z'
        self.assertEqual(self.client.get('players')['data'][0]['gsis_id'], '00-2')
        self.assertEqual(len(self.calls), 5)
    def test_invalid_replacement_preserves_old_asset(self):
        self.client.get('players')
        self.body = b'wrong,columns\na,b\n'
        self.revision = '2026-09-08T08:00:00Z'
        with self.assertRaises(NFLVerseError):
            self.client.get('players')
        with self.client.locked() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM assets').fetchone()[0], 1)
    def test_missing_asset_never_substitutes_season(self):
        self.body = b'gsis_id,pfr_id\n00-1,Test01\n'
        with self.assertRaises(NFLVerseError):
            self.client.get('snap_counts', 2025)
    def test_schema_season_and_truncated_rows(self):
        for body in (b'season,x\n2024,1\n', b'season,x\n2025\n'):
            with self.assertRaises(NFLVerseError):
                parse_csv(body, 'x.csv', {'season'}, 2025)
    def test_quota_cooldown_survives_restart(self):
        self.fail = (403, {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': str(self.now+100)}, b'')
        with self.assertRaises(Cooldown):
            self.client.get('players')
        restarted = NFLVerse(self.temp.name, self.send, lambda: self.now, self.sleep)
        with self.assertRaises(Cooldown):
            restarted.get('players')
        self.assertEqual(len(self.calls), 1)
    def test_bad_dataset_rejected_before_request(self):
        with self.assertRaises(ValueError):
            self.client.get('../bad', 2025)
        self.assertEqual(self.calls, [])


    def test_conditional_metadata_304_reuses_verified_asset(self):
        self.client.get('players')
        self.fail = (304, {}, b'')
        result = self.client.get('players')
        self.assertTrue(result['provenance']['cache_hit'])
        self.assertEqual(result['provenance']['network_attempts'], 1)
        self.assertEqual(self.calls[-1][1]['If-None-Match'], 'revision')

    def test_bounded_transient_retries(self):
        self.fail = (503, {}, b'')
        with self.assertRaises(NFLVerseError):
            self.client.get('players')
        self.assertEqual(len(self.calls), 3)

    def test_rest_budget_preserved_on_restart_and_expires(self):
        with self.client.locked() as db:
            db.executemany('INSERT INTO attempts(at,kind) VALUES (?,?)', [(self.now, 'rest')]*45)
            db.commit()
        restarted = NFLVerse(self.temp.name, self.send, lambda: self.now, self.sleep)
        with self.assertRaises(BudgetExceeded):
            restarted.get('players')
        self.assertEqual(self.calls, [])
        self.now += 3601
        restarted.get('players')
        self.assertEqual(len(self.calls), 2)

    def test_retry_reserve_and_hard_budget(self):
        with self.client.locked() as db:
            db.executemany('INSERT INTO attempts(at,kind) VALUES (?,?)', [(self.now, 'rest')]*44)
            db.commit()
        self.fail = (503, {}, b'')
        with self.assertRaises(NFLVerseError):
            self.client.get('players')
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.client.usage()['rest_attempts_last_hour'], 47)
        with self.client.locked() as db:
            db.executemany('INSERT INTO attempts(at,kind) VALUES (?,?)', [(self.now, 'rest')]*3)
            db.commit()
            with self.assertRaises(BudgetExceeded):
                self.client.request(db, API+'players')
        self.assertEqual(len(self.calls), 3)

    def test_total_budget_blocks_asset_requests(self):
        with self.client.locked() as db:
            db.executemany('INSERT INTO attempts(at,kind) VALUES (?,?)', [(self.now, 'asset')]*120)
            db.commit()
            with self.assertRaises(BudgetExceeded):
                self.client.request(db, 'https://github.com/nflverse/nflverse-data/releases/download/players/players.csv')
        self.assertEqual(self.calls, [])

    def test_last_rest_quota_allows_asset_then_blocks_next_metadata(self):
        def last_quota(url, headers):
            status, response, body = self.send(url, headers)
            if url.startswith(API):
                response |= {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': str(self.now+100)}
            return status, response, body
        self.client.send = last_quota
        self.client.get('players')
        self.assertEqual(len(self.calls), 2)
        with self.assertRaises(Cooldown):
            self.client.get('players')
        self.assertEqual(self.client.usage()['provider_observation']['remaining_at_observation'], 0)
        self.assertEqual(len(self.calls), 2)

    def test_secondary_limit_without_headers_backs_off_across_restarts(self):
        self.fail = (403, {}, b'{"message":"You have exceeded a secondary rate limit"}')
        with self.assertRaises(Cooldown):
            self.client.get('players')
        self.assertEqual(self.client.usage()['active_cooldowns']['rate'], self.now+60)
        self.now += 61
        restarted = NFLVerse(self.temp.name, self.send, lambda: self.now, self.sleep)
        with self.assertRaises(Cooldown):
            restarted.get('players')
        self.assertEqual(restarted.usage()['active_cooldowns']['rate'], self.now+120)

    def test_transport_retains_bounded_error_for_classification(self):
        error = HTTPError(API+'players', 403, 'Forbidden', {}, io.BytesIO(b'x'*9000))
        with patch('fantasy_agent.providers.nflverse.build_opener') as opener:
            opener.return_value.open.side_effect = error
            status, _, body = transport(API+'players', {})
        self.assertEqual(status, 403)
        self.assertEqual(len(body), 8192)

    def test_retry_after_and_reset_use_later_deadline(self):
        self.assertEqual(cooldown_delay({'retry-after': '10', 'x-ratelimit-remaining': '0',
                                        'x-ratelimit-reset': str(self.now+120)}, self.now), 121)
        self.assertEqual(cooldown_delay({'retry-after': 'nan'}, self.now), 60)

    def test_poll_interval_blocks_repeated_metadata(self):
        def polled(url, headers):
            status, response, body = self.send(url, headers)
            return status, response | {'X-Poll-Interval': '60'}, body
        self.client.send = polled
        self.client.get('players')
        with self.assertRaises(Cooldown):
            self.client.get('players')
        self.assertEqual(len(self.calls), 2)

    def test_metadata_cache_controls_and_catalog_expiry(self):
        self.assertEqual(metadata_cache_age({'cache-control': 'max-age=90', 'age': '30'}), 60)
        self.assertEqual(metadata_cache_age({'cache-control': 'max-age=999999'}), 21600)
        self.assertEqual(metadata_cache_age({'cache-control': 'no-cache'}), 0)
        def short_cache(url, headers):
            status, response, body = self.send(url, headers)
            return status, response | {'Cache-Control': 'max-age=10'}, body
        self.client.send = short_cache
        self.client.catalog('players')
        self.client.catalog('players')
        self.assertEqual(len(self.calls), 1)
        self.now += 11
        self.client.catalog('players')
        self.assertEqual(len(self.calls), 2)

    def test_no_store_removes_old_cache_and_preserves_check_time(self):
        self.client.get('players')
        def no_store(url, headers):
            status, response, body = self.send(url, headers)
            return status, response | {'Cache-Control': 'no-store'}, body
        self.client.send = no_store
        result = self.client.get('players', refresh=True)
        with self.client.locked() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM releases').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM assets').fetchone()[0], 0)
        self.assertLess(result['provenance']['metadata_checked_at'], result['provenance']['fetched_at'])

    def test_explicit_revalidation_reuses_historical_asset(self):
        self.body = b'player_id,season,week,season_type\n00-1,2025,1,REG\n'
        def historical(url, headers):
            status, response, body = self.send(url, headers)
            if url.startswith(API):
                body = body.replace(b'players.csv', b'stats_player_week_2025.csv').replace(b'players', b'stats_player')
            return status, response, body
        self.client.send = historical
        self.client.get('player_stats', 2025)
        self.client.get('player_stats', 2025)
        self.assertEqual(len(self.calls), 2)
        self.client.get('player_stats', 2025, revalidate=True)
        self.assertEqual(len(self.calls), 3)

    def test_legacy_database_migration_preserves_attempts_without_network(self):
        db = sqlite3.connect(Path(self.temp.name) / 'cache.sqlite3')
        db.execute('CREATE TABLE attempts(at REAL)')
        db.executemany('INSERT INTO attempts VALUES (?)', [(self.now,)]*12)
        db.commit()
        db.close()
        usage = self.client.usage()
        self.assertEqual(usage['attempts_last_hour'], 12)
        self.assertEqual(usage['rest_attempts_last_hour'], 12)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
