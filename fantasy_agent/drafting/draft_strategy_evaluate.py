"""Offline examples and paired synthetic draft evaluation; never operates Sleeper."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics

from fantasy_agent.drafting.draft_strategy import Engine, ROOT, load_policy, owner, upcoming, render
from fantasy_agent.core.storage import save_atomic


def board_digest(board):
    return hashlib.sha256(json.dumps(board,sort_keys=True).encode()).hexdigest()


def state_from_ids(board, ids, seat, label):
    players = {p['player_id']:p for p in board['players']}
    roster = board['roster_positions']
    settings = {'teams':board['teams'],'rounds':len(roster),'slots_flex':roster.count('FLEX')}
    settings |= {'slots_'+p.lower():roster.count(p) for p in ('QB','RB','WR','TE','K','DEF')}
    rosters = {str(s):[] for s in range(1,board['teams']+1)}
    for i,s in enumerate(ids,1):
        if s not in players:
            raise ValueError('Historical/synthetic pick not in current board: '+s)
        rosters[str(owner(i,board['teams']))].append(s)
    own = rosters[str(seat)]
    future = upcoming(len(ids),seat,board['teams'],len(roster))
    return {'simulation':True,'scenario':label,'observed_at':datetime.now(timezone.utc).isoformat(),
            'draft_id':'simulation-'+label,'league_id':board['league_id'],'settings':settings,
            'seat':seat,'last_pick':len(ids),'next_pick':future[0] if future else None,
            'drafted_ids':list(ids),'rosters_by_slot':rosters,
            'roster':[{'player_id':s,'position':players[s]['position'],'name':players[s]['name']} for s in own]}


def baseline_prefix(engine,seat,round_no,mode,seed):
    ids, available = [], list(engine.ordered)
    rosters = {s:[] for s in range(1,engine.teams+1)}
    target = upcoming(0,seat,engine.teams,engine.rounds)[round_no-1]
    for pick in range(1,target):
        slot = owner(pick,engine.teams)
        selected = engine.ecr_pick(available,rosters[slot]) if slot==seat else engine.opponent_pick(available,rosters[slot],mode,random.Random(seed+pick*97))
        ids.append(selected)
        available.remove(selected)
        rosters[slot].append(selected)
    return ids


def examples(board,policy,folder):
    engine = Engine(board,policy)
    specs = [('early_seat',1,1,'ecr'),('middle_seat',7,1,'needs'),('turn_seat',14,1,'adp'),
             ('mid_draft',7,5,'needs'),('quarterback_run',7,5,'qb_run'),
             ('bench',7,11,'needs'),('final_slots',7,14,'needs')]
    reports = []
    for label,seat,rnd,mode in specs:
        if seat>engine.teams or rnd>engine.rounds:
            continue
        ids = baseline_prefix(engine,seat,rnd,mode,policy['seed'])
        state = state_from_ids(board,ids,seat,label)
        result = engine.recommend(state)
        save_atomic(folder/label/'state.json',state)
        save_atomic(folder/label/'recommendations.json',result)
        (folder/label/'RECOMMENDATIONS.md').write_text(render(result))
        best = result['recommendations'][0]
        ecr = engine.ecr_pick([s for s in engine.ordered if s not in set(ids)],state['rosters_by_slot'][str(seat)])
        reports.append({'scenario':label,'seat':seat,'round':rnd,'opponent_mode':mode,'roster':[engine.players[s]['name'] for s in state['rosters_by_slot'][str(seat)]],
                        'engine_pick':best['name'],'ecr_pick':engine.players[ecr]['name'],'same_pick':best['player_id']==ecr,
                        'runtime_seconds':result['runtime_seconds'],'top_three':[p['name'] for p in result['recommendations'][:3]],
                        'needs':result['needs']})
        print(json.dumps(reports[-1]),flush=True)
    # Explicit hypothetical review scenario; never changes the active policy.
    flagged = next((s for s in engine.ordered if s in engine.values and s in engine.usable
                    and 'injury_review' in engine.players[s].get('flags',[])),None)
    if flagged:
        varied = copy.deepcopy(policy)
        varied.setdefault('overrides',{})[flagged] = {'multiplier':.8,'reason':'Hypothetical 20% season-value haircut for sensitivity review; not a forecast'}
        state = state_from_ids(board,[],1,'injury_sensitivity')
        result = Engine(board,varied).recommend(state)
        save_atomic(folder/'injury_sensitivity'/'state.json',state)
        save_atomic(folder/'injury_sensitivity'/'policy.json',varied)
        save_atomic(folder/'injury_sensitivity'/'recommendations.json',result)
        (folder/'injury_sensitivity'/'RECOMMENDATIONS.md').write_text(render(result))
        reports.append({'scenario':'injury_sensitivity','hypothetical_player':engine.players[flagged]['name'],
                        'hypothetical_multiplier':.8,'engine_pick':result['recommendations'][0]['name'],
                        'runtime_seconds':result['runtime_seconds'],'active_policy_changed':False})
    # Reconstruct completed mock sequences only for review. Today's later board
    # is not contemporaneous evidence, so this is not a historical performance test.
    for path in sorted((ROOT/'data/drafts').glob('*/state.json')):
        mock = json.loads(path.read_text())
        if mock.get('league_id') is not None or mock.get('status')!='complete':
            continue
        label = 'replay_'+mock['draft_id']
        prefix = mock['drafted_ids'][:mock['seat']-1]
        try:
            state = state_from_ids(board,prefix,mock['seat'],label)
            result = engine.recommend(state)
            save_atomic(folder/label/'state.json',state)
            save_atomic(folder/label/'recommendations.json',result)
            (folder/label/'RECOMMENDATIONS.md').write_text(render(result))
            reports.append({'scenario':label,'source':'Recorded mock first-round prefix; later data, not a backtest',
                            'engine_pick':result['recommendations'][0]['name'],'runtime_seconds':result['runtime_seconds']})
        except ValueError as error:
            reports.append({'scenario':label,'skipped':str(error)})
    save_atomic(folder/'examples.json',reports)
    save_atomic(folder/'provenance.json',{'board_sha256':board_digest(board),'policy':policy})
    return reports


def draft(engine,seat,mode,seed,strategy):
    ids,available = [],list(engine.ordered)
    rosters = {s:[] for s in range(1,engine.teams+1)}
    decisions = []
    for pick in range(1,engine.teams*engine.rounds+1):
        slot = owner(pick,engine.teams)
        if slot==seat:
            if strategy=='engine':
                state = state_from_ids(engine.board,ids,seat,f'evaluation-{mode}-{seed}')
                result = engine.recommend(state)
                selected = result['fallback_order'][0]
                decisions.append({'pick':pick,'player_id':selected,'name':engine.players[selected]['name'],'runtime_seconds':result['runtime_seconds']})
            else:
                selected = engine.ecr_pick(available,rosters[slot])
        else:
            # Same stream per overall pick in the paired policies; simulated
            # opponents still respond to different remaining pools/rosters.
            selected = engine.opponent_pick(available,rosters[slot],mode,random.Random(seed+pick*97))
        ids.append(selected)
        available.remove(selected)
        rosters[slot].append(selected)
    ours = rosters[seat]
    if any(engine.needs(ours).values()) or len(ours)!=engine.rounds:
        raise ValueError('Evaluation ended with illegal roster')
    return {'roster':ours,'names':[engine.players[s]['name'] for s in ours],
            'supported_offensive_starter_total':engine.utility(ours,include_bench=False,fill=False),
            'planning_utility':engine.utility(ours),'decisions':decisions}


def perturb(engine,seed,injury=False):
    """Uncalibrated stress draws, explicitly not season outcome forecasts."""
    changed = copy.copy(engine)
    changed.values = {}
    for sid,value in engine.values.items():
        stable = int(hashlib.sha256((str(seed)+sid).encode()).hexdigest()[:12],16)
        rng = random.Random(stable)
        factor = math_exp_normal(rng)
        if injury and 'injury_review' in engine.players[sid].get('flags',[]):
            factor *= .8
        changed.values[sid] = value*factor
    return changed


def math_exp_normal(rng):
    import math
    return math.exp(rng.gauss(-.5*.2**2,.2))


def evaluate(board,policy,folder,seats,seeds,modes):
    engine = Engine(board,policy)
    results = []
    total = len(seats)*len(seeds)*len(modes)
    for seat in seats:
        for mode in modes:
            for seed in seeds:
                a = draft(engine,seat,mode,seed,'engine')
                b = draft(engine,seat,mode,seed,'ecr')
                delta = a['supported_offensive_starter_total']-b['supported_offensive_starter_total']
                stress = []
                for draw in range(40):
                    varied = perturb(engine,seed+draw,injury=draw>=20)
                    stress.append(varied.utility(a['roster'],include_bench=False,fill=False)-varied.utility(b['roster'],include_bench=False,fill=False))
                result = {'seat':seat,'opponent_mode':mode,'seed':seed,'engine':a,'ecr':b,'starter_total_difference':delta,
                          'stress_mean_difference':statistics.mean(stress),'stress_positive_fraction':sum(d>0 for d in stress)/len(stress)}
                results.append(result)
                save_atomic(folder/'evaluation_progress.json',{'complete':False,'completed_pairs':len(results),'planned_pairs':total,'results':results})
                print(json.dumps({'pair':len(results),'of':total,'seat':seat,'mode':mode,'difference':round(delta,2)}),flush=True)
    differences = [r['starter_total_difference'] for r in results]
    summary = {'pairs':len(results),'mean_difference':statistics.mean(differences),'median_difference':statistics.median(differences),
               'minimum_difference':min(differences),'maximum_difference':max(differences),
               'positive_pairs':sum(d>0 for d in differences),
               'max_recommendation_seconds':max(d['runtime_seconds'] for r in results for d in r['engine']['decisions']),
               'stress_mean_difference':statistics.mean(r['stress_mean_difference'] for r in results)}
    report = {'complete':True,'generated_at':datetime.now(timezone.utc).isoformat(),'board_generated_at':board['generated_at'],
              'board_sha256':board_digest(board),'policy':policy,'summary':summary,'results':results,
              'limitations':['Synthetic drafts, not actual season outcomes or proof of a winning edge.',
                'Primary evaluation uses the same partial projection inputs as the planner, creating a favorable model-based yardstick.',
                'Both policies share eligibility constraints; baseline is highest legal ECR, not an intentionally broken drafter.',
                'Stress draws use arbitrary 20% lognormal dispersion, plus a 20% injury-flag discount in half the draws. No calibration or win probabilities.',
                'Offensive starters only are scored; K/DEF scoring gaps, weekly matchups, trades, waivers and real opponent agents are not evaluated.']}
    save_atomic(folder/'evaluation.json',report)
    save_atomic(folder/'evaluation_progress.json',{'complete':True,'completed_pairs':len(results),'planned_pairs':total})
    return report


def review_report(board,policy,folder):
    evaluation = json.loads((folder/'evaluation.json').read_text())
    examples = json.loads((folder/'examples'/'examples.json').read_text())
    provenance = json.loads((folder/'examples'/'provenance.json').read_text())
    if not evaluation.get('complete') or evaluation.get('board_sha256')!=board_digest(board) or evaluation['policy']!=policy:
        raise ValueError('Evaluation missing, incomplete, or based on a different board/policy')
    if provenance!={'board_sha256':board_digest(board),'policy':policy}:
        raise ValueError('Examples use a different board/policy')
    summary = evaluation['summary']
    lines = ['# Milestone 3 review checkpoint','',
             'Offline strategy implementation and evaluation. No live or browser mock was started.',
             f"Board collected/built earlier: {board['generated_at']}. Evaluation: {evaluation['generated_at']}.",
             f"Board content SHA-256: `{evaluation['board_sha256']}`.",'',
             '## What is implemented','',
             '- Roster-specific starter/FLEX value and discounted bench value.',
             '- Two-pick lookahead across consensus, ADP, roster needs and running-back runs.',
             '- Ranked alternatives, conditional availability fractions and explicit policy overrides.',
             '- Controller integration with all-team rosters, exact-state invalidation, computation reuse and source expiry.',
             '- Offline examples, two recorded mock first-round replays, paired full drafts and projection stress checks.','',
             '## Paired full-draft evaluation','',
             'Each pair uses the same opponent scenario/seed for the planner and highest legal ECR baseline. '
             f"QB-run opponents are outside the default planner scenario mix. All {2*summary['pairs']} resulting rosters filled all required slots.",
             'The metric is the sum of supported offensive season projections for the best starting lineup. '
             'It excludes kicker/defense and is not a league win probability.','',
             '| Seat | Opponents | Seed | Planner subtotal | ECR subtotal | Difference | Positive stress draws |',
             '|---:|---|---:|---:|---:|---:|---:|']
    for r in evaluation['results']:
        lines.append(f"| {r['seat']} | {r['opponent_mode']} | {r['seed']} | {r['engine']['supported_offensive_starter_total']:.1f} | {r['ecr']['supported_offensive_starter_total']:.1f} | {r['starter_total_difference']:+.1f} | {r['stress_positive_fraction']:.0%} |")
    lines += ['',f"Mean difference: {summary['mean_difference']:+.1f}; positive pairs: {summary['positive_pairs']}/{summary['pairs']}. "
              f"Slowest of {sum(len(r['engine']['decisions']) for r in evaluation['results'])} recommendations: {summary['max_recommendation_seconds']:.2f}s.",
              f"Mean difference across arbitrary projection stress draws: {summary['stress_mean_difference']:+.1f}. "
              'These fractions depend on the chosen perturbations, not measured real-world accuracy.','',
              '## Worked examples','', '| Scenario | Planner choice | ECR choice | Runtime |', '|---|---|---|---:|']
    for e in examples:
        lines.append(f"| [{e['scenario']}](examples/{e['scenario']}/RECOMMENDATIONS.md) | {e.get('engine_pick',e.get('skipped','—'))} | {e.get('ecr_pick','—')} | {e.get('runtime_seconds',0):.2f}s |")
    lines += ['','`injury_sensitivity` applies a hypothetical 20% season-value reduction to the highest-ranked injury-flagged offensive player. '
              'It writes a separate policy; the active policy is unchanged. Mock replays use later player data and only the recorded first-round prefixes; they are not historical performance tests.','',
              '## Assumptions to review','']+['- '+x for x in evaluation['limitations']]
    lines += [f"- Policy coefficients and opponent selection rules are explicit but uncalibrated. This run evaluated {summary['pairs']} paired drafts and {len({r['seed'] for r in evaluation['results']})} external seed(s).",
              '- History, current depth, news and injury flags remain evidence for strategic review. They do not automatically change season projections. No independent forecast has been fitted.',
              '- Saved data can expire during review. Operational export rechecks source deadlines and a real controller observation no older than 20 seconds.',
              '- Browser queue maintenance and selection remain supervised. The third integrated mock and pre-draft source refresh are separate operational checkpoints.','']
    path = folder/'MILESTONE_3.md'
    path.write_text('\n'.join(lines))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('examples','evaluate','report'))
    parser.add_argument('--board',type=Path,default=ROOT/'data/draft_board/2026/board.json')
    parser.add_argument('--policy',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'data/strategy/milestone3')
    parser.add_argument('--seats',nargs='+',type=int,default=[1,7,14])
    parser.add_argument('--seeds',nargs='+',type=int,default=[31001])
    parser.add_argument('--modes',nargs='+',choices=('ecr','adp','needs','rb_run','qb_run'),default=['ecr','needs'])
    args = parser.parse_args()
    try:
        board = json.loads(args.board.read_text())
        policy = load_policy(args.policy)
        if any(s<1 or s>board['teams'] for s in args.seats):
            raise ValueError('Invalid seat')
        if args.command=='examples':
            examples(board,policy,args.output/'examples')
        elif args.command=='evaluate':
            report = evaluate(board,policy,args.output,args.seats,args.seeds,args.modes)
            print(json.dumps(report['summary'],indent=2))
        else:
            print(review_report(board,policy,args.output))
    except (ValueError,KeyError,TypeError,OSError) as error:
        parser.exit(1,str(error)+'\n')


if __name__=='__main__':
    main()
