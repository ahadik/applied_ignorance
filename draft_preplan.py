"""Persist the assigned order and prepare offline scenarios for the next mock."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random

from controller import build as controller_state
from draft import snake_picks
from draft_data import read_pre_draft_context
from draft_strategy import Engine, ROOT, load_policy, owner, render
from draft_strategy_evaluate import state_from_ids
from storage import save_atomic


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def assigned_order(context):
    draft = context['draft']
    if context.get('traded_picks')!=[]:
        raise ValueError('Confirmed untraded picks required')
    if context['picks'] or draft['status']!='pre_draft':
        raise ValueError('Draft has started; use the live controller')
    if draft.get('league_id')!=context['league']['league_id']:
        raise ValueError('League/draft identity mismatch')
    teams = draft['settings']['teams']
    order = draft.get('draft_order') or {}
    users = {u['user_id']:u for u in context['league_users']}
    if len(users)!=len(context['league_users']) or set(order)-set(users):
        raise ValueError('Assigned users do not match verified league membership')
    if (any(type(s) is not int or not 1<=s<=teams for s in order.values())
            or len(set(order.values()))!=len(order)):
        raise ValueError('Draft order has invalid or duplicate seats')
    slots = draft.get('slot_to_roster_id') or {}
    if slots:
        rosters = {r['roster_id']:r for r in context['rosters']}
        if (set(slots)!={str(s) for s in range(1,teams+1)} or len(set(slots.values()))!=teams
                or set(slots.values())-set(rosters) or len(rosters)!=len(context['rosters'])):
            raise ValueError('Invalid slot-to-roster order mapping')
        rows,resolved = [],{}
        for seat in range(1,teams+1):
            rid = slots[str(seat)]
            uid = rosters[rid].get('owner_id')
            if uid is not None:
                if uid not in users or uid in resolved or uid in order and order[uid]!=seat:
                    raise ValueError('Order conflicts with roster ownership')
                resolved[uid] = seat
            rows.append({'seat':seat,'roster_id':rid,'user_id':uid,'ours':uid==context['user_id'],
                         'name':(users[uid].get('display_name') or uid) if uid else f'Unclaimed team (roster {rid})'})
        if any(resolved.get(uid)!=seat for uid,seat in order.items()):
            raise ValueError('Order conflicts with roster ownership')
    else:
        if len(order)!=teams:
            raise ValueError('Draft order is incomplete')
        resolved = order
        rows = [{'seat':seat,'user_id':uid,'name':users[uid].get('display_name') or uid,
                 'ours':uid==context['user_id']} for uid,seat in sorted(order.items(),key=lambda x:x[1])]
    if context['user_id'] not in resolved:
        raise ValueError('Our seat is missing from the draft order')
    state = controller_state(dict(draft,draft_order=resolved),[],context['user_id'])
    return state,rows


def make_plan(context,board,policy,folder):
    state,order = assigned_order(context)
    if board['league_id']!=context['league']['league_id'] or board['draft_id']!=context['draft']['draft_id']:
        raise ValueError('Valuation board belongs to a different draft')
    if (board['league_scoring']!=context['league']['scoring_settings']
            or board['roster_positions']!=context['league']['roster_positions']
            or str(board['season'])!=str(context['league']['season'])):
        raise ValueError('League scoring/roster/season changed; rebuild valuation board')
    engine = Engine(board,policy)
    engine.validate_state(state)
    picks = snake_picks(state['seat'],engine.teams,engine.rounds)
    schedule = [{'round':i,'overall_pick':pick,'other_picks_until_next':picks[i]-pick-1 if i<len(picks) else None}
                for i,pick in enumerate(picks,1)]
    current = datetime.now(timezone.utc)
    stale = [s['name'] for s in board['sources'] if not 0<=(current-datetime.fromisoformat(s['fetched_at'])).total_seconds()<=s['max_fetch_age_hours']*3600]
    branches = []
    # Branch only on picks ahead of us. Each first choice is evaluated against
    # all planner scenario families, not just the family producing the prefix.
    scenarios = [(mode,trial) for mode in policy['scenario_modes'] for trial in range(policy['samples_per_mode'])] if state['seat']>1 else [('ecr',0)]
    for index,(mode,trial) in enumerate(scenarios,1):
        seed = policy['seed']+index*1009+trial
        rng = random.Random(seed)
        ids,available = [],list(engine.ordered)
        rosters = {s:[] for s in range(1,engine.teams+1)}
        for pick in range(1,state['seat']):
            slot = owner(pick,engine.teams)
            sid = engine.opponent_pick(available,rosters[slot],mode,rng)
            ids.append(sid); available.remove(sid); rosters[slot].append(sid)
        label = f'{index:02d}_{mode}'
        synthetic = state_from_ids(board,ids,state['seat'],'assigned-seat-'+label)
        result = engine.recommend(synthetic)
        best = result['recommendations'][0]
        branch = {'scenario':label,'opponent_mode':mode,'seed':seed,'prefix_ids':ids,
                  'preceding_picks':[engine.players[s]['name'] for s in ids],
                  'first_choice':best,'alternatives':result['recommendations'][:5],
                  'runtime_seconds':result['runtime_seconds']}
        branches.append(branch)
        save_atomic(folder/'scenarios'/label/'state.json',synthetic)
        save_atomic(folder/'scenarios'/label/'recommendations.json',result)
        (folder/'scenarios'/label/'RECOMMENDATIONS.md').write_text(render(result))
        print(f"Scenario {index}/{len(scenarios)}: {best['name']}; {result['runtime_seconds']:.2f}s",flush=True)
    profile = {'review_only':True,'source_draft_id':state['draft_id'],'source_league_id':state['league_id'],
               'source_order_sha256':digest(order),'source_observed_at':context['fetched_at'],
               'seat':state['seat'],'teams':engine.teams,'rounds':engine.rounds,
               'draft_type':'snake','pick_timer':state['settings'].get('pick_timer'),
               'roster_positions':board['roster_positions'],'scoring_settings':board['league_scoring'],
               'requires_verified_new_mock_id':True}
    result = {'review_only':True,'generated_at':current.isoformat(),'order_observed_at':context['fetched_at'],
              'context_sha256':digest(context),'board_sha256':digest(board),'board_generated_at':board['generated_at'],
              'stale_board_sources':stale,'draft_id':state['draft_id'],'league_id':state['league_id'],
              'our_seat':state['seat'],'order':order,'pick_schedule':schedule,'policy':policy,'branches':branches,
              'mock_profile':profile,'draft_session':board.get('draft_session'),'limitations':['Static order must be verified again before live use.',
                'Scenario counts are uncalibrated examples, not probabilities or guaranteed availability.',
                'Member identities do not imply known opponent strategies; all use the same scenario rules.',
                'Original player-data timestamps are preserved. This does not refresh or export live candidates.']}
    save_atomic(folder/'plan.json',result)
    save_atomic(folder/'mock_profile.json',profile)
    (folder/'PRE_DRAFT_PLAN.md').write_text(render_plan(result))
    return result


def render_plan(plan):
    profile = plan['mock_profile']
    lines = ['# Assigned-seat pre-draft plan','',
             f"Our seat: **{plan['our_seat']} of {profile['teams']}**. Draft: {plan['draft_id']}.",
             f"Order observed: {plan['order_observed_at']}. Player board built: {plan['board_generated_at']}.",
             f"Stale board sources at review: {', '.join(plan['stale_board_sources']) or 'none'}.",
             'Static review only; no mock, watcher, native queue or live candidate export has been started.','',
             '## Assigned first-round order','', '| Seat | Member | Our team |','|---:|---|---|']
    lines += [f"| {r['seat']} | {r['name'].replace('|','/')} | {'Yes' if r['ours'] else ''} |" for r in plan['order']]
    lines += ['','## Our picks and waiting intervals','', '| Round | Overall pick | Other selections before our following pick |', '|---:|---:|---:|']
    lines += [f"| {r['round']} | {r['overall_pick']} | {r['other_picks_until_next'] if r['other_picks_until_next'] is not None else 'Finished'} |" for r in plan['pick_schedule']]
    gaps = sorted({r['other_picks_until_next'] for r in plan['pick_schedule'] if r['other_picks_until_next'] is not None})
    lines += ['',f"There are {plan['our_seat']-1} picks ahead of our opening selection. Our later waits are {', '.join(map(str,gaps))} other selections.",
              'Longer gaps increase the importance of comparing a scarce position now with the options likely to remain later. '
              'Shorter gaps allow planning the two choices together. Live selections still determine the actual choice.','',
              '## Opening branches','', '| Scenario | First choice | Likely next choices after taking them | Alternatives now |', '|---|---|---|---|']
    for b in plan['branches']:
        first = b['first_choice']
        lines.append(f"| [{b['scenario']}](scenarios/{b['scenario']}/RECOMMENDATIONS.md) | {first['name']} ({first['position']}) | {', '.join(p['name'] for p in first['likely_continuations'])} | {', '.join(p['name'] for p in b['alternatives'][1:])} |")
    counts = Counter(b['first_choice']['name'] for b in plan['branches'])
    lines += ['', 'First-choice counts in these illustrative branches: '+', '.join(f'{p}: {n}' for p,n in counts.most_common())+'.',
              'These are conditional examples, not a fixed queue or measured likelihoods. See each branch for the hypothetical preceding picks, flags and lookahead calculations.','',
              '## Next mock setup','',
              f"Use seat {profile['seat']}, {profile['teams']} teams, {profile['rounds']} rounds, snake order, and a {profile['pick_timer']}-second timer.",
              'Match the saved roster/scoring settings in `mock_profile.json`. Verify the new mock ID and its actual assigned seat before starting. '
              'The profile is an input for setup, not an applied Sleeper configuration. '+
              ('Use the approved frozen board and verify its session window; do not refresh non-Sleeper sources until the real draft completes.' if plan.get('draft_session') else 'Refresh player inputs before operational export.'),'',
              '## Limits','']+['- '+x for x in plan['limitations']]
    return '\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('sync','accept','inspect','build','summary'))
    parser.add_argument('--config',type=Path,default=ROOT/'config.json')
    parser.add_argument('--board',type=Path,default=ROOT/'data/draft_board/2026/board.json')
    parser.add_argument('--policy',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'data/strategy/pre_draft')
    args = parser.parse_args()
    try:
        if args.command in ('sync','accept'):
            if args.command=='sync':
                context = read_pre_draft_context(json.loads(args.config.read_text()))
                save_atomic(args.output/'last_observation.json',context)
            else:
                context = json.loads((args.output/'last_observation.json').read_text())
            state,order = assigned_order(context)
            save_atomic(args.output/'context.json',context)
            print(json.dumps({'observed_at':context['fetched_at'],'draft_id':state['draft_id'],
                              'seat':state['seat'],'order':order,'logical_provider_reads':7 if args.command=='sync' else 0},indent=2))
        elif args.command=='inspect':
            context = json.loads((args.output/'last_observation.json').read_text())
            print(json.dumps({'fetched_at':context['fetched_at'],'our_user_id':context['user_id'],
                              'draft':context['draft'],
                              'roster_owners':[{'roster_id':r.get('roster_id'),'owner_id':r.get('owner_id')} for r in context['rosters']]},indent=2))
        elif args.command=='build':
            result = make_plan(json.loads((args.output/'context.json').read_text()),json.loads(args.board.read_text()),load_policy(args.policy),args.output)
            print(render_plan(result))
        else:
            print(render_plan(json.loads((args.output/'plan.json').read_text())))
    except (OSError,ValueError,KeyError,TypeError) as error:
        parser.exit(1,str(error)+'\n')


if __name__=='__main__':
    main()
