"""Integrated local review package. Central reads only; no platform mutations."""
from fantasy_agent.paths import ROOT as PROJECT_ROOT
from fantasy_agent.core.project_config import load_config
import argparse
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import time
import uuid

from fantasy_agent.automation.automation_store import InvalidContract, utc
from fantasy_agent.execution.lineup_execution import Execution
from fantasy_agent.weekly.lineup_history import append_proposal
from fantasy_agent.weekly.lineup_validation import proposal_from_report, validate
from fantasy_agent.execution.roster_operations import collect as collect_rosters, RosterOperations
from fantasy_agent.weekly.season_strategy import pool_from_snapshots, pool_from_inputs, compare, season_calendar
from fantasy_agent.core.storage import save_new, save_atomic
from fantasy_agent.weekly.weekly_data import collect, load, acquisition_summary
from fantasy_agent.weekly.weekly_model import build


def replay(root, result_path):
    """Recompute saved evidence at its original time, with no operational export."""
    root = Path(root).resolve()
    source = json.loads(Path(result_path).read_text())
    inputs = load(Path(source['snapshot']))
    as_of = datetime.fromisoformat(source['finished_at'])
    pool = pool_from_inputs([inputs], [source['snapshot']], as_of)
    roster = json.loads(Path(source['roster_observation']['saved']).read_text())['context']['roster']['players']
    folder = root / 'data/agent_cycles' / ('replay-' + uuid.uuid4().hex)
    comparisons = [compare(pool, roster, [c['add']], [c['drop']]) for c in source['comparisons']]
    result = {'schema_version': 1, 'status': 'offline_replay', 'operational_export': False,
              'as_of': source['finished_at'], 'source_result': str(result_path), 'network_attempts': 0,
              'platform_changes': False, 'comparisons': comparisons,
              'season_calendar': season_calendar(inputs, roster)}
    save_new(folder / 'result.json', result)
    return {'saved': str(folder / 'result.json'), 'status': result['status'], 'network_attempts': 0,
            'comparisons': len(comparisons), 'operational_export': False}


def review(root, season, week, *, notify=False, checkpoint=lambda: None):
    root = Path(root).resolve()
    folder = root / 'data/agent_cycles' / uuid.uuid4().hex
    folder.mkdir(parents=True)
    config = load_config(root)
    weekly = root / 'data/weekly' / str(season) / str(week)
    weekly.mkdir(parents=True, exist_ok=True)
    result = {'schema_version': 1, 'started_at': utc(time.time()), 'status': 'running', 'platform_changes': False}
    with (root / 'data/agent_cycles/review.lock').open('a') as lock, (weekly / 'operation.lock').open('a') as weekly_lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(weekly_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise InvalidContract('Another integrated review is active') from None
        try:
            checkpoint()
            result['lineup_state'] = Execution(root).status()
            result['transaction_state'] = RosterOperations(root).roster_status()
            if (any(e['state'] != 'completed' for e in result['lineup_state']['executions'])
                    or any(a['state'] in ('armed', 'outcome_unknown') for a in result['transaction_state']['actions'])):
                raise InvalidContract('Reconcile incomplete actions before creating a new review')
            snapshot = collect(config, season, week, root=root)
            inputs = load(snapshot)
            checkpoint()
            result['acquisition'] = acquisition_summary(inputs)
            result['snapshot'] = str(snapshot)
            weekly = root / 'data/weekly' / str(season) / str(week)
            history_path = weekly / 'locks.json'
            history = json.loads(history_path.read_text()) if history_path.exists() else {}
            now = datetime.now(timezone.utc)
            report = build(inputs, now, history.get('players', []), history.get('kickoffs', {}))
            save_new(folder / 'lineup.json', report)
            if report['blockers']:
                raise InvalidContract('Weekly analysis has blockers; inspect the saved report')
            proposal_path = append_proposal(weekly, proposal_from_report(report, inputs['final_context']['roster']['roster_id']))
            proposal = json.loads(proposal_path.read_text())
            validation = validate(proposal, inputs, now, history)
            save_new(folder / 'validation.json', validation)
            result.update(proposal=str(proposal_path), validation_status=validation['status'])
            if validation['status'] != 'FAIL':
                save_atomic(history_path, {'league_id': config['league_id'], 'players': validation['locked_player_ids'],
                    'kickoffs': history.get('kickoffs', {}) | {p['player_id']: p['game']['kickoff'] for p in validation['players'] if p['game']}})
            pool = pool_from_inputs([inputs], [snapshot], now)
            pool_path = folder / 'forecast_pool.json'
            save_new(pool_path, pool)
            result['forecast_pool'] = str(pool_path)
            calendar = season_calendar(inputs, inputs['final_context']['roster']['players'])
            save_new(folder / 'season_calendar.json', calendar)
            observation = collect_rosters(root, season, week)
            checkpoint()
            result['roster_observation'] = observation
            data = json.loads(Path(observation['saved']).read_text())
            if sorted(data['context']['roster']['players']) != sorted(inputs['final_context']['roster']['players']):
                raise InvalidContract('Ownership changed during the review; rerun before relying on comparisons')
            owned = data['context']['roster']['players']
            all_owned = {sid for r in data['rosters']['data'] for sid in r.get('players') or []}
            candidates = [p for sid, p in pool['weeks'][0]['players'].items() if sid not in all_owned
                          and p['points'] is not None and not p['locked'] and not p['unavailable']
                          and not p['availability_review'] and set(p['positions']) & {'QB', 'RB', 'WR', 'TE'}]
            candidates.sort(key=lambda p: (-p['points'], p['id']))
            drops = [sid for sid in owned if sid not in report['current_starters'] and not report['players'][sid]['locked']]
            comparisons = []
            for player in candidates[:5]:
                for drop in sorted(drops):
                    checkpoint()
                    comparison = compare(pool, owned, [player['id']], [drop])
                    comparison['pool_path'] = pool_path.relative_to(root).as_posix()
                    path = folder / 'comparisons' / f"{player['id']}-{drop}.json"
                    save_new(path, comparison)
                    comparisons.append({'add': player['id'], 'drop': drop, 'path': str(path),
                                        'modeled_gain': comparison['modeled_gain'], 'status': comparison['status']})
            result.update(status='owner_review_required', comparisons=comparisons,
                          candidate_scope='Top five unowned offensive players by current supported projection; not an exhaustive optimal search.',
                          priority_cost='Not estimated. Owner must assess rolling-priority opportunity cost before a claim.',
                          native_review_required=True, future_player_valuations_available=False)
        except Exception as error:
            result.update(status='blocked', error_type=type(error).__name__,
                          cause=str(error) if isinstance(error, InvalidContract) else 'Collection or analysis failed; inspect saved provider evidence.')
            from fantasy_agent.providers.sleeper import SleeperError
            if isinstance(error, SleeperError):
                result['provider_diagnostic'] = error.diagnostic()
        result['finished_at'] = utc(time.time())
        if notify:
            from fantasy_agent.providers.pushover import get_pushover
            try:
                result['notification'] = get_pushover(root).send('agent-review-' + folder.name,
                    'Fantasy Football review ' + result['status'] + '. Open the task for lineup, roster and season evidence.')
            except Exception as error:
                result['notification'] = {'state': 'unavailable', 'error_type': type(error).__name__}
        save_new(folder / 'result.json', result)
    return {'saved': str(folder / 'result.json'), **result}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--season', type=int)
    p.add_argument('--week', type=int)
    p.add_argument('--replay')
    p.add_argument('--notify', action='store_true')
    a = p.parse_args()
    from fantasy_agent.automation.automation_run import wall_budget
    with wall_budget(240):
        if a.replay:
            if a.notify or a.season or a.week:
                p.error('Replay cannot notify or change the source scope')
            result = replay(PROJECT_ROOT, a.replay)
        else:
            if not a.season or not a.week:
                p.error('Live review requires season and week')
            result = review(PROJECT_ROOT, a.season, a.week, notify=a.notify)
    print(json.dumps(result, indent=2))
    raise SystemExit(result['status'] == 'blocked')
