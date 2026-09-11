"""Scheduler tests use simulated TOML records in temporary directories. No live tools."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fantasy_agent.automation.automation_reconcile import SchedulerStore, read_local, marker, desired_config
from fantasy_agent.automation.automation_store import InvalidContract, StaleRevision, IncompletePriorExecution, digest, instant, utc


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.directory = self.root / 'local-automations'
        self.directory.mkdir()
        self.now = instant('2026-09-11T12:00:00Z')
        self.store = SchedulerStore(self.root, clock=lambda: self.now)
        self.config = self.store.init(self.directory)
        self.desired = self.store.probe_spec('test-thread')
        (self.root / 'receipt.json').write_text('{"result":"simulated"}')

    def write_task(self, task_id, item=None, **changes):
        item = dict(item or self.desired['checks'][0])
        value = {'version': 1, 'id': task_id, 'kind': 'heartbeat',
                 **{key: item[key] for key in ('name', 'prompt', 'status', 'target_thread_id', 'rrule')}}
        value.update(changes)
        folder = self.directory / task_id
        folder.mkdir(exist_ok=True)
        (folder / 'automation.toml').write_text('\n'.join(f'{k} = {json.dumps(v)}' for k, v in value.items()))

    def diff(self, desired=None):
        inv = self.store.inventory()
        return self.store.diff(desired or self.desired, inv['inventory_id'])

    def begin(self):
        diff = self.diff()
        return self.store.begin(diff['diff_id'], 0)

    def verify(self, operation):
        self.now += 1
        inv = self.store.inventory()
        return self.store.verify(operation['operation_id'], inv['inventory_id'])

    def test_missing_matching_and_changed_are_idempotent(self):
        self.assertEqual(self.diff()['operations'][0]['action'], 'create')
        self.write_task('ours')
        self.assertEqual(self.diff()['operations'], [])
        self.assertTrue(self.diff()['coverage'][0]['configuration_verified'])
        self.assertFalse(self.diff()['coverage'][0]['enabled'])
        changed = self.store.probe_spec('test-thread', 2)
        self.assertEqual(self.diff(changed)['operations'][0]['action'], 'update')

    def test_incomplete_malformed_and_stale_inventory_fail_closed(self):
        child = self.directory / 'broken'
        child.mkdir()
        inv = self.store.inventory()
        self.assertFalse(inv['complete'])
        with self.assertRaises(InvalidContract):
            self.store.diff(self.desired, inv['inventory_id'])
        child.rmdir()
        inv = self.store.inventory()
        self.now += 61
        with self.assertRaises(StaleRevision):
            self.store.diff(self.desired, inv['inventory_id'])

    def test_imported_claim_cannot_certify_coverage(self):
        self.write_task('ours')
        data = read_local(self.directory, clock=lambda: self.now)
        inv = self.store.inventory(data)
        with self.assertRaises(InvalidContract):
            self.store.diff(self.desired, inv['inventory_id'])

    def test_unrelated_tasks_and_wrong_target_are_preserved(self):
        self.write_task('unrelated', prompt='Someone else owns this task')
        self.assertEqual(self.diff()['operations'][0]['action'], 'create')
        self.write_task('ours', target_thread_id='another-thread')
        diff = self.diff()
        self.assertEqual(diff['operations'], [])
        self.assertTrue(any('foreign_target' in x for x in diff['findings']))
        retired = self.store.probe_spec('test-thread', retire=True)
        self.assertEqual(self.diff(retired)['operations'], [])

    def test_duplicates_pause_only_after_exact_keeper_exists(self):
        self.write_task('keeper')
        self.write_task('duplicate', status='ACTIVE')
        diff = self.diff()
        self.assertEqual([x['action'] for x in diff['operations']], ['disable'])
        self.assertEqual(diff['operations'][0]['task_id'], 'duplicate')
        self.write_task('keeper', name='wrong')
        self.assertEqual(self.diff()['operations'], [])

    def test_daily_anchor_never_updates_or_retires(self):
        item = self.desired['checks'][0]
        item.update(role='anchor', status='ACTIVE')
        item['prompt'] = 'Daily planning.\n' + marker(self.config['installation'], item['key'], 'anchor', item['revision'])
        self.assertEqual(self.diff()['operations'], [])
        self.write_task('anchor')
        self.assertEqual(self.diff()['operations'], [])
        self.assertEqual(self.diff(self.store.probe_spec('test-thread', retire=True))['operations'], [])

    def test_capacity_accounts_for_unrelated_and_reserves_two_slots(self):
        self.desired['task_cap'] = 3
        self.write_task('unrelated', prompt='Unrelated')
        diff = self.diff()
        self.assertEqual(diff['operations'], [])
        self.assertTrue(any('capacity' in x for x in diff['findings']))

    def test_serialization_and_inventory_change_before_begin(self):
        diff = self.diff()
        self.write_task('unrelated', prompt='Unrelated')
        with self.assertRaises(StaleRevision):
            self.store.begin(diff['diff_id'], 0)
        op = self.begin()
        with self.assertRaises(IncompletePriorExecution):
            self.store.begin(diff['diff_id'], 0)
        self.assertEqual(self.diff()['operations'], [])
        self.assertTrue(op['token'])

    def test_lost_create_response_recovers_by_exact_read_back(self):
        op = self.begin()
        self.write_task('created-despite-timeout')
        self.store.record(op['operation_id'], op['token'], 'unknown', None, 'receipt.json')
        restarted = SchedulerStore(self.root, clock=lambda: self.now)
        self.store = restarted
        result = self.verify(op)
        self.assertTrue(result['verified'])
        self.assertEqual(result['task_id'], 'created-despite-timeout')
        self.assertEqual(self.diff()['operations'], [])

    def test_unknown_absence_never_authorizes_blind_retry(self):
        op = self.begin()
        self.store.record(op['operation_id'], op['token'], 'failed', None, 'receipt.json')
        self.assertFalse(self.verify(op)['verified'])
        self.now += 500
        with self.assertRaises(IncompletePriorExecution):
            self.store.begin('anything', 0)

    def test_success_requires_returned_id_and_separate_read_back(self):
        op = self.begin()
        with self.assertRaises(InvalidContract):
            self.store.record(op['operation_id'], op['token'], 'success', None, 'receipt.json')
        self.store.record(op['operation_id'], op['token'], 'success', 'ours', 'receipt.json')
        self.assertFalse(self.verify(op)['verified'])
        self.write_task('ours')
        self.assertTrue(self.verify(op)['verified'])

    def test_stale_preoperation_inventory_cannot_verify(self):
        inv = self.store.inventory()
        op = self.begin()
        with self.assertRaises(StaleRevision):
            self.store.verify(op['operation_id'], inv['inventory_id'])

    def test_wrong_returned_id_and_duplicate_create_do_not_pass(self):
        op = self.begin()
        self.store.record(op['operation_id'], op['token'], 'success', 'reported', 'receipt.json')
        self.write_task('other')
        self.assertFalse(self.verify(op)['verified'])
        self.write_task('reported')
        self.assertFalse(self.verify(op)['verified'])

    def test_notification_preferences_survive_update(self):
        self.write_task('ours', notification_policy='failed_runs_only')
        diff = self.diff(self.store.probe_spec('test-thread', 2))
        op = self.store.begin(diff['diff_id'], 0)
        self.assertEqual(op['arguments']['notificationPolicy'], 'failed_runs_only')

    def test_expired_desired_and_bad_timestamp_rejected(self):
        self.desired['expires_at'] = utc(self.now)
        with self.assertRaises(StaleRevision):
            self.diff()
        self.desired['expires_at'] = 'tomorrow'
        with self.assertRaises(InvalidContract):
            self.diff()

    def test_delete_verified_only_after_absence(self):
        self.write_task('ours')
        diff = self.diff(self.store.probe_spec('test-thread', retire=True))
        op = self.store.begin(diff['diff_id'], 0)
        self.assertFalse(self.verify(op)['verified'])
        (self.directory / 'ours/automation.toml').unlink()
        (self.directory / 'ours').rmdir()
        self.assertTrue(self.verify(op)['verified'])

    def test_history_append_only_export_omits_token(self):
        op = self.begin()
        with sqlite3.connect(self.store.path) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM records')
        output = self.root / 'export.json'
        self.store.export(output)
        self.assertNotIn(op['token'], output.read_text())

    def test_inventory_change_during_capture_detected(self):
        self.write_task('ours')
        original = Path.read_bytes
        calls = []
        def read(path):
            raw = original(path)
            calls.append(path)
            return raw if len(calls) == 1 else raw + b'\n'
        with patch.object(Path, 'read_bytes', read):
            inventory = read_local(self.directory, clock=lambda: self.now)
        self.assertFalse(inventory['complete'])

    def test_real_deadline_requires_manual_setup_under_m0_limits(self):
        item = self.desired['checks'][0]
        item.update(role='check', status='ACTIVE', run_at=utc(self.now+60),
                    latest_start_at=utc(self.now+120), expires_at=utc(self.now+180))
        item['prompt'] = 'Read the saved check.\n' + marker(self.config['installation'], item['key'], 'check', item['revision'])
        diff = self.diff()
        self.assertEqual(diff['operations'], [])
        self.assertTrue(any('manual_deadline' in x for x in diff['findings']))

    def test_explicit_recovery_requires_unchanged_state_and_preserves_history(self):
        op = self.begin()
        self.now += 1
        self.write_task('late-create')
        inv = self.store.inventory()
        with self.assertRaises(InvalidContract):
            self.store.resolve_not_applied(op['operation_id'], inv['inventory_id'], 'receipt.json', 'Inspected')
        (self.directory / 'late-create/automation.toml').unlink()
        (self.directory / 'late-create').rmdir()
        inv = self.store.inventory()
        result = self.store.resolve_not_applied(op['operation_id'], inv['inventory_id'], 'receipt.json',
                                                'Operator confirmed the control request ended with no late completion')
        self.assertEqual(result['resolution'], 'operator_confirmed_not_applied')
        self.assertEqual(self.diff()['operations'][0]['action'], 'create')

    def test_m2_plan_integration_keeps_manual_boundary_and_checks_sources(self):
        from fantasy_agent.automation.automation_plan import build, DEFAULT_PLAN_POLICY
        from fantasy_agent.automation.automation_store import AutomationStore
        from tests.test_automation_plan import observations, AT
        self.now = instant(AT)
        refs = [AutomationStore(self.root).reference('receipt.json')]
        plan = build(observations(), DEFAULT_PLAN_POLICY, AT, references=refs)
        desired = self.store.from_plan(plan, 'test-thread')
        self.assertEqual(len(desired['checks']), 4)
        self.assertEqual(len(desired['manual_instructions']), 4)
        diff = self.diff(desired)
        self.assertEqual(diff['operations'], [])
        self.assertEqual(len(diff['findings']), 4)
        (self.root / 'receipt.json').write_text('{}')
        with self.assertRaises(StaleRevision):
            self.store.from_plan(plan, 'test-thread')
