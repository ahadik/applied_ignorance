from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fantasy_agent.automation.automation import main
from fantasy_agent.automation.automation_store import (AutomationStore, MissingState, UnknownSchema, InvalidContract,
                              StaleRevision, ModeBlocked, DuplicateRun, LeaseConflict, LeaseExpired,
                              IncompletePriorExecution, DEFAULT_POLICY, validate_check, validate_policy)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = datetime(2026, 9, 11, 12, tzinfo=timezone.utc).timestamp()
        self.store = AutomationStore(self.root, clock=lambda: self.now)
        (self.root / 'evidence.json').write_text('{"review":"safe"}')
        self.spec = {'schema_version': 1, 'check_id': 'league:week1:inspect', 'scope': 'league:team1',
                     'operation': 'inspect_sleeper', 'season': 2026, 'week': 1,
                     'run_at': '2026-09-11T11:59:00Z', 'latest_start_at': '2026-09-11T12:50:00Z',
                     'expires_at': '2026-09-11T13:00:00Z', 'source_refs': ['evidence.json']}

    def ready(self):
        self.store.initialize()
        self.store.set_mode('observe', 'evidence.json')
        return self.store.register(self.spec)['revision']

    def test_missing_state_and_idempotent_init_preserve_records(self):
        with self.assertRaises(MissingState):
            self.store.status()
        self.assertFalse(self.store.path.exists())
        rev = self.ready()
        run = self.store.claim(self.spec['check_id'], rev)
        before = self.store.status()
        self.store.initialize()
        self.assertEqual(self.store.status(), before)
        self.assertEqual(self.store.context(self.spec['check_id'], rev)['unresolved'][0]['run_id'], run['run_id'])

    def test_default_disabled_and_proposal_mode_gates(self):
        self.store.initialize()
        rev = self.store.register(self.spec)['revision']
        with self.assertRaises(ModeBlocked):
            self.store.claim(self.spec['check_id'], rev)
        with self.assertRaises(ModeBlocked):
            self.store.set_mode('observe')
        with self.assertRaises(ModeBlocked):
            self.store.set_mode('authorized_apply', 'evidence.json')
        self.store.set_mode('observe', 'evidence.json')
        changed = {**self.spec, 'operation': 'propose_lineup'}
        rev = self.store.register(changed, rev)['revision']
        with self.assertRaises(ModeBlocked):
            self.store.claim(self.spec['check_id'], rev)
        self.store.set_mode('propose', 'evidence.json')
        self.store.claim(self.spec['check_id'], rev)

    def test_atomic_duplicate_claims_across_connections(self):
        rev = self.ready()
        def claim(_):
            try:
                return AutomationStore(self.root, clock=lambda: self.now).claim(self.spec['check_id'], rev)
            except LeaseConflict:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(claim, range(8)))
        self.assertEqual(sum(value is not None for value in results), 1)
        self.assertEqual(self.store.status()['runs'], {'running': 1})

    def test_completed_delivery_does_not_repeat(self):
        rev = self.ready()
        run = self.store.claim(self.spec['check_id'], rev)
        self.store.finish(run['run_id'], run['token'], 'completed', 'Inspected')
        with self.assertRaises(DuplicateRun):
            self.store.claim(self.spec['check_id'], rev)

    def test_crash_rollback_does_not_leave_half_claim(self):
        rev = self.ready()
        original = self.store.event
        def fail(db, kind, run_id, payload):
            if kind == 'claimed':
                raise RuntimeError('simulated crash before commit')
            return original(db, kind, run_id, payload)
        self.store.event = fail
        with self.assertRaises(RuntimeError):
            self.store.claim(self.spec['check_id'], rev)
        self.store.event = original
        self.assertEqual(self.store.status()['runs'], {})
        self.store.claim(self.spec['check_id'], rev)

    def test_expired_lease_requires_explicit_recovery_and_fences_old_worker(self):
        rev = self.ready()
        first = self.store.claim(self.spec['check_id'], rev)
        self.now += 300
        restarted = AutomationStore(self.root, clock=lambda: self.now)
        with self.assertRaises(LeaseExpired):
            restarted.finish(first['run_id'], first['token'], 'completed', 'Late result')
        with self.assertRaises(IncompletePriorExecution):
            restarted.claim(self.spec['check_id'], rev)
        restarted.recover(first['run_id'], 'safe_to_retry', 'evidence.json', 'Inspection confirmed no external action')
        second = restarted.claim(self.spec['check_id'], rev)
        self.assertNotEqual(first['token'], second['token'])
        with self.assertRaises(LeaseConflict):
            restarted.renew(first['run_id'], first['token'])
        self.assertEqual(restarted.status()['runs'], {'abandoned': 1, 'running': 1})

    def test_unknown_outcome_blocks_other_checks_in_scope(self):
        rev = self.ready()
        run = self.store.claim(self.spec['check_id'], rev)
        self.store.finish(run['run_id'], run['token'], 'outcome_unknown', 'Inspection needed')
        other = {**self.spec, 'check_id': 'other'}
        other_rev = self.store.register(other)['revision']
        with self.assertRaises(IncompletePriorExecution):
            self.store.claim('other', other_rev)
        self.store.recover(run['run_id'], 'completed', 'evidence.json', 'Reconciled saved result')
        self.store.claim('other', other_rev)

    def test_stale_revision_changed_source_and_live_recovery(self):
        rev = self.ready()
        with self.assertRaises(StaleRevision):
            self.store.register({**self.spec, 'week': 2})
        run = self.store.claim(self.spec['check_id'], rev)
        with self.assertRaises(LeaseConflict):
            self.store.recover(run['run_id'], 'safe_to_retry', 'evidence.json', 'Too early')
        new = self.store.register({**self.spec, 'week': 2}, rev)['revision']
        with self.assertRaises(StaleRevision):
            self.store.finish(run['run_id'], run['token'], 'completed', 'Stale')
        with self.assertRaises(StaleRevision):
            self.store.claim(self.spec['check_id'], rev)
        (self.root / 'evidence.json').write_text('{}')
        with self.assertRaises(StaleRevision):
            self.store.claim(self.spec['check_id'], new)

    def test_unknown_versions_and_nonempty_unversioned_database_fail_closed(self):
        self.store.initialize()
        with sqlite3.connect(self.store.path) as db:
            db.execute('PRAGMA user_version=99')
        with self.assertRaises(UnknownSchema):
            self.store.status()
        with self.assertRaises(UnknownSchema):
            self.store.initialize()
        with sqlite3.connect(self.store.path) as db:
            db.execute('PRAGMA user_version=0')
        with self.assertRaises(UnknownSchema):
            self.store.initialize()

    def test_event_and_reference_history_is_append_only(self):
        rev = self.ready()
        run = self.store.claim(self.spec['check_id'], rev)
        self.store.add_reference(run['run_id'], run['token'], 'proposal', 'evidence.json')
        with sqlite3.connect(self.store.path) as db:
            for table in ('events', 'refs', 'checks'):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(f'DELETE FROM {table}')
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(f'UPDATE {table} SET rowid=rowid')
        self.store.finish(run['run_id'], run['token'], 'completed', 'Done', ['evidence.json'])
        context = self.store.context(self.spec['check_id'], rev)
        self.assertEqual(context['references'][0]['kind'], 'proposal')
        self.assertNotIn(run['token'], json.dumps(context))
        self.store.export(self.root / 'export.json')
        exported = json.loads((self.root / 'export.json').read_text())
        self.assertNotIn(run['token'], json.dumps(exported))
        self.assertEqual(len(exported['runs']), 1)
        self.assertTrue(any(event['kind'] == 'finished' for event in exported['events']))

    def test_path_escape_and_hidden_files_rejected(self):
        self.ready()
        (self.root / '.env').write_text('do not read')
        (self.root / 'escape').symlink_to('/etc/hosts')
        for path in ('.env', '../file', '/etc/hosts', 'escape', 'missing.json'):
            with self.assertRaises(InvalidContract):
                self.store.reference(path)

    def test_renewal_and_clock_boundaries(self):
        rev = self.ready()
        run = self.store.claim(self.spec['check_id'], rev)
        self.now += 200
        self.store.renew(run['run_id'], run['token'])
        self.now += 101
        self.store.finish(run['run_id'], run['token'], 'failed', 'Safe failure')
        self.now += 3600
        with self.assertRaises(LeaseExpired):
            self.store.claim(self.spec['check_id'], rev)

    def test_contract_validation_and_equivalent_time_revisions(self):
        with self.assertRaises(InvalidContract):
            validate_check({**self.spec, 'expires_at': self.spec['latest_start_at']})
        with self.assertRaises(UnknownSchema):
            validate_check({**self.spec, 'schema_version': 99})
        with self.assertRaises(InvalidContract):
            validate_policy({**DEFAULT_POLICY, 'lease_seconds': True})
        rev = self.ready()
        alternate = {**self.spec, 'run_at': '2026-09-11T07:59:00-04:00'}
        self.assertEqual(self.store.register(alternate)['revision'], rev)

    def test_cli_init_status_and_typed_missing_state(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(['--root', str(self.root), 'status']), 1)
        self.assertEqual(json.loads(output.getvalue())['error'], 'MissingState')
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(['--root', str(self.root), 'init']), 0)
        self.assertEqual(json.loads(output.getvalue())['policy']['mode'], 'disabled')

    def test_invalid_json_contract_types_fail_with_typed_errors(self):
        for version in (True, 1.0, None, []):
            with self.assertRaises(UnknownSchema):
                validate_check({**self.spec, 'schema_version': version})
            with self.assertRaises(UnknownSchema):
                validate_policy({**DEFAULT_POLICY, 'schema_version': version})
        for operations in ([{}], [[]], ['unknown'], ['inspect_sleeper'] * 2):
            with self.assertRaises(InvalidContract):
                validate_policy({**DEFAULT_POLICY, 'allowed_operations': operations})
        with self.assertRaises(InvalidContract):
            validate_check({**self.spec, 'operation': {}})
        with self.assertRaises(InvalidContract):
            validate_check({**self.spec, 'source_refs': [None]})
        with self.assertRaises(UnknownSchema):
            self.store.initialize({})

    def test_disable_stops_renewal_but_allows_result_recording(self):
        rev = self.ready()
        run = self.store.claim(self.spec['check_id'], rev)
        self.store.set_mode('disabled')
        with self.assertRaises(ModeBlocked):
            self.store.renew(run['run_id'], run['token'])
        self.store.finish(run['run_id'], run['token'], 'failed', 'Stopped when disabled')
        with self.assertRaises(ModeBlocked):
            self.store.claim(self.spec['check_id'], rev)

    def test_lease_cannot_extend_past_check_expiry(self):
        self.spec['latest_start_at'] = '2026-09-11T12:00:10Z'
        self.spec['expires_at'] = '2026-09-11T12:00:30Z'
        rev = self.ready()
        run = self.store.claim(self.spec['check_id'], rev)
        self.now += 20
        self.assertEqual(self.store.renew(run['run_id'], run['token'])['lease_until'], run['lease_until'])
        self.now += 10
        with self.assertRaises(LeaseExpired):
            self.store.add_reference(run['run_id'], run['token'], 'evidence', 'evidence.json')

    def test_export_failure_preserves_last_complete_export_and_database(self):
        self.ready()
        output = self.root / 'export.json'
        self.store.export(output)
        previous = output.read_bytes()
        with patch('fantasy_agent.core.storage.os.replace', side_effect=OSError('simulated failed replacement')):
            with self.assertRaises(OSError):
                self.store.export(output)
        self.assertEqual(output.read_bytes(), previous)
        with self.assertRaises(InvalidContract):
            self.store.export(self.store.path)
        self.assertEqual(self.store.status()['checks'], 1)
        self.assertIsInstance(json.loads(previous)['checks'][0]['spec'], dict)

    def test_bounded_context_preserves_file_identity_without_contents(self):
        rev = self.ready()
        original = self.store.context(self.spec['check_id'], rev)['check']['sources'][0]
        run = self.store.claim(self.spec['check_id'], rev)
        for _ in range(25):
            self.store.add_reference(run['run_id'], run['token'], 'evidence', 'evidence.json')
        packet = self.store.context(self.spec['check_id'], rev)
        self.assertEqual(len(packet['references']), 20)
        self.assertEqual(len(packet['recent_events']), 10)
        self.assertNotIn('"review"', json.dumps(packet))
        (self.root / 'evidence.json').write_text('{"new":"content"}')
        self.assertEqual(self.store.context(self.spec['check_id'], rev)['check']['sources'][0], original)

    def test_policy_operation_allowlist_and_hidden_symlink_target(self):
        self.store.initialize({**DEFAULT_POLICY, 'allowed_operations': ['validate_lineup']})
        self.store.set_mode('observe', 'evidence.json')
        rev = self.store.register(self.spec)['revision']
        with self.assertRaises(ModeBlocked):
            self.store.claim(self.spec['check_id'], rev)
        (self.root / '.env').write_text('secret')
        (self.root / 'alias').symlink_to(self.root / '.env')
        with self.assertRaises(InvalidContract):
            self.store.reference('alias')
