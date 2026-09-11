import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from automation_run import Workflow, register_workflow, browser_observation
from automation_health import health
from automation_store import AutomationError, DuplicateRun, ModeBlocked, LeaseConflict


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.now = 1789128000.0  # 2026-09-11 12:00 UTC
        self.worker = Workflow(self.root, clock=lambda: self.now)
        self.store = self.worker.store
        self.store.initialize()
        self.write('config.json', {'league_id': 'league'})
        self.write('evidence.json', {'owner': 'test'})
        self.store.set_mode('observe', 'evidence.json')
        self.recipe = {'schema_version': 1, 'kind': 'inspection', 'league_id': 'league',
                       'season': 2026, 'week': 1, 'roster_id': 1, 'notify_on_failure': True}

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value))

    def register(self, name='check', recipe=None):
        recipe = dict(recipe or self.recipe)
        if recipe['kind'] == 'daily':
            self.write('planning.json', {})
            recipe.update(planning_policy='planning.json', target_thread_id='test-task')
        if recipe.get('operation') == 'validate_lineup' and not recipe.get('proposal'):
            self.write('proposal.json', {})
            recipe['proposal'] = 'proposal.json'
        self.write(name + '.json', recipe)
        return register_workflow(self.root, name + '.json', name, '2026-09-11T11:59:00Z',
                                 '2026-09-11T12:50:00Z', '2026-09-11T13:00:00Z')['revision']

    def test_receipt_survives_restart_and_suppresses_duplicate(self):
        rev = self.register()
        result = self.worker.execute('check', rev, 'check.json', 'scheduled')
        self.assertEqual(result['status'], 'completed')
        self.assertFalse(result['scheduled_execution_verified'])
        restarted = Workflow(self.root, clock=lambda: self.now)
        with self.assertRaises(DuplicateRun):
            restarted.execute('check', rev, 'check.json')
        self.assertEqual(self.store.status()['runs'], {'completed': 1})

    def test_integrated_review_uses_workflow_lease_and_proposal_mode(self):
        recipe = {**self.recipe, 'kind': 'deadline', 'operation': 'integrated_review'}
        rev = self.register(recipe=recipe)
        with patch('agent_cycle.review') as review:
            with self.assertRaises(ModeBlocked):
                self.worker.execute('check', rev, 'check.json')
            review.assert_not_called()
        self.store.set_mode('propose', 'evidence.json')
        with patch('agent_cycle.review', return_value={'status': 'owner_review_required', 'acquisition': {}}) as review:
            result = self.worker.execute('check', rev, 'check.json')
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(result['owner_action_required'])
        self.assertFalse(result['lineup_applied'])
        self.assertTrue(callable(review.call_args.kwargs['checkpoint']))

    def test_changed_recipe_and_disabled_mode_stop_before_work_or_alert(self):
        rev = self.register(recipe={**self.recipe, 'kind': 'daily'})
        with patch.object(self.worker, 'daily') as work, patch('automation_run.alert') as alert:
            self.store.set_mode('disabled')
            with self.assertRaises(ModeBlocked):
                self.worker.execute('check', rev, 'check.json')
            self.store.set_mode('observe', 'evidence.json')
            self.write('check.json', {**self.recipe, 'roster_id': 2})
            with self.assertRaises(AutomationError):
                self.worker.execute('check', rev, 'check.json')
            work.assert_not_called()
            alert.assert_not_called()

    def test_superseded_revision_stops_before_collection(self):
        rev = self.register(recipe={**self.recipe, 'kind': 'daily'})
        register_workflow(self.root, 'check.json', 'check', '2026-09-11T11:58:00Z',
                          '2026-09-11T12:50:00Z', '2026-09-11T13:00:00Z', rev)
        with patch.object(self.worker, 'daily') as work, patch('automation_run.alert') as alert:
            with self.assertRaises(AutomationError):
                self.worker.execute('check', rev, 'check.json')
            work.assert_not_called()
            alert.assert_not_called()

    def test_daily_and_deadline_share_claim_scope_after_restart(self):
        a = self.register('daily', {**self.recipe, 'kind': 'daily'})
        b = self.register('deadline', {**self.recipe, 'kind': 'deadline', 'operation': 'validate_lineup'})
        self.store.claim('daily', a)
        restarted = Workflow(self.root, clock=lambda: self.now)
        with self.assertRaises(LeaseConflict):
            restarted.execute('deadline', b, 'deadline.json')

    def test_failure_preserves_unknown_and_notification_failure(self):
        rev = self.register(recipe={**self.recipe, 'kind': 'daily'})
        with patch.object(self.worker, 'daily', side_effect=OSError('private detail')), \
                patch('automation_run.get_pushover') as provider:
            provider.return_value.send.side_effect = ValueError('private token')
            result = self.worker.execute('check', rev, 'check.json')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['notification']['state'], 'unavailable')
        self.assertEqual(self.store.status()['runs'], {'outcome_unknown': 1})
        self.assertNotIn('private', json.dumps(result))
        with self.assertRaises(AutomationError):
            self.worker.execute('check', rev, 'check.json')

    def test_expired_worker_cannot_report_success(self):
        rev = self.register(recipe={**self.recipe, 'kind': 'daily'})
        def expire(*args):
            self.now += 301
            return {'status': 'completed'}
        with patch.object(self.worker, 'daily', side_effect=expire), patch('automation_run.alert', return_value={'state': 'queued'}):
            result = self.worker.execute('check', rev, 'check.json')
        self.assertEqual(result['status'], 'failed')
        self.assertIn('recovery_required', result)

    def test_browser_failure_alert_is_independent_and_saved(self):
        with patch('automation_run.get_pushover') as provider:
            provider.return_value.send.return_value = {'state': 'queued', 'phone_delivery_confirmed': False}
            result = browser_observation(self.root, 'login_required', 'evidence.json', clock=lambda: self.now)
            provider.return_value.send.assert_called_once()
        saved = json.loads((self.root / 'data/automation/browser/latest.json').read_text())
        self.assertEqual(saved, result)

    def test_health_does_not_promote_completed_inspection_to_coverage(self):
        rev = self.register()
        self.worker.execute('check', rev, 'check.json')
        with patch('automation_health.get_pushover') as provider:
            provider.return_value.status.return_value = {'phone_delivery_confirmed': True}
            result = health(self.root, clock=lambda: self.now)
        self.assertFalse(result['production_ready'])
        self.assertIn('automatic_deadline_coverage_unverified', result['issues'])
        self.assertEqual(result['workflow_receipts'][0]['status'], 'completed')

    def test_two_offline_planning_cycles_retain_missing_schedule_coverage(self):
        from automation_plan import DEFAULT_PLAN_POLICY
        from automation_reconcile import SchedulerStore
        from automation_store import utc
        from tests.test_automation_plan import observations
        directory = self.root / 'schedules'
        directory.mkdir()
        SchedulerStore(self.root, clock=lambda: self.now).init(directory)
        self.write('config.json', {'league_id': 'test-league'})
        self.write('inputs.json', {})
        self.write('timing-proof.json', {})
        self.write('policy.json', DEFAULT_PLAN_POLICY)
        previous = None
        for cycle in range(2):
            name = 'cycle' + str(cycle)
            obs = observations(at=utc(self.now))
            obs['source_checksums'] = [self.store.reference(path) for path in sorted(set(obs['source_refs']))]
            self.write('observed' + str(cycle) + '.json', obs)
            recipe = {**self.recipe, 'kind': 'daily', 'league_id': 'test-league',
                      'planning_policy': 'policy.json', 'target_thread_id': 'test-task'}
            if previous:
                recipe['previous_plan'] = previous
            self.write(name + '.json', recipe)
            rev = register_workflow(self.root, name + '.json', name, '2026-09-11T11:59:00Z',
                                    '2026-09-11T12:50:00Z', '2026-09-11T13:00:00Z')['revision']
            collection = {'saved': str(self.root / ('observed' + str(cycle) + '.json')), 'acquisition': {'attempts': 0}}
            with patch('automation_deadlines.collect', return_value=collection), \
                    patch('automation_run.alert', return_value={'state': 'queued'}):
                result = Workflow(self.root, clock=lambda: self.now).execute(name, rev, name + '.json')
            self.assertEqual(result['status'], 'blocked', result)
            self.assertEqual(result['cause'], 'future_deadline_coverage_unverified')
            self.assertFalse(result['scheduler']['deadline_coverage_verified'])
            previous = Path(result['planning']['saved']).relative_to(self.root).as_posix()
            self.now += 60

    def test_validator_review_persists_observed_locks_without_lineup_write(self):
        proposal = {'league_id': 'league', 'season': 2026, 'week': 1}
        self.write('proposal.json', proposal)
        recipe = {**self.recipe, 'kind': 'deadline', 'operation': 'validate_lineup', 'proposal': 'proposal.json'}
        rev = self.register(recipe=recipe)
        inputs = {'final_context': {'roster': {'roster_id': 1}}}
        validation = {'status': 'REVIEW', 'locked_player_ids': ['p1'],
                      'players': [{'player_id': 'p1', 'game': {'kickoff': '2026-09-11T11:00:00Z'}}]}
        with patch('weekly_data.collect', return_value=self.root / 'snapshot') as collect, \
                patch('weekly_data.load', return_value=inputs), \
                patch('weekly_data.acquisition_summary', return_value={'sleeper': {'attempts': 5}}), \
                patch('lineup_validation.check_document'), patch('lineup_validation.validate', return_value=validation), \
                patch('automation_run.alert', return_value={'state': 'queued'}):
            result = self.worker.execute('check', rev, 'check.json')
        self.assertTrue(collect.call_args.kwargs['validation_only'])
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['lineup_applied'])
        locks = json.loads((self.root / 'data/weekly/2026/1/locks.json').read_text())
        self.assertEqual(locks['players'], ['p1'])


if __name__ == '__main__':
    unittest.main()
