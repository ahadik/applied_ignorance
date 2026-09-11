import copy
import json
import unittest
from unittest.mock import patch

from fantasy_agent.automation.automation_store import InvalidContract
from fantasy_agent.execution.manager_authority import install, authorize, verify
from fantasy_agent.maintenance.system_acceptance import source_digest
from fantasy_agent.weekly.weekly_data import fingerprint
from tests import test_lineup_execution as execution_tests
from tests import test_lineup_authority as authority_tests


class ManagerAuthorityTests(unittest.TestCase):
    write = execution_tests.ExecutionTests.write
    snapshot = execution_tests.ExecutionTests.snapshot
    prepare = execution_tests.ExecutionTests.prepare
    after = execution_tests.ExecutionTests.after
    windows = authority_tests.AuthorityTests.windows

    def setUp(self):
        execution_tests.ExecutionTests.setUp(self)
        fake = patch('fantasy_agent.automation.league_manager.Manager')
        self.manager = fake.start().return_value
        self.addCleanup(fake.stop)
        self.manager.state.return_value = {'enabled': True}
        self.manager.scheduler.return_value = {'verified': True}
        self.request = {'basis': 'explicit_owner_management_request', 'owner_statement': 'Simulated start managing my league',
                        'league_id': 'test', 'user_id': 'owner', 'roster_id': 1, 'season': 2026,
                        'operations': ['unlocked_starters', 'free_agent'], 'lineup_actions_per_day': 1, 'roster_actions_per_day': 1}
        self.write('request.json', self.request)
        install(self.engine, 'request.json')
        self.write('data/manager/acceptance.json', {'passed': 1, 'failed': 0, 'source_digest': source_digest(self.root),
                    'basis': 'verified_failure_exercises', 'command': 'python3 -m unittest discover -v'})
        self.write('decision.json', {'subject_hash': fingerprint(self.proposal), 'reason': 'Simulated informed decision',
                                     'unresolved_concerns': [], 'evidence': ['proposal.json']})

    def auth(self):
        return authorize(self.engine, 'proposal.json', 'decision.json', 'unlocked_starters')['saved']

    def test_acceptance_gate_is_not_bypassed_by_start_request(self):
        with self.assertRaisesRegex(InvalidContract, 'Two supervised'):
            self.auth()
        self.windows()
        self.assertTrue(self.auth())

    def test_full_lineup_path_and_single_use_dispatch(self):
        self.windows()
        eid = self.engine.register('proposal.json', self.auth())['id']
        action = self.prepare(eid)
        self.engine.dispatch(action['action_id'], action['token'])
        with self.assertRaises(InvalidContract):
            self.engine.dispatch(action['action_id'], action['token'])
        self.after(['b'])
        self.assertEqual(self.engine.reconcile(action['action_id'], 'post-api.json', 'post-native.json')['outcome'], 'confirmed')

    def test_lost_schedule_or_revocation_blocks_prepared_action(self):
        self.windows()
        eid = self.engine.register('proposal.json', self.auth())['id']
        action = self.prepare(eid)
        self.manager.scheduler.return_value = {'verified': False}
        with self.assertRaisesRegex(InvalidContract, 'future scheduling'):
            self.engine.dispatch(action['action_id'], action['token'])
        self.manager.scheduler.return_value = {'verified': True}
        value = json.loads((self.root / 'data/manager/authority.json').read_text())
        value['enabled'] = False
        self.write('data/manager/authority.json', value)
        with self.assertRaisesRegex(InvalidContract, 'revoked'):
            self.engine.dispatch(action['action_id'], action['token'])

    def test_model_uncertainty_and_changed_source_block_authority(self):
        self.windows()
        self.write('decision.json', {'subject_hash': fingerprint(self.proposal), 'reason': 'Not sure',
                                    'unresolved_concerns': ['injury'], 'evidence': ['proposal.json']})
        with self.assertRaises(InvalidContract):
            self.auth()
        (self.root / 'new.py').write_text('changed = True')
        self.write('decision.json', {'subject_hash': fingerprint(self.proposal), 'reason': 'Resolved',
                                    'unresolved_concerns': [], 'evidence': ['proposal.json']})
        with self.assertRaisesRegex(InvalidContract, 'current source'):
            self.auth()

    def test_daily_limit_applies_inside_execution_transaction(self):
        self.windows()
        path = self.auth()
        authority, _ = self.engine.read(path)
        with self.engine.db() as db:
            verify(self.engine, db, self.proposal, authority, 'unlocked_starters', dispatch=True)
        with self.engine.db() as db:
            with self.assertRaisesRegex(InvalidContract, 'daily action limit'):
                verify(self.engine, db, self.proposal, authority, 'unlocked_starters', dispatch=True)

    def test_trades_and_other_accounts_cannot_be_enabled(self):
        for changes in ({'operations': ['trade']}, {'user_id': 'another'}, {'league_id': 'another'}):
            self.write('other.json', {**self.request, **changes})
            with self.assertRaises(InvalidContract):
                install(self.engine, 'other.json')
