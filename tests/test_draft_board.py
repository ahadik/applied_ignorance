from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from controller import rank
from draft_inputs import load_inputs
from draft_board import (OFFENSE, POSITIONS, STAT_MAP, export_candidates, index, make_board,
                         match_player, scoring, starter_values, validate_sources)


def fixtures():
    now = datetime.now(timezone.utc)
    stamp = now.isoformat()
    scoring_settings = {'pass_yd':.04,'pass_td':4,'pass_int':-1,'rush_yd':.1,'rush_td':6,
                        'rec':1,'rec_yd':.1,'rec_td':6,'fum_lost':-2,'xpm':1,'fgmiss':-1,'sack':1,'int':2}
    context = {'fetched_at':stamp,'league':{'season':'2026','league_id':'123','scoring_settings':scoring_settings,
               'roster_positions':['QB','RB','WR','TE','FLEX','FLEX','K','DEF','BN']},
               'draft':{'draft_id':'456','season':'2026','settings':{'teams':1,'rounds':9}}}
    inputs = {'context':context}
    def envelope(data, request=None):
        return {'fetched_at':stamp,'cache_hit':True,'data':data,'request':{'params':request or {}}}
    sl, fp, ecr, proj = {}, [], [], {p:[] for p in POSITIONS}
    for p in POSITIONS:
        for n in range(5):
            fid = str(len(fp)+1)
            sid = 'sl'+fid
            club = 'T'+fid
            sl[sid] = {'player_id':sid,'full_name':p+fid,'position':p,'fantasy_positions':[p],
                       'team':club,'status':'Active','active':True,'sportradar_id':'uuid'+fid,'espn_id':fid}
            fp.append({'player_id':fid,'player_name':p+fid,'position_id':p,'team_id':club,
                       'sportsdata_player_id':'uuid'+fid,'espn_id':fid})
            ecr.append({'player_id':fid,'player_position_id':p,'rank_ecr':len(fp)})
            stats = {field:float(20-n) for field in STAT_MAP.values()}
            stats |= {'points':100,'points_ppr':120-n,'fumbles':2,'fga':30,'fg':25,'xpt':40,
                      'def_sack':40,'def_int':10,'def_fr':8,'def_ff':15,'def_safety':1}
            proj[p].append({'fpid':fid,'position_id':'DST' if p=='DEF' else p,'team_id':club,'stats':stats})
    inputs['sleeper_players'] = envelope(sl)
    inputs['fp_external'] = envelope({'season':'2026','players':fp,'count':len(fp)})
    for name in ('ecr','adp'):
        inputs[name] = envelope({'year':'2026','week':'0','scoring':'PPR','ranking_type_name':'draft' if name=='ecr' else 'adp','players':ecr,'count':len(ecr)})
    for pos, values in proj.items():
        pos = 'DST' if pos=='DEF' else pos
        inputs['projections_'+pos] = envelope({'season':'2026','week':'0','positions':pos,'players':values,'count':len(values)}, {'position':pos,'week':0})
    inputs['nfl_state'] = envelope({'season':'2026','week':1,'season_type':'regular'})
    inputs['injuries'] = envelope({'injuries':[],'count':0},{'year':2026,'week':1})
    inputs['news'] = envelope({'items':[],'count':0})
    history = {'players':[],'sources':[],'depth_quality':{}}
    return inputs, history, now


class ScoringTests(unittest.TestCase):
    def test_hand_calculated_ppr_and_custom_interception_penalty(self):
        stats = {'pass_yds':100,'pass_tds':2,'pass_ints':1,'rush_yds':20,'rush_tds':1,
                 'rec_rec':3,'rec_yds':40,'rec_tds':1,'fumbles':7,'points':29,'points_ppr':32}
        settings = {'pass_yd':.04,'pass_td':4,'pass_int':-1,'rush_yd':.1,'rush_td':6,
                    'rec':1,'rec_yd':.1,'rec_td':6,'fum_lost':-2}
        result = scoring(stats,'QB',settings)
        self.assertEqual(result['supported_points'],32)
        self.assertEqual(result['ppr_reception_check_error'],0)
        self.assertEqual(result['uncovered_rules'],['fum_lost'])
        self.assertFalse(result['exact_league_total'])
        self.assertNotIn('fum_lost',result['contributions'])

    def test_half_ppr_and_missing_receptions(self):
        result = scoring({'rec_rec':10,'rec_yds':100,'rec_tds':1},'WR',{'rec':.5,'rec_yd':.1,'rec_td':6})
        self.assertEqual(result['supported_points'],21)
        missing = scoring({'rec_yds':100,'rec_tds':1},'WR',{'rec':1,'rec_yd':.1,'rec_td':6})
        self.assertIn('rec',missing['uncovered_rules'])
        self.assertFalse(missing['core_fields_complete'])

    def test_kicker_bands_and_zero_defense_buckets_are_not_fabricated(self):
        result = scoring({'fg':30,'fga':35,'xpt':40},'K',{'fgmiss':-1,'xpm':1,'xpmiss':-1,'fgm_50_59':5})
        self.assertEqual(result['supported_points'],35)
        self.assertIn('fgm_50_59',result['uncovered_rules'])
        self.assertIn('xpmiss',result['uncovered_rules'])
        defense = scoring({'def_sack':40,'def_pa_a':0},'DEF',{'sack':1,'pts_allow_0':10})
        self.assertEqual(defense['supported_points'],40)
        self.assertIn('pts_allow_0',defense['uncovered_rules'])

    def test_unknown_league_rules_and_nonfinite_stats_fail(self):
        with self.assertRaises(ValueError):
            scoring({},'RB',{'unmapped_bonus':1})
        with self.assertRaises(ValueError):
            scoring({'rush_yds':float('nan')},'RB',{'rush_yd':.1})


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.sl = {'1':{'player_id':'1','position':'WR','sportradar_id':'u','espn_id':'e'},
                   '2':{'player_id':'2','position':'WR','sportradar_id':'v','espn_id':'f'}}
        self.indices = {f:index(self.sl.values(),f,'player_id') for f in ('sportradar_id','espn_id','yahoo_id')}

    def test_conflicting_ids_are_quarantined(self):
        sid, why = match_player([{'sportsdata_id':'u','espn_id':'f'}],'WR','X',self.sl,self.indices)
        self.assertIsNone(sid)
        self.assertEqual(why,['conflicting_ids'])

    def test_name_alone_never_matches(self):
        self.assertIsNone(match_player([{'player_name':'Same name'}],'WR','X',self.sl,self.indices)[0])

    def test_position_checks_and_numeric_id_normalization(self):
        self.assertEqual(match_player([{'sportsdata_id':'u'}],'WR','X',self.sl,self.indices)[0],'1')
        self.assertIsNone(match_player([{'sportsdata_id':'u'}],'TE','X',self.sl,self.indices)[0])

    def test_defenses_match_explicit_team_not_player_names(self):
        self.sl['JAX'] = {'position':'DEF','team':'JAX'}
        self.assertEqual(match_player([], 'DEF','JAX',self.sl,self.indices)[0],'JAX')


class BoardTests(unittest.TestCase):
    def test_flex_allocation_changes_replacement_without_double_counting(self):
        players = []
        for pos in OFFENSE:
            for n in range(6):
                points = {'QB':100,'RB':90,'WR':70,'TE':50}[pos]-n*10
                players.append({'position':pos,'player_id':pos+str(n),'name':pos+str(n),'exclude':False,
                                'scoring':{'core_fields_complete':True,'supported_points':points}})
        result = starter_values(players,['QB','RB','WR','TE','FLEX','FLEX'],1)
        self.assertEqual(sum(p['starter_count'] for p in result.values()),6)
        self.assertEqual(result['RB']['starter_count'],3)
        self.assertEqual(result['RB']['replacement_name'],'RB3')
        self.assertEqual(players[6]['starter_value'],30)

    def test_complete_board_and_controller_removes_drafted_candidate(self):
        inputs, history, now = fixtures()
        board = make_board(inputs,history,2026,now)
        self.assertFalse(board['critical_unmatched'])
        self.assertEqual(board['coverage']['matched_in_range'],9)
        exported = export_candidates(board,now)
        state = {'draft_id':'456','drafted_ids':['sl1'],'needs':{'QB':1,'RB':1,'WR':1,'TE':1,'FLEX':2,'K':1,'DEF':1},'remaining_slots':9}
        ranked = rank(state,exported)
        self.assertNotIn('sl1',[p['player_id'] for p in ranked])
        self.assertEqual(ranked[0]['player_id'],'sl2')

    def test_stale_export_does_not_retimestamp_sources(self):
        inputs, history, now = fixtures()
        board = make_board(inputs,history,2026,now)
        self.assertEqual(export_candidates(board,now)['observed_at'],inputs['ecr']['fetched_at'])
        with self.assertRaises(ValueError):
            export_candidates(board,now+timedelta(minutes=16))

    def test_controller_rejects_previously_exported_expired_inputs(self):
        inputs, history, now = fixtures()
        exported = export_candidates(make_board(inputs,history,2026,now),now)
        exported['expires_at'] = (now-timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError,'expired'):
            rank({'draft_id':'456'},exported)

    def test_mfl_conflict_excludes_projection_and_bad_probability_fails(self):
        inputs, history, now = fixtures()
        inputs['fp_external']['data']['players'][0]['mfl_id'] = '1'
        inputs['projections_QB']['data']['players'][0]['mflid'] = '2'
        board = make_board(inputs,history,2026,now)
        self.assertTrue(board['players'][0]['exclude'])
        inputs['injuries']['data'] = {'count':1,'injuries':[{'player_id':'1','probability_of_playing':1.2}]}
        with self.assertRaises(ValueError):
            make_board(inputs,history,2026,now)

    def test_mixed_season_and_wrong_injury_week_rejected(self):
        inputs, _, now = fixtures()
        inputs['projections_QB']['data']['season'] = '2025'
        with self.assertRaises(ValueError):
            validate_sources(inputs,2026,now)
        inputs, _, now = fixtures()
        inputs['injuries']['request']['params']['week'] = 2
        with self.assertRaises(ValueError):
            validate_sources(inputs,2026,now)

    def test_ros_and_wrong_position_requests_rejected(self):
        inputs, _, now = fixtures()
        inputs['projections_TE']['request']['params']['ros'] = True
        with self.assertRaises(ValueError):
            validate_sources(inputs,2026,now)

    def test_count_mismatch_and_duplicate_projection_ids_rejected(self):
        inputs, history, now = fixtures()
        inputs['projections_QB']['data']['count'] = 100
        with self.assertRaises(ValueError):
            make_board(inputs,history,2026,now)
        inputs, history, now = fixtures()
        inputs['projections_QB']['data']['players'][1]['fpid'] = '1'
        with self.assertRaises(ValueError):
            make_board(inputs,history,2026,now)

    def test_unmatched_top_candidate_blocks_export(self):
        inputs, history, now = fixtures()
        inputs['fp_external']['data']['players'][0]['sportsdata_player_id'] = 'unknown'
        inputs['fp_external']['data']['players'][0]['espn_id'] = None
        board = make_board(inputs,history,2026,now)
        self.assertEqual(len(board['critical_unmatched']),1)
        with self.assertRaises(ValueError):
            export_candidates(board,now)

    def test_injury_probability_does_not_change_numeric_projection(self):
        inputs, history, now = fixtures()
        before = make_board(inputs,history,2026,now)['players'][0]['scoring']
        inputs['injuries']['data'] = {'count':1,'injuries':[{'player_id':'1','status':'Out','probability_of_playing':0}]}
        after = make_board(inputs,history,2026,now)['players'][0]
        self.assertEqual(before,after['scoring'])
        self.assertIn('injury_review',after['flags'])

    def test_incomplete_collection_and_tampering_fail(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            (folder/'collection.json').write_text(json.dumps({'complete':False}))
            with self.assertRaises(ValueError):
                load_inputs(folder)
            (folder/'x.json').write_text('{}')
            manifest = {'complete':True,'datasets':[{'name':'x','file':'x.json','sha256':'bad'}]}
            (folder/'collection.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                load_inputs(folder)


if __name__ == '__main__':
    unittest.main()
