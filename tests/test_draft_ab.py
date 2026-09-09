"""Independent reference checks and bounded adversarial-tree tests; offline."""
import copy
import math
import random
import unittest
from unittest.mock import patch

from draft_ab import ABPlanner,phase
from draft_strategy import Engine,upcoming
from draft_strategy_evaluate import baseline_prefix,state_from_ids
from tests.test_draft_strategy import fixture


def slow_opponent(engine,available,roster,mode,rng):
    needs = engine.needs(roster)
    def score(s):
        pos = engine.players[s]['position']
        result = engine.market[s][int(mode=='adp')]
        if mode in ('needs','rb_run','qb_run'):
            fits = needs[pos]>0 or pos in ('RB','WR','TE') and needs['FLEX']>0
            result += -8 if fits else 30
        if mode=='rb_run' and pos=='RB': result -= 15
        if mode=='qb_run' and pos=='QB': result -= 20
        return result
    top = sorted(engine.eligible(available,roster,own=False),key=lambda s:(score(s),s))[:5]
    weights = [math.exp(-(score(s)-score(top[0]))/engine.policy['opponent_temperature']) for s in top]
    return rng.choices(top,weights=weights,k=1)[0]


class ABTests(unittest.TestCase):
    def setUp(self):
        self.board,self.policy = fixture()
        self.board['teams'] = 4
        self.policy['ab'].update(first_width=3,future_width=2,reply_width=2,response_width=2,tail_samples=1)
        self.engine = Engine(self.board,self.policy)

    def state(self,rnd=1):
        ids = baseline_prefix(self.engine,3,rnd,'needs',71)
        return state_from_ids(self.board,ids,3,'unit-ab')

    def test_actual_seat_phase_and_horizons(self):
        for last,expected in ((12,'A'),(15,'B'),(40,'A'),(43,'B'),(180,'A'),(183,'FINAL')):
            state = {'last_pick':last,'seat':13}
            self.assertEqual(phase(state,14,14),expected)
        self.assertEqual(upcoming(15,13,14,14)[:3],[16,41,44])
        self.assertEqual(phase({'last_pick':0,'seat':7},14,14),'GENERAL')

    def test_indexed_opponents_exactly_match_original_full_scan(self):
        rosters = [[],['QB0'],['QB0','RB0','WR0','TE0','RB1','WR1']]
        for roster in rosters:
            available = [s for s in self.engine.ordered if s not in roster and s not in ('WR2','RB3','QB2')]
            for mode in ('ecr','adp','needs','rb_run','qb_run'):
                for seed in range(20):
                    expected = slow_opponent(self.engine,available,roster,mode,random.Random(seed))
                    actual = self.engine.opponent_pick(set(available),roster,mode,random.Random(seed))
                    self.assertEqual(actual,expected)

    def test_greedy_keeps_nonmonotonic_flex_bench_case(self):
        self.engine.bench_floor.update(RB=0,WR=190)
        ours = ['RB0','WR0','WR1']
        self.assertGreater(self.engine.values['RB1'],self.engine.values['RB2'])
        self.assertLess(self.engine.utility(ours+['RB1']),self.engine.utility(ours+['RB2']))
        self.assertEqual(self.engine.greedy(['RB1','RB2'],ours),'RB2')
        self.assertEqual(ABPlanner(self.engine).greedy({'RB1','RB2'},ours),'RB2')

    def test_cached_greedy_reuses_exact_order_without_availability_leakage(self):
        planner = ABPlanner(self.engine)
        ours = ['QB0','RB0','WR0']
        pool = set(self.engine.usable)-set(ours)
        for _ in range(5):
            expected = self.engine.greedy(pool,ours)
            self.assertEqual(planner.greedy(pool,ours),expected)
            pool.remove(expected)
        self.assertEqual(planner.work['greedy_rankings_built'],1)

    def test_response_paths_are_legal_bounded_and_owned_by_neighbor(self):
        state = self.state()
        pool = set(self.engine.players)-set(state['drafted_ids'])
        teams = {int(s):list(r) for s,r in state['rosters_by_slot'].items()}
        planner = ABPlanner(self.engine)
        responses = planner.responses(pool,teams,4,6)
        self.assertLessEqual(len(responses),4)
        self.assertGreater(len(responses),1)
        for later,after,path in responses:
            self.assertEqual(len(path),2)
            self.assertEqual(len(set(path)),2)
            self.assertFalse(set(path)&later)
            self.assertEqual(after[4],teams[4]+path)
            self.assertEqual(after[3],teams[3])
            self.assertEqual(later,pool-set(path))
        with self.assertRaisesRegex(ValueError,'short gap'):
            planner.responses(pool,teams,4,8)

    def test_pair_uses_best_reply_after_each_response_then_worst_outcome(self):
        planner = ABPlanner(self.engine)
        teams = {s:[] for s in range(1,5)}
        # Two explicit scenarios: the opponent takes WR0 or WR1. TE7 is
        # available in both but is an inferior reply. Recourse must adapt.
        replies = [({'WR1','TE7'},teams,['WR0','QB0']),({'WR0','TE7'},teams,['WR1','QB0'])]
        with patch.object(planner,'responses',return_value=replies):
            result = planner.pair_for('RB0',{'RB0','WR0','WR1','TE7','QB0'},teams,3,3,6)
        self.assertEqual({r['reply'] for r in result['branches']},{'WR0','WR1'})
        expected = self.engine.utility(['RB0','WR1'])
        self.assertEqual(result['score'],expected)
        self.assertGreater(result['mean'],expected)
        self.assertEqual(result['worst']['reply'],'WR1')

    def test_a_uses_terminal_proxy_and_b_solves_future_pair(self):
        planner = ABPlanner(self.engine)
        with patch.object(planner,'tail_gain',wraps=planner.tail_gain) as tail:
            a = planner.recommend(self.state(1))
            self.assertGreater(tail.call_count,0)
        self.assertEqual(a['phase'],'A')
        self.assertEqual(a['horizon_picks'],[3,6,11])
        self.assertTrue(all(r['score']==r['downside_gain'] for r in a['recommendations']))
        planner = ABPlanner(self.engine)
        with patch.object(planner,'solve_pair',wraps=planner.solve_pair) as solve:
            b = planner.recommend(self.state(2))
            self.assertGreater(solve.call_count,0)
            self.assertTrue(all(c.args[-2:]==(11,14) for c in solve.call_args_list))
        self.assertEqual(b['phase'],'B')
        self.assertEqual(b['horizon_picks'],[6,11,14])
        for r in b['recommendations']:
            self.assertAlmostEqual(r['score'],.75*r['horizon_mean_gain']+.25*r['downside_gain'])
            self.assertLessEqual(r['downside_gain'],r['horizon_mean_gain'])

    def test_terminal_pair_never_simulates_past_draft_and_last_pick_truncates(self):
        planner = ABPlanner(self.engine)
        with patch.object(planner,'tail_gain',side_effect=AssertionError('No terminal continuation')):
            result = planner.recommend(self.state(7))
        self.assertEqual(len(result['horizon_picks']),2)
        final = self.engine.recommend(self.state(8))
        self.assertEqual(final['phase'],'FINAL')
        self.assertEqual(len(final['horizon_picks']),1)

    def test_reproducibility_and_no_input_mutation(self):
        state = self.state(2)
        original = copy.deepcopy(state)
        a,b = self.engine.recommend(state),self.engine.recommend(state)
        a.pop('runtime_seconds'); b.pop('runtime_seconds')
        self.assertEqual(a,b)
        self.assertEqual(state,original)

    def test_policy_bounds_reject_unbounded_work(self):
        for key,value in (('response_width',100),('tail_weight',float('nan')),('prefix_samples',0)):
            changed = copy.deepcopy(self.policy)
            changed['ab'][key] = value
            with self.assertRaisesRegex(ValueError,'A/B'):
                Engine(self.board,changed)

    def test_offturn_prefix_choices_remain_available_in_observed_state(self):
        state = state_from_ids(self.board,[],3,'before-turn')
        result = self.engine.recommend(state)
        self.assertEqual(result['target_pick'],3)
        self.assertTrue(all(0<r['scenario_survival_to_our_pick']<=1 for r in result['recommendations']))
        self.assertEqual(len(result['fallback_order']),len(set(result['fallback_order'])))


if __name__=='__main__':
    unittest.main()
