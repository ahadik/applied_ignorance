"""Offline roster comparisons. Never invent future projections or submit transactions."""
import argparse
import copy
from datetime import datetime, timezone, timedelta
import json
import math
from pathlib import Path

from automation_store import InvalidContract
from storage import save_new
from weekly_data import load, fingerprint
from weekly_model import build, optimize, ELIGIBLE, schedule_games
from player_scoring import team


def season_calendar(inputs, owned):
    ctx = inputs['final_context']
    slots = [s for s in ctx['league']['roster_positions'] if s not in ('BN', 'IR', 'TAXI')]
    players = inputs['sleeper_players']['data']
    result = []
    for week in range(ctx['week'], 19):
        games, teams = schedule_games(inputs['schedule']['data'], ctx['season'], week)
        available, byes = {}, []
        for sid in owned:
            player = players[sid]
            club = team(player.get('team') or (sid if player['position'] == 'DEF' else None))
            if club not in teams:
                raise InvalidContract('Current roster has an unknown team for season planning')
            if club not in games:
                byes.append(sid)
            else:
                available[sid] = set(player.get('fantasy_positions') or [player['position']])
        matches = {}
        def assign(slot_index, visited):
            for sid in sorted(available):
                if sid in visited or not available[sid] & ELIGIBLE[slots[slot_index]]:
                    continue
                visited.add(sid)
                if sid not in matches or assign(matches[sid], visited):
                    matches[sid] = slot_index
                    return True
            return False
        for i in range(len(slots)):
            assign(i, set())
        result.append({'week': week, 'bye_players': byes,
                       'uncovered_slots': [slot for i, slot in enumerate(slots) if i not in matches.values()]})
    return {'weeks': result, 'trade_deadline_week': ctx['league']['settings'].get('trade_deadline'),
            'playoffs_start_week': ctx['league']['settings'].get('playoff_week_start'),
            'assumption': 'Current roster held constant; positional coverage only, not future projections or availability clearance.'}


def pool_from_snapshots(paths, now):
    reports = [build(load(Path(path)), now, analysis_pool=True) for path in paths]
    sources = [{'snapshot': str(p), 'input_hash': r['input_hash']} for p, r in zip(paths, reports)]
    scopes = {(r['league_id'], r['season']) for r in reports}
    if len(scopes) != 1 or len({r['week'] for r in reports}) != len(reports):
        raise InvalidContract('Use unique forecast weeks from one league and season')
    reports.sort(key=lambda r: r['week'])
    first = reports[0]
    from roster_operations import rules_key
    ctx = load(Path(paths[0]))['final_context']
    if any(r['slots'] != first['slots'] for r in reports):
        raise InvalidContract('Starting slots differ across forecast snapshots')
    return {'schema_version': 1, 'kind': 'roster_forecast_pool', 'league_id': first['league_id'],
            'rules_hash': rules_key(ctx), 'roster_id': ctx['roster']['roster_id'],
            'season': first['season'], 'created_at': now.isoformat(), 'weeks': reports,
            'sources': sources,
            'operational_export': False, 'future_weeks_extrapolated': False}


def roster_value(pool, owned, *, bench_weight=0.1):
    if pool.get('schema_version') != 1 or pool.get('kind') != 'roster_forecast_pool':
        raise InvalidContract('Unknown roster forecast schema')
    if not math.isfinite(bench_weight) or not 0 <= bench_weight <= 1 or len(owned) != len(set(owned)):
        raise InvalidContract('Invalid bench weight or duplicate ownership')
    weeks, missing, caveats = [], [], []
    for report in pool['weeks']:
        players = {}
        for sid in owned:
            p = report['players'].get(sid)
            if not p or (p['points'] is None and not p['unavailable']):
                missing.append({'week': report['week'], 'player_id': sid})
                continue
            p = copy.deepcopy(p)
            p['owned'] = True
            players[sid] = p
            if p.get('availability_review'):
                caveats.append(f"Availability review: {sid}, week {report['week']}")
            if p.get('scoring') and not p['scoring']['exact_league_total']:
                caveats.append(f"Partial scoring: {sid}, week {report['week']}")
        if len(players) != len(owned):
            continue
        current = [sid if sid in players else None for sid in report.get('current_starters', [None] * len(report['slots']))]
        removed_locks = [sid for sid in report.get('current_starters', []) if sid and sid not in players and report['players'][sid]['locked']]
        if removed_locks:
            missing.extend({'week': report['week'], 'player_id': sid, 'reason': 'locked_starter_removed'} for sid in removed_locks)
            continue
        lineup = optimize(players, report['slots'], current)
        # Replacement depth: value recoverable by the bench if one selected
        # starter is absent. This coefficient is an explicit uncalibrated policy.
        replacements = []
        for sid in lineup['starters']:
            if not sid or players[sid]['locked']:
                continue
            alternate = optimize(players, report['slots'], current, excluded=[sid])
            recovered = alternate['adjustable_projected_points'] - (lineup['adjustable_projected_points'] - players[sid]['points'])
            replacements.append(max(0, recovered))
        reserve = sum(replacements) / max(1, len(replacements))
        weeks.append({'week': report['week'], 'lineup': lineup, 'reserve_value': reserve,
                      'value': lineup['adjustable_projected_points'] + bench_weight * reserve,
                      'unfilled_slots': [report['slots'][i] for i, sid in enumerate(lineup['starters']) if not sid],
                      'bye_or_unavailable': [sid for sid, p in players.items() if p['unavailable']]})
    return {'complete': not missing and bool(weeks), 'missing_forecasts': missing, 'weeks': weeks,
            'value': sum(w['value'] for w in weeks) if not missing and weeks else None,
            'caveats': sorted(set(caveats)), 'bench_weight': bench_weight,
            'assumption': 'Uncalibrated bench replacement weight; projected components are not exact league totals.'}


def compare(pool, owned, add, drop, *, priority_cost=0.0, bench_weight=0.1):
    if (set(add) & set(owned) or not set(drop) <= set(owned) or set(add) & set(drop)
            or len(set(add)) != len(add) or len(set(drop)) != len(drop)
            or not math.isfinite(priority_cost) or priority_cost < 0):
        raise InvalidContract('Invalid add/drop package or priority cost')
    before = roster_value(pool, owned, bench_weight=bench_weight)
    after = roster_value(pool, sorted(set(owned) - set(drop) | set(add)), bench_weight=bench_weight)
    complete = before['complete'] and after['complete']
    delta = after['value'] - before['value'] if complete else None
    specialist = any(set(pool['weeks'][0]['players'].get(s, {}).get('positions', [])) & {'K', 'DEF'} for s in add)
    partial = any(c.startswith('Partial scoring:') for c in after['caveats'])
    return {'schema_version': 1, 'kind': 'roster_comparison', 'pool_hash': fingerprint(pool),
            'created_at': pool['created_at'],
            'expires_at': (datetime.fromisoformat(pool['created_at']) + timedelta(minutes=15)).isoformat(),
            'owned_before': sorted(owned), 'add': add, 'drop': drop, 'before': before, 'after': after,
            'modeled_gain': delta, 'rolling_priority_cost': priority_cost,
            'net_policy_value': delta - priority_cost if complete else None,
            'status': 'blocked' if not complete else 'review_required',
            'specialist_streaming_eligible': complete and not (specialist and partial),
            'platform_changes': False, 'trade_offer_authorized': False,
            'priority_assumption': 'Owner-selected opportunity cost, not a bid or calibrated win probability.'}


def chronological_evaluation(records):
    """Evaluate only prediction-time records with separately observed outcomes."""
    values = []
    for r in records:
        predicted = datetime.fromisoformat(r['predicted_at'].replace('Z', '+00:00'))
        kickoff = datetime.fromisoformat(r['kickoff'].replace('Z', '+00:00'))
        observed = datetime.fromisoformat(r['outcome_observed_at'].replace('Z', '+00:00'))
        if not all(t.tzinfo for t in (predicted, kickoff, observed)) or not predicted < kickoff <= observed:
            raise InvalidContract('Evaluation contains prediction-time leakage')
        if any(datetime.fromisoformat(t.replace('Z', '+00:00')) > predicted for t in r['source_observed_at']):
            raise InvalidContract('Prediction uses a later source observation')
        selected, baseline = float(r['selected_actual_points']), float(r['baseline_actual_points'])
        if not math.isfinite(selected) or not math.isfinite(baseline):
            raise InvalidContract('Evaluation outcome is not finite')
        values.append(selected - baseline)
    return {'observations': len(values), 'paired_actual_difference': sum(values),
            'mean_difference': sum(values) / len(values) if values else None,
            'proven_winning_edge': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    pool = sub.add_parser('pool')
    pool.add_argument('--snapshot', action='append', required=True)
    pool.add_argument('--output', required=True)
    comparison = sub.add_parser('compare')
    comparison.add_argument('--pool', required=True)
    comparison.add_argument('--owned', nargs='+', required=True)
    comparison.add_argument('--add', nargs='*', default=[])
    comparison.add_argument('--drop', nargs='*', default=[])
    comparison.add_argument('--priority-cost', type=float, default=0)
    comparison.add_argument('--output', required=True)
    evaluate = sub.add_parser('evaluate')
    evaluate.add_argument('--records', required=True)
    evaluate.add_argument('--output', required=True)
    a = p.parse_args()
    if a.command == 'pool':
        result = pool_from_snapshots(a.snapshot, datetime.now(timezone.utc))
    elif a.command == 'compare':
        result = compare(json.loads(Path(a.pool).read_text()), a.owned, a.add, a.drop, priority_cost=a.priority_cost)
        result['pool_path'] = a.pool
    else:
        result = chronological_evaluation(json.loads(Path(a.records).read_text()))
    save_new(Path(a.output), result)
    print(json.dumps({'saved': a.output, 'status': result.get('status', 'analysis_only'), 'platform_changes': False}))


if __name__ == '__main__':
    main()
