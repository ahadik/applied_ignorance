"""Local automation contracts and transactional records. No provider or browser I/O."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from storage import save_atomic

VERSION = 1
OPERATIONS = {'inspect_sleeper', 'collect_inputs', 'validate_lineup', 'propose_lineup', 'integrated_review'}
MODES = {'disabled', 'observe', 'propose'}
DEFAULT_POLICY = {'schema_version': 1, 'mode': 'disabled', 'timezone': 'America/New_York',
                  'lease_seconds': 300, 'allowed_operations': sorted(OPERATIONS)}


class AutomationError(ValueError):
    """Base class for safe automation errors."""


class MissingState(AutomationError): pass
class UnknownSchema(AutomationError): pass
class InvalidContract(AutomationError): pass
class StaleRevision(AutomationError): pass
class ModeBlocked(AutomationError): pass
class DuplicateRun(AutomationError): pass
class LeaseConflict(AutomationError): pass
class LeaseExpired(AutomationError): pass
class IncompletePriorExecution(AutomationError): pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.timestamp()
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise InvalidContract('Use an ISO timestamp with a time zone') from None


def text(value, name, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or '\x00' in value:
        raise InvalidContract(f'Invalid {name}')
    return value


def validate_policy(value):
    if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != VERSION:
        raise UnknownSchema('Unsupported policy schema')
    if set(value) != set(DEFAULT_POLICY):
        raise InvalidContract('Unexpected policy fields')
    if not isinstance(value['mode'], str) or value['mode'] not in MODES:
        raise ModeBlocked('M1 supports disabled, observe and propose modes only')
    lease = value['lease_seconds']
    if type(lease) is not int or not 1 <= lease <= 3600:
        raise InvalidContract('Lease must be between 1 and 3600 seconds')
    operations = value['allowed_operations']
    if not isinstance(operations, list) or not operations or any(not isinstance(op, str) or op not in OPERATIONS for op in operations):
        raise InvalidContract('Unsupported allowed operations')
    if len(set(operations)) != len(operations):
        raise InvalidContract('Duplicate allowed operations')
    try:
        ZoneInfo(value['timezone'])
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        raise InvalidContract('Unknown time zone') from None
    return json.loads(canonical(value))


def validate_check(value):
    fields = {'schema_version', 'check_id', 'scope', 'operation', 'season', 'week',
              'run_at', 'latest_start_at', 'expires_at', 'source_refs'}
    if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != VERSION:
        raise UnknownSchema('Unsupported check schema')
    if set(value) != fields:
        raise InvalidContract('Unexpected check fields')
    for key in ('check_id', 'scope'):
        text(value[key], key)
    if not isinstance(value['operation'], str) or value['operation'] not in OPERATIONS:
        raise InvalidContract('Unsupported check operation')
    if type(value['season']) is not int or not 2000 <= value['season'] <= 2200:
        raise InvalidContract('Invalid season')
    if type(value['week']) is not int or not 1 <= value['week'] <= 22:
        raise InvalidContract('Invalid week')
    times = [instant(value[key]) for key in ('run_at', 'latest_start_at', 'expires_at')]
    if not times[0] <= times[1] < times[2]:
        raise InvalidContract('Check times must satisfy run_at <= latest_start_at < expires_at')
    if not isinstance(value['source_refs'], list) or len(value['source_refs']) > 20:
        raise InvalidContract('Use at most 20 source references')
    for path in value['source_refs']:
        text(path, 'reference path', 500)
    result = json.loads(canonical(value))
    for key, stamp in zip(('run_at', 'latest_start_at', 'expires_at'), times):
        result[key] = utc(stamp)
    return result


DDL = '''
CREATE TABLE policy (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
CREATE TABLE checks (check_id TEXT, revision TEXT, spec TEXT NOT NULL,
                     PRIMARY KEY(check_id, revision));
CREATE TABLE current_checks (check_id TEXT PRIMARY KEY, revision TEXT NOT NULL);
CREATE TABLE runs (run_id TEXT PRIMARY KEY, check_id TEXT NOT NULL, revision TEXT NOT NULL,
                   scope TEXT NOT NULL, token TEXT NOT NULL, state TEXT NOT NULL,
                   started REAL NOT NULL, lease_until REAL NOT NULL, finished REAL,
                   policy_revision TEXT NOT NULL, result TEXT);
CREATE INDEX scope_runs ON runs(scope, state);
CREATE TABLE refs (sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                   kind TEXT NOT NULL, reference TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL,
                     kind TEXT NOT NULL, run_id TEXT, payload TEXT NOT NULL);
'''


class AutomationStore:
    def __init__(self, root=None, *, clock=time.time):
        self.root = Path(root or Path(__file__).resolve().parent).resolve()
        self.path = self.root / 'data/automation/state.sqlite3'
        self.clock = clock

    def now(self):
        value = self.clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise InvalidContract('Invalid clock')
        return value

    @contextmanager
    def transaction(self):
        if not self.path.is_file():
            raise MissingState('Run automation.py init first')
        db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, isolation_level=None, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('PRAGMA user_version').fetchone()[0] != VERSION:
                raise UnknownSchema('Unsupported automation database version')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self, policy=None):
        value = validate_policy(DEFAULT_POLICY if policy is None else policy)
        if value['mode'] != 'disabled':
            raise ModeBlocked('New automation must start disabled')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        try:
            db.execute('BEGIN IMMEDIATE')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if version == VERSION:
                # Initialization is idempotent and cannot reset existing policy or records.
                db.rollback()
                return self.status()
            if version != 0 or tables:
                raise UnknownSchema('Refuse to initialize an unknown or nonempty database')
            for statement in DDL.split(';'):
                if statement.strip():
                    db.execute(statement)
            for table in ('checks', 'refs', 'events'):
                for action in ('UPDATE', 'DELETE'):
                    db.execute(f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} "
                               "BEGIN SELECT RAISE(ABORT, 'Immutable history'); END")
            db.execute('INSERT INTO policy VALUES (1,?)', (canonical(value),))
            self.event(db, 'initialized', None, {'policy': value, 'from_version': 0, 'to_version': VERSION})
            db.execute(f'PRAGMA user_version={VERSION}')
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
        return self.status()

    def event(self, db, kind, run_id, payload):
        db.execute('INSERT INTO events(at,kind,run_id,payload) VALUES (?,?,?,?)',
                   (self.now(), kind, run_id, canonical(payload)))

    def policy(self, db):
        row = db.execute('SELECT value FROM policy WHERE id=1').fetchone()
        if row is None:
            raise MissingState('Missing automation policy')
        return validate_policy(json.loads(row[0]))

    def reference(self, relative):
        text(relative, 'reference path', 500)
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts or any(part.startswith('.') for part in path.parts):
            raise InvalidContract('Use a non-hidden project-relative reference')
        resolved = (self.root / path).resolve()
        if (not resolved.is_relative_to(self.root) or not resolved.is_file()
                or any(part.startswith('.') for part in resolved.relative_to(self.root).parts)):
            raise InvalidContract('Reference must identify an existing project file')
        return {'path': path.as_posix(), 'sha256': hashlib.sha256(resolved.read_bytes()).hexdigest()}

    def set_mode(self, mode, evidence=None):
        if mode not in MODES:
            raise ModeBlocked('M1 cannot enable platform writes')
        proof = self.reference(evidence) if evidence else None
        if mode != 'disabled' and proof is None:
            raise ModeBlocked('Enabling a mode requires setup evidence')
        with self.transaction() as db:
            policy = self.policy(db)
            old = policy['mode']
            policy['mode'] = mode
            db.execute('UPDATE policy SET value=? WHERE id=1', (canonical(policy),))
            self.event(db, 'mode_changed', None, {'old': old, 'new': mode, 'evidence': proof})
        return self.status()

    def register(self, spec, expected_revision=None):
        spec = validate_check(spec)
        # Freeze source identity as part of the stored revision, without copying source contents.
        refs = [self.reference(path) for path in spec['source_refs']]
        payload = {'spec': spec, 'sources': refs}
        revision = digest(payload)
        with self.transaction() as db:
            current = db.execute('SELECT revision FROM current_checks WHERE check_id=?', (spec['check_id'],)).fetchone()
            if current and current[0] == revision:
                return {'check_id': spec['check_id'], 'revision': revision, 'changed': False}
            if (current[0] if current else None) != expected_revision:
                raise StaleRevision('Current check revision differs from expected revision')
            if current:
                old = json.loads(db.execute('SELECT spec FROM checks WHERE check_id=? AND revision=?',
                                           (spec['check_id'], current[0])).fetchone()[0])
                if old['spec']['scope'] != spec['scope']:
                    raise InvalidContract('A check cannot change scope')
            db.execute('INSERT OR IGNORE INTO checks VALUES (?,?,?)', (spec['check_id'], revision, canonical(payload)))
            db.execute('INSERT INTO current_checks VALUES (?,?) ON CONFLICT(check_id) DO UPDATE SET revision=excluded.revision',
                       (spec['check_id'], revision))
            self.event(db, 'check_registered', None, {'check_id': spec['check_id'], 'revision': revision,
                                                    'previous_revision': expected_revision})
        return {'check_id': spec['check_id'], 'revision': revision, 'changed': True}

    def current(self, db, check_id, revision):
        row = db.execute('SELECT revision FROM current_checks WHERE check_id=?', (check_id,)).fetchone()
        if row is None:
            raise MissingState('Check not found')
        if row[0] != revision:
            raise StaleRevision('Check was superseded')
        return json.loads(db.execute('SELECT spec FROM checks WHERE check_id=? AND revision=?',
                                     (check_id, revision)).fetchone()[0])

    def gate(self, policy, operation):
        if policy['mode'] == 'disabled' or operation not in policy['allowed_operations']:
            raise ModeBlocked('Policy does not permit this check')
        if operation in ('propose_lineup', 'integrated_review') and policy['mode'] != 'propose':
            raise ModeBlocked('Lineup proposals require propose mode')

    def claim(self, check_id, revision):
        with self.transaction() as db:
            payload = self.current(db, check_id, revision)
            spec = payload['spec']
            policy = self.policy(db)
            self.gate(policy, spec['operation'])
            now = self.now()
            if not instant(spec['run_at']) <= now <= instant(spec['latest_start_at']):
                raise LeaseExpired('Check is not within its start window')
            for source in payload['sources']:
                if self.reference(source['path']) != source:
                    raise StaleRevision('A source changed after check registration')
            if db.execute("SELECT 1 FROM runs WHERE check_id=? AND revision=? AND state='completed'",
                          (check_id, revision)).fetchone():
                raise DuplicateRun('This check revision already completed')
            blocked = db.execute("SELECT state,lease_until FROM runs WHERE scope=? AND state IN ('running','outcome_unknown')",
                                 (spec['scope'],)).fetchall()
            if blocked:
                if any(row['state'] == 'outcome_unknown' or row['lease_until'] <= now for row in blocked):
                    raise IncompletePriorExecution('Inspect and recover the prior execution before claiming this scope')
                raise LeaseConflict('Another run owns this scope')
            run_id, token = uuid.uuid4().hex, uuid.uuid4().hex
            until = min(now + policy['lease_seconds'], instant(spec['expires_at']))
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (run_id, check_id, revision, spec['scope'], token, 'running', now, until, None, digest(policy), None))
            self.event(db, 'claimed', run_id, {'check_id': check_id, 'revision': revision, 'lease_until': utc(until)})
            return {'run_id': run_id, 'token': token, 'lease_until': utc(until), 'revision': revision}

    def owned(self, db, run_id, token):
        row = db.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone()
        if row is None:
            raise MissingState('Run not found')
        if row['token'] != token or row['state'] != 'running':
            raise LeaseConflict('Run token is not active')
        if not row['started'] <= self.now() < row['lease_until']:
            raise LeaseExpired('Run lease expired or clock moved backward')
        self.current(db, row['check_id'], row['revision'])
        return row

    def renew(self, run_id, token):
        with self.transaction() as db:
            row = self.owned(db, run_id, token)
            policy = self.policy(db)
            spec = self.current(db, row['check_id'], row['revision'])['spec']
            self.gate(policy, spec['operation'])
            until = min(self.now() + policy['lease_seconds'], instant(spec['expires_at']))
            db.execute('UPDATE runs SET lease_until=? WHERE run_id=?', (until, run_id))
            self.event(db, 'renewed', run_id, {'lease_until': utc(until)})
        return {'run_id': run_id, 'lease_until': utc(until)}

    def add_reference(self, run_id, token, kind, path):
        if kind not in {'proposal', 'action', 'evidence'}:
            raise InvalidContract('Unknown reference kind')
        reference = self.reference(path)
        with self.transaction() as db:
            self.owned(db, run_id, token)
            db.execute('INSERT INTO refs(run_id,kind,reference,at) VALUES (?,?,?,?)',
                       (run_id, kind, canonical(reference), self.now()))
            self.event(db, 'reference_added', run_id, {'kind': kind, 'reference': reference})
        return reference

    def finish(self, run_id, token, outcome, summary, artifacts=()):
        if outcome not in {'completed', 'failed', 'outcome_unknown'}:
            raise InvalidContract('Unknown run outcome')
        text(summary, 'result summary', 1000)
        if len(artifacts) > 20:
            raise InvalidContract('Use at most 20 artifacts')
        result = {'summary': summary, 'artifacts': [self.reference(path) for path in artifacts]}
        with self.transaction() as db:
            self.owned(db, run_id, token)
            db.execute('UPDATE runs SET state=?,finished=?,result=? WHERE run_id=?',
                       (outcome, self.now(), canonical(result), run_id))
            self.event(db, 'finished', run_id, {'outcome': outcome, **result})
        return {'run_id': run_id, 'state': outcome}

    def recover(self, run_id, resolution, evidence, reason):
        if resolution not in {'safe_to_retry', 'completed'}:
            raise InvalidContract('Unknown recovery resolution')
        proof = self.reference(evidence)
        text(reason, 'recovery reason', 1000)
        with self.transaction() as db:
            row = db.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone()
            if row is None:
                raise MissingState('Run not found')
            if row['state'] == 'running' and row['lease_until'] > self.now():
                raise LeaseConflict('Cannot recover a live lease')
            if row['state'] not in {'running', 'outcome_unknown'}:
                raise InvalidContract('Run does not require recovery')
            state = 'abandoned' if resolution == 'safe_to_retry' else 'completed'
            db.execute('UPDATE runs SET state=?,finished=? WHERE run_id=?', (state, self.now(), run_id))
            self.event(db, 'recovered', run_id, {'resolution': resolution, 'evidence': proof, 'reason': reason,
                                              'previous_state': row['state']})
        return {'run_id': run_id, 'state': state}

    def status(self):
        with self.transaction() as db:
            counts = {row[0]: row[1] for row in db.execute('SELECT state,COUNT(*) FROM runs GROUP BY state')}
            return {'schema_version': VERSION, 'project': str(self.root), 'observed_at': utc(self.now()),
                    'policy': self.policy(db), 'checks': db.execute('SELECT COUNT(*) FROM current_checks').fetchone()[0],
                    'runs': counts, 'events': db.execute('SELECT COUNT(*) FROM events').fetchone()[0],
                    'expired_leases': db.execute("SELECT COUNT(*) FROM runs WHERE state='running' AND lease_until<=?",
                                                (self.now(),)).fetchone()[0],
                    'external_execution': False}

    def context(self, check_id, revision):
        with self.transaction() as db:
            payload = self.current(db, check_id, revision)
            scope = payload['spec']['scope']
            unresolved = db.execute("SELECT run_id,state,check_id,revision,lease_until FROM runs WHERE scope=? "
                                    "AND state IN ('running','outcome_unknown') ORDER BY started DESC LIMIT 21", (scope,)).fetchall()
            refs = db.execute('SELECT refs.run_id,refs.kind,refs.reference FROM refs JOIN runs USING(run_id) '
                              'WHERE runs.scope=? ORDER BY refs.sequence DESC LIMIT 20', (scope,)).fetchall()
            events = db.execute('SELECT events.sequence,events.kind,events.at,events.payload FROM events JOIN runs USING(run_id) '
                                'WHERE runs.scope=? ORDER BY events.sequence DESC LIMIT 10', (scope,)).fetchall()
            return {'schema_version': VERSION, 'observed_at': utc(self.now()), 'check': payload,
                    'revision': revision, 'policy': self.policy(db), 'execution_authority': 'records_only',
                    'unresolved': [dict(row) for row in unresolved[:20]], 'unresolved_truncated': len(unresolved) > 20,
                    'references': [{**dict(row), 'reference': json.loads(row['reference'])} for row in refs],
                    'recent_events': [{**dict(row), 'payload': json.loads(row['payload'])} for row in events],
                    'instructions': ['docs/M1_AUTOMATION.md', 'docs/M0_EXIT_REPORT.md'],
                    'limits': {'references': 20, 'events': 10, 'unresolved': 20},
                    'source_freshness': 'Not evaluated. References identify saved files, not current provider state.'}

    def export(self, output):
        with self.transaction() as db:
            record = {'schema_version': VERSION, 'observed_at': utc(self.now()), 'policy': self.policy(db)}
            for table in ('checks', 'current_checks', 'runs', 'refs', 'events'):
                rows = [dict(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY rowid')]
                for row in rows:
                    row.pop('token', None)
                    for field in ('spec', 'result', 'reference', 'payload'):
                        if field in row and row[field] is not None:
                            row[field] = json.loads(row[field])
                record[table] = rows
        self.save_report(output, record)
        return {'saved': str(output), 'schema_version': VERSION}

    def save_report(self, output, record):
        output = Path(output).resolve()
        if output == self.path or output.name.startswith('state.sqlite3') or output.suffix != '.json':
            raise InvalidContract('Reports require a JSON path outside the database files')
        save_atomic(output, record)
