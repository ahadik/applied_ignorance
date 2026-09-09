"""Single, cache-first entry point for FantasyPros reads. No network calls on import."""
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parent
BASE = 'https://api.fantasypros.com/public/v2/json/'
# Account approval supplied by the user on 2026-09-08: full responses,
# personal use, 1 request/second and 500/day. See docs/FANTASYPROS.md.
# Reserve 20% for retries; rolling 24h avoids assuming a provider reset timezone.
ROUTINE_LIMIT = 400
HARD_LIMIT = 500
TTL = {'players': 86400, 'news': 900, 'injuries': 900, 'projections': 21600,
       'rankings': 21600, 'consensus-rankings': 21600, 'experts': 86400,
       'compare-players': 21600}


class APIError(Exception):
    """Safe error: contains no credentials, request headers or response body."""


class BudgetExceeded(APIError):
    pass


class RateLimited(APIError):
    pass


class InvalidData(APIError):
    pass


def quota_headers(headers):
    """Keep only numeric quota headers; never retain arbitrary provider headers."""
    allowed = {'ratelimit-limit', 'ratelimit-remaining', 'ratelimit-reset',
               'x-ratelimit-limit', 'x-ratelimit-remaining', 'x-ratelimit-reset'}
    return {k.lower(): str(v) for k, v in headers.items()
            if k.lower() in allowed and re.fullmatch(r'\d{1,16}', str(v))}


def load_key():
    key = os.environ.get('FANTASYPROS_API_KEY', '').strip()
    if not key and (ROOT / '.env').exists():
        for line in (ROOT / '.env').read_text().splitlines():
            match = re.fullmatch(r'\s*(?:export\s+)?FANTASYPROS_API_KEY\s*=\s*(.*?)\s*', line)
            if match:
                key = match[1].strip().strip('\"\'')
    if not key or '\n' in key or '\r' in key:
        raise APIError('FANTASYPROS_API_KEY is missing or invalid; save .env first')
    return key


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward the credential to a redirect target.


def transport(path, params, key):
    url = BASE + path + ('?' + urlencode(params) if params else '')
    request = Request(url, headers={'x-api-key': key, 'Accept': 'application/json'})
    try:
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            status, headers, body = response.status, dict(response.headers), response.read()
    except HTTPError as error:
        return error.code, dict(error.headers), None
    except (URLError, TimeoutError, OSError):
        raise APIError('FantasyPros connection failed') from None
    try:
        return status, headers, json.loads(body)
    except (ValueError, UnicodeError):
        raise InvalidData('FantasyPros returned invalid JSON') from None


def clean(data):
    """Discard image URL fields before caching or returning licensed data."""
    if isinstance(data, list):
        return [clean(item) for item in data]
    if isinstance(data, dict):
        return {k: clean(v) for k, v in data.items()
                if not any(word in k.lower() for word in ('image', 'headshot', 'photo', 'thumbnail', 'avatar'))}
    return data


def request_identity(path, params):
    path = path.strip('/')
    if not re.fullmatch(r'nfl/(players|news|injuries|compare-players|\d{4}/(projections|rankings|consensus-rankings|rankings/experts))', path):
        raise ValueError('Use a supported relative NFL endpoint; historical points are not enabled')
    normalized = {}
    for k, v in (params or {}).items():
        if not re.fullmatch(r'[A-Za-z_]+', k) or any(x in k.lower() for x in ('key', 'token', 'secret', 'auth')):
            raise ValueError('Invalid or credential-like query parameter')
        if v is None:
            continue
        if isinstance(v, bool):
            v = str(v).lower()
        elif not isinstance(v, (str, int, float)) or isinstance(v, float) and not math.isfinite(v):
            raise ValueError('Query parameters must be finite scalar values')
        normalized[k] = str(v)
    return path, dict(sorted(normalized.items()))


def validate_payload(path, params, data):
    if not isinstance(data, dict) or any(k in data for k in ('error', 'errors', 'message')):
        raise InvalidData('Response is not a data object')
    for flag in ('sample', 'is_sample', 'demo', 'is_demo'):
        if data.get(flag) not in (None, False, 0, 'false', '0'):
            raise InvalidData('Sample/demo data rejected')
    if 'sport' in data and str(data['sport']).lower() != 'nfl':
        raise InvalidData('Wrong sport')
    pieces = path.split('/')
    if len(pieces) > 2 and pieces[1].isdigit():
        if str(data.get('season', data.get('year'))) != pieces[1]:
            raise InvalidData('Missing or mismatched season')
    if 'week' in params and 'week' in data and str(data['week']) != params['week']:
        raise InvalidData('Wrong projection/ranking week')
    if 'scoring' in params and 'scoring' in data and data['scoring'] != params['scoring']:
        raise InvalidData('Wrong scoring format')
    field = {'news': 'items', 'injuries': 'injuries', 'experts': 'experts',
             'compare-players': 'rankings'}.get(pieces[-1], 'players')
    if field not in data or not isinstance(data[field], (list, dict)):
        raise InvalidData('Missing expected collection')
    if not data[field] and pieces[-1] not in ('news', 'injuries'):
        raise InvalidData('Empty player/ranking dataset rejected')


class FantasyPros:
    def __init__(self, cache_dir=None, key_loader=load_key, send=transport,
                 clock=time.time, sleep=time.sleep):
        self.directory = Path(cache_dir or ROOT / 'data' / 'fantasypros')
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.key_loader, self.send, self.clock, self.sleep = key_loader, send, clock, sleep

    @contextmanager
    def locked(self):
        # Lock spans cache check, reservation, transport and write: concurrent
        # processes requesting the same resource consume only one request.
        with (self.directory / 'client.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            db = sqlite3.connect(self.directory / 'cache.sqlite3')
            try:
                db.executescript('''
                    CREATE TABLE IF NOT EXISTS attempts (at REAL NOT NULL);
                    CREATE TABLE IF NOT EXISTS cache (id TEXT PRIMARY KEY, at REAL, payload TEXT);
                    CREATE TABLE IF NOT EXISTS control (id TEXT PRIMARY KEY, until REAL);
                    CREATE TABLE IF NOT EXISTS cache_metadata (id TEXT PRIMARY KEY, headers TEXT);
                ''')
                yield db
            finally:
                db.close()
                fcntl.flock(lock, fcntl.LOCK_UN)

    def usage(self):
        """Local attempts in the preceding 24 hours; not an account-wide quota API."""
        with self.locked() as db:
            count = db.execute('SELECT COUNT(*) FROM attempts WHERE at > ?', (self.clock()-86400,)).fetchone()[0]
            return {'attempts_last_24h': count, 'routine_remaining': max(0, ROUTINE_LIMIT-count),
                    'hard_remaining': max(0, HARD_LIMIT-count), 'scope': 'this shared local cache directory'}

    def get(self, path, params=None, *, max_age=None, validator=None, retries=2):
        """Cache-first read; validators run on hits too. Never silently serves stale data.

        Result includes data, fetched_at and cache_hit. Provider freshness and
        production entitlement still require endpoint-specific validation.
        """
        path, params = request_identity(path, params)
        ttl = TTL[path.split('/')[-1]] if max_age is None else max_age
        if not isinstance(ttl, (int, float)) or not math.isfinite(ttl) or ttl < 0 or retries not in (0, 1, 2):
            raise ValueError('Invalid cache age or retry count')
        key = self.key_loader()
        scope = hashlib.sha256(key.encode()).hexdigest()
        identity = hashlib.sha256(json.dumps([scope, path, params], sort_keys=True).encode()).hexdigest()
        with self.locked() as db:
            row = db.execute('SELECT at,payload FROM cache WHERE id=?', (identity,)).fetchone()
            if row and 0 <= self.clock()-row[0] < ttl:
                data = json.loads(row[1])
                validate_payload(path, params, data)
                if validator:
                    validator(data)
                metadata = db.execute('SELECT headers FROM cache_metadata WHERE id=?', (identity,)).fetchone()
                return self.result(data, row[0], True, json.loads(metadata[0]) if metadata else {})
            for attempt in range(retries + 1):
                from provider_freeze import check
                check('fantasypros',self.directory)
                cooldown = db.execute('SELECT MAX(until) FROM control WHERE id IN (?,?)', ('rate', scope)).fetchone()[0]
                if cooldown and cooldown > self.clock():
                    raise RateLimited('Provider cooldown or credential failure is active; no call sent')
                count = db.execute('SELECT COUNT(*) FROM attempts WHERE at > ?', (self.clock()-86400,)).fetchone()[0]
                if count >= (ROUTINE_LIMIT if attempt == 0 else HARD_LIMIT):
                    raise BudgetExceeded('Local rolling-24-hour request budget exhausted; no call sent')
                last = db.execute('SELECT MAX(at) FROM attempts').fetchone()[0]
                if last is not None:
                    self.sleep(max(0, last + 1.05 - self.clock()))
                check('fantasypros',self.directory)
                started = self.clock()
                # Commit reservation BEFORE I/O: crashes and failed requests count.
                db.execute('INSERT INTO attempts VALUES (?)', (started,))
                db.commit()
                try:
                    status, headers, data = self.send(path, params, key)
                except InvalidData:
                    raise
                except APIError:
                    status, headers, data = 503, {}, None
                if status == 200:
                    data = clean(data)
                    validate_payload(path, params, data)
                    if validator:
                        validator(data)
                    fetched = self.clock()
                    db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)', (identity, fetched, json.dumps(data, allow_nan=False)))
                    safe_headers = quota_headers(headers)
                    db.execute('INSERT OR REPLACE INTO cache_metadata VALUES (?,?)', (identity, json.dumps(safe_headers)))
                    db.commit()
                    return self.result(data, fetched, False, safe_headers)
                if status in (401, 403):
                    db.execute('INSERT OR REPLACE INTO control VALUES (?,?)', (scope, self.clock()+86400))
                    db.commit()
                    raise APIError(f'FantasyPros HTTP {status}; check credentials/entitlement; credential paused for 24h')
                if status == 429:
                    value = next((v for k, v in headers.items() if k.lower() == 'retry-after'), None)
                    delay = 60.0
                    if value:
                        try:
                            delay = max(1.0, float(value))
                        except ValueError:
                            try:
                                delay = max(1.0, parsedate_to_datetime(value).timestamp()-self.clock())
                            except (ValueError, TypeError, OverflowError):
                                pass
                    if not math.isfinite(delay):
                        delay = 60.0
                    db.execute('INSERT OR REPLACE INTO control VALUES (?,?)', ('rate', self.clock()+delay))
                    db.commit()
                    raise RateLimited('FantasyPros HTTP 429; shared Retry-After cooldown saved; no immediate retry')
                if status not in (500, 502, 503, 504) or attempt == retries:
                    raise APIError(f'FantasyPros HTTP {status}; no usable new data; last good cache retained')
                self.sleep(2 ** (attempt + 1))

    @staticmethod
    def result(data, fetched, hit, headers=None):
        return {'data': data, 'fetched_at': datetime.fromtimestamp(fetched, timezone.utc).isoformat(),
                'quota_headers_at_fetch': headers or {},
                'cache_hit': hit, 'validation': 'transport/basic schema; not proof of production entitlement'}


_client = None


def get_fantasypros(path, params=None, **options):
    """All project FantasyPros collectors must call this shared entry point."""
    global _client
    if _client is None:
        _client = FantasyPros()
    return _client.get(path, params, **options)
