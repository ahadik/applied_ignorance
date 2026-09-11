"""Simulated local scheduler records. No scheduler tools or provider requests."""
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from automation_dispatch import Dispatcher
from automation_reconcile import SchedulerStore
from automation_run import register_workflow
from automation_store import AutomationError, utc


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.now = 1789128000.0
        self.dispatch = Dispatcher(self.root, clock=lambda: self.now)
        self.store = self.dispatch.store
        self.store.initialize()
        (self.root / 'config.json').write_text('{"league_id":"league"}')
        (self.root / 'evidence.json').write_text('{}')
        self.store.set_mode('observe', 'evidence.json')
        self.directory = self.root / 'schedules'
        self.directory.mkdir()
        SchedulerStore(self.root, clock=lambda: self.now).init(self.directory)
        self.prepared = self.dispatch.prepare('task', utc(self.now + 86400))
        self.revision = self.prepared['revision']
        value = self.dispatch.config()
        self.task = {'id': 'task-id', 'kind': 'heartbeat', 'name': value['name'], 'prompt': value['prompt'],
                     'rrule': value['rrule'], 'target_thread_id': 'task', 'status': 'ACTIVE'}
        self.write_task()
        self.dispatch.bind()

    def write_task(self, name='task-id'):
        folder = self.directory / name
        folder.mkdir(exist_ok=True)
        (folder / 'automation.toml').write_text('\n'.join(f'{k} = {json.dumps(v)}' for k, v in {**self.task, 'id': name}.items()))

    def test_expired_dispatcher_requires_verified_removal_before_new_contract(self):
        with self.assertRaises(AutomationError):
            self.dispatch.archive_expired()
        self.now += 86401
        with self.assertRaises(AutomationError):
            self.dispatch.archive_expired()
        (self.directory / 'task-id' / 'automation.toml').unlink()
        (self.directory / 'task-id').rmdir()
        archived = self.dispatch.archive_expired()
        self.assertTrue(Path(archived['archived']).exists())
        fresh = self.dispatch.prepare('task', utc(self.now + 86400))
        self.assertFalse(fresh['existing'])
        self.assertNotEqual(fresh['revision'], self.revision)

    def check(self, name, offset=0, window=1200):
        recipe = {'schema_version': 1, 'kind': 'inspection', 'league_id': 'league', 'season': 2026,
                  'week': 1, 'roster_id': 1, 'notify_on_failure': False}
        path = name + '.json'
        (self.root / path).write_text(json.dumps(recipe))
        result = register_workflow(self.root, path, name, utc(self.now + offset),
                                   utc(self.now + offset + window), utc(self.now + offset + window + 600))
        return {'check_id': name, 'revision': result['revision'], 'recipe': path}

    def test_creation_restart_binds_existing_and_never_offers_duplicate(self):
        restarted = Dispatcher(self.root, clock=lambda: self.now)
        self.assertTrue(restarted.prepare('task', utc(self.now + 86400))['existing'])
        self.assertEqual(restarted.bind()['task_id'], 'task-id')

    def test_two_ticks_with_republished_future_coverage_and_no_replay(self):
        first, second, future = self.check('first'), self.check('second', 60), self.check('future', 3600)
        report = self.dispatch.publish([first, second, future], utc(self.now + 7200))
        self.assertTrue(report['configuration_coverage_verified'], report)
        a = self.dispatch.tick(self.revision)
        self.assertEqual(a['workflow']['check_id'], 'first')
        self.assertEqual(self.dispatch.tick(self.revision)['status'], 'idle')
        self.now += 60
        self.assertTrue(self.dispatch.publish([first, second, future], utc(self.now + 7200))['configuration_coverage_verified'])
        b = Dispatcher(self.root, clock=lambda: self.now).tick(self.revision)
        self.assertEqual(b['workflow']['check_id'], 'second')
        self.assertTrue(self.dispatch.coverage()['configuration_coverage_verified'])
        self.assertEqual(self.store.status()['runs'], {'completed': 2})

    def test_changed_target_paused_and_duplicate_schedules_block(self):
        self.dispatch.publish([self.check('first')], utc(self.now + 7200))
        for key, value in [('status', 'PAUSED'), ('target_thread_id', 'foreign')]:
            old = self.task[key]
            self.task[key] = value
            self.write_task()
            with self.assertRaises(AutomationError):
                self.dispatch.tick(self.revision)
            self.task[key] = old
        self.write_task()
        self.write_task('duplicate')
        with self.assertRaises(AutomationError):
            self.dispatch.coverage()

    def test_superseded_prompt_and_changed_source_stop_before_work(self):
        item = self.check('first')
        self.dispatch.publish([item], utc(self.now + 7200))
        with patch('automation_dispatch.Workflow') as worker:
            with self.assertRaises(AutomationError):
                self.dispatch.tick('0' * 64)
            (self.root / item['recipe']).write_text('{}')
            with self.assertRaises(AutomationError):
                self.dispatch.tick(self.revision)
            worker.assert_not_called()

    def test_crash_after_claim_requires_recovery(self):
        item = self.check('first')
        self.dispatch.publish([item], utc(self.now + 7200))
        self.store.claim(item['check_id'], item['revision'])
        self.now += 301
        result = Dispatcher(self.root, clock=lambda: self.now).tick(self.revision)
        self.assertEqual(result['status'], 'recovery_required')
        self.assertFalse(self.dispatch.coverage()['configuration_coverage_verified'])

    def test_actual_child_process_crash_preserves_claim_for_restarted_dispatcher(self):
        item = self.check('first')
        self.dispatch.publish([item], utc(self.now + 7200))
        fixture = Path(__file__).with_name('claim_then_exit.py')
        result = subprocess.run([sys.executable, str(fixture), str(self.root), item['check_id'], item['revision'], str(self.now)],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 17, result.stderr.decode())
        self.now += 301
        restarted = Dispatcher(self.root, clock=lambda: self.now)
        self.assertEqual(restarted.tick(self.revision)['status'], 'recovery_required')
        (self.root / 'recovery.json').write_text('{"basis":"child exited immediately after claim before workflow execution"}')
        context = self.store.context(item['check_id'], item['revision'])
        self.store.recover(context['unresolved'][0]['run_id'], 'safe_to_retry', 'recovery.json', 'Child exited before workflow work')
        self.assertEqual(restarted.tick(self.revision)['status'], 'completed')
        self.assertEqual(restarted.tick(self.revision)['status'], 'idle')

    def test_expired_contract_and_narrow_window_do_not_claim_coverage(self):
        report = self.dispatch.publish([self.check('narrow', window=60)], utc(self.now + 7200))
        self.assertFalse(report['configuration_coverage_verified'])
        self.now += 86401
        self.assertTrue(self.dispatch.tick(self.revision)['retire'])

    def test_real_daily_planner_registers_deadlines_and_next_daily(self):
        from automation_plan import DEFAULT_PLAN_POLICY
        from automation_run import Workflow
        from tests.test_automation_plan import observations
        self.now += 2 * 86400
        config = self.dispatch.config()
        config['contract']['expires_at'] = utc(self.now + 3 * 86400)
        from automation_store import digest
        config['revision'] = digest(config['contract'])
        config['prompt'] = config['prompt'].replace(self.revision, config['revision'])
        self.task['prompt'] = config['prompt']
        self.write_task()
        # This isolated test config has no production scheduler effect.
        from storage import save_atomic
        save_atomic(self.dispatch.folder / 'config.json', config)
        (self.root / 'config.json').write_text('{"league_id":"test-league"}')
        (self.root / 'inputs.json').write_text('{}')
        (self.root / 'timing-proof.json').write_text('{}')
        obs = observations(at=utc(self.now))
        obs['source_checksums'] = [self.store.reference(path) for path in sorted(set(obs['source_refs']))]
        (self.root / 'obs.json').write_text(json.dumps(obs))
        (self.root / 'policy.json').write_text(json.dumps(DEFAULT_PLAN_POLICY))
        (self.root / 'proposal.json').write_text('{}')
        base = {'schema_version': 1, 'kind': 'deadline', 'operation': 'validate_lineup', 'league_id': 'test-league',
                'season': 2026, 'week': 1, 'roster_id': 1, 'notify_on_failure': False, 'proposal': 'proposal.json'}
        (self.root / 'base.json').write_text(json.dumps(base))
        daily = {**base, 'kind': 'daily', 'planning_policy': 'policy.json', 'target_thread_id': 'task',
                 'dispatcher_check_recipe': 'base.json'}
        daily.pop('proposal')
        (self.root / 'daily.json').write_text(json.dumps(daily))
        registration = register_workflow(self.root, 'daily.json', 'daily', utc(self.now), utc(self.now + 600), utc(self.now + 900))
        with patch('automation_deadlines.collect', return_value={'saved': str(self.root / 'obs.json'), 'acquisition': {}}):
            result = Workflow(self.root, clock=lambda: self.now).execute('daily', registration['revision'], 'daily.json')
        self.assertEqual(result['status'], 'completed', result)
        publication = self.dispatch.publication()
        self.assertEqual(len(publication['checks']), 5)
        self.assertEqual(sum(c['check_id'].startswith('daily-') for c in publication['checks']), 1)
        self.assertTrue(result['scheduler']['deadline_coverage_verified'])


if __name__ == '__main__':
    unittest.main()
