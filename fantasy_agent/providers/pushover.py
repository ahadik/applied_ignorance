"""Central Pushover provider. Fixed HTTPS endpoint, bounded sends and persistent incident deduplication."""
from fantasy_agent.paths import ROOT as PROJECT_ROOT
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

from fantasy_agent.automation.automation_store import InvalidContract, canonical, digest, text, utc


class PushoverError(ValueError):
    pass


def credentials(root):
    names = ('PUSHOVER_APP_TOKEN', 'PUSHOVER_USER_KEY')
    values = {name: os.environ.get(name, '').strip() for name in names}
    path = Path(root) / '.env'
    if path.exists():
        for line in path.read_text().splitlines():
            match = re.fullmatch(r'\s*(?:export\s+)?(PUSHOVER_APP_TOKEN|PUSHOVER_USER_KEY)\s*=\s*(.*?)\s*', line)
            if match and not values[match[1]]:
                values[match[1]] = match[2].strip().strip('\"\'')
    return values


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def transport(payload):
    request = Request('https://api.pushover.net/1/messages.json', data=urlencode(payload).encode(),
                      headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
    try:
        with build_opener(NoRedirect()).open(request, timeout=10) as response:
            return response.status, dict(response.headers), response.read(16385)
    except HTTPError as error:
        return error.code, dict(error.headers), error.read(16385)
    except (URLError, TimeoutError, OSError):
        raise PushoverError('Notification transport outcome is unknown') from None


class Pushover:
    def __init__(self, root, *, request=transport, clock=time.time, sleep=time.sleep):
        self.root = Path(root).resolve()
        self.path = self.root / 'data/pushover/state.sqlite3'
        self.request, self.clock, self.sleep = request, clock, sleep

    def status(self):
        values = credentials(self.root)
        missing = [k for k, v in values.items() if not re.fullmatch(r'[A-Za-z0-9]{30}', v)]
        result = {'configured': not missing, 'missing_or_invalid': missing, 'network_attempts': 0,
                  'phone_delivery_confirmed': False, 'counts': {}}
        if self.path.exists():
            with sqlite3.connect(self.path) as db:
                result['counts'] = dict(db.execute('SELECT state,COUNT(*) FROM incidents GROUP BY state'))
                result['phone_delivery_confirmed'] = bool(db.execute("SELECT 1 FROM incidents WHERE state='confirmed' LIMIT 1").fetchone())
        return result

    def database(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE IF NOT EXISTS incidents(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, state TEXT NOT NULL, at REAL NOT NULL, attempts INTEGER NOT NULL, request_id TEXT, confirmation TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS attempts(at REAL NOT NULL, incident TEXT NOT NULL, status INTEGER, outcome TEXT NOT NULL)')
        db.commit()
        return db

    def send(self, incident, message, title='Fantasy Football agent'):
        text(incident, 'incident ID', 200)
        text(message, 'notification message', 1024)
        text(title, 'notification title', 250)
        values = credentials(self.root)
        if any(not re.fullmatch(r'[A-Za-z0-9]{30}', v) for v in values.values()):
            raise PushoverError('Configure PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY in .env')
        payload = {'token': values['PUSHOVER_APP_TOKEN'], 'user': values['PUSHOVER_USER_KEY'],
                   'title': title, 'message': message, 'priority': 0}
        fingerprint = digest({'title': title, 'message': message,
                              'recipient': hashlib.sha256(values['PUSHOVER_USER_KEY'].encode()).hexdigest()})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with (self.path.parent / 'send.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            db = self.database()
            try:
                old = db.execute('SELECT * FROM incidents WHERE id=?', (incident,)).fetchone()
                if old:
                    if old['fingerprint'] != fingerprint:
                        raise PushoverError('Incident ID already belongs to different content or recipient')
                    return {'incident': incident, 'state': old['state'], 'deduplicated': True,
                            'network_attempts': 0, 'phone_delivery_confirmed': old['state'] == 'confirmed'}
                now = self.clock()
                if db.execute('SELECT COUNT(*) FROM attempts WHERE at>?', (now - 86400,)).fetchone()[0] >= 50:
                    raise PushoverError('Local notification attempt budget reached')
                last = db.execute('SELECT MAX(at) FROM attempts').fetchone()[0]
                if last is not None and now - last < 5:
                    raise PushoverError('Notification cooldown is active')
                db.execute('INSERT INTO incidents VALUES (?,?,?,?,?,?,?)', (incident, fingerprint, 'sending', now, 0, None, None))
                db.commit()
                state, request_id, attempts = 'unknown', None, 0
                for attempt in range(2):
                    if db.execute('SELECT COUNT(*) FROM attempts WHERE at>?', (self.clock() - 86400,)).fetchone()[0] >= 50:
                        break
                    # Commit before I/O so restart cannot blindly resend an uncertain incident.
                    db.execute('INSERT INTO attempts VALUES (?,?,?,?)', (self.clock(), incident, None, 'pending'))
                    attempt_row = db.execute('SELECT last_insert_rowid()').fetchone()[0]
                    attempts += 1
                    db.execute('UPDATE incidents SET attempts=? WHERE id=?', (attempts, incident))
                    db.commit()
                    code, body = None, None
                    try:
                        code, headers, raw = self.request(payload)
                        if len(raw) > 16384:
                            raise PushoverError('Oversized notification response')
                        body = json.loads(raw)
                        if not isinstance(body, dict):
                            raise PushoverError('Invalid notification response')
                        if code == 200 and body.get('status') == 1:
                            state = 'queued'
                            candidate = body.get('request')
                            request_id = candidate if isinstance(candidate, str) and re.fullmatch(r'[A-Za-z0-9-]{1,100}', candidate) else None
                        elif 400 <= code < 500 or body.get('status') == 0:
                            state = 'rejected'
                    except (PushoverError, ValueError, TypeError, OSError):
                        state = 'unknown'
                    db.execute('UPDATE attempts SET status=?,outcome=? WHERE rowid=?', (code, state, attempt_row))
                    db.commit()
                    # Retry only explicit server rejection. Never replay an ambiguous accepted send.
                    if attempt == 0 and code is not None and 500 <= code < 600 and isinstance(body, dict) and body.get('status') == 0:
                        self.sleep(5)
                        continue
                    break
                db.execute('UPDATE incidents SET state=?,request_id=? WHERE id=?', (state, request_id, incident))
                db.commit()
                return {'incident': incident, 'state': state, 'request_id': request_id,
                        'network_attempts': attempts, 'deduplicated': False, 'phone_delivery_confirmed': False}
            finally:
                db.close()

    def confirm(self, incident, evidence):
        from fantasy_agent.automation.automation_store import AutomationStore
        proof = AutomationStore(self.root).reference(evidence)
        with self.database() as db:
            row = db.execute('SELECT state FROM incidents WHERE id=?', (incident,)).fetchone()
            if row is None or row['state'] not in ('queued', 'confirmed'):
                raise PushoverError('A queued message is required before phone confirmation')
            db.execute("UPDATE incidents SET state='confirmed',confirmation=? WHERE id=?", (canonical(proof), incident))
        return {'incident': incident, 'phone_delivery_confirmed': True, 'basis': 'saved_owner_confirmation'}


def get_pushover(root=None):
    return Pushover(root or PROJECT_ROOT)
