"""Shared Sleeper reads with conservative caching and bounded retry policies.

Only user profiles are cached by default. Mutable and unknown resources are live.
No I/O on import. Saved commands must use get_sleeper and the shared directory.
"""
from fantasy_agent.paths import ROOT as PROJECT_ROOT
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import fcntl
import json
import math
from pathlib import Path
import re
import sqlite3
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

BASE = 'https://api.sleeper.app/v1/'
ROOT = PROJECT_ROOT


class SleeperError(OSError):
    """Safe provider error without response bodies or arbitrary error text."""

    def __init__(self, message, *, category=None, http_status=None, network_attempts=None):
        super().__init__(message)
        self.category = category
        self.http_status = http_status
        self.network_attempts = network_attempts

    def diagnostic(self):
        return {'category': self.category, 'http_status': self.http_status,
                'network_attempts': self.network_attempts, 'cache_hit': False}


class SleeperConnectionError(SleeperError):
    pass


class SleeperRateLimited(SleeperError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_path(path):
    if not isinstance(path, str) or not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*', path):
        raise ValueError('Sleeper requires a relative path with plain resource segments')
    return path


def cache_policy(path):
    """Hard maximum staleness: callers may shorten, but cannot extend this."""
    validate_path(path)
    return 300 if re.fullmatch(r'user/[A-Za-z0-9_-]+', path) else 0


def validate_payload(data):
    if data is not None and not isinstance(data, (dict, list)):
        raise SleeperError('Sleeper returned an unexpected JSON value')
    if isinstance(data, dict) and any(k in data for k in ('error', 'errors')):
        raise SleeperError('Sleeper returned an error object')


def transport(path):
    request = Request(BASE + path, headers={'User-Agent': 'PersonalFantasyAssistant/1.0',
                                            'Accept': 'application/json',
                                            'Cache-Control': 'no-cache'})
    try:
        with build_opener(NoRedirect()).open(request, timeout=5) as response:
            headers = dict(response.headers)
            data = json.load(response)
    except HTTPError as error:
        return error.code, dict(error.headers or {}), None
    except (URLError, TimeoutError, OSError):
        raise SleeperConnectionError('Sleeper connection failed; no usable new data') from None
    except (ValueError, UnicodeError):
        raise SleeperError('Sleeper returned invalid JSON') from None
    return 200, headers, data


def retry_delay(headers, now):
    value = headers.get('retry-after')
    if value is not None:
        try:
            delay = float(value)
            if math.isfinite(delay):
                return max(1, delay)
        except ValueError:
            try:
                return max(1, parsedate_to_datetime(value).timestamp() - now)
            except (ValueError, TypeError, OverflowError):
                pass
    return 60


def response_ttl(headers, ttl):
    """Server directives may shorten our policy, never lengthen it."""
    directives = [p.strip().lower() for p in headers.get('cache-control', '').split(',')]
    if any(p.split('=')[0] in ('no-store', 'no-cache') for p in directives):
        return 0
    for directive in directives:
        if directive.startswith('max-age='):
            try:
                ttl = min(ttl, max(0, int(directive.split('=', 1)[1].strip('"'))))
            except ValueError:
                return 0
    try:
        return max(0, ttl - max(0, int(headers.get('age', '0'))))
    except ValueError:
        return 0


class Sleeper:
    def __init__(self, cache_dir=None, send=transport, clock=time.time, sleep=time.sleep):
        self.directory = Path(cache_dir or ROOT / 'data' / 'sleeper')
        self.send, self.clock, self.sleep = send, clock, sleep

    @contextmanager
    def locked(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.directory / 'client.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            db = sqlite3.connect(self.directory / 'cache.sqlite3')
            try:
                db.executescript('''
                    CREATE TABLE IF NOT EXISTS cache (path TEXT PRIMARY KEY, at REAL, expires REAL, payload TEXT);
                    CREATE TABLE IF NOT EXISTS attempts (at REAL NOT NULL);
                    CREATE TABLE IF NOT EXISTS control (id TEXT PRIMARY KEY, until REAL);
                ''')
                yield db
            finally:
                db.close()
                fcntl.flock(lock, fcntl.LOCK_UN)

    def invalidate(self, path=None):
        """Remove cached data after a known change; never clears cooldown/ledger."""
        if path is not None:
            validate_path(path)
        with self.locked() as db:
            if path is None:
                db.execute('DELETE FROM cache')
            else:
                db.execute('DELETE FROM cache WHERE path=?', (path,))
            db.commit()

    def usage(self):
        with self.locked() as db:
            count = db.execute('SELECT COUNT(*) FROM attempts WHERE at>?', (self.clock()-86400,)).fetchone()[0]
            return {'attempts_last_24h': count, 'scope': 'this shared local cache directory'}

    def get(self, path, *, max_age=None, refresh=False, retries=2, validator=None, with_metadata=False):
        policy = cache_policy(path)
        ttl = policy if max_age is None else max_age
        if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or not math.isfinite(ttl) or not 0 <= ttl <= policy:
            raise ValueError('max_age must be finite, nonnegative, and no greater than the endpoint policy')
        if type(retries) is not int or retries not in (0, 1, 2):
            raise ValueError('retries must be 0, 1 or 2')
        with self.locked() as db:
            row = db.execute('SELECT at,expires,payload FROM cache WHERE path=?', (path,)).fetchone()
            if not refresh and ttl > 0 and row and row[0] <= self.clock() < min(row[1], row[0]+ttl):
                data = json.loads(row[2])
                validate_payload(data)
                if validator:
                    validator(data)
                return self.result(data, row[0], True, 0, with_metadata)
            for attempt in range(retries + 1):
                now = self.clock()
                until = db.execute('SELECT until FROM control WHERE id=?', ('rate',)).fetchone()
                if until and until[0] > now:
                    raise SleeperRateLimited('Sleeper shared cooldown active; no request sent',
                                             category='cooldown', network_attempts=attempt)
                # Local pacing, not a claim about the provider's account quota.
                last = db.execute('SELECT MAX(at) FROM attempts').fetchone()[0]
                if last is not None:
                    self.sleep(max(0, last + 0.1 - now))
                db.execute('DELETE FROM attempts WHERE at<=?', (self.clock()-172800,))
                db.execute('INSERT INTO attempts VALUES (?)', (self.clock(),))
                db.commit()  # Failed requests and interrupted processes still count.
                connection_failed = False
                try:
                    status, raw_headers, data = self.send(path)
                except SleeperConnectionError:
                    connection_failed = True
                    status, raw_headers, data = 503, {}, None
                headers = {k.lower(): str(v) for k, v in raw_headers.items()}
                if status == 200:
                    validate_payload(data)
                    if validator:
                        validator(data)
                    payload = json.dumps(data, allow_nan=False)
                    fetched = self.clock()
                    age = response_ttl(headers, ttl)
                    if age > 0 and data:  # No negative caching of null/empty results.
                        db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?,?)',
                                   (path, fetched, fetched+age, payload))
                    else:
                        db.execute('DELETE FROM cache WHERE path=?', (path,))
                    db.commit()
                    return self.result(data, fetched, False, attempt+1, with_metadata)
                if status == 429 or status in (500, 502, 503, 504) and 'retry-after' in headers:
                    db.execute('INSERT OR REPLACE INTO control VALUES (?,?)',
                               ('rate', self.clock()+retry_delay(headers, self.clock())))
                    db.commit()
                    raise SleeperRateLimited(f'Sleeper HTTP {status}; shared cooldown saved; no immediate retry',
                                             category='http', http_status=status, network_attempts=attempt+1)
                if status not in (500, 502, 503, 504) or attempt == retries:
                    if connection_failed:
                        raise SleeperConnectionError('Sleeper connection failed; no usable new data',
                                                     category='connection', network_attempts=attempt+1)
                    raise SleeperError(f'Sleeper HTTP {status}; no usable new data; expired cache not served',
                                       category='http', http_status=status, network_attempts=attempt+1)
                self.sleep(2 ** attempt)

    def result(self, data, fetched, hit, attempts, metadata):
        if not metadata:
            return data
        return {'data': data, 'fetched_at': datetime.fromtimestamp(fetched, timezone.utc).isoformat(),
                'cache_hit': hit, 'cache_age_seconds': max(0, self.clock()-fetched),
                'network_attempts': attempts, 'source_updated_at': None}


_client = None


def shared_client():
    global _client
    if _client is None:
        _client = Sleeper()
    return _client


def get_sleeper(path, **options):
    """Shared entry point; raw payload by default, metadata available on request."""
    return shared_client().get(path, **options)


def invalidate_sleeper(path=None):
    return shared_client().invalidate(path)
