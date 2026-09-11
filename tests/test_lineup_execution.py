import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fantasy_agent.automation.automation_store import InvalidContract, utc
from fantasy_agent.execution.lineup_execution import Execution, observe
from fantasy_agent.weekly.lineup_review import resolve
from fantasy_agent.weekly.weekly_data import fingerprint
from fantasy_agent.weekly.weekly_model import timestamp
from tests.test_weekly import weekly_fixture


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.now = timestamp('2026-09-09T12:00:01Z').timestamp()
        self.engine = Execution(self.root, clock=lambda: self.now)
        self.inputs, self.games = weekly_fixture()
        self.inputs['final_context']['user'] = {'user_id': 'owner', 'username': 'owner'}
        self.inputs['final_context']['roster']['owner_id'] = 'owner'
        for p in self.inputs['fp_external']['data']['players']:
            p.update(position_id='QB', team_id='BUF')
        self.proposal = {'schema_version': 2, 'rationale': 'Test relevant replacement', 'league_id': 'test', 'roster_id': 1,
                         'season': 2026, 'week': 1, 'created_at': '2026-09-09T12:00:00Z',
                         'assignments': [{'slot_index': 0, 'slot': 'QB', 'player_id': 'b'}]}
        self.write('config.json', {'league_id': 'test', 'username': 'owner'})
        self.write('proposal.json', self.proposal)
        self.write('owner.json', {'basis': 'explicit_owner_approval', 'proposal_hash': fingerprint(self.proposal)})
        self.authority = {k: self.proposal[k] for k in ('league_id', 'roster_id', 'season', 'week')}
        self.authority.update(schema_version=1, mode='supervised', proposal_hash=fingerprint(self.proposal),
                              issued_at=utc(self.now), expires_at=utc(self.now + 600), owner_approval='owner.json')
        self.write('authority.json', self.authority)
        self.native = {'account': 'owner', 'account_menu_observed': True, 'url': 'https://sleeper.com/leagues/test/team',
                       'league_id': 'test', 'roster_id': 1, 'season': 2026, 'week': 1, 'observed_at': utc(self.now),
                       'full_reload': True, 'starters': ['a'], 'owned_player_ids': ['a', 'b'],
                       'locked_player_ids': [], 'lock_controls_observed': True}
        self.write('native.json', self.native)
        self.write('api.json', self.inputs['final_context'])
        self.snapshot()

    def write(self, path, value):
        if path == 'config.json' and 'league_id' in value:
            (self.root / '.env').write_text('SLEEPER_LEAGUE_ID=' + value['league_id'] + '\nSLEEPER_USER_ID=owner\n')
        path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def snapshot(self):
        datasets = []
        for name, value in self.inputs.items():
            self.write('snapshot/' + name + '.json', value)
            raw = (self.root / 'snapshot' / (name + '.json')).read_bytes()
            datasets.append({'name': name, 'file': name + '.json', 'sha256': hashlib.sha256(raw).hexdigest()})
        self.write('snapshot/manifest.json', {'complete': True, 'datasets': datasets})

    def register(self):
        return self.engine.register('proposal.json', 'authority.json')['id']

    def test_league_change_blocks_prepared_action(self):
        action = self.prepare(self.register())
        (self.root / '.env').write_text('SLEEPER_LEAGUE_ID=another\nSLEEPER_USER_ID=owner\n')
        with self.assertRaisesRegex(InvalidContract, 'configured league'):
            self.engine.dispatch(action['action_id'], action['token'])

    def test_user_change_blocks_prepared_action(self):
        action = self.prepare(self.register())
        (self.root / '.env').write_text('SLEEPER_LEAGUE_ID=test\nSLEEPER_USER_ID=other\n')
        with self.assertRaisesRegex(InvalidContract, 'configured user'):
            self.engine.dispatch(action['action_id'], action['token'])

    def test_browser_account_requires_menu_profile_and_owner_agreement(self):
        api = self.inputs['final_context']
        for native_patch, api_patch in (
            ({'account': 'another'}, {}),
            ({'account_menu_observed': False}, {}),
            ({}, {'user': {'user_id': 'different', 'username': 'owner'}}),
            ({}, {'user': {}}),
            ({}, {'roster': {**api['roster'], 'owner_id': 'different'}}),
        ):
            with self.subTest(native_patch=native_patch, api_patch=api_patch):
                with self.assertRaisesRegex(InvalidContract, 'signed-in account'):
                    self.engine.check_pair({**api, **api_patch}, {**self.native, **native_patch}, self.proposal)
        self.engine.check_pair(api, self.native, self.proposal)

    def test_cached_profile_does_not_replace_live_lineup_evidence(self):
        api = copy.deepcopy(self.inputs['final_context'])
        api['evidence']['user'] = {'fetched_at': utc(self.now - 120)}
        self.write('api.json', api)
        self.engine.paired('api.json', 'native.json', self.proposal, after=self.now - 1)
        action = self.prepare(self.register())
        self.engine.dispatch(action['action_id'], action['token'])
        self.after(['b'])
        post = json.loads((self.root / 'post-api.json').read_text())
        post['evidence']['user'] = api['evidence']['user']
        self.write('post-api.json', post)
        self.assertEqual(self.engine.reconcile(action['action_id'], 'post-api.json', 'post-native.json')['execution_state'], 'completed')
        api['evidence']['user']['fetched_at'] = utc(self.now - 301)
        self.write('api.json', api)
        with self.assertRaises(InvalidContract):
            self.engine.paired('api.json', 'native.json', self.proposal)
        api['evidence']['user']['fetched_at'] = utc(self.now)
        api['evidence']['league']['fetched_at'] = utc(self.now - 61)
        self.write('api.json', api)
        with self.assertRaises(InvalidContract):
            self.engine.paired('api.json', 'native.json', self.proposal)

    def prepare(self, execution_id):
        with patch('fantasy_agent.weekly.lineup_validation.schedule_games', return_value=(self.games, {'BUF', 'NYJ'})):
            return self.engine.prepare(execution_id, 'snapshot', 'api.json', 'native.json')

    def after(self, starters):
        self.now += 1
        api = copy.deepcopy(self.inputs['final_context'])
        api['roster']['starters'] = starters
        api['matchup']['starters'] = starters
        api['evidence']['league']['fetched_at'] = utc(self.now)
        self.write('post-api.json', api)
        self.write('post-native.json', {**self.native, 'observed_at': utc(self.now), 'starters': starters})

    def test_consumed_action_cannot_replay_and_requires_native_api_confirmation(self):
        eid = self.register()
        action = self.prepare(eid)
        self.engine.dispatch(action['action_id'], action['token'])
        restarted = Execution(self.root, clock=lambda: self.now)
        with self.assertRaises(InvalidContract):
            restarted.dispatch(action['action_id'], action['token'])
        with self.assertRaises(InvalidContract):
            self.prepare(eid)
        self.after(['b'])
        result = restarted.reconcile(action['action_id'], 'post-api.json', 'post-native.json')
        self.assertEqual(result['execution_state'], 'completed')
        with self.assertRaises(InvalidContract):
            self.engine.register('proposal.json', 'authority.json')

    def test_disconnect_after_click_does_not_allow_retry_when_before_state_returns(self):
        eid = self.register()
        action = self.prepare(eid)
        self.engine.dispatch(action['action_id'], action['token'])
        self.after(['a'])
        result = self.engine.reconcile(action['action_id'], 'post-api.json', 'post-native.json')
        self.assertEqual(result['outcome'], 'not_applied')
        with self.assertRaises(InvalidContract):
            self.prepare(eid)
        self.write('recovery.json', {'basis': 'explicit_owner_recovery', 'action_id': action['action_id'], 'reason': 'Fresh browser and API still show original lineup'})
        self.engine.recover(action['action_id'], 'recovery.json')
        self.assertEqual(self.engine.status()['executions'][0]['state'], 'planned')

    def test_changed_proposal_authority_and_stale_native_block(self):
        eid = self.register()
        self.write('native.json', {**self.native, 'observed_at': utc(self.now - 61)})
        with self.assertRaises(InvalidContract):
            self.prepare(eid)
        self.write('native.json', self.native)
        self.write('proposal.json', {**self.proposal, 'rationale': 'Changed rationale'})
        with self.assertRaises(InvalidContract):
            self.prepare(eid)

    def test_native_lock_and_disagreement_block_even_if_optimizer_wanted_change(self):
        eid = self.register()
        self.write('native.json', {**self.native, 'locked_player_ids': ['a']})
        with self.assertRaises(InvalidContract):
            self.prepare(eid)
        self.write('native.json', {**self.native, 'starters': ['b']})
        with self.assertRaises(InvalidContract):
            self.prepare(eid)

    def test_expired_token_and_changed_snapshot_cannot_dispatch(self):
        action = self.prepare(self.register())
        self.now += 31
        with self.assertRaises(InvalidContract):
            self.engine.dispatch(action['action_id'], action['token'])
        self.now -= 31
        self.write('snapshot/news.json', {})
        with self.assertRaises(ValueError):
            self.engine.dispatch(action['action_id'], action['token'])
        self.assertEqual(self.engine.status()['actions'][0]['state'], 'armed')

    def test_changed_ownership_after_click_preserves_unknown(self):
        action = self.prepare(self.register())
        self.engine.dispatch(action['action_id'], action['token'])
        self.after(['b'])
        api = json.loads((self.root / 'post-api.json').read_text())
        api['roster']['players'].append('new-player')
        self.write('post-api.json', api)
        with self.assertRaises(InvalidContract):
            self.engine.reconcile(action['action_id'], 'post-api.json', 'post-native.json')
        self.assertEqual(self.engine.status()['actions'][0]['state'], 'outcome_unknown')

    def test_blanket_or_delegated_authority_is_not_supervised_approval(self):
        self.write('authority.json', {**self.authority, 'mode': 'delegated'})
        with self.assertRaises(InvalidContract):
            self.register()
        self.write('authority.json', self.authority)
        self.write('owner.json', {'basis': 'complete_m5'})
        with self.assertRaises(InvalidContract):
            self.register()

    def test_unknown_schema_stops(self):
        self.engine.status()
        import sqlite3
        with sqlite3.connect(self.engine.folder / 'state.sqlite3') as db:
            db.execute('PRAGMA user_version=99')
        db.close()
        with self.assertRaises(InvalidContract):
            self.engine.status()

    def test_version_one_upgrade_preserves_execution(self):
        eid = self.register()
        import sqlite3
        db = sqlite3.connect(self.engine.folder / 'state.sqlite3')
        db.execute('PRAGMA user_version=1')
        db.close()
        self.assertEqual(self.engine.status()['executions'][0]['id'], eid)
        db = sqlite3.connect(self.engine.folder / 'state.sqlite3')
        self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
        db.close()

    def test_review_cannot_turn_definite_failure_into_permission(self):
        self.inputs['sleeper_players']['data']['b']['injury_status'] = 'Out'
        self.snapshot()
        with self.assertRaises(InvalidContract):
            self.prepare(self.register())

    def test_official_review_requires_exact_observed_primary_evidence(self):
        finding = {'level': 'review', 'code': 'pregame_confirmation', 'player_id': 'b', 'slot_index': 0, 'message': 'Confirm'}
        result = {'status': 'REVIEW', 'issues': [finding], 'proposal_hash': 'p', 'input_hash': 'i', 'state_key': 's',
                  'expires_at': utc(self.now + 120), 'players': [{'player_id': 'b', 'game': {'game_id': 'g'}}]}
        official = {'url': 'https://www.nfl.com/news/week-1-inactives', 'player_id': 'b', 'game_id': 'g',
                    'status': 'active', 'statement': 'Player b is active for game g', 'published_at': utc(self.now - 120),
                    'observed_at': utc(self.now - 10), 'evidence': 'official.json'}
        self.write('official.json', {**official, 'basis': 'observed_official_nfl_page'})
        review = {'schema_version': 1, 'proposal_hash': 'p', 'input_hash': 'i', 'state_key': 's',
                  'issues_hash': fingerprint([finding]), 'reviewed_at': utc(self.now), 'expires_at': utc(self.now + 120),
                  'owner_approval': 'review-owner.json', 'resolutions': [{'issue_index': 0, 'reason': 'Read official report',
                  'disposition': 'official_active_reviewed', 'official': official}]}
        self.write('review-owner.json', {'basis': 'explicit_owner_review', **{k: review[k] for k in ('proposal_hash', 'input_hash', 'issues_hash')}})
        self.assertTrue(resolve(result, review, self.native, self.now, self.engine.read)['eligible'])
        official['url'] = 'https://example.com/news/week-1-inactives'
        with self.assertRaises(InvalidContract):
            resolve(result, review, self.native, self.now, self.engine.read)

    def test_observation_retains_disagreement_without_relaxing_production_collection(self):
        ctx = copy.deepcopy(self.inputs['final_context'])
        ctx['roster']['starters'] = ['b']
        with patch('fantasy_agent.execution.lineup_execution.context', return_value=ctx) as read:
            result = observe(self.root, 2026, 1)
        self.assertFalse(result['starters_agree'])
        self.assertFalse(read.call_args.kwargs['require_agreement'])

    def test_future_game_cannot_be_counted_as_a_supervised_window_today(self):
        self.write('window.json', {'basis': 'actual_owner_supervised_window', 'execution_id': 'none', 'kickoff': '2026-09-13T17:00:00Z'})
        with self.assertRaises(InvalidContract):
            self.engine.record_window('none', '2026-09-13T17:00:00Z', 'window.json')

    def test_unknown_action_cannot_be_retired_or_reauthorized(self):
        eid = self.register()
        action = self.prepare(eid)
        self.engine.dispatch(action['action_id'], action['token'])
        self.write('recovery.json', {'basis': 'explicit_owner_recovery', 'action_id': action['action_id'], 'reason': 'Unknown effects'})
        with self.assertRaises(InvalidContract):
            self.engine.recover(action['action_id'], 'recovery.json')
        with self.assertRaises(InvalidContract):
            self.engine.reauthorize(eid, 'authority.json')

    def test_concurrent_preparation_can_arm_only_one_action(self):
        from concurrent.futures import ThreadPoolExecutor
        eid = self.register()
        def attempt(_):
            try:
                return Execution(self.root, clock=lambda: self.now).prepare(eid, 'snapshot', 'api.json', 'native.json')
            except InvalidContract:
                return None
        with patch('fantasy_agent.weekly.lineup_validation.schedule_games', return_value=(self.games, {'BUF', 'NYJ'})):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(attempt, range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)


if __name__ == '__main__':
    unittest.main()
