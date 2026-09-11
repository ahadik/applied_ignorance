"""Local scheduler evidence and serialized, operator-applied reconciliation. No scheduler API calls."""
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import tomllib
import uuid

from fantasy_agent.automation.automation_store import (AutomationStore, InvalidContract, MissingState, UnknownSchema,
                              StaleRevision, IncompletePriorExecution, canonical, digest, instant, text, utc)
from fantasy_agent.core.storage import save_new

MARKER = re.compile(r'^Fantasy Football ownership: ([a-f0-9]{32})/([a-z0-9-]{1,100})/(check|anchor|probe)/([a-f0-9]{64})\.$', re.M)


def marker(installation, key, role, revision):
    value = f'Fantasy Football ownership: {installation}/{key}/{role}/{revision}.'
    if not MARKER.fullmatch(value):
        raise InvalidContract('Invalid scheduling ownership marker')
    return value


def read_local(directory, *, clock=time.time):
    """Read twice to detect changes. The result is local evidence, not an atomic account inventory."""
    directory = Path(directory).resolve()
    started = utc(clock())
    errors, entries, hashes = [], [], {}
    def scan():
        result = {}
        for child in sorted(directory.iterdir()):
            if not child.is_dir():
                continue
            path = child / 'automation.toml'
            if child.is_symlink() or path.is_symlink():
                raise InvalidContract('Inventory contains a symlink')
            result[child.name] = path.read_bytes()
        return result
    try:
        first = scan()
        for name, raw in first.items():
            try:
                value = tomllib.loads(raw.decode())
                if value.get('id') != name or value.get('kind') not in ('heartbeat', 'cron'):
                    raise InvalidContract('Unsupported scheduler record')
                if value.get('status') not in ('ACTIVE', 'PAUSED'):
                    raise InvalidContract('Unknown scheduler status')
                for key in ('prompt', 'rrule', 'name'):
                    text(value.get(key), key, 30000)
                matches = list(MARKER.finditer(value['prompt']))
                owner = dict(zip(('installation', 'key', 'role', 'revision'), matches[0].groups())) if len(matches) == 1 else None
                if len(matches) > 1:
                    raise InvalidContract('Ambiguous ownership')
                target = value.get('target', {})
                config = {'kind': value['kind'], 'status': value['status'], 'rrule': value['rrule'],
                          'name': value['name'], 'prompt_sha256': hashlib.sha256(value['prompt'].encode()).hexdigest(),
                          'target_thread_id': value.get('target_thread_id'),
                          'project_id': target.get('project_id', value.get('project_id')),
                          'cwds': value.get('cwds', []), 'notification_policy': value.get('notification_policy')}
                entries.append({'id': name, 'owner': owner, 'config': config,
                                'fingerprint': digest(config), 'file_sha256': hashlib.sha256(raw).hexdigest()})
                hashes[name] = hashlib.sha256(raw).hexdigest()
            except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
                errors.append('invalid_record:' + name)
        second = scan()
        if first != second:
            errors.append('inventory_changed_during_capture')
    except (OSError, ValueError):
        errors.append('inventory_unavailable_or_incomplete')
    return {'schema_version': 1, 'started_at': started, 'observed_at': utc(clock()),
            'scope': str(directory), 'complete': not errors, 'entries': entries, 'errors': errors,
            'source_hashes': hashes, 'provenance': 'local_files_double_read', 'account_wide': False}


def validate_inventory(value, now, scope):
    if value.get('schema_version') != 1:
        raise UnknownSchema('Unsupported scheduler inventory')
    if not instant(value['started_at']) <= instant(value['observed_at']) <= now:
        raise InvalidContract('Invalid inventory timestamps')
    if now - instant(value['started_at']) > 60 or value['scope'] != scope:
        raise StaleRevision('Inventory is stale or outside the configured local scope')
    if value.get('complete') is not True or value.get('errors'):
        raise InvalidContract('Complete scheduler inventory is required')
    ids = set()
    for entry in value['entries']:
        text(entry['id'], 'task ID')
        if entry['id'] in ids or digest(entry['config']) != entry['fingerprint']:
            raise InvalidContract('Duplicate or changed inventory entries')
        ids.add(entry['id'])


def desired_config(item):
    return {'kind': 'heartbeat', 'status': item['status'], 'rrule': item['rrule'], 'name': item['name'],
            'prompt_sha256': hashlib.sha256(item['prompt'].encode()).hexdigest(),
            'target_thread_id': item['target_thread_id'], 'project_id': None, 'cwds': [],
            'notification_policy': None}


def validate_desired(value, installation, project, now):
    if value.get('schema_version') != 1:
        raise UnknownSchema('Unsupported desired schedule')
    if value.get('installation') != installation or value.get('project') != project:
        raise InvalidContract('Desired schedule belongs to another installation')
    if not instant(value['created_at']) <= now < instant(value['expires_at']):
        raise StaleRevision('Desired schedule expired or is from the future')
    if type(value.get('task_cap')) is not int or not 2 <= value['task_cap'] <= 100:
        raise InvalidContract('Invalid task cap')
    seen = set()
    for item in value['checks']:
        key = item['key']
        if key in seen or item['role'] not in ('check', 'anchor', 'probe'):
            raise InvalidContract('Duplicate key or unknown role')
        seen.add(key)
        expected = marker(installation, key, item['role'], item['revision'])
        if item['prompt'].splitlines()[-1] != expected or len(MARKER.findall(item['prompt'])) != 1:
            raise InvalidContract('Desired prompt lacks exact ownership marker')
        for field in ('name', 'target_thread_id', 'rrule', 'prompt'):
            text(item[field], field, 30000)
        if item['status'] not in ('ACTIVE', 'PAUSED'):
            raise InvalidContract('Invalid desired status')
        if item['role'] == 'probe' and item['status'] != 'PAUSED':
            raise InvalidContract('M3 probes must remain paused')
        if item['role'] == 'check':
            instant(item['run_at'])
            if not now < instant(item['latest_start_at']) < instant(item['expires_at']):
                raise StaleRevision('Deadline check is no longer schedulable')
    return value


def compare(desired, inventory, installation, project, now):
    validate_desired(desired, installation, project, now)
    validate_inventory(inventory, now, inventory['scope'])
    operations, findings, coverage = [], ['plan_issue:' + x for x in desired.get('plan_issues', [])], []
    own = [e for e in inventory['entries'] if e['owner'] and e['owner']['installation'] == installation]
    by_key = {}
    for e in own:
        by_key.setdefault(e['owner']['key'], []).append(e)
    count = len(inventory['entries'])
    for item in desired['checks']:
        records = sorted(by_key.get(item['key'], []), key=lambda e: e['id'])
        config = desired_config(item)
        # Existing notification preferences belong to the user and must survive an update.
        matches = [e for e in records if {**e['config'], 'notification_policy': None} == config]
        if matches:
            keeper = matches[0]
            coverage.append({'key': item['key'], 'task_id': keeper['id'], 'configuration_verified': True,
                             'enabled': keeper['config']['status'] == 'ACTIVE',
                             'deadline_coverage_verified': False})
            for duplicate in records:
                if duplicate['id'] != keeper['id'] and duplicate['config']['status'] == 'ACTIVE':
                    if duplicate['owner']['role'] == 'anchor' or item['role'] == 'anchor':
                        findings.append('protected_anchor_duplicate:' + item['key'])
                    elif duplicate['config']['target_thread_id'] != item['target_thread_id']:
                        findings.append('target_conflict:' + item['key'])
                    else:
                        operations.append({'action': 'disable', 'task_id': duplicate['id'], 'key': item['key'],
                                           'expected': duplicate, 'desired': item})
            continue
        if item['role'] == 'anchor':
            findings.append('protected_anchor_needs_manual_setup:' + item['key'])
            continue
        if records and (len(records) != 1 or records[0]['config']['target_thread_id'] != item['target_thread_id']
                        or records[0]['config']['kind'] != 'heartbeat' or records[0]['owner']['role'] == 'anchor'):
            findings.append('ambiguous_or_foreign_target:' + item['key'])
            continue
        if item['role'] == 'check':
            findings.append('manual_deadline_setup_required:' + item['key'])
            continue
        if records:
            operations.append({'action': 'update', 'task_id': records[0]['id'], 'key': item['key'],
                               'expected': records[0], 'desired': item})
        elif count >= desired['task_cap'] - 2:
            findings.append('capacity_uncovered:' + item['key'])
        else:
            count += 1
            operations.append({'action': 'create', 'task_id': None, 'key': item['key'], 'expected': None, 'desired': item})
    # Cleanup requires explicit keys. Missing M2 data never implies deletion.
    desired_keys = {item['key'] for item in desired['checks']}
    for key in desired.get('retire_keys', []):
        if key in desired_keys:
            raise InvalidContract('Cannot retire a desired key')
        for record in by_key.get(key, []):
            if record['owner']['role'] == 'anchor':
                findings.append('protected_anchor_retirement:' + key)
            elif record['config']['target_thread_id'] != desired['target_thread_id'] or record['config']['kind'] != 'heartbeat':
                findings.append('retirement_target_conflict:' + key)
            else:
                operations.append({'action': 'delete', 'task_id': record['id'], 'key': key,
                                   'expected': record, 'desired': None})
    return {'schema_version': 1, 'installation': installation, 'project': project, 'created_at': utc(now),
            'expires_at': utc(min(now + 60, instant(desired['expires_at']))),
            'desired': desired, 'operations': operations, 'findings': findings, 'coverage': coverage,
            'automatic_reconciliation': False, 'scope': inventory['scope']}


class SchedulerStore:
    def __init__(self, root, *, clock=time.time):
        self.root = Path(root).resolve()
        self.folder = self.root / 'data/automation/scheduler'
        self.path = self.folder / 'state.sqlite3'
        self.clock = clock

    @contextmanager
    def db(self):
        if not self.path.exists():
            raise MissingState('Run schedule-init first')
        db = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise UnknownSchema('Unsupported scheduler database')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def init(self, directory=None):
        if self.path.exists():
            with self.db() as db:
                return self.config(db)
        self.folder.mkdir(parents=True, exist_ok=True)
        directory = Path(directory or Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'automations').resolve()
        db = sqlite3.connect(self.path)
        try:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE config(value TEXT NOT NULL)')
            db.execute('CREATE TABLE records(id TEXT PRIMARY KEY, kind TEXT NOT NULL, at REAL NOT NULL, value TEXT NOT NULL)')
            db.execute('CREATE TABLE pending(id TEXT PRIMARY KEY, token TEXT NOT NULL, state TEXT NOT NULL, at REAL NOT NULL, value TEXT NOT NULL)')
            for action in ('UPDATE', 'DELETE'):
                db.execute(f"CREATE TRIGGER history_{action.lower()} BEFORE {action} ON records BEGIN SELECT RAISE(ABORT,'Immutable scheduler history'); END")
            config = {'installation': uuid.uuid4().hex, 'project': str(self.root), 'inventory_scope': str(directory),
                      'automatic_reconciliation': False, 'exact_one_off_verified': False}
            db.execute('INSERT INTO config VALUES (?)', (canonical(config),))
            db.execute('PRAGMA user_version=1')
            db.commit()
            return config
        finally:
            db.close()

    def config(self, db):
        config = json.loads(db.execute('SELECT value FROM config').fetchone()[0])
        if config['project'] != str(self.root):
            raise InvalidContract('Scheduler installation belongs to another checkout')
        return config

    def save(self, db, kind, value):
        identifier = uuid.uuid4().hex
        db.execute('INSERT INTO records VALUES (?,?,?,?)', (identifier, kind, self.clock(), canonical(value)))
        return identifier

    def get(self, db, identifier, kind):
        row = db.execute('SELECT value FROM records WHERE id=? AND kind=?', (identifier, kind)).fetchone()
        if row is None:
            raise MissingState('Scheduler record not found')
        return json.loads(row[0])

    def inventory(self, imported=None):
        with self.db() as db:
            config = self.config(db)
            value = read_local(config['inventory_scope'], clock=self.clock) if imported is None else imported
            # Only the local reader can establish trusted inventory in this milestone.
            value = {**value, 'trusted_local_read': imported is None}
            identifier = self.save(db, 'inventory', value)
        return {'inventory_id': identifier, 'complete': value.get('complete'),
                'trusted_local_read': value['trusted_local_read'], 'entries': len(value.get('entries', [])),
                'errors': value.get('errors', []), 'scope': value.get('scope')}

    def checked_inventory(self, db, identifier):
        inv = self.get(db, identifier, 'inventory')
        config = self.config(db)
        if inv.get('trusted_local_read') is not True:
            raise InvalidContract('Imported declarations do not prove scheduler state')
        validate_inventory(inv, self.clock(), config['inventory_scope'])
        return inv

    def diff(self, desired, inventory_id):
        with self.db() as db:
            config = self.config(db)
            inv = self.checked_inventory(db, inventory_id)
            report = compare(desired, inv, config['installation'], config['project'], self.clock())
            report['inventory_id'] = inventory_id
            if db.execute("SELECT 1 FROM pending WHERE state IN ('pending','reported','unknown')").fetchone():
                report['findings'].append('unresolved_scheduler_operation')
                report['operations'] = []
            identifier = self.save(db, 'diff', report)
        return {'diff_id': identifier, **report}

    def begin(self, diff_id, index):
        with self.db() as db:
            if db.execute("SELECT 1 FROM pending WHERE state IN ('pending','reported','unknown')").fetchone():
                raise IncompletePriorExecution('Verify the prior scheduler operation before another change')
            report = self.get(db, diff_id, 'diff')
            if not instant(report['created_at']) <= self.clock() < instant(report['expires_at']):
                raise StaleRevision('Scheduler diff expired')
            inv = self.checked_inventory(db, report['inventory_id'])
            current = read_local(self.config(db)['inventory_scope'], clock=self.clock)
            if not current['complete'] or current['source_hashes'] != inv['source_hashes']:
                raise StaleRevision('Scheduler inventory changed before the operation')
            if type(index) is not int or not 0 <= index < len(report['operations']):
                raise InvalidContract('Invalid operation index')
            op = report['operations'][index]
            identifier, token = uuid.uuid4().hex, uuid.uuid4().hex
            value = {'operation': op, 'diff_id': diff_id, 'before_inventory': report['inventory_id'],
                     'returned_task_id': None, 'reported_at': None}
            db.execute('INSERT INTO pending VALUES (?,?,?,?,?)', (identifier, token, 'pending', self.clock(), canonical(value)))
            self.save(db, 'operation_started', {'operation_id': identifier, **value})
        return {'operation_id': identifier, 'token': token, 'action': op['action'],
                'apply_before': report['expires_at'],
                'tool': 'automation_update', 'arguments': self.arguments(op), 'automatic_execution': False}

    def arguments(self, op):
        if op['action'] == 'delete':
            return {'mode': 'delete', 'id': op['task_id']}
        if op['action'] == 'disable':
            # Preserve the complete current tool-visible fields during a pause.
            path = Path(self.init()['inventory_scope']) / op['task_id'] / 'automation.toml'
            raw = tomllib.loads(path.read_text())
            item = {k: raw[k] for k in ('name', 'prompt', 'rrule', 'target_thread_id')}
            item['status'] = 'PAUSED'
        else:
            item = {k: op['desired'][k] for k in ('name', 'prompt', 'rrule', 'target_thread_id', 'status')}
        args = {'mode': 'create' if op['action'] == 'create' else 'update', 'kind': 'heartbeat', **item}
        args['targetThreadId'] = args.pop('target_thread_id')
        if op['task_id']:
            args['id'] = op['task_id']
            args['notificationPolicy'] = op['expected']['config']['notification_policy']
        return args

    def record(self, operation_id, token, outcome, task_id, evidence):
        if outcome not in ('success', 'unknown', 'failed'):
            raise InvalidContract('Invalid operation outcome')
        proof = AutomationStore(self.root).reference(evidence)
        with self.db() as db:
            row = db.execute('SELECT * FROM pending WHERE id=?', (operation_id,)).fetchone()
            if row is None or row['token'] != token or row['state'] != 'pending':
                raise InvalidContract('Operation token is not active')
            value = json.loads(row['value'])
            if task_id:
                text(task_id, 'returned task ID')
            if outcome == 'success' and value['operation']['action'] == 'create' and not task_id:
                raise InvalidContract('Successful creation requires the returned task ID')
            value.update(returned_task_id=task_id, reported_at=self.clock(), evidence=proof, reported_outcome=outcome)
            db.execute('UPDATE pending SET state=?,value=? WHERE id=?',
                       ('reported' if outcome == 'success' else 'unknown', canonical(value), operation_id))
            self.save(db, 'operation_reported', {'operation_id': operation_id, **value})
        return {'operation_id': operation_id, 'verified': False, 'read_back_required': True}

    def verify(self, operation_id, inventory_id):
        with self.db() as db:
            inv = self.checked_inventory(db, inventory_id)
            row = db.execute('SELECT * FROM pending WHERE id=?', (operation_id,)).fetchone()
            if row is None:
                raise MissingState('Scheduler operation not found')
            value = json.loads(row['value'])
            if instant(inv['started_at']) <= max(row['at'], value.get('reported_at') or row['at']):
                raise StaleRevision('Read-back must follow the scheduler operation')
            op = value['operation']
            config = self.config(db)
            records = [e for e in inv['entries'] if e['owner'] and e['owner']['installation'] == config['installation']
                       and e['owner']['key'] == op['key']]
            exact = []
            if op['action'] in ('create', 'update'):
                expected = desired_config(op['desired'])
                exact = [e for e in records if {**e['config'], 'notification_policy': None} == expected]
                success = len(records) == 1 and len(exact) == 1
                expected_id = value['returned_task_id'] or op['task_id']
                if expected_id and success:
                    success = exact[0]['id'] == expected_id
            elif op['action'] == 'delete':
                success = not any(e['id'] == op['task_id'] for e in inv['entries'])
            else:
                exact = [e for e in records if e['id'] == op['task_id']]
                expected = {**op['expected']['config'], 'status': 'PAUSED'}
                success = len(exact) == 1 and exact[0]['config'] == expected
            result = {'operation_id': operation_id, 'inventory_id': inventory_id, 'verified': success,
                      'task_id': exact[0]['id'] if success and exact else op['task_id'],
                      'scope': inv['scope'], 'provenance': inv['provenance'], 'deadline_coverage_verified': False}
            self.save(db, 'verification', result)
            if success:
                db.execute("UPDATE pending SET state='verified' WHERE id=?", (operation_id,))
        return result

    def export(self, output):
        with self.db() as db:
            value = {'config': self.config(db), 'records': [dict(r) for r in db.execute('SELECT * FROM records ORDER BY at,rowid')],
                     'pending': [dict(r) for r in db.execute('SELECT id,state,at,value FROM pending ORDER BY at')],
                     'observed_at': utc(self.clock())}
        for row in value['records'] + value['pending']:
            row['value'] = json.loads(row['value'])
        save_new(output, value)
        return {'saved': str(output)}

    def resolve_not_applied(self, operation_id, inventory_id, evidence, reason):
        """Record an explicit operator decision after external completion is settled."""
        proof = AutomationStore(self.root).reference(evidence)
        text(reason, 'recovery reason', 1000)
        with self.db() as db:
            inv = self.checked_inventory(db, inventory_id)
            row = db.execute('SELECT * FROM pending WHERE id=?', (operation_id,)).fetchone()
            if row is None or row['state'] not in ('pending', 'reported', 'unknown'):
                raise InvalidContract('Operation does not require recovery')
            value = json.loads(row['value'])
            if instant(inv['started_at']) <= max(row['at'], value.get('reported_at') or row['at']):
                raise StaleRevision('Recovery inventory must follow the operation')
            before = self.get(db, value['before_inventory'], 'inventory')
            installation = self.config(db)['installation']
            def affected(snapshot):
                return sorted((e['id'], e['fingerprint']) for e in snapshot['entries'] if e['owner']
                              and e['owner']['installation'] == installation
                              and e['owner']['key'] == value['operation']['key'])
            if affected(before) != affected(inv):
                raise InvalidContract('Affected scheduler state differs from the pre-operation state')
            result = {'operation_id': operation_id, 'resolution': 'operator_confirmed_not_applied',
                      'inventory_id': inventory_id, 'evidence': proof, 'reason': reason,
                      'basis': 'explicit_operator_decision_plus_unchanged_local_state'}
            self.save(db, 'recovery', result)
            db.execute("UPDATE pending SET state='resolved_not_applied' WHERE id=?", (operation_id,))
        return result

    def probe_spec(self, target_thread, version=1, retire=False):
        config = self.init()
        key = 'm3-disposable-probe'
        revision = digest({'probe_version': version})
        prompt = ('This paused task tests scheduler configuration only. If manually invoked, report that it is an M3 probe and stop. '
                  'Do not call providers, change files, change Sleeper, or create other tasks.\n' +
                  marker(config['installation'], key, 'probe', revision))
        return {'schema_version': 1, 'installation': config['installation'], 'project': str(self.root),
                'created_at': utc(self.clock()), 'expires_at': utc(self.clock() + 3600), 'task_cap': 10,
                'target_thread_id': target_thread, 'retire_keys': [key] if retire else [],
                'checks': [] if retire else [{'key': key, 'role': 'probe', 'revision': revision,
                  'name': f'Fantasy Football M3 disposable probe v{version}', 'prompt': prompt,
                  'status': 'PAUSED', 'target_thread_id': target_thread,
                  'rrule': f'RRULE:FREQ=DAILY;BYHOUR=9;BYMINUTE={version};BYSECOND=0'}]}

    def from_plan(self, plan, target_thread):
        config = self.init()
        if plan.get('schema_version') != 1 or digest({k: v for k, v in plan.items() if k != 'plan_id'}) != plan.get('plan_id'):
            raise InvalidContract('Invalid M2 plan checksum')
        if not instant(plan['as_of']) <= self.clock() < instant(plan['horizon']['end']):
            raise StaleRevision('M2 plan is outside its planning horizon')
        for reference in plan['source_references']:
            if AutomationStore(self.root).reference(reference['path']) != reference:
                raise StaleRevision('M2 source changed after planning')
        checks = []
        for check in plan['desired_checks']:
            spec = check['spec']
            if instant(spec['latest_start_at']) <= self.clock():
                continue
            checks.append({'key': check['check_id'], 'role': 'check', 'revision': check['revision'],
                           'name': 'Fantasy Football deadline ' + check['check_id'][-12:],
                           'prompt': check['prompt'] + '\n' + marker(config['installation'], check['check_id'], 'check', check['revision']),
                           'status': 'ACTIVE', 'target_thread_id': target_thread,
                           'rrule': 'MANUAL_EXACT_DATE_REQUIRED',
                           **{key: spec[key] for key in ('run_at', 'latest_start_at', 'expires_at')}})
        return {'schema_version': 1, 'installation': config['installation'], 'project': str(self.root),
                'created_at': utc(self.clock()), 'expires_at': utc(min(self.clock() + 300, instant(plan['horizon']['end']))),
                'task_cap': plan['capacity']['task_cap'], 'target_thread_id': target_thread, 'retire_keys': [],
                'checks': checks, 'plan_id': plan['plan_id'], 'plan_issues': plan['issues'],
                'manual_instructions': [{'key': c['key'], 'run_at': c['run_at'], 'latest_start_at': c['latest_start_at'],
                                         'instruction': 'Register the exact M1 check. Configure this date and time through supported controls. '
                                         'Verify the prompt and target. Explicitly remove the task after completion. '
                                         'Do not substitute an unverified recurring schedule.'} for c in checks]}
