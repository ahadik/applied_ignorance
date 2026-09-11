import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fantasy_agent.automation.automation_store import InvalidContract
from fantasy_agent.automation.league_manager import Manager, discover


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1800000000.0
        self.inventory = self.root / 'schedules'
        self.inventory.mkdir()
        (self.root / 'templates/automation').mkdir(parents=True)
        (self.root / 'templates/automation/manager-v1.txt').write_text('Manage {project}.')
        (self.root / 'config.json').write_text('{"username":"owner"}')
        (self.root / '.env').write_text('SLEEPER_LEAGUE_ID=123\nSLEEPER_USER_ID=u\n')
        self.manager = Manager(self.root, clock=lambda: self.now, inventory_path=self.inventory)
        self.manager.start('task')
        self.bind()

    def bind(self, status='ACTIVE', target='task'):
        folder = self.inventory / 'manager'
        folder.mkdir(exist_ok=True)
        prompt = self.manager.prompt(self.manager.state())
        (folder / 'automation.toml').write_text('\n'.join(
            key + ' = ' + json.dumps(value) for key, value in {
                'id': 'manager', 'kind': 'heartbeat', 'name': 'Fantasy Football league manager',
                'status': status, 'target_thread_id': target, 'rrule': 'FREQ=MINUTELY;INTERVAL=5', 'prompt': prompt}.items()))

    def context(self, phase='regular_season'):
        return {'phase': phase, 'season': 2026, 'week': 1, 'league_id': '123', 'user_id': 'u'}

    def tick(self, phase='regular_season', failure=None):
        with patch('fantasy_agent.automation.league_manager.discover', side_effect=failure, return_value=self.context(phase)), \
             patch('fantasy_agent.automation.agent_cycle.review', return_value={'status': 'owner_review_required'}) as review:
            result = self.manager.tick()
        return result, review

    def finish(self, outcome='no_change'):
        pending = self.manager.state()['pending']
        path = self.root / 'decision.json'
        path.write_text(json.dumps({'run_id': pending['id'], 'outcome': outcome, 'reason': 'Simulated decision',
                                    'next_review_at': self.now + 600, 'evidence': [pending['path']]}))
        return self.manager.finish(path)

    def test_idempotent_start_preserves_one_installation(self):
        before = self.manager.state()['installation']
        self.assertTrue(self.manager.start('task')['schedule']['verified'])
        self.assertEqual(self.manager.state()['installation'], before)
        with self.assertRaises(InvalidContract):
            self.manager.start('another-task')

    def test_schedule_first_before_network(self):
        self.bind(status='PAUSED')
        result, review = self.tick()
        self.assertEqual(result['status'], 'repair_schedule_first')
        review.assert_not_called()

    def test_transfer_preserves_work_and_requires_schedule_update(self):
        self.tick()
        before = self.manager.state()
        before['obligations'] = {'game': {'id': 'game', 'at': self.now + 600, 'reason': 'Review game'}}
        self.manager.save(before)
        result = self.manager.transfer('new-task')
        after = self.manager.state()
        for key in before:
            if key != 'target':
                self.assertEqual(before[key], after[key])
        self.assertFalse(result['schedule']['verified'])
        self.assertEqual(result['schedule']['tool_arguments']['id'], 'manager')
        self.assertEqual(result['schedule']['tool_arguments']['targetThreadId'], 'new-task')
        result, review = self.tick()
        self.assertEqual(result['status'], 'repair_schedule_first')
        review.assert_not_called()
        self.bind(target='new-task')
        self.assertTrue(self.manager.status()['schedule']['verified'])
        self.manager.transfer('new-task')
        self.assertEqual(len(self.manager.state()['transfers']), 1)

    def test_transfer_rejects_empty_target_and_stopped_manager(self):
        with self.assertRaises(InvalidContract):
            self.manager.transfer(' ')
        self.manager.stop()
        with self.assertRaises(InvalidContract):
            self.manager.transfer('new-task')

    def test_pending_inference_survives_restart_without_recollecting(self):
        self.tick()
        restarted = Manager(self.root, clock=lambda: self.now, inventory_path=self.inventory)
        with patch('fantasy_agent.automation.league_manager.discover') as provider:
            result = restarted.tick()
        self.assertEqual(result['status'], 'inference_required')
        provider.assert_not_called()
        self.assertTrue(result['schedule']['verified'])

    def test_finish_keeps_schedule_and_future_review(self):
        self.tick()
        result = self.finish()
        self.assertTrue(result['schedule']['verified'])
        self.assertIsNone(result['pending'])
        self.assertEqual(self.manager.tick()['status'], 'waiting')
        self.now += 601
        result, review = self.tick()
        review.assert_called_once()
        self.assertEqual(result['status'], 'inference_required')

    def test_finish_refuses_missing_followup(self):
        self.tick()
        self.bind(status='PAUSED')
        with self.assertRaisesRegex(InvalidContract, 'future scheduling'):
            self.finish()
        self.assertIsNotNone(self.manager.state()['pending'])

    def test_failed_provider_preserves_future_and_retry(self):
        result, _ = self.tick(failure=RuntimeError('simulated disconnect'))
        self.assertEqual(result['status'], 'exception')
        self.assertTrue(result['schedule']['verified'])
        with self.assertRaisesRegex(InvalidContract, 'Failed collection'):
            self.finish('no_change')
        self.finish('retry')
        self.now += 601
        self.assertEqual(self.tick()[0]['status'], 'inference_required')

    def test_wrong_target_not_coverage(self):
        self.bind(target='other')
        self.assertFalse(self.manager.status()['schedule']['verified'])

    def test_interrupted_collection_never_becomes_success(self):
        value = self.manager.state()
        value['pending'] = {'id': 'broken', 'status': 'collecting', 'path': 'data/manager/state.json'}
        self.manager.save(value)
        with self.assertRaisesRegex(InvalidContract, 'Interrupted collection'):
            self.finish()
        self.finish('retry')

    def test_stop_is_only_normal_retirement(self):
        self.assertEqual(self.manager.stop()['delete_task'], 'manager')
        self.assertEqual(self.manager.tick()['status'], 'stopped')

    def test_no_weekly_projection_in_draft_or_offseason(self):
        for phase in ('pre_draft', 'live_draft', 'paused_draft', 'post_draft_waiting', 'season_complete'):
            result, review = self.tick(phase)
            review.assert_not_called()
            self.assertEqual(result['status'], 'inference_required')
            self.finish()
            self.now += 601

    def test_silent_gap_reported_on_return(self):
        self.tick()
        self.finish()
        self.now += 1800
        self.assertTrue(self.manager.status()['overdue_wakeup'])
        self.tick()
        self.assertEqual(self.manager.status()['missed_wakeups'], 1)

    def test_obligations_survive_unrelated_reviews_and_trigger_when_due(self):
        path = self.root / 'followup.json'
        path.write_text(json.dumps({'id': 'claim', 'at': self.now + 100, 'reason': 'Check actual processing'}))
        self.manager.obligation(path)
        self.tick()
        self.finish()
        self.assertIn('claim', self.manager.status()['obligations'])
        self.now += 101
        result, review = self.tick()
        review.assert_called_once()
        self.assertIn('claim', result['result']['due_obligations'])

    def test_long_or_missing_next_review_is_rejected(self):
        self.tick()
        pending = self.manager.state()['pending']
        path = self.root / 'bad-decision.json'
        path.write_text(json.dumps({'run_id': pending['id'], 'outcome': 'no_change', 'reason': 'Test',
                                   'next_review_at': self.now + 86400, 'evidence': [pending['path']]}))
        with self.assertRaisesRegex(InvalidContract, 'within one hour'):
            self.manager.finish(path)


class DiscoveryTests(unittest.TestCase):
    def read(self, draft_status='complete', league_status='in_season', nfl_type='regular', user='u'):
        responses = [
            {'league_id': '123', 'sport': 'nfl', 'season': '2026', 'total_rosters': 1,
             'status': league_status, 'draft_id': '456'},
            {'user_id': user, 'username': 'owner'}, [{'roster_id': 7, 'owner_id': 'u'}],
            {'season': '2026', 'season_type': nfl_type, 'week': 1},
            {'draft_id': '456', 'league_id': '123', 'status': draft_status}]
        return patch('fantasy_agent.automation.league_manager.get_sleeper', side_effect=[{'data': r, 'network_attempts': 1} for r in responses])

    def test_phase_detection_and_request_evidence(self):
        for draft, league, nfl, phase in [('pre_draft', 'pre_draft', 'pre', 'pre_draft'),
                 ('drafting', 'drafting', 'regular', 'live_draft'), ('paused', 'drafting', 'regular', 'paused_draft'),
                 ('complete', 'in_season', 'regular', 'regular_season'), ('complete', 'in_season', 'pre', 'post_draft_waiting'),
                 ('complete', 'complete', 'post', 'season_complete')]:
            with self.read(draft, league, nfl) as provider:
                result = discover({'league_id': '123', 'user_id': 'u', 'username': 'owner'})
            self.assertEqual(result['phase'], phase)
            self.assertEqual(result['acquisition']['network_attempts'], 5)
            self.assertTrue(all(call.kwargs['retries'] == 0 for call in provider.call_args_list))

    def test_wrong_user_stops_before_roster_and_other_reads(self):
        with self.read(user='wrong') as provider:
            with self.assertRaises(ValueError):
                discover({'league_id': '123', 'user_id': 'u', 'username': 'owner'})
        self.assertEqual(provider.call_count, 2)
