import copy
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from weekly_model import optimize, fresh, timestamp, schedule_games, build
from weekly_data import load
from nflverse import NFLVerse, NFLVerseError


def player(pos, points, kickoff='2026-09-13T17:00:00+00:00', **changes):
    return dict(positions=[pos], points=points, game={'kickoff': kickoff},
                owned=True, locked=False, unavailable=False) | changes


class WeeklyOptimizerTests(unittest.TestCase):
    def test_exact_assignment_and_late_flex(self):
        p = {'a': player('RB', 20), 'b': player('RB', 19, '2026-09-14T00:00:00+00:00'),
             'c': player('WR', 18), 'd': player('WR', 17)}
        best = optimize(p, ['RB','WR','FLEX'], ['a','c','d'])
        self.assertEqual(best['starters'], ['a','c','b'])
        self.assertEqual(best['adjustable_projected_points'], 57)

    def test_started_starter_fixed_and_started_bench_excluded(self):
        p = {'a': player('RB', 2, locked=True), 'b': player('RB', 100, locked=True),
             'c': player('RB', 10), 'd': player('WR', 8)}
        best = optimize(p, ['RB','FLEX'], ['a','d'])
        self.assertEqual(best['starters'], ['a','c'])
        self.assertEqual(best['adjustable_projected_points'], 10)

    def test_off_roster_locked_starter_preserved(self):
        p = {'a': player('RB', None, locked=True, owned=False), 'b': player('RB', 20)}
        self.assertEqual(optimize(p, ['RB'], ['a'])['starters'], ['a'])

    def test_unavailable_and_contingency(self):
        p = {'a': player('RB', 100, unavailable=True), 'b': player('RB', 20), 'c': player('RB', 10)}
        self.assertEqual(optimize(p, ['RB'], ['a'])['starters'], ['b'])
        self.assertEqual(optimize(p, ['RB'], ['a'], excluded=['b'])['starters'], ['c'])

    def test_multi_eligibility_matches_bruteforce(self):
        p = {'a': player('RB', 5, positions=['RB','WR']), 'b': player('RB', 4),
             'c': player('WR', 3), 'd': player('TE', 7)}
        best = optimize(p, ['RB','WR','FLEX'], [None]*3)
        totals = [sum(p[x]['points'] for x in a) for a in itertools.permutations(p, 3)
                  if 'RB' in p[a[0]]['positions'] and 'WR' in p[a[1]]['positions']]
        self.assertEqual(best['adjustable_projected_points'], max(totals))
        self.assertEqual(len(set(best['starters'])), 3)

    def test_all_locked_no_changes(self):
        p = {'a': player('QB', 5, locked=True)}
        r = optimize(p, ['QB'], ['a'])
        self.assertEqual(r['starters'], ['a'])
        self.assertEqual(r['adjustable_projected_points'], 0)

    def test_freshness_and_timezone(self):
        now = timestamp('2026-09-13T17:00:00Z')
        fresh('2026-09-13T13:00:00-04:00', now, 300, 'test')
        for value in ('2026-09-13T16:00:00Z','2026-09-13T18:00:00Z'):
            with self.assertRaises(ValueError):
                fresh(value, now, 300, 'test')
        with self.assertRaises(ValueError):
            timestamp('2026-09-13T17:00:00')

    def test_snapshot_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path/'data.json').write_text('{}')
            (path/'manifest.json').write_text(json.dumps({'complete': True, 'datasets': [
                {'name': 'data', 'file': 'data.json', 'sha256': 'wrong'}]}))
            with self.assertRaises(ValueError):
                load(path)


def weekly_fixture():
    at = '2026-09-09T12:00:00+00:00'
    context = {'season': 2026, 'week': 1, 'fetched_at': at,
        'evidence': {'league': {'fetched_at': at}},
        'league': {'league_id': 'test', 'settings': {}, 'roster_positions': ['QB','BN'],
                   'scoring_settings': {'pass_yd': .04, 'pass_td': 4, 'pass_int': -1, 'rush_yd': .1, 'rush_td': 6}},
        'roster': {'roster_id': 1, 'players': ['a','b'], 'starters': ['a']},
        'matchup': {'starters': ['a'], 'points': 0}}
    p = {sid: {'player_id': sid, 'full_name': sid, 'position': 'QB', 'fantasy_positions': ['QB'],
               'team': 'BUF', 'espn_id': sid} for sid in ('a','b')}
    inputs = {'final_context': context, 'context': context,
        'sleeper_players': {'fetched_at': at, 'data': p},
        'schedule': {'data': [], 'provenance': {'metadata_checked_at': at}},
        'fp_external': {'fetched_at': at, 'data': {'season': '2026', 'players': [
            {'player_id': sid, 'espn_id': sid} for sid in p]}},
        'injuries': {'fetched_at': at, 'request': {'params': {'year': 2026, 'week': 1}}, 'data': {'injuries': []}},
        'news': {'fetched_at': at, 'data': {'items': []}}}
    for pos in ('QB','RB','WR','TE','K','DST'):
        rows = [{'fpid': sid, 'position_id': 'QB', 'team_id': 'BUF', 'stats': {
            'pass_yds': yards, 'pass_tds': 2, 'pass_ints': 1, 'rush_yds': 10, 'rush_tds': 0}}
            for sid, yards in (('a', 200), ('b', 300))] if pos == 'QB' else []
        inputs['projections_'+pos] = {'fetched_at': at, 'request': {'params': {'week': 1, 'position': pos}},
            'data': {'season': '2026', 'week': '1', 'positions': pos, 'players': rows}}
    games = {'BUF': {'game_id': 'g', 'kickoff': '2026-09-13T17:00:00+00:00', 'opponent': 'NYJ', 'has_score': False}}
    return inputs, games


class WeeklyPipelineTests(unittest.TestCase):
    def run_build(self, inputs, games, **kwargs):
        with patch('weekly_model.schedule_games', return_value=(games, {'BUF','NYJ'})):
            return build(inputs, timestamp('2026-09-09T12:00:01+00:00'), **kwargs)

    def test_weekly_stat_scoring_and_reproducibility(self):
        inputs, games = weekly_fixture()
        result = self.run_build(inputs, games)
        self.assertEqual(result['recommendation']['starters'], ['b'])
        self.assertEqual(result['players']['b']['points'], 20)
        self.assertEqual(result['projected_component_gain'], 4)
        self.assertEqual(result, self.run_build(inputs, games))

    def test_wrong_scope_stale_feed_and_unknown_identity(self):
        for mutate in (lambda x: x['projections_QB']['data'].update(week='0'),
                       lambda x: x['injuries'].update(fetched_at='2026-09-08T00:00:00Z')):
            inputs, games = weekly_fixture()
            mutate(inputs)
            with self.assertRaises(ValueError):
                self.run_build(inputs, games)
        inputs, games = weekly_fixture()
        inputs['fp_external']['data']['players'][1]['espn_id'] = 'unknown'
        result = self.run_build(inputs, games)
        self.assertEqual(result['status'], 'blocked')
        self.assertTrue(result['quarantine'])

    def test_injury_exclusion_and_no_double_discount(self):
        inputs, games = weekly_fixture()
        inputs['injuries']['data']['injuries'] = [{'player_id': 'b', 'status': 'Questionable', 'probability_of_playing': .5}]
        result = self.run_build(inputs, games)
        self.assertEqual(result['players']['b']['points'], 20)
        self.assertTrue(result['players']['b']['availability_review'])
        inputs['injuries']['data']['injuries'][0]['status'] = 'Out'
        self.assertEqual(self.run_build(inputs, games)['recommendation']['starters'], ['a'])

    def test_prior_kickoff_and_score_cannot_unlock(self):
        inputs, games = weekly_fixture()
        result = self.run_build(inputs, games, previous_kickoffs={'a': '2026-09-08T00:00:00Z'})
        self.assertEqual(result['recommendation']['starters'], ['a'])
        games['BUF']['has_score'] = True
        result = self.run_build(inputs, games)
        self.assertEqual(result['locked_player_ids'], ['a','b'])

    def test_bye_excludes_players_and_reports_empty(self):
        inputs, games = weekly_fixture()
        result = self.run_build(inputs, {})
        self.assertEqual(result['recommendation']['starters'], [None])
        self.assertEqual(result['recommendation']['filled_slots'], 0)

    def test_schedule_full_coverage_timezone_and_invalid_times(self):
        records = [{'game_id': f'{w}_{i}', 'season': '2026', 'game_type': 'REG',
            'week': str(w), 'home_team': f'T{i}', 'away_team': f'T{i+16}',
            'gameday': '2026-09-13', 'gametime': '13:00'} for w in range(1,18) for i in range(16)]
        games, teams = schedule_games(records, 2026, 1)
        self.assertEqual(len(teams), 32)
        self.assertEqual(games['T0']['kickoff'], '2026-09-13T17:00:00+00:00')
        with self.assertRaises(ValueError):
            schedule_games(records[:-1], 2026, 1)
        records[0]['gametime'] = 'TBD'
        with self.assertRaises(ValueError):
            schedule_games(records, 2026, 1)


class ScheduleProviderTests(unittest.TestCase):
    def test_revision_reuse_and_integrity(self):
        body = b'game_id,season,game_type,week,gameday,gametime,away_team,home_team\nx,2026,REG,1,2026-09-13,13:00,BUF,NYJ\n'
        sha = hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()
        calls = []
        def send(url, headers):
            calls.append(url)
            if url.startswith('https://api.github.com/'):
                return 200, {}, json.dumps({'sha': sha, 'path': 'data/games.csv', 'size': len(body),
                    'download_url': 'https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv'}).encode()
            return 200, {}, body
        with tempfile.TemporaryDirectory() as folder:
            client = NFLVerse(folder, send=send, sleep=lambda _: None)
            first = client.get('schedules', 2026)
            second = client.get('schedules', 2026)
            self.assertEqual(first['provenance']['network_attempts'], 2)
            self.assertTrue(second['provenance']['cache_hit'])
            self.assertEqual(client.usage()['rest_attempts_last_hour'], 2)
            self.assertEqual(len(calls), 3)
            with self.assertRaises(NFLVerseError):
                client.get('schedules', 2025)
