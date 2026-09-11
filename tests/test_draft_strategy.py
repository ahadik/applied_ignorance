"""Synthetic, offline strategy and controller handoff tests."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from fantasy_agent.drafting.controller import build, rank, update_strategy
from fantasy_agent.drafting.draft_strategy import Engine, candidate_export, fingerprint, load_policy, owner
from fantasy_agent.drafting.draft_strategy_evaluate import draft, state_from_ids
from fantasy_agent.core.storage import save_atomic


def fixture():
    policy = load_policy()
    policy.update(samples_per_mode=1, shortlist_each=2, scenario_modes=['ecr', 'needs'])
    players = []
    for pos in ('QB', 'RB', 'WR', 'TE', 'K', 'DEF'):
        for n in range(8):
            sid = pos+str(n)
            players.append({'player_id':sid, 'name':sid, 'position':pos,
                            'ecr':n*6+len(players)//8+1, 'adp_rank':n*6+1,
                            'board_rank':len(players)+1, 'flags':[], 'exclude':False,
                            'scoring':{'core_fields_complete':True, 'supported_points':200-n*15}})
    stamp = datetime.now(timezone.utc).isoformat()
    board = {'players':players, 'teams':2, 'league_id':'123', 'draft_id':'456',
             'generated_at':stamp, 'roster_positions':['QB','RB','WR','TE','FLEX','K','DEF','BN'],
             'starter_baselines':{p:{'supported_points':100} for p in ('QB','RB','WR','TE')},
             'critical_unmatched':[],
             'sources':[{'name':'ecr','fetched_at':stamp,'max_fetch_age_hours':6},
                        {'name':'injuries','fetched_at':stamp,'max_fetch_age_hours':.25}]}
    return board, policy


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.board, self.policy = fixture()
        self.engine = Engine(self.board, self.policy)

    def test_marginal_value_depends_on_owned_starters(self):
        self.assertGreater(self.engine.marginal('QB1',[]), self.engine.marginal('QB1',['QB0']))
        self.assertGreater(self.engine.marginal('WR0',['QB0']), self.engine.marginal('QB1',['QB0']))

    def test_flex_and_bench_do_not_double_count_starters(self):
        roster = ['QB0','RB0','WR0','TE0','WR1']
        self.assertEqual(self.engine.utility(roster, include_bench=False, fill=False), 985)
        self.assertEqual(self.engine.utility(roster, fill=False), 985)
        self.assertGreater(self.engine.utility(roster+['QB1'], fill=False),985)
        self.assertEqual(self.engine.utility(roster+['QB1'], include_bench=False,fill=False),985)

    def test_specialists_late_and_no_excess_backups_early(self):
        allowed = self.engine.eligible(self.engine.ordered,['QB0'])
        self.assertNotIn('QB1',allowed)
        self.assertNotIn('K0',allowed)
        roster = ['QB0','RB0','WR0','TE0','RB1','WR1']
        allowed = self.engine.eligible(self.engine.ordered,roster)
        self.assertEqual({self.engine.players[s]['position'] for s in allowed},{'K','DEF'})

    def test_last_pick_must_fill_defense(self):
        roster = ['QB0','RB0','WR0','TE0','RB1','WR1','K0']
        allowed = self.engine.eligible(self.engine.ordered,roster)
        self.assertEqual({self.engine.players[s]['position'] for s in allowed},{'DEF'})

    def test_impossible_roster_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'cannot satisfy'):
            self.engine.eligible(self.engine.ordered,['QB0','QB1','QB2','QB3','QB4','QB5'])

    def test_explicit_exclusion_and_reasoned_multiplier(self):
        self.policy['overrides'] = {'RB0':{'exclude':True,'reason':'Synthetic unavailable player'},
                                    'WR0':{'multiplier':.8,'reason':'Sensitivity scenario only'}}
        engine = Engine(self.board,self.policy)
        self.assertNotIn('RB0',engine.eligible(engine.ordered,[]))
        self.assertEqual(engine.values['WR0'],160)
        self.policy['overrides']['QB0'] = {'exclude':True}
        with self.assertRaisesRegex(ValueError,'reason'):
            Engine(self.board,self.policy)

    def test_weekly_injury_flags_are_not_season_probability(self):
        self.board['players'][0].update(injury={'probability_of_playing':0}, flags=['injury_review'])
        engine = Engine(self.board,self.policy)
        self.assertEqual(engine.values['QB0'],self.engine.values['QB0'])

    def test_policy_rejects_nonfinite_coefficients(self):
        for key in ('bench_weight','opponent_temperature'):
            policy = copy.deepcopy(self.policy)
            policy[key] = float('nan')
            with self.assertRaises(ValueError):
                Engine(self.board,policy)

    def test_unknown_override_and_insufficient_caps_fail(self):
        self.policy['overrides'] = {'missing':{'exclude':True,'reason':'Typo'}}
        with self.assertRaisesRegex(ValueError,'Unknown override'):
            Engine(self.board,self.policy)
        self.policy['overrides'] = {}
        self.board['roster_positions'].append('QB')
        self.policy['caps']['QB'] = 1
        with self.assertRaisesRegex(ValueError,'caps'):
            Engine(self.board,self.policy)

    def test_recommendations_repeat_for_same_seed_and_state(self):
        state = state_from_ids(self.board,[],1,'repeat')
        a,b = self.engine.recommend(state),self.engine.recommend(state)
        a.pop('runtime_seconds'); b.pop('runtime_seconds')
        self.assertEqual(a,b)
        self.assertEqual(len(a['fallback_order']),len(set(a['fallback_order'])))

    def test_turn_seat_has_certain_immediate_return_availability(self):
        state = state_from_ids(self.board,['RB0'],2,'turn')
        result = self.engine.recommend(state)
        self.assertEqual(result['following_pick'],3)
        self.assertTrue(all(p['scenario_survival_if_pass']==1 for p in result['recommendations']))
        self.assertNotIn('RB0',result['fallback_order'])

    def test_opponents_respond_to_roster_needs(self):
        available = ['QB0','RB0','WR0','TE0','K0','DEF0']
        # Exactly two slots left: only the unfilled mandatory specialists are legal.
        roster = ['QB1','RB1','WR1','TE1','RB2','WR2']
        for mode in ('ecr','adp','needs','rb_run','qb_run'):
            self.assertIn(self.engine.opponent_pick(available,roster,mode,random.Random(1)),['K0','DEF0'])

    def test_changed_ownership_unknown_ids_and_format_fail(self):
        state = state_from_ids(self.board,['RB0'],2,'invalid')
        changed = copy.deepcopy(state)
        changed['rosters_by_slot'] = {'1':[],'2':['RB0']}
        with self.assertRaisesRegex(ValueError,'ownership'):
            self.engine.recommend(changed)
        changed = copy.deepcopy(state)
        changed['drafted_ids'] = ['unknown']
        with self.assertRaisesRegex(ValueError,'absent'):
            self.engine.recommend(changed)
        changed = copy.deepcopy(state)
        changed['settings']['reversal_round'] = 3
        with self.assertRaisesRegex(ValueError,'unsupported'):
            self.engine.recommend(changed)

    def test_missing_opponent_rosters_and_wrong_slots_fail(self):
        state = state_from_ids(self.board,[],1,'invalid')
        state.pop('rosters_by_slot')
        with self.assertRaisesRegex(ValueError,'opponent rosters'):
            self.engine.recommend(state)
        state = state_from_ids(self.board,[],1,'invalid')
        state['settings']['slots_flex'] += 1
        with self.assertRaisesRegex(ValueError,'FLEX'):
            self.engine.recommend(state)

    def test_unknown_opponent_identity_counts_without_valuation(self):
        state = state_from_ids(self.board,['RB0'],2,'identity')
        state['drafted_ids'] = ['missing']
        state['rosters_by_slot']['1'] = ['missing']
        state['drafted_identity'] = {'missing':{'name':'Opponent receiver','position':'WR'}}
        original = copy.deepcopy(self.board)
        result = self.engine.recommend(state)
        self.assertEqual(self.engine.needs(['missing'])['WR'],0)
        self.assertNotIn('missing',self.engine.values)
        self.assertNotIn('missing',self.engine.usable)
        self.assertNotIn('missing',result['fallback_order'])
        self.assertEqual(self.board,original)
        changed = copy.deepcopy(state)
        changed['drafted_identity']['missing']['position'] = 'RB'
        self.assertNotEqual(fingerprint(state),fingerprint(changed))

    def test_unknown_own_player_and_invalid_identity_still_fail(self):
        state = state_from_ids(self.board,['RB0'],1,'identity')
        state['drafted_ids'] = ['missing']
        state['rosters_by_slot']['1'] = ['missing']
        state['roster'][0]['player_id'] = 'missing'
        state['drafted_identity'] = {'missing':{'name':'Missing owned player','position':'RB'}}
        with self.assertRaisesRegex(ValueError,'absent'):
            Engine(self.board,self.policy).recommend(state)
        state = state_from_ids(self.board,['RB0'],2,'identity')
        state['drafted_ids'] = ['missing']
        state['rosters_by_slot']['1'] = ['missing']
        state['drafted_identity'] = {'missing':{'name':'Unknown role','position':'UNKNOWN'}}
        with self.assertRaisesRegex(ValueError,'absent'):
            Engine(self.board,self.policy).recommend(state)

    def test_unsupported_extra_slots_and_bad_seat_fail(self):
        state = state_from_ids(self.board,[],1,'invalid')
        state['settings']['slots_super_flex'] = 1
        with self.assertRaisesRegex(ValueError,'additional roster'):
            self.engine.recommend(state)
        state['settings'].pop('slots_super_flex')
        state['seat'] = 0
        with self.assertRaisesRegex(ValueError,'seat'):
            self.engine.recommend(state)

    def test_complete_paired_synthetic_drafts_have_legal_unique_rosters(self):
        for seat in (1,2):
            for method in ('engine','ecr'):
                result = draft(self.engine,seat,'qb_run',77,method)
                self.assertEqual(len(result['roster']),8)
                self.assertEqual(len(set(result['roster'])),8)
                self.assertFalse(any(self.engine.needs(result['roster']).values()))


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.board,self.policy = fixture()
        self.engine = Engine(self.board,self.policy)
        self.state = state_from_ids(self.board,[],1,'handoff')
        self.state.update(simulation=False,draft_id='456',remaining_slots=8,needs=self.engine.needs([]))
        self.result = self.engine.recommend(self.state)

    def test_operational_export_preserves_source_deadline_and_order(self):
        exported = candidate_export(self.board,self.state,self.result,datetime.now(timezone.utc))
        self.assertEqual(exported['observed_at'],self.board['sources'][0]['fetched_at'])
        self.assertEqual([p['player_id'] for p in rank(self.state,exported)],self.result['fallback_order'])

    def test_another_pick_invalidates_old_strategy(self):
        exported = candidate_export(self.board,self.state,self.result,datetime.now(timezone.utc))
        changed = copy.deepcopy(self.state)
        changed['last_pick'] = 1
        with self.assertRaisesRegex(ValueError,'recompute'):
            rank(changed,exported)

    def test_explicit_mock_binding_cannot_override_another_real_league(self):
        mock = dict(self.state,league_id=None,draft_id='789')
        result = self.engine.recommend(mock)
        current = datetime.now(timezone.utc)
        with self.assertRaises(ValueError):
            candidate_export(self.board,mock,result,current)
        exported = candidate_export(self.board,mock,result,current,allow_mock=True)
        self.assertEqual(exported['draft_id'],'789')
        self.assertTrue(exported['mock_uses_league_board'])
        mock['league_id'] = 'other-real-league'
        with self.assertRaises(ValueError):
            candidate_export(self.board,mock,result,current,allow_mock=True)

    def test_finished_controller_does_not_require_old_candidates(self):
        from fantasy_agent.drafting.controller import report
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            save_atomic(folder/'state.json',dict(self.state,next_pick=None))
            save_atomic(folder/'health.json',{'ok':True})
            save_atomic(folder/'candidates.json',{'expires_at':'2020-01-01T00:00:00+00:00'})
            result = report(folder)
            self.assertFalse(result['ready'])
            self.assertTrue(result['finished_selecting'])
            self.assertEqual(result['blockers'],[])

    def test_timestamp_refresh_does_not_change_fingerprint(self):
        changed = dict(self.state,observed_at='2020-01-01T00:00:00+00:00')
        self.assertEqual(fingerprint(changed),fingerprint(self.state))
        changed['seat'] = 2
        self.assertNotEqual(fingerprint(changed),fingerprint(self.state))

    def test_simulation_wrong_league_stale_state_and_stale_source_block_export(self):
        current = datetime.now(timezone.utc)
        for changed in (dict(self.state,simulation=True),dict(self.state,league_id='789'),
                        dict(self.state,observed_at=(current-timedelta(seconds=21)).isoformat())):
            with self.assertRaises(ValueError):
                candidate_export(self.board,changed,self.result,current)
        with self.assertRaisesRegex(ValueError,'stale inputs'):
            candidate_export(self.board,dict(self.state,observed_at=(current+timedelta(minutes=16)).isoformat()),
                             self.result,current+timedelta(minutes=16))

    def test_controller_reuses_result_but_revalidates_source_age(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            board_path,policy_path = folder/'board.json',folder/'policy.json'
            save_atomic(board_path,self.board); save_atomic(policy_path,self.policy)
            update_strategy(folder,self.state,board_path,policy_path)
            with patch('fantasy_agent.drafting.draft_strategy.Engine.recommend',side_effect=AssertionError('Unexpected recompute')):
                update_strategy(folder,self.state,board_path,policy_path)
            self.policy['seed'] += 1
            save_atomic(policy_path,self.policy)
            with patch('fantasy_agent.drafting.draft_strategy.Engine.recommend',wraps=self.engine.recommend) as recommend:
                update_strategy(folder,self.state,board_path,policy_path)
                self.assertEqual(recommend.call_count,1)
            before = (folder/'candidates.json').read_bytes()
            self.board['sources'][1]['fetched_at'] = '2020-01-01T00:00:00+00:00'
            save_atomic(board_path,self.board)
            with self.assertRaises(ValueError):
                update_strategy(folder,self.state,board_path,policy_path)
            self.assertEqual((folder/'candidates.json').read_bytes(),before)

    def test_controller_keeps_every_teams_roster(self):
        settings = self.state['settings']
        settings['rounds'] = 8
        draft_record = {'draft_id':'456','type':'snake','status':'drafting','draft_order':{'u':1},'settings':settings}
        picks = [{'draft_id':'456','pick_no':i,'draft_slot':owner(i,2),'player_id':sid,'metadata':{'position':sid[:2]}}
                 for i,sid in enumerate(['RB0','WR0','QB0'],1)]
        state = build(draft_record,picks,'u')
        self.assertEqual(state['rosters_by_slot'],{'1':['RB0'],'2':['WR0','QB0']})

    def test_controller_recomputes_after_engine_version_change(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            board_path,policy_path = folder/'board.json',folder/'policy.json'
            save_atomic(board_path,self.board)
            save_atomic(policy_path,self.policy)
            update_strategy(folder,self.state,board_path,policy_path)
            previous = json.loads((folder/'strategy_result.json').read_text())
            previous['engine_version'] = 0
            save_atomic(folder/'strategy_result.json',previous)
            with patch('fantasy_agent.drafting.draft_strategy.Engine.recommend',wraps=self.engine.recommend) as recommend:
                update_strategy(folder,self.state,board_path,policy_path)
                self.assertEqual(recommend.call_count,1)


if __name__=='__main__':
    unittest.main()
