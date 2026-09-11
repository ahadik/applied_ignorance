"""M2 acceptance fixtures are synthetic and use temporary storage only."""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from fantasy_agent.automation.automation_deadlines import normalize, collect, incorporate_rules, incorporate_saved
from fantasy_agent.automation.automation_plan import build, plan_files, next_daily, validate_policy, DEFAULT_PLAN_POLICY
from fantasy_agent.automation.automation_store import AutomationStore, InvalidContract, UnknownSchema, canonical, digest, instant, utc
from fantasy_agent.providers.sleeper import SleeperError

AT = '2026-09-13T12:00:00+00:00'


def fixture(at=AT):
    wrap = lambda data: {'data': data, 'fetched_at': at, 'network_attempts': 1, 'cache_hit': False,
                         'source_updated_at': None}
    league = {'league_id': 'test-league', 'season': '2026', 'sport': 'nfl', 'total_rosters': 1,
              'settings': {'max_subs': 0, 'waiver_type': 2}}
    roster = {'roster_id': 1, 'owner_id': 'owner', 'players': ['starter', 'backup'], 'starters': ['starter']}
    records = [{'game_id': f'g{w}_{i}', 'season': '2026', 'game_type': 'REG', 'week': str(w),
                'home_team': f'T{i}', 'away_team': f'T{i+16}',
                'gameday': (datetime(2026, 9, 13) + timedelta(days=(w-1)*7)).date().isoformat(),
                'gametime': '16:25' if i == 0 else '13:00', 'home_score': '', 'away_score': ''}
               for w in range(1, 18) for i in range(16)]
    raw = {'league': wrap(league), 'state': wrap({'season': '2026', 'season_type': 'regular', 'week': 1}),
           'user': wrap({'user_id': 'owner'}), 'rosters': wrap([roster]),
           'players': wrap({'starter': {'team': 'T0'}, 'backup': {'team': 'T1'}}),
           'schedule': {'data': records, 'provenance': {'metadata_checked_at': at, 'fetched_at': at,
                        'asset_updated_at': None, 'network_attempts': 1, 'cache_hit': True}},
           'final_league': wrap(league), 'final_rosters': wrap([roster])}
    timing = {'schema_version': 1, 'league_id': 'test-league', 'season': 2026, 'week': 1,
              'settings_hash': digest(league['settings']), 'complete': True, 'observed_at': at,
              'coverage_start': '2026-09-12T00:00:00Z', 'coverage_end': '2026-09-20T00:00:00Z',
              'evidence_refs': ['timing-proof.json'], 'events': []}
    return raw, timing


def observations(raw=None, timing=None, at=AT):
    if raw is None:
        raw, timing = fixture(at)
    return normalize(raw, season=2026, week=1, league_id='test-league', username='test-user',
                     source_refs=['inputs.json'], observed_at=at, timing=timing)


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.policy = deepcopy(DEFAULT_PLAN_POLICY)
        self.refs = [{'path': 'inputs.json', 'sha256': 'a' * 64}]

    def plan(self, obs=None, at=AT, previous=None):
        return build(obs or observations(), self.policy, at, references=self.refs, previous=previous)

    def test_hand_calculated_starter_and_earlier_backup_times(self):
        plan = self.plan()
        self.assertEqual(plan['issues'], [])
        times = {(o['event_id'], o['offset_minutes']): o['spec']['run_at'] for o in plan['desired_checks']}
        self.assertEqual(times[('g1_1', 90)], '2026-09-13T15:30:00+00:00')
        self.assertEqual(times[('g1_1', 30)], '2026-09-13T16:30:00+00:00')
        self.assertEqual(times[('g1_0', 90)], '2026-09-13T18:55:00+00:00')
        self.assertEqual(times[('g1_0', 30)], '2026-09-13T19:55:00+00:00')
        self.assertEqual(plan['desired_checks'][0]['player_ids'], ['backup'])
        self.assertFalse(plan['coverage']['scheduler_verified'])

    def test_byte_stability_and_m1_revision_agreement(self):
        self.assertEqual(canonical(self.plan()), canonical(self.plan()))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'inputs.json').write_text('{}')
            store = AutomationStore(root)
            refs = [store.reference('inputs.json')]
            plan = build(observations(), self.policy, AT, references=refs)
            store.initialize()
            for check in plan['desired_checks']:
                self.assertEqual(store.register(check['spec'])['revision'], check['revision'])

    def test_postponement_changes_revision_not_identity(self):
        obs = observations()
        old = self.plan(obs)
        next(e for e in obs['events'] if e['event_id'] == 'g1_0')['deadline_at'] = '2026-09-13T21:25:00Z'
        new = self.plan(obs, previous=old)
        old_ids = {x['check_id']: x for x in old['obligations']}
        new_ids = {x['check_id']: x for x in new['obligations']}
        self.assertEqual(set(old_ids), set(new_ids))
        moved = [k for k in old_ids if old_ids[k]['revision'] != new_ids[k]['revision']]
        self.assertEqual(len(moved), 2)

    def test_passed_prior_kickoff_cannot_unlock_after_postponement(self):
        old = self.plan()
        at = '2026-09-13T18:00:00Z'
        obs = observations(at=at)
        for e in obs['events']:
            if e['event_id'] == 'g1_1':
                e['deadline_at'] = '2026-09-14T17:00:00Z'
        new = self.plan(obs, at, old)
        self.assertTrue(all(x['disposition'] == 'locked' for x in new['obligations'] if x['event_id'] == 'g1_1'))
        self.assertFalse(any(x['event_id'] == 'g1_1' for x in new['desired_checks']))

    def test_late_but_useful_and_expired_not_rescheduled(self):
        at = '2026-09-13T15:35:00Z'
        plan = self.plan(observations(at=at), at)
        late = next(x for x in plan['desired_checks'] if x['event_id'] == 'g1_1' and x['offset_minutes'] == 90)
        self.assertEqual(late['disposition'], 'due')
        self.assertEqual(late['spec']['run_at'], utc(instant(at)))
        at = '2026-09-13T15:41:00Z'
        plan = self.plan(observations(at=at), at)
        missed = next(x for x in plan['obligations'] if x['check_id'] == late['check_id'])
        self.assertEqual(missed['disposition'], 'missed')
        self.assertEqual(missed['spec']['run_at'], '2026-09-13T15:30:00+00:00')

    def test_missing_data_preserves_obligations_and_bounded_retry(self):
        old = self.plan()
        obs = observations()
        obs['complete'] = False
        obs['events'] = []
        new = self.plan(obs, previous=old)
        self.assertEqual(len(new['preserved_obligations']), 4)
        self.assertEqual(new['desired_checks'], [])
        self.assertEqual(new['retry_obligation']['max_attempts'], 1)
        self.assertFalse(new['deletion_authorized'])
        self.assertTrue(new['coverage']['unknown_intervals'])

    def test_missing_ownership_preserves_previous_scope_without_execution(self):
        old = self.plan()
        obs = observations()
        obs.update(roster_id=None, owned_player_ids=[], events=[], complete=False)
        new = self.plan(obs, previous=old)
        self.assertEqual(new['scope'], old['scope'])
        self.assertEqual(len(new['preserved_obligations']), 4)
        self.assertEqual(new['desired_checks'], [])

    def test_observed_score_lock_survives_missing_score_in_next_observation(self):
        obs = observations()
        next(e for e in obs['events'] if e['event_id'] == 'g1_0')['locked'] = True
        old = self.plan(obs)
        new = self.plan(previous=old)
        self.assertTrue(all(x['disposition'] == 'locked' for x in new['obligations'] if x['event_id'] == 'g1_0'))

    def test_future_publication_and_invalid_source_records(self):
        obs = observations()
        obs['sources']['schedule']['asset_updated_at'] = '2026-09-14T00:00:00Z'
        self.assertIn('invalid_publication_time:schedule', self.plan(obs)['issues'])
        obs['sources']['schedule'] = []
        with self.assertRaises(InvalidContract):
            self.plan(obs)

    def test_capacity_reserves_anchor_and_retry_then_earliest_deadlines(self):
        self.policy.update(task_cap=4, reserved_slots=2)
        plan = self.plan()
        self.assertEqual(plan['capacity']['uncovered'], 2)
        self.assertEqual(len(plan['desired_checks']), 2)
        self.assertEqual({x['event_id'] for x in plan['desired_checks']}, {'g1_1'})
        self.assertEqual(len(plan['coverage']['gaps']), 2)

    def test_midnight_and_next_week_are_not_filtered_by_current_week(self):
        obs = observations()
        obs['events'] = [{'event_id': 'overnight', 'kind': 'game', 'week': 2, 'player_ids': ['backup'],
                          'deadline_at': '2026-09-14T00:20:00+00:00', 'locked': False, 'source': 'schedule', 'published_at': None}]
        plan = self.plan(obs)
        self.assertEqual(plan['desired_checks'][0]['spec']['week'], 2)
        self.assertEqual(plan['desired_checks'][0]['spec']['run_at'], '2026-09-13T22:50:00+00:00')

    def test_daily_dst_gap_and_fold_and_recovery_overlap(self):
        self.policy['daily_time'] = '02:30'
        self.assertEqual(utc(next_daily(instant('2026-03-08T05:00:00Z'), self.policy)), '2026-03-08T07:00:00+00:00')
        self.policy['daily_time'] = '01:30'
        self.assertEqual(utc(next_daily(instant('2026-11-01T04:00:00Z'), self.policy)), '2026-11-01T05:30:00+00:00')
        self.assertEqual(utc(next_daily(instant('2026-11-01T05:45:00Z'), self.policy)), '2026-11-02T06:30:00+00:00')
        self.policy['horizon_hours'] = 1
        plan = self.plan()
        self.assertGreaterEqual(instant(plan['horizon']['end']), instant(plan['next_daily_at']) + 86400)

    def test_waivers_require_matching_rules_and_explicit_times(self):
        raw, timing = fixture()
        timing['events'] = [{'event_id': 'processing-1', 'kind': 'waiver', 'week': 1,
                             'deadline_at': '2026-09-14T07:00:00Z', 'player_ids': []}]
        plan = self.plan(observations(raw, timing))
        check = next(x for x in plan['desired_checks'] if x['kind'] == 'waiver')
        self.assertEqual(check['spec']['run_at'], '2026-09-14T06:00:00+00:00')
        timing['settings_hash'] = 'wrong'
        blocked = self.plan(observations(raw, timing))
        self.assertEqual(blocked['desired_checks'], [])
        self.assertIn('waiver_and_review_timing_invalid', blocked['issues'])

    def test_stale_future_and_short_coverage_block(self):
        obs = observations()
        obs['sources']['players']['fetched_at'] = '2026-09-13T11:54:59Z'
        obs['sources']['schedule']['metadata_checked_at'] = '2026-09-13T12:00:01Z'
        obs['timing_coverage']['coverage_end'] = '2026-09-13T13:00:00Z'
        plan = self.plan(obs)
        self.assertEqual(plan['desired_checks'], [])
        self.assertIn('stale_or_missing:players', plan['issues'])
        self.assertIn('stale_or_missing:schedule', plan['issues'])
        self.assertIn('waiver_and_review_coverage_short', plan['issues'])

    def test_unknown_schema_duplicate_events_and_bad_policy(self):
        obs = observations()
        obs['schema_version'] = 99
        with self.assertRaises(UnknownSchema):
            self.plan(obs)
        obs = observations()
        obs['events'].append(deepcopy(obs['events'][0]))
        with self.assertRaises(InvalidContract):
            self.plan(obs)
        for values in ({'task_cap': 1}, {'offsets_minutes': {}}, {'allowed_operations': ['apply_lineup']}):
            with self.assertRaises(InvalidContract):
                validate_policy({**self.policy, **values})

    def test_input_text_never_becomes_a_command(self):
        obs = observations()
        obs['events'][0]['event_id'] = 'bad; echo PRIVATE'
        plan = self.plan(obs)
        self.assertTrue(all('PRIVATE' not in x['prompt'] for x in plan['desired_checks']))

    def test_immutable_file_plan_repeats_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            obs = observations()
            obs['source_refs'] = ['inputs.json']
            (root / 'inputs.json').write_text('{}')
            obs['source_checksums'] = [AutomationStore(root).reference('inputs.json')]
            for name, value in [('obs.json', obs), ('policy.json', self.policy), ('inputs.json', {})]:
                (root / name).write_text(json.dumps(value))
            args = (root / 'obs.json', root / 'policy.json', AT)
            result = plan_files(*args, root=root)
            path = Path(result['saved'])
            before = path.read_bytes()
            self.assertEqual(plan_files(*args, root=root)['saved'], str(path))
            self.assertEqual(path.read_bytes(), before)
            (root / 'inputs.json').write_text('{"changed":true}')
            with self.assertRaises(InvalidContract):
                plan_files(*args, root=root)
            (root / 'inputs.json').write_text('{}')
            path.write_text('{}')
            with self.assertRaises(InvalidContract):
                plan_files(*args, root=root)


class DeadlineTests(unittest.TestCase):
    def test_confirmed_rules_preserve_dates_and_do_not_claim_complete_coverage(self):
        raw, _ = fixture()
        obs = observations(raw, None)
        rules = {'schema_version': 1, 'league_id': 'test-league', 'season': 2026,
                 'confirmed_on': '2026-09-09', 'evidence_refs': ['proof.md'],
                 'matched_settings': {'waiver_type': 2},
                 'confirmed_labels': {'clear_waivers': 'Wednesday (3 AM EDT)'}}
        updated = incorporate_rules(obs, rules, raw['league']['data']['settings'])
        self.assertEqual(updated['observed_at'], obs['observed_at'])
        self.assertEqual(updated['known_waiver_rules']['confirmed_on'], '2026-09-09')
        self.assertFalse(updated['complete'])
        self.assertIsNone(updated['timing_coverage'])
        plan = build(updated, DEFAULT_PLAN_POLICY, AT, references=[{'path': 'proof.md', 'sha256': 'a'*64}])
        self.assertEqual(plan['known_waiver_rules'], rules)
        self.assertIn('waiver_exceptions_and_review_coverage_missing', plan['issues'])
        with self.assertRaises(InvalidContract):
            incorporate_rules(obs, rules, {'waiver_type': 0})

    def test_offline_rule_incorporation_is_immutable_and_checks_source_hashes(self):
        raw, _ = fixture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch('fantasy_agent.automation.automation_deadlines.get_sleeper', side_effect=[raw[k] for k in ('league', 'state', 'user', 'rosters', 'players', 'final_league', 'final_rosters')]), patch('fantasy_agent.automation.automation_deadlines.get_nflverse', return_value=raw['schedule']):
                collected = collect({'league_id': 'test-league', 'username': 'test-user', 'user_id': 'owner'}, 2026, 1,
                                    root=root, clock=lambda: instant(AT))
            path = Path(collected['saved']).relative_to(root.resolve()).as_posix()
            (root / 'proof.md').write_text('Saved confirmation')
            (root / 'rules.json').write_text(json.dumps({'schema_version': 1, 'league_id': 'test-league',
                'season': 2026, 'confirmed_on': '2026-09-09', 'evidence_refs': ['proof.md'],
                'matched_settings': {'waiver_type': 2}}))
            with patch('fantasy_agent.automation.automation_deadlines.get_sleeper') as sleeper, patch('fantasy_agent.automation.automation_deadlines.get_nflverse') as nfl:
                first = incorporate_saved(path, 'rules.json', root=root)
                self.assertEqual(first, incorporate_saved(path, 'rules.json', root=root))
                sleeper.assert_not_called()
                nfl.assert_not_called()
            self.assertFalse(first['timestamps_refreshed'])
            original = json.loads((root / path).read_text())
            self.assertNotIn('known_waiver_rules', original)
            (root / original['source_refs'][0]).write_text('{}')
            with self.assertRaises(InvalidContract):
                incorporate_saved(path, 'rules.json', root=root)

    def test_missing_fixture_or_player_cannot_become_a_bye(self):
        raw, timing = fixture()
        raw['schedule']['data'].pop()
        self.assertIn('season_fixture_coverage_incomplete', observations(raw, timing)['issues'])
        raw, timing = fixture()
        del raw['players']['data']['backup']
        self.assertIn('owned_player_team_unknown:backup', observations(raw, timing)['issues'])

    def test_unknown_kickoff_and_ambiguous_dst_remain_unknown(self):
        for day, value in [('2026-09-13', 'TBD'), ('2026-11-01', '01:30'), ('2026-03-08', '02:30')]:
            raw, timing = fixture()
            raw['schedule']['data'][0].update(gameday=day, gametime=value)
            obs = observations(raw, timing)
            self.assertFalse(obs['complete'])
            self.assertIsNone(next(x for x in obs['events'] if x['event_id'] == 'g1_0')['deadline_at'])

    def test_scope_and_ownership_changes_block(self):
        raw, timing = fixture()
        raw['state']['data']['week'] = 2
        raw['final_rosters'] = deepcopy(raw['rosters'])
        raw['final_rosters']['data'][0]['players'] = ['starter']
        obs = observations(raw, timing)
        self.assertIn('league_or_current_week_unverified', obs['issues'])
        self.assertIn('league_or_rosters_changed_during_collection', obs['issues'])

    def test_collection_routes_shared_clients_and_keeps_attempt_evidence(self):
        raw, timing = fixture()
        responses = [raw[k] for k in ('league', 'state', 'user', 'rosters', 'players', 'final_league', 'final_rosters')]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'timing-proof.json').write_text('{}')
            (root / 'timing.json').write_text(json.dumps(timing))
            with patch('fantasy_agent.automation.automation_deadlines.get_sleeper', side_effect=responses) as sleeper, patch('fantasy_agent.automation.automation_deadlines.get_nflverse', return_value=raw['schedule']) as nfl:
                result = collect({'league_id': 'test-league', 'username': 'test-user', 'user_id': 'owner'}, 2026, 1,
                                 root=root, timing_path='timing.json', clock=lambda: instant(AT))
            self.assertTrue(result['complete'])
            self.assertEqual(sleeper.call_count, 7)
            self.assertTrue(all(call.kwargs == {'with_metadata': True, 'retries': 0} for call in sleeper.call_args_list))
            nfl.assert_called_once_with('schedules', 2026)
            self.assertEqual(sum(v['network_attempts'] for v in result['acquisition'].values()), 8)
            self.assertTrue(result['acquisition']['schedule']['cache_hit'])
            self.assertTrue(Path(result['saved']).exists())

    def test_failed_collection_saves_partial_evidence_without_error_body(self):
        with tempfile.TemporaryDirectory() as folder:
            error = SleeperError('PRIVATE provider body', category='connection', network_attempts=1)
            with patch('fantasy_agent.automation.automation_deadlines.get_sleeper', side_effect=error), patch('fantasy_agent.automation.automation_deadlines.get_nflverse') as nfl:
                result = collect({'league_id': 'test-league', 'username': 'test-user', 'user_id': 'owner'}, 2026, 1,
                                 root=folder, clock=lambda: instant(AT))
            self.assertFalse(result['complete'])
            nfl.assert_not_called()
            self.assertEqual(result['acquisition']['league']['network_attempts'], 1)
            self.assertNotIn('PRIVATE', Path(result['saved']).read_text())

    def test_wrong_week_stops_before_directory_and_schedule_reads(self):
        raw, _ = fixture()
        raw['state']['data']['week'] = 2
        with tempfile.TemporaryDirectory() as folder:
            with patch('fantasy_agent.automation.automation_deadlines.get_sleeper', side_effect=[raw['league'], raw['state']]) as sleeper, patch('fantasy_agent.automation.automation_deadlines.get_nflverse') as nfl:
                result = collect({'league_id': 'test-league', 'username': 'test-user', 'user_id': 'owner'}, 2026, 1,
                                 root=folder, clock=lambda: instant(AT))
            self.assertFalse(result['complete'])
            self.assertEqual(sleeper.call_count, 2)
            nfl.assert_not_called()
