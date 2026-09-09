"""Offline A/B and two-pick draft planning. See docs/AB_STRATEGY.md."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import time

from draft_board import OFFENSE, POSITIONS, export_candidates
from storage import save_atomic

ROOT = Path(__file__).resolve().parent
ENGINE_VERSION = 2


def fingerprint(state):
    fields = ('draft_id','league_id','seat','last_pick','next_pick','settings','drafted_ids','roster','rosters_by_slot')
    return hashlib.sha256(json.dumps({k:state.get(k) for k in fields},sort_keys=True).encode()).hexdigest()


def owner(pick, teams):
    rnd, offset = divmod(pick-1,teams)
    return offset+1 if rnd%2==0 else teams-offset


def upcoming(last_pick, seat, teams, rounds):
    return [p for p in range(last_pick+1,teams*rounds+1) if owner(p,teams)==seat]


def load_policy(path=None):
    policy = json.loads(Path(path or ROOT/'strategy_policy.json').read_text())
    validate_policy(policy)
    return policy


def validate_policy(p):
    if p.get('planning_mode','two_pick') not in ('two_pick','ab'):
        raise ValueError('Unknown planning mode')
    if p.get('planning_mode')=='ab':
        for key,lo,hi in (('first_width',1,10),('future_width',1,6),('reply_width',1,6),
                          ('response_width',1,4),('prefix_samples',1,4),('tail_samples',1,4)):
            if type(p.get('ab',{}).get(key)) is not int or not lo<=p['ab'][key]<=hi:
                raise ValueError('Invalid A/B setting: '+key)
        for key,hi in (('rank_slack',30),('tail_weight',1),('downside_fraction',1)):
            v=p['ab'].get(key)
            if isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or not 0<v<=hi:
                raise ValueError('Invalid A/B setting: '+key)
    for key,low,high in (('samples_per_mode',1,8),('shortlist_each',1,12),('specialist_last_rounds',1,4),('backup_qb_te_round',1,30)):
        if type(p.get(key)) is not int or not low <= p[key] <= high:
            raise ValueError('Invalid policy '+key)
    for key in ('bench_weight','bench_decay','robust_weight'):
        if isinstance(p.get(key),bool) or not isinstance(p.get(key),(float,int)) or not 0 <= p[key] <= 1:
            raise ValueError('Policy coefficient outside [0,1]: '+key)
    if not isinstance(p.get('opponent_temperature'),(float,int)) or not 0 < p['opponent_temperature'] <= 30:
        raise ValueError('Invalid opponent temperature')
    if type(p.get('seed')) is not int or not p.get('scenario_modes') or any(m not in ('ecr','adp','needs','rb_run','qb_run') for m in p['scenario_modes']):
        raise ValueError('Unsupported scenario configuration')
    if set(p['caps']) != set(POSITIONS) or any(type(v) is not int or not 1<=v<=15 for v in p['caps'].values()):
        raise ValueError('Invalid roster caps')
    for override in p.get('overrides',{}).values():
        if not override.get('reason') or set(override)-{'exclude','multiplier','reason'}:
            raise ValueError('Overrides require a reason and supported fields')
        if 'exclude' in override and type(override['exclude']) is not bool:
            raise ValueError('Override exclude must be boolean')
        value = override.get('multiplier',1)
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not 0<=value<=1.5:
            raise ValueError('Invalid override multiplier')


class Engine:
    def __init__(self, board, policy):
        validate_policy(policy)
        self.board, self.policy = board, policy
        self.players = {p['player_id']:p for p in board['players']}
        if len(self.players)!=len(board['players']):
            raise ValueError('Duplicate board player ID')
        roster = board['roster_positions']
        if any(p not in (*POSITIONS,'FLEX','BN') for p in roster):
            raise ValueError('Unsupported roster format')
        self.slots = {p:roster.count(p) for p in POSITIONS}
        if any(policy['caps'][p]<self.slots[p] for p in POSITIONS):
            raise ValueError('Policy caps prevent required roster coverage')
        if set(policy.get('overrides',{}))-set(self.players):
            raise ValueError('Unknown override player ID')
        self.flex = roster.count('FLEX')
        self.rounds = len(roster)
        self.teams = board['teams']
        self.floor = {p:board['starter_baselines'][p]['supported_points'] for p in OFFENSE}
        self.values, self.usable, self.market = {}, set(), {}
        for sid,p in self.players.items():
            override = policy.get('overrides',{}).get(sid,{})
            scoring = p.get('scoring')
            value = scoring.get('supported_points') if scoring else None
            if value is not None and (isinstance(value,bool) or not math.isfinite(value)):
                raise ValueError('Invalid scoring value')
            if p['position'] in OFFENSE and value is not None and scoring.get('core_fields_complete'):
                self.values[sid] = value*override.get('multiplier',1)
            if not p.get('exclude') and not override.get('exclude') and (sid in self.values or p['position'] in ('K','DEF')):
                self.usable.add(sid)
            self.market[sid] = (p.get('ecr') or 1000, p.get('adp_rank') or p.get('ecr') or 1000)
        self.ordered = sorted(self.players, key=lambda sid:(self.market[sid][0],sid))
        self.position = {s:p['position'] for s,p in self.players.items()}
        self.market_order = {(mode,pos):sorted((s for s in self.players if self.position[s]==pos),
                                    key=lambda s:(self.market[s][mode],s)) for mode in (0,1) for pos in POSITIONS}
        self.value_order = {pos:sorted((s for s in self.usable if self.position[s]==pos),
                            key=lambda s:(-self.values.get(s,0),self.market[s][0],s)) for pos in POSITIONS}
        self.bench_floor = {}
        for pos in OFFENSE:
            values = sorted((self.values[sid] for sid in self.usable if self.players[sid]['position']==pos),reverse=True)
            # Deeper reference for reserves; an assumption, not predicted waivers.
            depth = self.teams*(2 if pos in ('QB','TE') else 5)
            self.bench_floor[pos] = values[min(depth,len(values)-1)] if values else 0

    def needs(self, roster):
        counts = Counter(self.players[s]['position'] for s in roster)
        needs = {p:max(0,self.slots[p]-counts[p]) for p in POSITIONS}
        surplus = sum(max(0,counts[p]-self.slots[p]) for p in ('RB','WR','TE'))
        needs['FLEX'] = max(0,self.flex-surplus)
        return needs

    def allowed_positions(self, roster, *, own=True):
        needs = self.needs(roster)
        remaining = self.rounds-len(roster)
        missing = sum(needs.values())
        if remaining<=0:
            return []
        if missing>remaining:
            raise ValueError('Roster cannot satisfy required slots')
        counts = Counter(self.players[s]['position'] for s in roster)
        result = []
        for p in POSITIONS:
            fits = needs[p]>0 or p in ('RB','WR','TE') and needs['FLEX']>0
            if remaining<=missing and not fits:
                continue
            if own:
                if counts[p]>=self.policy['caps'][p]:
                    continue
                if p in ('K','DEF') and remaining>self.policy['specialist_last_rounds'] and remaining>missing:
                    continue
                if p in ('QB','TE') and counts[p]>=self.slots[p] and len(roster)+1<min(self.policy['backup_qb_te_round'],self.rounds) and not fits:
                    continue
            result.append(p)
        return result

    def eligible(self, available, roster, *, own=True):
        allowed = set(self.allowed_positions(roster,own=own))
        return [s for s in available if self.position[s] in allowed and (not own or s in self.usable)]

    def utility(self, roster, *, include_bench=True, fill=True):
        grouped = {p:[] for p in OFFENSE}
        for sid in roster:
            p = self.players[sid]['position']
            if p in OFFENSE:
                if sid not in self.values:
                    raise ValueError('Owned player lacks supported projection: '+sid)
                grouped[p].append((self.values[sid],sid))
        starters, reserves, real_starters = 0.0, [], set()
        for pos, group in grouped.items():
            choices = group + ([(self.floor[pos],None)]*(self.slots[pos]+self.flex) if fill else [])
            choices.sort(key=lambda r:(-r[0],r[1] or '~'))
            selected = choices[:self.slots[pos]]
            starters += sum(v for v,_ in selected)
            real_starters.update(s for _,s in selected if s)
            if pos in ('RB','WR','TE'):
                reserves += choices[self.slots[pos]:]
        reserves.sort(key=lambda r:(-r[0],r[1] or '~'))
        flex = reserves[:self.flex]
        starters += sum(v for v,_ in flex)
        real_starters.update(s for _,s in flex if s)
        bench = 0.0
        if include_bench:
            for pos, group in grouped.items():
                remaining = sorted((v for v,s in group if s not in real_starters),reverse=True)
                for n,value in enumerate(remaining):
                    bench += self.policy['bench_weight']*self.policy['bench_decay']**n*max(0,value-self.bench_floor[pos])
        return starters+bench

    def marginal(self, sid, roster, base=None):
        if self.players[sid]['position'] not in OFFENSE:
            return 0.0
        return self.utility(roster+[sid])-(self.utility(roster) if base is None else base)

    def greedy(self, available, roster):
        # Evaluate all eligible players: position-specific bench references can
        # make utility non-monotonic when a player displaces another FLEX starter.
        eligible = self.eligible(available,roster)
        if not eligible:
            raise ValueError('No legal modeled candidate')
        base = self.utility(roster)
        return min(eligible,key=lambda s:(-self.marginal(s,roster,base),self.market[s][0],s))

    def ecr_pick(self, available, roster):
        eligible = self.eligible(available,roster)
        if not eligible:
            raise ValueError('No legal baseline candidate')
        return min(eligible,key=lambda s:(self.market[s][0],s))

    def opponent_options(self, available, roster, mode, count=5):
        available = available if isinstance(available,(set,frozenset)) else set(available)
        needs = self.needs(roster)
        def score(s):
            p = self.players[s]['position']
            ecr,adp = self.market[s]
            value = adp if mode=='adp' else ecr
            if mode in ('needs','rb_run','qb_run'):
                fits = needs[p]>0 or p in ('RB','WR','TE') and needs['FLEX']>0
                value += -8 if fits else 30
            if mode=='rb_run' and p=='RB':
                value -= 15
            if mode=='qb_run' and p=='QB':
                value -= 20
            return value
        candidates = []
        for pos in self.allowed_positions(roster,own=False):
            found = 0
            for sid in self.market_order[(int(mode=='adp'),pos)]:
                if sid in available:
                    candidates.append(sid)
                    found += 1
                    if found==count:
                        break
        return sorted(((score(s),s) for s in candidates),key=lambda v:(v[0],v[1]))[:count]

    def opponent_pick(self, available, roster, mode, rng):
        options = self.opponent_options(available,roster,mode)
        if not options:
            raise ValueError('No legal opponent candidate')
        top = [s for _,s in options]
        scores = dict((s,v) for v,s in options)
        floor = options[0][0]
        weights = [math.exp(-(scores[s]-floor)/self.policy['opponent_temperature']) for s in top]
        return rng.choices(top,weights=weights,k=1)[0]

    def simulate(self, available, rosters, start, end, mode, seed):
        available = set(available)
        rosters = {k:list(v) for k,v in rosters.items()}
        rng = random.Random(seed)
        for pick in range(start,end):
            seat = owner(pick,self.teams)
            sid = self.opponent_pick(available,rosters[seat],mode,rng)
            rosters[seat].append(sid)
            available.remove(sid)
        return sorted(available,key=lambda s:(self.market[s][0],s)),rosters

    def recommend(self, state):
        if self.policy.get('planning_mode')=='ab':
            from draft_ab import ABPlanner, phase
            self.validate_state(state)
            if phase(state,self.teams,self.rounds) in ('A','B'):
                return ABPlanner(self).recommend(state)
        result = self.recommend_two_pick(state)
        from draft_ab import phase
        result.update(planning_mode='two_pick',phase=phase(state,self.teams,self.rounds),
                      horizon_picks=upcoming(state['last_pick'],state['seat'],self.teams,self.rounds)[:2])
        return result

    def recommend_two_pick(self, state):
        started = time.monotonic()
        self.validate_state(state)
        ours = list(state['rosters_by_slot'][str(state['seat'])])
        drafted = set(state['drafted_ids'])
        available = [s for s in self.ordered if s not in drafted]
        choices = self.eligible(available,ours)
        if not choices:
            raise ValueError('No eligible candidates')
        own_picks = upcoming(state['last_pick'],state['seat'],self.teams,self.rounds)
        first,second = own_picks[0],own_picks[1] if len(own_picks)>1 else None
        base = self.utility(ours)
        immediate = {s:self.marginal(s,ours,base) for s in choices}
        count = self.policy['shortlist_each']
        shortlist = sorted(set(sorted(choices,key=lambda s:(self.market[s][0],s))[:count] +
                               sorted(choices,key=lambda s:(-immediate[s],self.market[s][0],s))[:count]),
                           key=lambda s:(self.market[s][0],s))
        records = {s:{'gains':[],'modes':defaultdict(list),'survives_first':0,'survives_pass':0,'pass_trials':0,
                      'continuations':Counter()} for s in shortlist}
        rosters = {int(k):list(v) for k,v in state['rosters_by_slot'].items()}
        for mi,mode in enumerate(self.policy['scenario_modes']):
            for trial in range(self.policy['samples_per_mode']):
                seed = self.policy['seed']+state['last_pick']*1009+mi*101+trial
                before,r_before = self.simulate(available,rosters,state['last_pick']+1,first,mode,seed)
                for sid in shortlist:
                    record = records[sid]
                    survives = sid in before
                    record['survives_first'] += survives
                    selected = sid if survives else self.greedy(before,ours)
                    roster = ours+[selected]
                    remaining = [s for s in before if s!=selected]
                    if second:
                        r = dict(r_before)
                        r[state['seat']] = roster
                        later,_ = self.simulate(remaining,r,first+1,second,mode,seed+37)
                        following = self.greedy(later,roster)
                        roster = roster+[following]
                        record['continuations'][following] += 1
                        # Availability is conditional on choosing the best legal
                        # ECR alternative now, not an unconditional probability.
                        if survives:
                            alternate_pool = [s for s in before if s!=sid]
                            alternate = self.ecr_pick(alternate_pool,ours) if self.eligible(alternate_pool,ours) else None
                            if alternate:
                                r[state['seat']] = ours+[alternate]
                                passed,_ = self.simulate([s for s in before if s!=alternate],r,first+1,second,mode,seed+37)
                                record['pass_trials'] += 1
                                record['survives_pass'] += sid in passed
                    gain = self.utility(roster)-base
                    record['gains'].append(gain)
                    record['modes'][mode].append(gain)
        ranked = []
        for sid,record in records.items():
            p = self.players[sid]
            mean = statistics.mean(record['gains'])
            worst = min(statistics.mean(v) for v in record['modes'].values())
            w = self.policy['robust_weight']
            ranked.append({'player_id':sid,'name':p['name'],'position':p['position'],
                           'immediate_gain':immediate[sid], 'two_pick_mean_gain':mean,
                           'worst_mode_mean_gain':worst, 'score':(1-w)*mean+w*worst,
                           'scenario_survival_to_our_pick':record['survives_first']/len(record['gains']),
                           'scenario_survival_if_pass':record['survives_pass']/record['pass_trials'] if record['pass_trials'] else None,
                           'pass_trials':record['pass_trials'], 'mode_mean_gains':{m:statistics.mean(v) for m,v in record['modes'].items()},
                           'likely_continuations':[{'player_id':s,'name':self.players[s]['name'],'scenarios':n} for s,n in record['continuations'].most_common(3)],
                           'flags':p.get('flags',[]),'ecr':p.get('ecr'),'adp_rank':p.get('adp_rank'),
                           'override':self.policy.get('overrides',{}).get(sid),
                           'bye_conflicts':sum(self.players[s].get('bye_week')==p.get('bye_week') for s in ours) if p.get('bye_week') else None})
        ranked.sort(key=lambda r:(-r['score'],-r['immediate_gain'],r['ecr'] or 1000,r['player_id']))
        evaluated = {p['player_id'] for p in ranked}
        fallbacks = sorted((s for s in choices if s not in evaluated),key=lambda s:(-immediate[s],self.market[s][0],s))
        queue = [p['player_id'] for p in ranked]+fallbacks
        return {'engine_version':ENGINE_VERSION,'draft_id':state['draft_id'],'based_on_pick':state['last_pick'],'state_fingerprint':fingerprint(state),
                'target_pick':first,'following_pick':second,'our_roster':ours,'needs':self.needs(ours),
                'opponent_rosters':state['rosters_by_slot'],'seed':self.policy['seed'],'policy':self.policy,
                'recommendations':ranked,'fallback_order':queue,'evaluated_candidates':len(ranked),
                'scenario_count':len(self.policy['scenario_modes'])*self.policy['samples_per_mode'],
                'runtime_seconds':time.monotonic()-started,
                'assumptions':['Two-pick horizon; future own pick uses greedy marginal utility.',
                  'Scenario fractions depend on uncalibrated opponent assumptions, not measured probabilities.',
                  'Pass survival assumes selecting the best legal ECR alternative at this turn.',
                  'Season scoring subtotals, virtual replacement starters and discounted bench utility are proxies.',
                  'No opponent agent identity/strategy is inferred from mock bot behavior.',
                  'News/injury/depth flags require review; no automatic weekly injury probability multiplier.']}

    def validate_state(self,state):
        if type(state.get('seat')) is not int or not 1<=state['seat']<=self.teams:
            raise ValueError('Invalid assigned seat')
        if state['settings']['teams']!=self.teams or state['settings']['rounds']!=self.rounds:
            raise ValueError('Draft size differs from valuation board')
        if state['settings'].get('reversal_round') or state.get('traded_picks'):
            raise ValueError('Traded/reversed drafts unsupported')
        supported_slots = {'slots_'+p.lower() for p in POSITIONS}|{'slots_flex','slots_bn'}
        if any(k.startswith('slots_') and k not in supported_slots and v for k,v in state['settings'].items()):
            raise ValueError('Unsupported additional roster slots')
        for pos in POSITIONS:
            if state['settings'].get('slots_'+pos.lower(),0)!=self.slots[pos]:
                raise ValueError('Draft roster slots differ from valuation board')
        if state['settings'].get('slots_flex',0)!=self.flex:
            raise ValueError('FLEX settings differ from valuation board')
        rosters = state.get('rosters_by_slot')
        if not rosters or set(rosters)!={str(s) for s in range(1,self.teams+1)}:
            raise ValueError('All opponent rosters required; refresh controller state')
        ids = state['drafted_ids']
        if len(ids)!=state['last_pick'] or len(set(ids))!=len(ids):
            raise ValueError('Invalid drafted sequence')
        if any(s not in self.players for s in ids):
            raise ValueError('A drafted player is absent from the board; explicit identity integration required')
        expected = {str(s):[] for s in range(1,self.teams+1)}
        for i,sid in enumerate(ids,1):
            expected[str(owner(i,self.teams))].append(sid)
        if rosters!=expected:
            raise ValueError('Roster ownership differs from supported snake order')
        if [p['player_id'] for p in state['roster']]!=rosters[str(state['seat'])]:
            raise ValueError('Our roster differs from seat ownership')
        picks = upcoming(state['last_pick'],state['seat'],self.teams,self.rounds)
        if not picks or state.get('next_pick')!=picks[0]:
            raise ValueError('Draft complete or next pick mismatch')


def candidate_export(board,state,result,current,*,allow_mock=False):
    mock = allow_mock and state.get('league_id') is None
    if not mock and (board['draft_id']!=state['draft_id'] or board['league_id']!=state.get('league_id')):
        raise ValueError('Live candidate export requires matching league and draft')
    if state.get('simulation') or not 0 <= (current-datetime.fromisoformat(state['observed_at'])).total_seconds() <= 20:
        raise ValueError('Fresh real controller observation required for operational export')
    if fingerprint(state)!=result['state_fingerprint']:
        raise ValueError('Recommendation state mismatch')
    Engine(board,result['policy']).validate_state(state)
    base = export_candidates(board,current)
    detail = {r['player_id']:r for r in result['recommendations']}
    players = {r['player_id']:r for r in board['players']}
    base.update(draft_id=state['draft_id'],mock_uses_league_board=mock,
                source='Draft scenario planner ('+result.get('planning_mode','two_pick')+'); uncalibrated utility/availability assumptions.',
                based_on_pick=state['last_pick'],state_fingerprint=result['state_fingerprint'],
                policy_sha256=hashlib.sha256(json.dumps(result['policy'],sort_keys=True).encode()).hexdigest())
    base['players'] = [{'player_id':s,'name':players[s]['name'],'position':players[s]['position'],'priority':i,'exclude':False,
                        'rationale':detail.get(s,{'basis':'Unevaluated marginal-utility fallback; refresh after next selection'})} for i,s in enumerate(result['fallback_order'],1)]
    return base


def render(result):
    lines = ['# Draft strategy recommendations', '', f"Draft {result['draft_id']}; observed through pick {result['based_on_pick']}; targeting {result['target_pick']} then {result['following_pick']}.",
             f"{result['scenario_count']} scenarios; {result['evaluated_candidates']} evaluated candidates; {result['runtime_seconds']:.2f}s computation.", '',
             'Scenario survival percentages are model-dependent fractions, not calibrated probabilities.', '',
             f"Planning: {result.get('planning_mode','two_pick')}; phase: {result.get('phase','general')}; horizon: {result.get('horizon_picks',[result['target_pick'],result['following_pick']])}.", '',
             '| Player | Pos | Immediate gain | Horizon gain | Downside | Survives if passed | Flags |', '|---|---|---:|---:|---:|---:|---|']
    for p in result['recommendations']:
        survive = f"{100*p['scenario_survival_if_pass']:.0f}%" if p['scenario_survival_if_pass'] is not None else '—'
        gain = p.get('horizon_mean_gain',p.get('two_pick_mean_gain'))
        downside = p.get('downside_gain',p.get('worst_mode_mean_gain'))
        lines.append(f"| {p['name']} | {p['position']} | {p['immediate_gain']:.1f} | {gain:.1f} | {downside:.1f} | {survive} | {', '.join(p['flags'])} |")
    lines += ['', 'Assumptions:','']+['- '+x for x in result['assumptions']]
    return '\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board',type=Path,default=ROOT/'data/draft_board/2026/board.json')
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--policy',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--export',type=Path,help='Operational export requires fresh matching real state and board')
    parser.add_argument('--allow-mock',action='store_true',help='Explicitly use league board for a verified league-less mock of the same roster format')
    args = parser.parse_args()
    try:
        board = json.loads(args.board.read_text())
        state = json.loads(args.state.read_text())
        result = Engine(board,load_policy(args.policy)).recommend(state)
        result['board_sha256'] = hashlib.sha256(args.board.read_bytes()).hexdigest()
        result['review_only'] = True
        save_atomic(args.output/'recommendations.json',result)
        (args.output/'RECOMMENDATIONS.md').write_text(render(result))
        if args.export:
            save_atomic(args.export,candidate_export(board,state,result,datetime.now(timezone.utc),allow_mock=args.allow_mock))
        print(render(result))
    except (OSError,ValueError,KeyError,TypeError) as error:
        parser.exit(1,str(error)+'\n')


if __name__=='__main__':
    main()
