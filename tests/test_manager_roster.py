import copy
import json
import unittest
from unittest.mock import patch

from fantasy_agent.automation.automation_store import InvalidContract
from fantasy_agent.execution.manager_authority import install, authorize
from fantasy_agent.weekly.season_strategy import compare
from fantasy_agent.maintenance.system_acceptance import source_digest
from fantasy_agent.weekly.weekly_data import fingerprint
from tests import test_roster_operations as roster_tests
from tests import test_lineup_authority as lineup_tests


class ManagedRosterTests(unittest.TestCase):
    write = roster_tests.RosterTests.write
    snapshot = roster_tests.RosterTests.snapshot
    observations = roster_tests.RosterTests.observations
    advance = roster_tests.RosterTests.advance
    register = roster_tests.RosterTests.register
    prepare = roster_tests.RosterTests.prepare
    pending = roster_tests.RosterTests.pending
    win = roster_tests.RosterTests.win
    windows = lineup_tests.AuthorityTests.windows

    def setUp(self):
        roster_tests.RosterTests.setUp(self)
        fake = patch('fantasy_agent.automation.league_manager.Manager')
        self.manager = fake.start().return_value
        self.addCleanup(fake.stop)
        self.manager.state.return_value = {'enabled': True}
        self.manager.scheduler.return_value = {'verified': True}
        self.write('request.json', {'basis': 'explicit_owner_management_request', 'owner_statement': 'Simulated delegation',
                   'league_id': 'test', 'user_id': 'owner', 'roster_id': 1, 'season': 2026,
                   'operations': ['free_agent', 'waiver'], 'lineup_actions_per_day': 2, 'roster_actions_per_day': 1})
        install(self.engine, 'request.json')
        self.write('data/manager/acceptance.json', {'passed': 1, 'failed': 0, 'source_digest': source_digest(self.root),
                    'basis': 'verified_failure_exercises', 'command': 'python3 -m unittest discover -v'})
        self.windows()

    def decision(self):
        self.write('managed-plan.json', self.plan)
        self.write('decision.json', {'subject_hash': fingerprint(self.plan), 'reason': 'Simulated improvement',
                    'unresolved_concerns': [], 'evidence': ['valuation.json'],
                    'season_impact': 'Simulated longer-term comparison supports the move',
                    'alternatives_considered': ['Keep the existing roster']})

    def test_live_roster_acceptance_cannot_be_inferred_from_windows(self):
        self.decision()
        with self.assertRaisesRegex(InvalidContract, 'supervised roster transaction'):
            authorize(self.engine, 'managed-plan.json', 'decision.json', 'waiver')

    def next_plan(self, priority_cost=0):
        action = self.prepare(self.register())
        self.ops.dispatch_step(action['id'], action['token'])
        self.pending(action)
        self.win(action)
        self.plan['steps'][0].update(add='d', drop='c', claim_key='two')
        self.native['candidates']['d'] = {'action': 'Claim', 'deadline': self.plan['steps'][0]['deadline']}
        pool = json.loads((self.root / 'pool.json').read_text())
        pool['weeks'][0]['players']['d'] = {**pool['weeks'][0]['players']['c'], 'id': 'd', 'points': 30}
        self.write('pool.json', pool)
        self.valuation = compare(pool, ['a', 'c'], ['d'], ['c'], priority_cost=priority_cost)
        self.valuation['pool_path'] = 'pool.json'
        self.write('valuation.json', self.valuation)
        self.observations()
        self.decision()
        authority = authorize(self.engine, 'managed-plan.json', 'decision.json', 'waiver')['saved']
        return self.ops.register_plan('managed-plan.json', authority)['id']

    def test_managed_plan_dispatches_and_lost_schedule_blocks(self):
        pid = self.next_plan()
        action = self.prepare(pid)
        self.manager.scheduler.return_value = {'verified': False}
        with self.assertRaisesRegex(InvalidContract, 'future scheduling'):
            self.ops.dispatch_step(action['id'], action['token'])
        self.manager.scheduler.return_value = {'verified': True}
        self.assertEqual(self.ops.dispatch_step(action['id'], action['token'])['status'], 'outcome_unknown')

    def test_priority_cost_can_block_automatic_acquisition(self):
        pid = self.next_plan(priority_cost=100)
        with self.assertRaisesRegex(InvalidContract, 'priority cost'):
            self.prepare(pid)
