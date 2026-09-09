import copy
import hashlib
import json
from datetime import datetime,timezone
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from draft_data import read_pre_draft_context
from draft_preplan import assigned_order,make_plan
from draft_inputs import adopt_context,load_inputs
from storage import save_atomic
from tests.test_draft_strategy import fixture


def context_fixture():
    board,policy = fixture()
    board.update(season=2026,league_scoring={'rec':1})
    settings = {'teams':2,'rounds':8,'pick_timer':120,'slots_flex':1,
                **{'slots_'+p.lower():1 for p in ('QB','RB','WR','TE','K','DEF')}}
    context = {'fetched_at':datetime.now(timezone.utc).isoformat(),'user_id':'us','picks':[],
               'traded_picks':[],'rosters':[],'league_users':[{'user_id':'us','display_name':'Our team'},
                                                          {'user_id':'them','display_name':'Other team'}],
               'league':{'league_id':'123','draft_id':'456','season':'2026',
                         'roster_positions':board['roster_positions'],'scoring_settings':{'rec':1}},
               'draft':{'draft_id':'456','league_id':'123','type':'snake','status':'pre_draft',
                        'draft_order':{'them':1,'us':2},'settings':settings}}
    return context,board,policy


class PreplanTests(unittest.TestCase):
    def test_assigned_order_requires_complete_unique_slots(self):
        context,_,_ = context_fixture()
        self.assertEqual(assigned_order(context)[0]['seat'],2)
        for order in ({'us':1},{'them':1,'us':1},{'them':True,'us':2}):
            context['draft']['draft_order'] = order
            with self.assertRaisesRegex(ValueError,'order'):
                assigned_order(context)

    def test_started_draft_or_unconfirmed_trades_fail(self):
        context,_,_ = context_fixture()
        for trades in (None,[{'round':1}]):
            context['traded_picks'] = trades
            with self.assertRaisesRegex(ValueError,'untraded'):
                assigned_order(context)
        context['traded_picks'] = []
        context['draft']['status'] = 'drafting'
        with self.assertRaisesRegex(ValueError,'started'):
            assigned_order(context)

    def test_unknown_member_and_reversal_fail(self):
        context,_,_ = context_fixture()
        context['league_users'].pop()
        with self.assertRaisesRegex(ValueError,'membership'):
            assigned_order(context)

    def test_complete_slot_mapping_supports_unclaimed_team(self):
        context,_,_ = context_fixture()
        context['draft']['draft_order'] = {'us':2}
        context['draft']['slot_to_roster_id'] = {'1':10,'2':11}
        context['rosters'] = [{'roster_id':10,'owner_id':None},{'roster_id':11,'owner_id':'us'}]
        state,rows = assigned_order(context)
        self.assertEqual(state['seat'],2)
        self.assertIsNone(rows[0]['user_id'])
        self.assertIn('Unclaimed',rows[0]['name'])
        context['draft']['draft_order']['us'] = 1
        with self.assertRaisesRegex(ValueError,'conflicts'):
            assigned_order(context)

    def test_incomplete_slot_mapping_fails(self):
        context,_,_ = context_fixture()
        context['draft']['slot_to_roster_id'] = {'1':1}
        context['rosters'] = [{'roster_id':1,'owner_id':'them'}]
        with self.assertRaisesRegex(ValueError,'slot-to-roster'):
            assigned_order(context)
        context,_,_ = context_fixture()
        context['draft']['settings']['reversal_round'] = 3
        with self.assertRaisesRegex(ValueError,'reversal'):
            assigned_order(context)

    def test_scenario_plan_uses_real_seat_and_preserves_stale_data(self):
        context,board,policy = context_fixture()
        board['sources'][0]['fetched_at'] = '2020-01-01T00:00:00+00:00'
        original = copy.deepcopy(board)
        with tempfile.TemporaryDirectory() as directory,patch('builtins.print'):
            plan = make_plan(context,board,policy,Path(directory))
            self.assertEqual([r['overall_pick'] for r in plan['pick_schedule']],[2,3,6,7,10,11,14,15])
            self.assertEqual([r['other_picks_until_next'] for r in plan['pick_schedule'][:2]],[0,2])
            self.assertTrue(plan['review_only'])
            self.assertEqual(plan['mock_profile']['seat'],2)
            self.assertIn('ecr',plan['stale_board_sources'])
            self.assertTrue(all(len(b['prefix_ids'])==1 for b in plan['branches']))
            self.assertFalse((Path(directory)/'candidates.json').exists())
        self.assertEqual(board,original)

    def test_changed_scoring_fails_before_artifacts(self):
        context,board,policy = context_fixture()
        context['league']['scoring_settings']['rec'] = .5
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'scoring/roster/season'):
                make_plan(context,board,policy,Path(directory))
            self.assertEqual(list(Path(directory).iterdir()),[])

    def test_collector_routes_seven_reads_through_central_sleeper(self):
        context,_,_ = context_fixture()
        responses = [context['league'],context['draft'],{'user_id':'us'},[],[],[],context['league_users']]
        with patch('draft_data.get_sleeper',side_effect=responses) as get:
            result = read_pre_draft_context({'league_id':'123','username':'example'})
        self.assertEqual(get.call_count,7)
        self.assertEqual(result['traded_picks'],[])
        self.assertEqual(result['league_users'],context['league_users'])

    def test_adopt_context_preserves_other_files_and_rejects_scope_changes(self):
        context,_,_ = context_fixture()
        context['draft']['season'] = '2026'
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            save_atomic(folder/'context.json',context)
            save_atomic(folder/'players.json',{'fetched_at':'2020-01-01','players':[]})
            entries = [{'name':name,'file':name+'.json',
                        'sha256':hashlib.sha256((folder/(name+'.json')).read_bytes()).hexdigest()}
                       for name in ('context','players')]
            save_atomic(folder/'collection.json',{'season':2026,'complete':True,'datasets':entries})
            original = (folder/'players.json').read_bytes()
            changed = copy.deepcopy(context)
            changed['draft']['draft_order'] = {'us':1,'them':2}
            adopt_context(folder,changed)
            manifest,inputs = load_inputs(folder)
            self.assertEqual(inputs['context'],changed)
            self.assertEqual((folder/'players.json').read_bytes(),original)
            self.assertEqual(json.loads((folder/'context.json').read_text()),context)
            changed['league']['league_id'] = 'wrong'
            with self.assertRaisesRegex(ValueError,'scope'):
                adopt_context(folder,changed)
            self.assertEqual(load_inputs(folder)[0],manifest)


if __name__=='__main__':
    unittest.main()
