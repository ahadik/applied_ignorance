"""Offline A/B benchmarks and paired comparison with the previous two-pick planner."""
import argparse
import copy
from datetime import datetime,timezone
import json
from pathlib import Path
import statistics

from draft_strategy import Engine,ROOT,load_policy,render,ENGINE_VERSION
from draft_strategy_evaluate import baseline_prefix,state_from_ids,draft,board_digest
from storage import save_atomic


def benchmark(board,policy,folder,seat):
    engine = Engine(board,policy)
    baseline = copy.deepcopy(policy)
    baseline['planning_mode'] = 'two_pick'
    old = Engine(board,baseline)
    rows = []
    for rnd in sorted({1,2,5,6,len(board['roster_positions'])-1,len(board['roster_positions'])}):
        ids = baseline_prefix(old,seat,rnd,'needs',31001)
        state = state_from_ids(board,ids,seat,'ab-benchmark-'+str(rnd))
        a,b = engine.recommend(state),old.recommend(state)
        label = f"round_{rnd}"
        save_atomic(folder/label/'state.json',state)
        save_atomic(folder/label/'ab.json',a)
        save_atomic(folder/label/'two_pick.json',b)
        (folder/label/'RECOMMENDATIONS.md').write_text(render(a))
        row = {'round':rnd,'phase':a['phase'],'pick':a['target_pick'],'horizon':a['horizon_picks'],
               'ab_pick':a['recommendations'][0]['name'],'two_pick':b['recommendations'][0]['name'],
               'ab_seconds':a['runtime_seconds'],'two_pick_seconds':b['runtime_seconds'],'work':a.get('work',{})}
        rows.append(row)
        print(json.dumps(row),flush=True)
    # Before our first turn: exercise the bounded uncertain-prefix branch.
    state = state_from_ids(board,[],seat,'ab-before-draft')
    result = engine.recommend(state)
    save_atomic(folder/'before_turn'/'state.json',state)
    save_atomic(folder/'before_turn'/'ab.json',result)
    (folder/'before_turn'/'RECOMMENDATIONS.md').write_text(render(result))
    report = {'engine_version':ENGINE_VERSION,'board_sha256':board_digest(board),'policy':policy,
              'seat':seat,'rows':rows,'before_turn_seconds':result['runtime_seconds']}
    save_atomic(folder/'benchmark.json',report)
    return report


def compare(board,policy,folder,seat,seeds,modes):
    baseline = copy.deepcopy(policy)
    baseline['planning_mode'] = 'two_pick'
    new,old = Engine(board,policy),Engine(board,baseline)
    results = []
    for mode in modes:
        for seed in seeds:
            a = draft(new,seat,mode,seed,'engine')
            b = draft(old,seat,mode,seed,'engine')
            c = draft(old,seat,mode,seed,'ecr')
            row = {'mode':mode,'seed':seed,'ab':a,'two_pick':b,'ecr':c,
                   'difference_vs_two_pick':a['supported_offensive_starter_total']-b['supported_offensive_starter_total'],
                   'difference_vs_ecr':a['supported_offensive_starter_total']-c['supported_offensive_starter_total']}
            results.append(row)
            save_atomic(folder/'progress.json',{'complete':False,'results':results})
            print(json.dumps({k:v for k,v in row.items() if k not in ('ab','two_pick','ecr')}),flush=True)
    report = {'complete':True,'engine_version':ENGINE_VERSION,'board_sha256':board_digest(board),
              'generated_at':datetime.now(timezone.utc).isoformat(),'policy':policy,'seat':seat,'results':results,
              'mean_difference_vs_two_pick':statistics.mean(r['difference_vs_two_pick'] for r in results),
              'mean_difference_vs_ecr':statistics.mean(r['difference_vs_ecr'] for r in results),
              'max_ab_seconds':max(d['runtime_seconds'] for r in results for d in r['ab']['decisions']),
              'max_two_pick_seconds':max(d['runtime_seconds'] for r in results for d in r['two_pick']['decisions'])}
    save_atomic(folder/'comparison.json',report)
    save_atomic(folder/'progress.json',{'complete':True,'comparisons':len(results)})
    return report


def report(board,policy,folder):
    bench = json.loads((folder/'benchmark'/'benchmark.json').read_text())
    comparison = json.loads((folder/'comparison.json').read_text())
    for item in (bench,comparison):
        if item['board_sha256']!=board_digest(board) or item['policy']!=policy or item['engine_version']!=ENGINE_VERSION:
            raise ValueError('Benchmark/comparison is for different code, board or policy')
    if not comparison['complete']:
        raise ValueError('Incomplete comparison')
    lines = ['# A/B planner checkpoint','',f"Seat {comparison['seat']}; generated {comparison['generated_at']}.",
             'Offline tests and synthetic drafts only. Source freshness and live-state checks are unchanged.','',
             '## Planning','',
             '- A enumerates bounded plausible short-gap responses and chooses the strongest worst-case pair. A discounted greedy terminal pick approximates the long gap.',
             '- B samples the long gap and solves a constrained-maximin future A–B pair in every path. Its score blends mean utility with the lower-quarter average.',
             '- Last picks truncate the horizon. Other seats without a short pair retain the two-pick planner.',
             '- Opponent rankings are pre-indexed by position; eligibility/position adjustments are applied before merging the best few options. Greedy marginal evaluation remains exhaustive.','',
             '## Same-state timing and choices','', '| Phase | Pick | Horizon | A/B choice | Previous choice | A/B seconds | Previous seconds |', '|---|---:|---|---|---|---:|---:|']
    for r in bench['rows']:
        lines.append(f"| {r['phase']} | {r['pick']} | {r['horizon']} | {r['ab_pick']} | {r['two_pick']} | {r['ab_seconds']:.3f} | {r['two_pick_seconds']:.3f} |")
    lines += ['',f"Before-turn prefix forecast: {bench['before_turn_seconds']:.3f}s. Timings are observations on this machine, not guarantees.",
              'The previous planner here also uses the new, equivalent opponent-ranking index; comparing against old 2-second timings would mix algorithm and implementation changes.','',
              '## Paired complete drafts','', '| Opponents | Seed | Difference vs two-pick | Difference vs ECR |', '|---|---:|---:|---:|']
    for r in comparison['results']:
        lines.append(f"| {r['mode']} | {r['seed']} | {r['difference_vs_two_pick']:+.1f} | {r['difference_vs_ecr']:+.1f} |")
    lines += ['',f"Mean differences: {comparison['mean_difference_vs_two_pick']:+.1f} vs two-pick; {comparison['mean_difference_vs_ecr']:+.1f} vs ECR.",
              f"All {3*len(comparison['results'])} final rosters satisfy required slots. Slowest A/B calculation: {comparison['max_ab_seconds']:.3f}s; previous planner: {comparison['max_two_pick_seconds']:.3f}s.",
              'The score is the supported offensive starter season subtotal. It uses the same inputs as the planner and is not a win rate or calibrated forecast. K/DEF, weekly lineup changes and real agents are not evaluated.','',
              '## Limits','',
              '- Search is exact only within the capped choices/responses. Plausibility uses adjusted-rank slack, not a proven optimal opponent objective.',
              '- A and B use different truncated approximations; an A forecast does not commit the later B action.',
              '- Bench references can make utility non-monotonic at FLEX transitions. No unsafe dominance pruning is used in exhaustive greedy continuations; A/B beams can still omit useful candidates.',
              '- Terminal weight, candidate widths and downside blend are explicit assumptions, not fitted parameters.',
              '- Saved player data may be expired. No live export or browser action was performed.','']
    path = folder/'AB_REVIEW.md'
    path.write_text('\n'.join(lines))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('benchmark','compare','report'))
    parser.add_argument('--board',type=Path,default=ROOT/'data/draft_board/2026/board.json')
    parser.add_argument('--policy',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'data/strategy/ab')
    parser.add_argument('--seat',type=int,default=13)
    parser.add_argument('--seeds',type=int,nargs='+',default=[31001,31002])
    parser.add_argument('--modes',nargs='+',choices=('ecr','adp','needs','rb_run','qb_run'),default=['ecr','qb_run'])
    args = parser.parse_args()
    try:
        board = json.loads(args.board.read_text())
        policy = load_policy(args.policy)
        if not 1<=args.seat<=board['teams'] or policy.get('planning_mode')!='ab':
            raise ValueError('A/B policy and valid seat required')
        if args.command=='benchmark':
            benchmark(board,policy,args.output/'benchmark',args.seat)
        elif args.command=='compare':
            result = compare(board,policy,args.output,args.seat,args.seeds,args.modes)
            print(json.dumps({k:v for k,v in result.items() if k not in ('results','policy')},indent=2))
        else:
            print(report(board,policy,args.output))
    except (OSError,ValueError,KeyError,TypeError) as error:
        parser.exit(1,str(error)+'\n')


if __name__=='__main__':
    main()
