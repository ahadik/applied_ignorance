"""Read-only draft controller. See docs/CONTROLLER.md for commands and inputs."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
from draft import snake_picks
from draft_data import read_live_draft
from storage import save_atomic


def now():
    return datetime.now(timezone.utc).isoformat()


def age(stamp):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds()


def validate(draft, picks, draft_id):
    if draft.get('draft_id') != draft_id or draft.get('type') != 'snake':
        raise ValueError('Wrong draft or unsupported draft format')
    if draft['settings'].get('reversal_round'):
        raise ValueError('Third-round reversal not supported')
    if not isinstance(picks, list):
        raise ValueError('Invalid picks response')
    numbers = sorted(p['pick_no'] for p in picks)
    if numbers != list(range(1, len(picks) + 1)):
        raise ValueError('Non-contiguous or duplicate picks; refresh before acting')
    ids = [p['player_id'] for p in picks]
    if len(set(ids)) != len(ids) or any(p['draft_id'] != draft_id for p in picks):
        raise ValueError('Duplicate player or mismatched draft record')
    if len(picks) > draft['settings']['teams'] * draft['settings']['rounds']:
        raise ValueError('Too many picks')


def roster_needs(roster, settings):
    counts = Counter(p['position'] for p in roster)
    needs = {}
    for pos in ('QB', 'RB', 'WR', 'TE', 'K', 'DEF'):
        required = settings.get('slots_' + pos.lower(), 0)
        used = min(required, counts[pos])
        needs[pos] = required - used
        counts[pos] -= used
    needs['FLEX'] = max(0, settings.get('slots_flex', 0) - sum(counts[p] for p in ('RB', 'WR', 'TE')))
    return needs


def build(draft, picks, user_id):
    validate(draft, picks, draft['draft_id'])
    picks = sorted(picks,key=lambda p:p['pick_no'])
    settings = draft['settings']
    if settings.get('slots_super_flex', 0) or settings.get('slots_idp_flex', 0):
        raise ValueError('Unsupported roster slots')
    slot = (draft.get('draft_order') or {}).get(user_id)
    if slot is None:
        raise ValueError('User seat is unassigned')
    # In mocks roster_id is null. Real league ownership uses roster_id;
    # traded picks are rejected during refresh instead of silently misassigned.
    roster_id = (draft.get('slot_to_roster_id') or {}).get(str(slot))
    mine = [p for p in picks if (p.get('roster_id') == roster_id
            if p.get('roster_id') is not None and roster_id is not None
            else p['draft_slot'] == slot)]
    roster = [{'player_id': p['player_id'], 'pick_no': p['pick_no'],
               'name': ' '.join(p['metadata'].get(k, '') for k in ('first_name', 'last_name')).strip(),
               'position': p['metadata']['position']} for p in mine]
    rosters_by_slot = {str(s):[] for s in range(1,settings['teams']+1)}
    for pick in sorted(picks,key=lambda p:p['pick_no']):
        selected_slot = str(pick['draft_slot'])
        if selected_slot not in rosters_by_slot:
            raise ValueError('Unknown pick owner slot')
        rosters_by_slot[selected_slot].append(pick['player_id'])
    upcoming = [n for n in snake_picks(slot, settings['teams'], settings['rounds']) if n > len(picks)]
    return {'observed_at': now(), 'draft_id': draft['draft_id'], 'league_id': draft.get('league_id'),
            'url': 'https://sleeper.com/draft/nfl/' + draft['draft_id'], 'status': draft['status'],
            'seat': slot, 'last_pick': len(picks), 'next_pick': upcoming[0] if upcoming else None,
            'our_turn': bool(upcoming and upcoming[0] == len(picks) + 1 and draft['status'] == 'drafting'),
            'roster': roster, 'rosters_by_slot':rosters_by_slot, 'needs': roster_needs(roster, settings),
            'remaining_slots': settings['rounds'] - len(roster),
            'drafted_ids': [p['player_id'] for p in picks],
            'drafted_identity': {p['player_id']: {'position': p['metadata']['position'],
                'name': ' '.join(p['metadata'].get(k, '') for k in ('first_name','last_name')).strip()}
                for p in picks}, 'settings': settings}


def rank(state, candidates):
    if candidates['draft_id'] != state['draft_id']:
        raise ValueError('Candidate file belongs to another draft')
    if not candidates.get('source') or not 0 <= age(candidates['observed_at']) <= 86400:
        raise ValueError('Candidate source missing or older than 24 hours')
    if candidates.get('expires_at') and age(candidates['expires_at']) >= 0:
        raise ValueError('Candidate inputs expired; refresh sources and rebuild candidates')
    if 'state_fingerprint' in candidates:
        from draft_strategy import fingerprint
        if candidates.get('based_on_pick')!=state['last_pick'] or candidates['state_fingerprint']!=fingerprint(state):
            raise ValueError('Draft changed; recompute roster-specific strategy')
    players = candidates['players']
    if len({p['player_id'] for p in players}) != len(players):
        raise ValueError('Duplicate candidate IDs')
    result = []
    for p in players:
        value = p['priority']
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('Priorities must be finite numbers')
        if p['position'] not in ('QB', 'RB', 'WR', 'TE', 'K', 'DEF'):
            raise ValueError('Unknown candidate position')
        if p['player_id'] in state['drafted_ids'] or p.get('exclude', False):
            continue
        missing = sum(state['needs'].values())
        eligible = state['needs'].get(p['position'], 0) > 0 or (
            p['position'] in ('RB', 'WR', 'TE') and state['needs']['FLEX'] > 0)
        if state['remaining_slots'] <= missing and not eligible:
            continue
        result.append(p)
    return sorted(result, key=lambda p: (p['priority'], p['player_id']))


def assess(state, ui, candidates, pending=None):
    problems = []
    if not 0 <= age(state['observed_at']) <= 20:
        problems.append('STALE_API: refresh picks')
    if not ui or ui.get('draft_id') != state['draft_id'] or not 0 <= age(ui['observed_at']) <= 20:
        problems.append('STALE_UI: observe room, queue and auto-pick')
        ui = {}
    if ui.get('auto_pick') is not False:
        problems.append('AUTO_PICK: verify off before supervised selection')
    if ui.get('last_pick') != state['last_pick']:
        problems.append('BOARD_MISMATCH: reconcile browser and API')
    if pending:
        problems.append('PENDING: reconcile previous submission before another click')
    ranked = rank(state, candidates) if candidates else []
    ids = {p['player_id'] for p in ranked}
    queue = [p for p in ui.get('queue', []) if p not in state['drafted_ids']]
    if not queue:
        problems.append('EMPTY_QUEUE: populate native queue')
    elif any(p not in ids for p in queue):
        problems.append('QUEUE_REVIEW: queued player excluded or absent from current candidates')
    if not ranked:
        problems.append('NO_CANDIDATES: load sourced priorities')
    return {'blockers': problems, 'ready': not problems and state['our_turn'],
            'queue_depth_warning': len(queue) < min(3, state['remaining_slots']),
            'queue_observed': queue, 'recommended_queue': [p['player_id'] for p in ranked[:8]],
            'candidates': ranked[:8], 'state': state}


def refresh(folder, draft_id, user):
    draft, picks = read_live_draft(draft_id)
    validate(draft, picks, draft_id)
    state = build(draft, picks, user)
    save_atomic(folder / 'state.json', state)
    save_atomic(folder / 'health.json', {'ok': True, 'observed_at': now()})
    pending = read(folder / 'pending.json')
    if pending and state['last_pick'] >= pending['pick_no']:
        actual = next(p for p in picks if p['pick_no'] == pending['pick_no'])
        save_atomic(folder / 'last_submission.json', {'expected': pending, 'actual': actual,
                    'matched': actual['player_id'] == pending['player_id'], 'observed_at': now()})
        if actual['player_id'] == pending['player_id']:
            save_atomic(folder / 'pending.json', None)
    return state


def read(path):
    return json.loads(path.read_text()) if path.exists() else None


def update_strategy(folder,state,board_path,policy_path=None,*,allow_mock=False):
    """Offline planning after a fresh provider read; no browser writes."""
    import hashlib
    from draft_strategy import ENGINE_VERSION, Engine, candidate_export, fingerprint, load_policy
    raw = board_path.read_bytes()
    board = json.loads(raw)
    policy = load_policy(policy_path)
    digest = hashlib.sha256(raw).hexdigest()
    previous = read(folder/'strategy_result.json')
    if previous and previous.get('engine_version')==ENGINE_VERSION and previous.get('state_fingerprint')==fingerprint(state) and previous.get('board_sha256')==digest and previous.get('policy')==policy:
        result = previous
    else:
        result = Engine(board,policy).recommend(state)
        result['board_sha256'] = digest
    candidates = candidate_export(board,state,result,datetime.now(timezone.utc),allow_mock=allow_mock)
    choice = read(folder/'reviewed_choice.json')
    if choice and state['our_turn'] and choice.get('pick_no') == state['next_pick']:
        apply_reviewed_choice(state,candidates,choice)
    save_atomic(folder/'strategy_result.json',result)
    save_atomic(folder/'candidates.json',candidates)


def apply_reviewed_choice(state,candidates,choice):
    """Explicit specialist timing decision; never invent a model score."""
    if choice.get('draft_id') != state['draft_id'] or not choice.get('reason'):
        raise ValueError('Reviewed choice requires matching draft and a reason')
    if not state['our_turn'] or choice.get('pick_no') != state['next_pick']:
        raise ValueError('Reviewed choice must match our current turn')
    player = next((p for p in candidates['players'] if p['player_id']==choice.get('player_id')),None)
    if (not player or player.get('exclude') or player['player_id'] in state['drafted_ids']
            or player['position'] not in ('K','DEF') or not state['needs'].get(player['position'])
            or state['remaining_slots'] > 4):
        raise ValueError('Reviewed specialist choice is unavailable or outside allowed scope')
    candidates['players'].remove(player)
    player['rationale'] = {'basis':'Explicit specialist timing review; not model-ranked first',
                           'reason':choice['reason']}
    candidates['players'].insert(0,player)
    for i,p in enumerate(candidates['players'],1):
        p['priority']=i
    candidates['reviewed_choice']=choice


def report(folder):
    state = read(folder / 'state.json')
    if not state:
        raise ValueError('No state; run sync')
    if state['next_pick'] is None:
        pending = read(folder/'pending.json')
        blockers = ['PENDING: reconcile previous submission'] if pending else []
        if not (read(folder/'health.json') or {}).get('ok'):
            blockers.append('FETCH_FAILED: refresh required')
        result = {'ready':False,'finished_selecting':True,'blockers':blockers,'state':state,
                  'recommended_queue':[],'candidates':[]}
        save_atomic(folder/'checkpoint.json',result)
        return result
    result = assess(state, read(folder / 'ui.json'), read(folder / 'candidates.json'), read(folder / 'pending.json'))
    if not (read(folder / 'health.json') or {}).get('ok'):
        result['blockers'].append('FETCH_FAILED: refresh required')
        result['ready'] = False
    save_atomic(folder / 'checkpoint.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['sync', 'watch', 'status', 'observe', 'prepare', 'resolve'])
    parser.add_argument('--draft', required=True)
    parser.add_argument('--user', default='1403069775155884032')
    parser.add_argument('--file', type=Path)
    parser.add_argument('--player')
    parser.add_argument('--strategy-board',type=Path,help='Recompute offline strategy from this board after live sync')
    parser.add_argument('--strategy-policy',type=Path)
    parser.add_argument('--allow-mock',action='store_true',help='Permit league-board valuations in a verified league-less mock')
    args = parser.parse_args()
    if not args.draft.isdigit():
        parser.error('Draft ID must be numeric')
    folder = Path(__file__).resolve().parent / 'data' / 'drafts' / args.draft
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if args.command in ('sync', 'watch'):
            while True:
                try:
                    state = refresh(folder, args.draft, args.user)
                    if args.strategy_board and state['next_pick'] is not None:
                        update_strategy(folder,state,args.strategy_board,args.strategy_policy,allow_mock=args.allow_mock)
                    report(folder)
                    print(f"Pick {state['last_pick']}; next {state['next_pick']}; ours={state['our_turn']}", flush=True)
                except Exception as error:
                    save_atomic(folder / 'health.json', {'ok': False, 'observed_at': now(), 'error': str(error)})
                    print('Refresh failed: ' + str(error), flush=True)
                    if args.command == 'sync':
                        raise
                if args.command == 'sync' or (read(folder / 'state.json') or {}).get('status') == 'complete':
                    break
                time.sleep(5)
        elif args.command == 'observe':
            ui = read(args.file)
            if ui['draft_id'] != args.draft or type(ui['auto_pick']) is not bool:
                raise ValueError('Wrong room or unknown auto-pick state')
            if not isinstance(ui['queue'], list) or len(set(ui['queue'])) != len(ui['queue']):
                raise ValueError('Invalid queue')
            if not 0 <= age(ui['observed_at']) <= 20:
                raise ValueError('Observation already stale')
            save_atomic(folder / 'ui.json', ui)
        elif args.command == 'prepare':
            result = report(folder)
            if not result['ready'] or args.player not in result['recommended_queue'] or args.player not in result['queue_observed']:
                raise ValueError('Selection blocked: ' + '; '.join(result['blockers']) + ' (must be queued and recommended)')
            save_atomic(folder / 'pending.json', {'player_id': args.player, 'pick_no': result['state']['next_pick'], 'prepared_at': now()})
            print('Prepared for ONE immediate verified UI click. This command does not draft.')
        elif args.command == 'resolve':
            state = read(folder / 'state.json')
            pending = read(folder / 'pending.json')
            if pending and (age(state['observed_at']) > 20 or state['last_pick'] < pending['pick_no']):
                raise ValueError('Pending pick not reconciled; refresh first')
            save_atomic(folder / 'pending.json', None)
        else:
            result = report(folder)
            print(json.dumps({k: v for k, v in result.items() if k != 'state'}, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
