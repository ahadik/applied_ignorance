"""General nflverse release-data client. No draft dependencies or I/O on import.

Discover published CSV assets through GitHub release metadata; cache by asset
revision, validate before saving, and retain original publication provenance.
"""
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import fcntl
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sqlite3
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parent
API = 'https://api.github.com/repos/nflverse/nflverse-data/releases/tags/'
DOWNLOAD = 'https://github.com/nflverse/nflverse-data/releases/download/'
DATASETS = {
    'players': ('players', 'players.csv', {'gsis_id', 'pfr_id'}),
    'player_stats': ('stats_player', 'stats_player_week_{season}.csv', {'player_id', 'season', 'week', 'season_type'}),
    'snap_counts': ('snap_counts', 'snap_counts_{season}.csv', {'pfr_player_id', 'season', 'week', 'game_type', 'offense_snaps', 'offense_pct'}),
    'depth_charts': ('depth_charts', 'depth_charts_{season}.csv', {'gsis_id'}),
}
MAX_BYTES = 256 * 1024 * 1024
REST_ROUTINE_LIMIT = 45
REST_HARD_LIMIT = 50
TOTAL_ROUTINE_LIMIT = 120
TOTAL_HARD_LIMIT = 150


class NFLVerseError(OSError):
    pass


class ConnectionError(NFLVerseError):
    pass


class Cooldown(NFLVerseError):
    pass


class BudgetExceeded(NFLVerseError):
    pass


def finite_header(headers, key):
    try:
        value = float(headers[key])
        return value if math.isfinite(value) and value >= 0 else None
    except (KeyError, ValueError, TypeError):
        return None


def cooldown_delay(headers, now, fallback=60):
    delays = [fallback]
    value = finite_header(headers, 'retry-after')
    if value is None and 'retry-after' in headers:
        try:
            value = parsedate_to_datetime(headers['retry-after']).timestamp()-now
        except (ValueError, TypeError, OverflowError):
            pass
    if value is not None and math.isfinite(value):
        delays.append(value)
    reset = finite_header(headers, 'x-ratelimit-reset')
    if headers.get('x-ratelimit-remaining') == '0' and reset is not None:
        delays.append(reset-now+1)
    return max(delays)


def metadata_cache_age(headers):
    ttl = 21600
    for part in headers.get('cache-control', '').lower().split(','):
        key, _, value = part.strip().partition('=')
        if key in ('no-store', 'no-cache'):
            return 0
        if key == 'max-age':
            try:
                ttl = min(ttl, max(0, int(value.strip('"'))))
            except ValueError:
                return 0
    return max(0, ttl-(finite_header(headers, 'age') or 0))


def safe_url(url):
    parts = urlsplit(url)
    return (parts.scheme == 'https' and parts.hostname in
            ('api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com')
            and not parts.username and not parts.password and parts.port in (None, 443))


class ReleaseRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_url(newurl):
            raise NFLVerseError('Untrusted release redirect rejected')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def transport(url, headers):
    if not safe_url(url):
        raise NFLVerseError('Untrusted download URL rejected')
    request = Request(url, headers={'User-Agent': 'PersonalFantasyAssistant/1.0',
                                   'Accept': 'application/octet-stream', **headers})
    try:
        with build_opener(ReleaseRedirect()).open(request, timeout=15) as response:
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise NFLVerseError('Dataset exceeds download size limit')
            return response.status, dict(response.headers), body
    except HTTPError as error:
        # GitHub can signal a secondary limit only in a 403 JSON message.
        # Bound this read and never log or persist the error body.
        with error:
            body = error.read(8192)
        return error.code, dict(error.headers or {}), body
    except NFLVerseError:
        raise
    except (URLError, TimeoutError, OSError):
        raise ConnectionError('nflverse download connection failed') from None


def specification(dataset, season):
    if dataset not in DATASETS:
        raise ValueError('Unsupported nflverse dataset')
    if dataset == 'players':
        if season is not None:
            raise ValueError('Player identity directory is not season-specific')
    elif type(season) is not int or not 1999 <= season <= datetime.now(timezone.utc).year:
        raise ValueError('An explicit supported season is required')
    tag, pattern, columns = DATASETS[dataset]
    return tag, pattern.format(season=season), columns


def parse_csv(body, filename, required, season):
    try:
        if filename.endswith('.gz'):
            with gzip.GzipFile(fileobj=io.BytesIO(body)) as file:
                body = file.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise NFLVerseError('Expanded dataset exceeds size limit')
        reader = csv.DictReader(io.StringIO(body.decode('utf-8-sig')))
        columns = reader.fieldnames or []
        if len(columns) < 2 or len(columns) != len(set(columns)) or not required.issubset(columns):
            raise NFLVerseError('Dataset schema does not match required columns')
        rows = list(reader)
        if not rows or any(None in row or any(v is None for v in row.values()) for row in rows):
            raise NFLVerseError('Empty or malformed CSV rejected')
        if season is not None and 'season' in columns and any(row['season'] != str(season) for row in rows):
            raise NFLVerseError('Dataset contains a mismatched season')
        return rows, columns
    except (UnicodeError, csv.Error, OSError, EOFError) as error:
        if isinstance(error, NFLVerseError):
            raise
        raise NFLVerseError('Unable to decode dataset CSV') from None


class NFLVerse:
    def __init__(self, cache_dir=None, send=transport, clock=time.time, sleep=time.sleep):
        self.directory = Path(cache_dir or ROOT / 'data' / 'nflverse' / 'cache')
        self.send, self.clock, self.sleep = send, clock, sleep

    @contextmanager
    def locked(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.directory / 'client.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            db = sqlite3.connect(self.directory / 'cache.sqlite3')
            try:
                db.executescript('''
                  CREATE TABLE IF NOT EXISTS releases(tag TEXT PRIMARY KEY, checked REAL, etag TEXT, payload TEXT);
                  CREATE TABLE IF NOT EXISTS assets(revision TEXT PRIMARY KEY, fetched REAL, payload BLOB, sha256 TEXT);
                  CREATE TABLE IF NOT EXISTS attempts(at REAL);
                  CREATE TABLE IF NOT EXISTS control(id TEXT PRIMARY KEY, until REAL);
                  CREATE TABLE IF NOT EXISTS quota(id TEXT PRIMARY KEY, observed REAL, remaining REAL, resets REAL, max_requests REAL);
                  CREATE TABLE IF NOT EXISTS polls(url TEXT PRIMARY KEY, until REAL);
                ''')
                # Preserve earlier attempt history; legacy requests conservatively
                # count toward both buckets until they leave the rolling window.
                if 'kind' not in {r[1] for r in db.execute('PRAGMA table_info(attempts)')}:
                    db.execute("ALTER TABLE attempts ADD COLUMN kind TEXT NOT NULL DEFAULT 'legacy'")
                if 'expires' not in {r[1] for r in db.execute('PRAGMA table_info(releases)')}:
                    db.execute('ALTER TABLE releases ADD COLUMN expires REAL NOT NULL DEFAULT 0')
                db.commit()
                yield db
            finally:
                db.close()
                fcntl.flock(lock, fcntl.LOCK_UN)

    def request(self, db, url, headers=None, retries=2):
        if type(retries) is not int or retries not in (0, 1, 2):
            raise ValueError('Retry count must be 0, 1 or 2')
        kind = 'rest' if url.startswith(API) else 'asset'
        for attempt in range(retries + 1):
            from provider_freeze import check
            check('nflverse',self.directory)
            now = self.clock()
            row = db.execute('SELECT until FROM control WHERE id="rate"').fetchone()
            if row and row[0] > now:
                raise Cooldown('Shared nflverse/GitHub cooldown active; no request sent')
            if kind == 'rest':
                primary = db.execute('SELECT until FROM control WHERE id="primary_rest"').fetchone()
                poll = db.execute('SELECT until FROM polls WHERE url=?', (url,)).fetchone()
                if primary and primary[0] > now or poll and poll[0] > now:
                    raise Cooldown('GitHub REST quota/poll interval active; no request sent')
            total, rest = self.counts(db)
            if total >= (TOTAL_ROUTINE_LIMIT if attempt == 0 else TOTAL_HARD_LIMIT) or kind == 'rest' and rest >= (REST_ROUTINE_LIMIT if attempt == 0 else REST_HARD_LIMIT):
                raise BudgetExceeded('Local nflverse rolling-hour request budget exhausted; no request sent')
            last = db.execute('SELECT MAX(at) FROM attempts').fetchone()[0]
            if last is not None:
                self.sleep(max(0, last + 0.25 - now))
            check('nflverse',self.directory)
            db.execute('INSERT INTO attempts(at,kind) VALUES (?,?)', (self.clock(), kind))
            db.commit()
            try:
                status, raw, body = self.send(url, headers or {})
            except ConnectionError:
                status, raw, body = 503, {}, b''
            response = {k.lower(): str(v) for k, v in raw.items()}
            if kind == 'rest':
                remaining = finite_header(response, 'x-ratelimit-remaining')
                reset = finite_header(response, 'x-ratelimit-reset')
                if remaining is not None:
                    db.execute('INSERT OR REPLACE INTO quota VALUES (?,?,?,?,?)',
                               ('rest', self.clock(), remaining, reset, finite_header(response, 'x-ratelimit-limit')))
                    if remaining == 0:
                        db.execute('INSERT OR REPLACE INTO control VALUES ("primary_rest", ?)',
                                   (max(self.clock()+1, reset+1) if reset is not None else self.clock()+60,))
                interval = finite_header(response, 'x-poll-interval')
                if interval is not None:
                    db.execute('INSERT OR REPLACE INTO polls VALUES (?,?)', (url, self.clock()+interval))
                db.commit()
            if status in (200, 304):
                db.execute('DELETE FROM control WHERE id="secondary_failures"')
                db.commit()
                return status, response, body
            secondary = False
            if status == 403:
                try:
                    message = str(json.loads(body).get('message', '')).lower()
                    secondary = any(term in message for term in ('secondary rate limit', 'abuse', 'rate limit exceeded'))
                except (ValueError, UnicodeError, AttributeError):
                    pass  # Error bodies are classified, never logged or saved.
            if status == 429 or status == 403 and (secondary or response.get('x-ratelimit-remaining') == '0' or 'retry-after' in response) or status in (500, 502, 503, 504) and 'retry-after' in response:
                previous = db.execute('SELECT until FROM control WHERE id="secondary_failures"').fetchone()
                failures = min(7, int(previous[0])+1) if previous else 1
                delay = cooldown_delay(response, self.clock(), 60 * 2 ** (failures-1))
                db.execute('INSERT OR REPLACE INTO control VALUES ("secondary_failures", ?)', (failures,))
                db.execute('INSERT OR REPLACE INTO control VALUES ("rate", ?)', (self.clock()+max(1, delay),))
                db.commit()
                raise Cooldown('nflverse/GitHub rate limit; shared cooldown saved')
            if status not in (500, 502, 503, 504) or attempt == retries:
                raise NFLVerseError(f'nflverse HTTP {status}; no replacement dataset saved')
            self.sleep(2 ** attempt)

    def counts(self, db):
        total = db.execute('SELECT COUNT(*) FROM attempts WHERE at>?', (self.clock()-3600,)).fetchone()[0]
        rest = db.execute("SELECT COUNT(*) FROM attempts WHERE at>? AND kind IN ('rest','legacy')", (self.clock()-3600,)).fetchone()[0]
        return total, rest

    def usage(self):
        """Local-only status; never calls GitHub's rate-limit endpoint."""
        with self.locked() as db:
            total, rest = self.counts(db)
            quota = db.execute('SELECT observed,remaining,resets,max_requests FROM quota WHERE id="rest"').fetchone()
            return {'attempts_last_hour': total, 'rest_attempts_last_hour': rest,
                    'rest_routine_remaining': max(0, REST_ROUTINE_LIMIT-rest),
                    'rest_hard_remaining': max(0, REST_HARD_LIMIT-rest),
                    'total_routine_remaining': max(0, TOTAL_ROUTINE_LIMIT-total),
                    'total_hard_remaining': max(0, TOTAL_HARD_LIMIT-total),
                    'provider_observation': dict(zip(('observed_at_epoch','remaining_at_observation','reset_epoch','limit'), quota)) if quota else None,
                    'active_cooldowns': {r[0]: r[1] for r in db.execute("SELECT id,until FROM control WHERE id!='secondary_failures' AND until>?", (self.clock(),))},
                    'scope': 'shared local directory; provider quota is IP-wide and may include other clients'}

    def release(self, db, tag, max_age):
        previous = db.execute('SELECT checked,etag,payload,expires FROM releases WHERE tag=?', (tag,)).fetchone()
        if previous and 0 <= self.clock()-previous[0] < max_age and self.clock() < previous[3]:
            return json.loads(previous[2]) | {'metadata_checked_at_epoch': previous[0]}
        headers = {'Accept': 'application/vnd.github+json', 'Cache-Control': 'no-cache'}
        if previous and previous[1]:
            headers['If-None-Match'] = previous[1]
        status, response, body = self.request(db, API+tag, headers)
        if status == 304:
            if not previous:
                raise NFLVerseError('Unexpected metadata 304 without saved release')
            payload, etag = previous[2], previous[1]
        else:
            try:
                data = json.loads(body)
            except (ValueError, UnicodeError):
                raise NFLVerseError('Invalid release metadata JSON') from None
            if not isinstance(data, dict) or data.get('tag_name') != tag or not isinstance(data.get('assets'), list):
                raise NFLVerseError('Unexpected release metadata schema')
            # Persist only relevant metadata, never temporary signed redirect URLs.
            assets = [{k: a.get(k) for k in ('id', 'name', 'size', 'updated_at', 'browser_download_url', 'digest')}
                      for a in data['assets'] if isinstance(a, dict)]
            payload = json.dumps({'tag_name': tag, 'assets': assets})
            etag = response.get('etag')
        checked = self.clock()
        if 'no-store' in response.get('cache-control', '').lower():
            db.execute('DELETE FROM releases WHERE tag=?', (tag,))
        else:
            db.execute('INSERT OR REPLACE INTO releases(tag,checked,etag,payload,expires) VALUES (?,?,?,?,?)',
                       (tag, checked, etag, payload, checked+metadata_cache_age(response)))
        db.commit()
        return json.loads(payload) | {'metadata_checked_at_epoch': checked}

    def catalog(self, dataset, season=None):
        tag, _, _ = specification(dataset, season)
        with self.locked() as db:
            return self.release(db, tag, 300)

    def get(self, dataset, season=None, *, refresh=False, revalidate=False, validator=None):
        tag, filename, required = specification(dataset, season)
        # Current depth/identity feeds revalidate publication metadata on every read.
        now = datetime.fromtimestamp(self.clock(), timezone.utc)
        historical = season is not None and (season < now.year-1 or season == now.year-1 and now.month >= 3)
        metadata_age = 21600 if historical and dataset in ('player_stats', 'snap_counts') else 0
        with self.locked() as db:
            started = db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]
            release = self.release(db, tag, 0 if refresh or revalidate else metadata_age)
            candidates = [a for a in release['assets'] if a['name'] in (filename, filename+'.gz')]
            if not candidates:
                raise NFLVerseError(f'No published CSV asset for {dataset} season {season}; no older-season fallback')
            asset = sorted(candidates, key=lambda a: a['name'].endswith('.gz'))[0]
            url = asset['browser_download_url']
            if url != DOWNLOAD+tag+'/'+asset['name'] or not asset['updated_at'] or type(asset['size']) is not int or not 0 < asset['size'] <= MAX_BYTES:
                raise NFLVerseError('Invalid asset provenance or size')
            revision = hashlib.sha256(json.dumps(asset, sort_keys=True).encode()).hexdigest()
            cached = db.execute('SELECT fetched,payload,sha256 FROM assets WHERE revision=?', (revision,)).fetchone()
            if cached and not refresh:
                fetched, body, digest = cached
                if hashlib.sha256(body).hexdigest() != digest:
                    raise NFLVerseError('Cached dataset checksum failed')
            else:
                status, download_headers, body = self.request(db, url, {'Cache-Control': 'no-cache'})
                if status != 200 or len(body) != asset['size']:
                    raise NFLVerseError('Incomplete asset download')
                digest = hashlib.sha256(body).hexdigest()
                if asset.get('digest') and asset['digest'] != 'sha256:'+digest:
                    raise NFLVerseError('Published asset checksum failed')
                fetched = self.clock()
            rows, columns = parse_csv(body, asset['name'], required, season)
            if validator:
                validator(rows)
            if not cached or refresh:
                if 'no-store' in download_headers.get('cache-control', '').lower():
                    db.execute('DELETE FROM assets WHERE revision=?', (revision,))
                else:
                    db.execute('INSERT OR REPLACE INTO assets VALUES (?,?,?,?)', (revision, fetched, body, digest))
                db.commit()
            attempts = db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0] - started
            checked = release['metadata_checked_at_epoch']
            return {'data': rows, 'provenance': {'dataset': dataset, 'season': season, 'url': url,
                    'asset_updated_at': asset['updated_at'], 'sha256': digest, 'columns': columns,
                    'fetched_at': datetime.fromtimestamp(fetched, timezone.utc).isoformat(),
                    'metadata_checked_at': datetime.fromtimestamp(checked, timezone.utc).isoformat(),
                    'cache_hit': bool(cached and not refresh), 'network_attempts': attempts}}


_client = None


def shared_client():
    global _client
    if _client is None:
        _client = NFLVerse()
    return _client


def get_nflverse(dataset, season=None, **options):
    return shared_client().get(dataset, season, **options)
