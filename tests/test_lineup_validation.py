import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lineup_validation import validate, check_document
from tests.test_weekly import weekly_fixture
from weekly_model import timestamp
from fantasypros import APIError
import lineup_validate


class LineupValidationTests(unittest.TestCase):
    def setUp(self):
        self.inputs, self.games = weekly_fixture()
        for row in self.inputs['fp_external']['data']['players']:
            row.update(position_id='QB', team_id='BUF')
        self.proposal = {'schema_version': 1, 'league_id': 'test', 'roster_id': 1,
            'season': 2026, 'week': 1, 'created_at': '2026-09-09T12:00:00Z',
            'assignments': [{'slot_index': 0, 'slot': 'QB', 'player_id': 'b'}]}
        self.now = timestamp('2026-09-09T12:00:01Z')

    def run_check(self, **kwargs):
        with patch('lineup_validation.schedule_games', return_value=(self.games, {'BUF','NYJ'})):
            return validate(self.proposal, self.inputs, self.now, **kwargs)

    def codes(self, result):
        return {i['code'] for i in result['issues']}

    def test_valid_proposal_and_hash(self):
        result = self.run_check()
        self.assertEqual(result['status'], 'PASS')
        self.assertTrue(result['checks_passed'])
        self.assertLessEqual(timestamp(result['expires_at']), self.now.replace(minute=5))
        changed = copy.deepcopy(self.proposal)
        self.proposal['assignments'][0]['player_id'] = 'a'
        self.assertNotEqual(result['proposal_hash'], self.run_check()['proposal_hash'])

    def test_ignores_inferred_health_flags(self):
        self.proposal.update(healthy=True, validated=True, locked=False)
        self.inputs['sleeper_players']['data']['b']['injury_status'] = 'Out'
        result = self.run_check()
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('unavailable', self.codes(result))

    def test_doubtful_and_low_probability_require_review(self):
        self.inputs['injuries']['data']['injuries'] = [{'player_id':'b', 'status':'Doubtful', 'probability_of_playing': .1}]
        result = self.run_check()
        self.assertEqual(result['status'], 'REVIEW')
        self.assertFalse(result['checks_passed'])
        self.assertIn('low_play_probability', self.codes(result))

    def test_duplicate_slot_empty_and_wrong_scope(self):
        self.proposal['assignments'] *= 2
        result = self.run_check()
        self.assertTrue({'duplicate_player','slot_coverage'} <= self.codes(result))
        self.proposal['assignments'] = [{'slot_index':0,'slot':'QB','player_id':None}]
        self.assertIn('empty_slot', self.codes(self.run_check()))
        self.proposal['week'] = 2
        self.assertIn('scope_mismatch', self.codes(self.run_check()))

    def test_wrong_position_and_unowned(self):
        self.inputs['sleeper_players']['data']['b']['fantasy_positions'] = ['WR']
        self.inputs['final_context']['roster']['players'] = ['a']
        result = self.run_check()
        self.assertTrue({'not_owned','ineligible_position'} <= self.codes(result))

    def test_locked_starter_and_started_bench_moves_fail(self):
        result = self.run_check(history={'league_id':'test','players':['a','b']})
        self.assertTrue({'locked_starter_moved','started_player_added'} <= self.codes(result))
        self.proposal['assignments'][0]['player_id'] = 'a'
        self.inputs['final_context']['roster']['players'] = ['b']
        self.inputs['sleeper_players']['data']['a']['injury_status'] = 'Out'
        result = self.run_check(history={'league_id':'test','players':['a']})
        self.assertEqual(result['status'], 'REVIEW')
        self.assertIn('locked_health_flag', self.codes(result))

    def test_bye_stale_and_unrecognized_status(self):
        self.games = {}
        self.assertIn('no_game', self.codes(self.run_check()))
        self.inputs['injuries']['fetched_at'] = '2026-09-08T00:00:00Z'
        self.assertIn('stale_evidence', self.codes(self.run_check()))

    def test_news_and_missing_crosswalk_do_not_pass(self):
        self.inputs['news']['data']['items'] = [{'player_id':'b','title':'Expected to have surgery'}]
        self.assertIn('concerning_news', self.codes(self.run_check()))
        self.inputs['fp_external']['data']['players'] = []
        self.assertIn('injury_identity', self.codes(self.run_check()))

    def test_pregame_requires_official_confirmation(self):
        self.games['BUF']['kickoff'] = '2026-09-09T13:00:00Z'
        self.assertIn('pregame_confirmation', self.codes(self.run_check()))

    def test_malformed_schema(self):
        self.proposal['assignments'][0]['slot_index'] = True
        with self.assertRaises(ValueError):
            check_document(self.proposal)

    def test_provider_failure_replaces_previous_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'config.json').write_text(json.dumps({'league_id':'test','username':'me'}))
            file = root/'proposal.json'
            file.write_text(json.dumps(self.proposal))
            folder = root/'data/weekly/2026/1'
            folder.mkdir(parents=True)
            (folder/'latest_validation.json').write_text('{"status":"PASS"}')
            with patch('lineup_validate.ROOT',root), patch('lineup_validate.collect',side_effect=APIError('unavailable')), \
                 patch('sys.argv',['lineup_validate.py','--lineup',str(file)]), patch('builtins.print'):
                with self.assertRaises(SystemExit) as error:
                    lineup_validate.main()
            self.assertEqual(error.exception.code, 3)
            result = json.loads((folder/'latest_validation.json').read_text())
            self.assertEqual(result['status'], 'UNAVAILABLE')
            self.assertFalse(result['checks_passed'])
