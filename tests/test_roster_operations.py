import copy
import json
import unittest

from automation_store import InvalidContract, utc
from roster_operations import RosterOperations, rules_key
from season_strategy import compare
from tests.test_season_strategy import pool_fixture
from tests import test_lineup_execution as execution_tests
from weekly_data import fingerprint


class RosterTests(unittest.TestCase):
    write = execution_tests.ExecutionTests.write
    snapshot = execution_tests.ExecutionTests.snapshot

    def setUp(self):
        execution_tests.ExecutionTests.setUp(self)
        self.ops = RosterOperations(self.root, clock=lambda: self.now)
        ctx = copy.deepcopy(self.inputs['final_context'])
        ctx['league']['roster_positions'] = ['QB', 'BN']
        ctx['league']['settings']['reserve_slots'] = 0
        ctx['roster'].update(owner_id='owner', reserve=[], settings={'waiver_position': 2})
        self.api = {'schema_version': 1, 'context': ctx,
                    'rosters': {'data': [copy.deepcopy(ctx['roster'])], 'fetched_at': utc(self.now)},
                    'transactions': {'data': [], 'fetched_at': utc(self.now)}}
        self.native.update(reserve=[], transactions_observed=True, pending_claims=[], acquisitions_unlocked=True,
                           rules_confirmed=True, ir_roster_legal=True, waiver_type='Rolling Waivers',
                           candidates={'c': {'action': 'Claim', 'deadline': utc(self.now + 3600)},
                                       'd': {'action': 'Claim', 'deadline': utc(self.now + 3600)}})
        self.plan = {'schema_version': 1, 'mode': 'supervised', 'league_id': 'test', 'roster_id': 1,
                     'season': 2026, 'week': 1, 'created_at': utc(self.now), 'expires_at': utc(self.now + 86400),
                     'rules_hash': rules_key(ctx), 'waiver_position': 2, 'protected_player_ids': ['a'],
                     'steps': [{'kind': 'waiver', 'claim_key': 'one', 'add': 'c', 'drop': 'b', 'deadline': utc(self.now + 3600)}]}
        pool = pool_fixture()
        pool['created_at'] = utc(self.now)
        pool.update(rules_hash=self.plan['rules_hash'], league_id='test', season=2026)
        self.write('pool.json', pool)
        self.valuation = compare(pool, ['a', 'b'], ['c'], ['b'])
        self.valuation['pool_path'] = 'pool.json'
        self.write('valuation.json', self.valuation)
        self.observations()

    def observations(self):
        self.write('roster-api.json', self.api)
        self.write('roster-native.json', self.native)

    def register(self):
        self.write('roster-plan.json', self.plan)
        self.write('roster-owner.json', {'basis': 'explicit_owner_transaction_approval', 'plan_hash': fingerprint(self.plan),
                                        'owner_statement': 'Simulated exact transaction approval'})
        return self.ops.register_plan('roster-plan.json', 'roster-owner.json')['id']

    def prepare(self, pid, ordinal=0):
        return self.ops.prepare_step(pid, ordinal, 'roster-api.json', 'roster-native.json', 'valuation.json')

    def advance(self):
        self.now += 1
        for meta in self.api['context']['evidence'].values():
            meta['fetched_at'] = utc(self.now)
        self.api['rosters']['fetched_at'] = self.api['transactions']['fetched_at'] = utc(self.now)
        self.native['observed_at'] = utc(self.now)

    def pending(self, action):
        self.advance()
        self.native['pending_claims'] = [{'claim_id': 'native-1', 'add': 'c', 'drop': 'b', 'priority': 1}]
        self.observations()
        return self.ops.reconcile_step(action['id'], 'roster-api.json', 'roster-native.json')

    def win(self, action):
        self.advance()
        self.api['context']['roster']['players'] = ['a', 'c']
        self.api['rosters']['data'][0]['players'] = ['a', 'c']
        self.native['owned_player_ids'] = ['a', 'c']
        self.native['pending_claims'] = []
        self.native['claim_results'] = [{'claim_key': 'one', 'claim_id': 'native-1', 'add': 'c', 'drop': 'b',
                                         'status': 'won', 'transaction_id': 'tx1'}]
        self.api['transactions']['data'] = [{'transaction_id': 'tx1', 'status': 'complete', 'adds': {'c': 1}, 'drops': {'b': 1}}]
        self.observations()
        return self.ops.reconcile_step(action['id'], 'roster-api.json', 'roster-native.json')

    def test_claim_pending_then_won_and_restart_cannot_replay(self):
        pid = self.register()
        action = self.prepare(pid)
        self.ops.dispatch_step(action['id'], action['token'])
        restarted = RosterOperations(self.root, clock=lambda: self.now)
        with self.assertRaises(InvalidContract):
            restarted.dispatch_step(action['id'], action['token'])
        self.assertEqual(self.pending(action)['outcome'], 'pending')
        self.assertEqual(self.win(action)['outcome'], 'won')

    def test_shared_drop_consumed_by_earlier_win_requires_new_plan(self):
        self.plan['steps'].append({'kind': 'waiver', 'claim_key': 'two', 'add': 'd', 'drop': 'b', 'deadline': utc(self.now + 3600)})
        pid = self.register()
        action = self.prepare(pid)
        self.ops.dispatch_step(action['id'], action['token'])
        self.pending(action)
        self.win(action)
        with self.assertRaisesRegex(InvalidContract, 'shared drop'):
            self.prepare(pid, 1)

    def test_native_disagreement_and_new_owner_block(self):
        pid = self.register()
        self.api['rosters']['data'].append({'roster_id': 2, 'players': ['c']})
        self.observations()
        with self.assertRaises(InvalidContract):
            self.prepare(pid)
        self.api['rosters']['data'].pop()
        self.native['owned_player_ids'] = ['a']
        self.observations()
        with self.assertRaises(InvalidContract):
            self.prepare(pid)

    def test_lock_priority_deadline_and_incomplete_valuation_block(self):
        pid = self.register()
        for key, value in [('locked_player_ids', ['b']), ('acquisitions_unlocked', False)]:
            old = self.native[key]
            self.native[key] = value
            self.observations()
            with self.assertRaises(InvalidContract): self.prepare(pid)
            self.native[key] = old
        self.api['context']['roster']['settings']['waiver_position'] = 1
        self.observations()
        with self.assertRaises(InvalidContract): self.prepare(pid)
        self.api['context']['roster']['settings']['waiver_position'] = 2
        self.observations()
        self.write('valuation.json', {**self.valuation, 'status': 'blocked'})
        with self.assertRaises(InvalidContract): self.prepare(pid)

    def test_disconnect_retains_unknown_without_native_claim(self):
        action = self.prepare(self.register())
        self.ops.dispatch_step(action['id'], action['token'])
        self.advance()
        self.observations()
        self.assertEqual(self.ops.reconcile_step(action['id'], 'roster-api.json', 'roster-native.json')['outcome'], 'outcome_unknown')
        with self.assertRaises(InvalidContract): self.prepare(action['plan_id'])

    def test_zero_ir_slots_and_full_activation_block(self):
        self.plan['steps'] = [{'kind': 'ir_place', 'claim_key': 'ir', 'add': 'b'}]
        self.native['ir_eligible_player_ids'] = ['b']
        self.observations()
        with self.assertRaises(InvalidContract): self.prepare(self.register())

    def test_full_ir_activation_requires_separate_space_creation(self):
        self.api['context']['roster'].update(players=['a', 'b', 'c'], reserve=['b'])
        self.native.update(owned_player_ids=['a', 'b', 'c'], reserve=['b'], ir_roster_legal=False)
        self.plan['steps'] = [{'kind': 'ir_activate', 'claim_key': 'activate', 'add': 'b'}]
        self.observations()
        with self.assertRaisesRegex(InvalidContract, 'capacity'):
            self.prepare(self.register())

    def test_exact_cancellation_and_unmanaged_claims(self):
        self.native['pending_claims'] = [{'claim_id': 'old', 'add': 'd', 'drop': 'b', 'priority': 1}]
        self.observations()
        with self.assertRaisesRegex(InvalidContract, 'Unmanaged'):
            self.prepare(self.register())
        self.plan['steps'] = [{'kind': 'cancel_claim', 'claim_key': 'cancel-old', 'platform_claim_id': 'old'}]
        action = self.prepare(self.register())
        self.ops.dispatch_step(action['id'], action['token'])
        self.advance()
        self.native['pending_claims'] = []
        self.native['claim_results'] = [{'claim_id': 'old', 'status': 'cancelled'}]
        self.observations()
        self.assertEqual(self.ops.reconcile_step(action['id'], 'roster-api.json', 'roster-native.json')['outcome'], 'cancelled')

    def test_transaction_and_lineup_share_conflict_gate(self):
        action = self.prepare(self.register())
        with self.assertRaisesRegex(InvalidContract, 'roster transaction'):
            self.engine.register('proposal.json', 'authority.json')
        self.ops.dispatch_step(action['id'], action['token'])
        with self.assertRaises(InvalidContract):
            self.engine.register('proposal.json', 'authority.json')

    def test_protected_drop_and_tampered_comparison_block(self):
        self.plan['protected_player_ids'].append('b')
        with self.assertRaisesRegex(InvalidContract, 'Protected'):
            self.prepare(self.register())
        self.plan['protected_player_ids'].remove('b')
        pid = self.register()
        self.write('valuation.json', {**self.valuation, 'modeled_gain': 1000})
        with self.assertRaisesRegex(InvalidContract, 'differs from its source'):
            self.prepare(pid)

    def test_unused_expired_token_retires_but_unknown_token_does_not(self):
        action = self.prepare(self.register())
        self.write('recovery.json', {'basis': 'explicit_owner_recovery', 'action_id': action['id'], 'reason': 'Simulated unused action'})
        with self.assertRaises(InvalidContract): self.ops.retire_unused(action['id'], 'recovery.json')
        self.now += 31
        self.assertEqual(self.ops.retire_unused(action['id'], 'recovery.json')['status'], 'new_plan_required')

    def test_ir_place_and_activate_with_capacity(self):
        self.api['context']['league']['settings']['reserve_slots'] = 1
        self.plan['rules_hash'] = rules_key(self.api['context'])
        self.plan['steps'] = [{'kind': 'ir_place', 'claim_key': 'ir', 'add': 'b'}]
        self.native['ir_eligible_player_ids'] = ['b']
        self.observations()
        action = self.prepare(self.register())
        self.ops.dispatch_step(action['id'], action['token'])
        self.advance()
        self.api['context']['roster']['reserve'] = ['b']
        self.native['reserve'] = ['b']
        self.observations()
        self.assertEqual(self.ops.reconcile_step(action['id'], 'roster-api.json', 'roster-native.json')['outcome'], 'applied')
        self.plan['steps'] = [{'kind': 'ir_activate', 'claim_key': 'activate', 'add': 'b'}]
        self.plan['created_at'] = utc(self.now)
        self.assertEqual(self.prepare(self.register())['after_reserve'], [])

    def test_wrong_pending_order_and_false_win_do_not_pass(self):
        action = self.prepare(self.register())
        self.ops.dispatch_step(action['id'], action['token'])
        self.pending(action)
        self.native['pending_claims'][0]['priority'] = 2
        self.observations()
        with self.assertRaises(InvalidContract): self.ops.reconcile_step(action['id'], 'roster-api.json', 'roster-native.json')
        self.native['pending_claims'] = []
        self.native['claim_results'] = [{'claim_key': 'one', 'claim_id': 'native-1', 'add': 'c', 'drop': 'b', 'status': 'won', 'transaction_id': 'missing'}]
        self.observations()
        self.assertEqual(self.ops.reconcile_step(action['id'], 'roster-api.json', 'roster-native.json')['outcome'], 'outcome_unknown')

    def test_lost_and_cancelled_claims_require_explicit_native_result(self):
        action = self.prepare(self.register())
        self.ops.dispatch_step(action['id'], action['token'])
        self.pending(action)
        self.native['pending_claims'] = []
        self.native['claim_results'] = [{'claim_key': 'one', 'claim_id': 'native-1', 'add': 'c', 'drop': 'b', 'status': 'lost'}]
        self.observations()
        self.assertEqual(self.ops.reconcile_step(action['id'], 'roster-api.json', 'roster-native.json')['outcome'], 'lost')
