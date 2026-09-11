"""Weekly lineup pipeline. run collects live inputs; recommend is offline.

python3 -m fantasy_agent weekly_lineup run --season 2026 --week 1
python3 -m fantasy_agent weekly_lineup recommend --season 2026 --week 1
python3 -m fantasy_agent weekly_lineup verify --season 2026 --week 1
All commands save private reports; none submits a Sleeper lineup.
"""
from fantasy_agent.core.project_config import load_config
import argparse
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import uuid

from fantasy_agent.weekly.weekly_data import ROOT, collect, load, context, state_key, stamp
from fantasy_agent.weekly.weekly_model import build, timestamp
from fantasy_agent.core.storage import save_atomic
from fantasy_agent.weekly.lineup_validation import proposal_from_report
from fantasy_agent.providers.fantasypros import APIError
from fantasy_agent.weekly.lineup_history import append_proposal


def report(result):
    names = lambda sid: result['players'][sid]['name'] if sid else 'EMPTY'
    lines = ['# Weekly lineup recommendation', '',
        f"Season {result['season']}, week {result['week']} | {result['generated_at']}",
        f"Status: {result['status']}. Applied: no.", '', result['objective'], '',
        'Points below are supported projected components, not exact league totals.',
        'Locked slots are fixed; their original full-game projections are not remaining points.', '',
        '| Slot | Current | Recommended | Projection | Game / kickoff UTC | Status |',
        '|---|---|---|---:|---|---|']
    target = result.get('recommendation', {}).get('starters', result['current_starters'])
    for i, sid in enumerate(target):
        p = result['players'].get(sid, {})
        game = p.get('game') or {}
        score = 'fixed' if p.get('locked') else str(round(p['points'], 2)) if p.get('points') is not None else 'unknown'
        lines.append(f"| {result['slots'][i]} | {names(result['current_starters'][i])} | {names(sid)} | {score} | {game.get('opponent', 'No game')} / {game.get('kickoff', '—')} | {'LOCKED' if p.get('locked') else 'injury review' if p.get('availability_review') else 'unlocked'} |")
    if 'recommendation' in result:
        lines += ['', f"Adjustable-slot projected subtotal: {result['recommendation']['adjustable_projected_points']:.2f}",
                  f"Next owned-player lock: {result.get('next_player_lock') or 'none remaining'}", '', '## Alternatives', '']
        for a in result['alternatives']:
            replacement = ', '.join(names(x) for x in a['starters'] if x and x not in target) or 'no replacement'
            lines.append(f"- Without {names(a['without'])}: {replacement}; projected component difference {a['projected_component_loss']:.2f}; filled slots {a['filled_slots']}/{len(target)}; decide before {a['decision_deadline']}.")
        lines += ['', 'Alternative timing: use the player table below; rerun before a replacement locks.']
    lines += ['', '## All owned/starting players', '', '| Player | Projection | Kickoff | Availability |', '|---|---:|---|---|']
    for p in result['players'].values():
        lines.append(f"| {p['name']} | {p['points']} | {(p['game'] or {}).get('kickoff', 'No game')} | {'locked' if p['locked'] else 'unavailable' if p['unavailable'] else 'review' if p['availability_review'] else 'no exclusion reported'} |")
    lines += ['', '## Blockers and caveats', '']+[f'- {x}' for x in result['blockers']]
    injured = [p['name'] for p in result['players'].values() if p['availability_review'] and not p['locked']]
    if injured:
        lines.append('- Availability/workload review: '+', '.join(injured))
    if any(p.get('scoring') and not p['scoring']['exact_league_total'] for p in result['players'].values()):
        lines.append('- Scoring is partial: omitted offensive events, kicker distance bands and defense categories remain in the JSON coverage report. The kicker subtotal notably excludes made-field-goal points.')
    lines += ['- '+x for x in result['warnings'] if not x.startswith(('Partial league scoring','Availability/workload'))]
    lines += ['', 'Provider publication times may be unknown. Injury/news absence is not medical clearance.',
        'JSON report retains scoring contributions, source ages, injuries, news, identity quarantine and complete alternate lineups.',
        'Re-run live before execution, verify native game locks, apply sequentially in Sleeper, then run verify.']
    return '\n'.join(lines)+'\n'


def publish(folder, run, inputs, rationale=None):
    previous = json.loads((folder/'locks.json').read_text()) if (folder/'locks.json').exists() else {}
    if previous and previous.get('league_id') != inputs['final_context']['league']['league_id']:
        raise ValueError('Lock history belongs to another league')
    result = build(inputs, datetime.now(timezone.utc), previous.get('players', []), previous.get('kickoffs', {}))
    result['snapshot'] = str(run)
    rid = uuid.uuid4().hex
    save_atomic(folder/'reports'/(rid+'.json'), result)
    (folder/'reports'/(rid+'.md')).write_text(report(result))
    save_atomic(folder/'locks.json', {'league_id': result['league_id'], 'players': result['locked_player_ids'],
        'kickoffs': {sid: p['game']['kickoff'] for sid, p in result['players'].items() if p['game']}})
    save_atomic(folder/'latest_report.json', result)
    (folder/'LINEUP.md').write_text(report(result))
    if not result['blockers']:
        save_atomic(folder/'latest_snapshot.json', {'path': str(run)})
        proposal = proposal_from_report(result, inputs['final_context']['roster']['roster_id'], rationale)
        append_proposal(folder, proposal)
    print(report(result))
    print(json.dumps({'report': str(folder/'LINEUP.md'), 'json': str(folder/'latest_report.json')}))
    print(json.dumps({'acquisition': result['acquisition']}))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run','recommend','verify','export'))
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--week', type=int, required=True)
    parser.add_argument('--rationale-file', type=Path, help='Free-text overall explanation to store with the new proposal')
    parser.add_argument('--projection-max-age', type=int, default=21600,
        help='Shorten FP projection cache age for a justified news/deadline refresh (seconds)')
    args = parser.parse_args()
    if not 1 <= args.week <= 18 or not 0 <= args.projection_max_age <= 21600:
        parser.error('Week must be 1–18; projection age 0–21600 seconds')
    config = load_config(ROOT)
    folder = ROOT/'data/weekly'/str(args.season)/str(args.week)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        rationale = args.rationale_file.read_text().strip() if args.rationale_file else None
        if rationale == '':
            raise ValueError('Rationale file must not be empty')
        with (folder/'operation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if args.command == 'export':
                saved = json.loads((folder/'latest_report.json').read_text())
                inputs = load(Path(saved['snapshot']))
                if saved['league_id'] != config['league_id'] or saved['season'] != args.season or saved['week'] != args.week:
                    raise ValueError('Saved recommendation scope mismatch')
                proposal = proposal_from_report(saved, inputs['final_context']['roster']['roster_id'], rationale)
                path = append_proposal(folder, proposal)
                print('Appended '+str(path)+'; original analysis timestamps retained. Run lineup_validate.py before relying on it.')
                return
            if args.command == 'verify':
                saved = json.loads((folder/'latest_report.json').read_text())
                if saved['blockers']:
                    raise ValueError('No complete recommendation to verify')
                ctx = context(config, args.season, args.week)
                if saved['league_id'] != ctx['league']['league_id'] or saved['season'] != args.season or saved['week'] != args.week:
                    raise ValueError('Recommendation scope differs from current league/week')
                observed = [None if x in ('0','',None) else x for x in ctx['matchup']['starters']]
                outcome = {'checked_at': stamp(), 'matches': observed == saved['recommendation']['starters'],
                    'recommendation_age_seconds': (datetime.now(timezone.utc)-timestamp(saved['generated_at'])).total_seconds(),
                    'observed_starters': observed, 'recommended_starters': saved['recommendation']['starters'],
                    'state_unchanged_since_analysis': state_key(ctx) == saved['state_key'],
                    'note': 'Read-back comparison only; not a refreshed recommendation or permission to change locked slots.'}
                save_atomic(folder/'verification'/ (uuid.uuid4().hex+'.json'), outcome)
                print(json.dumps(outcome, indent=2))
                return
            if args.command == 'run':
                run = collect(config, args.season, args.week, projection_max_age=args.projection_max_age)
            else:
                run = Path(json.loads((folder/'latest_snapshot.json').read_text())['path'])
            result = publish(folder, run, load(run), rationale)
            if result['blockers']:
                parser.exit(1, 'Recommendation blocked; see saved report.\n')
    except (APIError, OSError, ValueError, KeyError, TypeError) as error:
        save_atomic(folder/'last_failure.json', {'at': stamp(), 'error': str(error),
            'note': 'Previous reports retain their original timestamps and are not current advice.'})
        parser.exit(1, f'Weekly pipeline failed: {error}\nNo lineup submitted.\n')


if __name__ == '__main__':
    main()
