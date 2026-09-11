import copy
import unittest
from unittest.mock import patch

from automation_store import InvalidContract, utc
from lineup_authority import promote, revoke, authorize
from tests import test_lineup_execution as execution_tests


class AuthorityTests(unittest.TestCase):
    setUp = execution_tests.ExecutionTests.setUp
    write = execution_tests.ExecutionTests.write
    snapshot = execution_tests.ExecutionTests.snapshot
    prepare = execution_tests.ExecutionTests.prepare
    after = execution_tests.ExecutionTests.after

    def test_daily_limit_and_code_change_block_future_dispatch(self):
        self.grant()
        self.windows()
        promote(self.engine, 'grant.json', 'tests.json')
        eid = self.engine.register('proposal.json', authorize(self.engine, 'proposal.json')['saved'])['id']
        action = self.prepare(eid)
        self.engine.dispatch(action['action_id'], action['token'])
        self.after(['b'])
        self.engine.reconcile(action['action_id'], 'post-api.json', 'post-native.json')
        self.inputs['final_context']['roster']['starters'] = ['b']
        self.inputs['final_context']['matchup']['starters'] = ['b']
        self.native['starters'] = ['b']
        self.native['observed_at'] = utc(self.now)
        self.write('next-native.json', self.native)
        self.write('next-api.json', self.inputs['final_context'])
        self.snapshot()
        proposal = copy.deepcopy(self.proposal)
        proposal['assignments'][0]['player_id'] = 'a'
        proposal['rationale'] = 'Second simulated change'
        self.write('second.json', proposal)
        eid = self.engine.register('second.json', authorize(self.engine, 'second.json')['saved'])['id']
        with patch('lineup_validation.schedule_games', return_value=(self.games, {'BUF', 'NYJ'})):
            second = self.engine.prepare(eid, 'snapshot', 'next-api.json', 'next-native.json')
        with self.assertRaisesRegex(InvalidContract, 'daily action limit'):
            self.engine.dispatch(second['action_id'], second['token'])
        (self.root / 'new_code.py').write_text('changed = True\n')
        with self.assertRaisesRegex(InvalidContract, 'Code changed'):
            authorize(self.engine, 'second.json')

    def grant(self):
        grant = {'schema_version': 1, 'basis': 'explicit_owner_lineup_delegation',
                 'league_id': 'test', 'roster_id': 1, 'season': 2026,
                 'operations': ['unlocked_starters'], 'owner_statement': 'Simulated explicit delegation',
                 'issued_at': utc(self.now), 'expires_at': utc(self.now + 3600), 'max_actions_per_day': 1}
        self.write('grant.json', grant)
        self.write('tests.json', {'basis': 'verified_failure_exercises', 'passed': 1, 'failed': 0,
                                  'command': 'python3 -m unittest discover -v',
                                  'source_digest': __import__('system_acceptance').source_digest(self.root)})
        return grant

    def windows(self):
        from weekly_data import fingerprint
        for n in (1, 2):
            proposal = copy.deepcopy(self.proposal)
            proposal['assignments'][0]['player_id'] = 'a'
            proposal['rationale'] = 'Simulated qualifying window ' + str(n)
            self.write(f'p{n}.json', proposal)
            self.write(f'o{n}.json', {'basis': 'explicit_owner_approval', 'proposal_hash': fingerprint(proposal)})
            self.write(f'a{n}.json', {**self.authority, 'proposal_hash': fingerprint(proposal), 'owner_approval': f'o{n}.json'})
            eid = self.engine.register(f'p{n}.json', f'a{n}.json')['id']
            kickoff = utc(self.now + n * 1000)
            validation = {'status': 'PASS', 'locked_player_ids': [], 'expires_at': utc(self.now + 300),
                          'players': [{'game': {'kickoff': kickoff}}]}
            with patch('lineup_execution.validate', return_value=validation):
                self.engine.prepare(eid, 'snapshot', 'api.json', 'native.json')
            self.write(f'w{n}.json', {'basis': 'actual_owner_supervised_window', 'execution_id': eid, 'kickoff': kickoff})
            self.engine.record_window(eid, kickoff, f'w{n}.json')

    def test_default_disabled_and_two_distinct_windows_required(self):
        self.grant()
        with self.assertRaises(InvalidContract):
            authorize(self.engine, 'proposal.json')
        with self.assertRaises(InvalidContract):
            promote(self.engine, 'grant.json', 'tests.json')
        self.windows()
        self.assertTrue(promote(self.engine, 'grant.json', 'tests.json')['enabled'])

    def test_promoted_delegation_executes_once_and_revocation_blocks_dispatch(self):
        self.grant()
        self.windows()
        promote(self.engine, 'grant.json', 'tests.json')
        authority = authorize(self.engine, 'proposal.json')['saved']
        eid = self.engine.register('proposal.json', authority)['id']
        action = self.prepare(eid)
        revoke(self.engine, 'Owner paused the simulated system')
        with self.assertRaises(InvalidContract):
            self.engine.dispatch(action['action_id'], action['token'])

    def test_review_and_changed_evidence_block_delegated_work(self):
        self.grant()
        self.windows()
        promote(self.engine, 'grant.json', 'tests.json')
        authority = authorize(self.engine, 'proposal.json')['saved']
        eid = self.engine.register('proposal.json', authority)['id']
        with patch('lineup_execution.validate', return_value={'status': 'REVIEW'}):
            with self.assertRaises(InvalidContract):
                self.engine.prepare(eid, 'snapshot', 'api.json', 'native.json')
        self.write('w1.json', {'tampered': True})
        with self.assertRaises(InvalidContract):
            self.prepare(eid)

    def test_expiry_scope_and_broader_permissions_refused(self):
        grant = self.grant()
        self.windows()
        grant['operations'].append('trades')
        self.write('grant.json', grant)
        with self.assertRaises(InvalidContract):
            promote(self.engine, 'grant.json', 'tests.json')
        self.grant()
        promote(self.engine, 'grant.json', 'tests.json')
        self.now += 3601
        with self.assertRaises(InvalidContract):
            authorize(self.engine, 'proposal.json')
