"""Bounded A/B search. No provider access; see docs/AB_STRATEGY.md."""
from collections import Counter, defaultdict
import math
import statistics
import time

from fantasy_agent.drafting.draft_strategy import ENGINE_VERSION, fingerprint, owner, upcoming


def phase(state,teams,rounds):
    picks = upcoming(state['last_pick'],state['seat'],teams,rounds)
    if len(picks)<2:
        return 'FINAL'
    gap = picks[1]-picks[0]-1
    other_gap = 2*teams-2-gap
    if gap<=2 and gap<other_gap:
        return 'A'
    if len(picks)>2 and other_gap<=2 and other_gap<gap:
        return 'B'
    return 'GENERAL'


class ABPlanner:
    def __init__(self,engine):
        self.e = engine
        self.p = engine.policy['ab']
        self.cache = {}
        self.greedy_orders = {}
        self.work = Counter()

    def utility(self,roster):
        key = tuple(sorted(roster))
        if key not in self.cache:
            self.cache[key] = self.e.utility(list(key))
            self.work['utility_evaluations'] += 1
        return self.cache[key]

    def greedy(self,available,roster):
        """Exact marginal ranking reused across paths with the same own roster."""
        key = tuple(sorted(roster))
        if key not in self.greedy_orders:
            allowed = self.e.eligible(self.e.usable-set(roster),roster)
            self.greedy_orders[key] = sorted(allowed,key=lambda s:(-self.utility(roster+[s]),self.e.market[s][0],s))
            self.work['greedy_rankings_built'] += 1
        for sid in self.greedy_orders[key]:
            if sid in available:
                return sid
        raise ValueError('No legal greedy continuation')

    def choices(self,available,roster,width):
        """A bounded mixture of marginal-value and consensus choices."""
        available = set(available)
        pool = set()
        for pos in self.e.allowed_positions(roster):
            for ordering in (self.e.value_order[pos],self.e.market_order[(0,pos)]):
                found = 0
                for sid in ordering:
                    if sid in available and sid in self.e.usable:
                        pool.add(sid)
                        found += 1
                        if found==width:
                            break
        if not pool:
            raise ValueError('No legal A/B candidate')
        value = sorted(pool,key=lambda s:(-self.utility(roster+[s]),self.e.market[s][0],s))
        consensus = sorted(pool,key=lambda s:(self.e.market[s][0],s))
        result = []
        for a,b in zip(value,consensus):
            for sid in (a,b):
                if sid not in result:
                    result.append(sid)
                if len(result)==width:
                    return result
        return result

    def plausible(self,available,roster):
        """Near-best adjusted ranks under at least one opponent model, capped."""
        regrets = {}
        for mode in self.e.policy['scenario_modes']:
            options = self.e.opponent_options(available,roster,mode,self.p['response_width'])
            if not options:
                continue
            floor = options[0][0]
            for score,sid in options:
                regret = score-floor
                if regret<=self.p['rank_slack']:
                    regrets[sid] = min(regrets.get(sid,float('inf')),regret)
        return sorted(regrets,key=lambda s:(regrets[s],self.e.market[s][0],s))[:self.p['response_width']]

    def responses(self,available,rosters,start,end):
        """Enumerate <= two opponent selections, preserving actual owners."""
        if not 0<=end-start<=2:
            raise ValueError('A response enumeration requires a short gap')
        states = [(set(available),{s:list(r) for s,r in rosters.items()},[])]
        for pick in range(start,end):
            expanded = []
            seat = owner(pick,self.e.teams)
            for pool,teams,path in states:
                for sid in self.plausible(pool,teams[seat]):
                    changed = dict(teams)
                    changed[seat] = teams[seat]+[sid]
                    expanded.append((pool-{sid},changed,path+[sid]))
            states = expanded
        if not states:
            raise ValueError('No plausible legal opponent responses')
        # Same team picking X/Y or Y/X leaves the same state for our decision.
        unique = {}
        for pool,teams,path in states:
            key = tuple((s,tuple(sorted(r))) for s,r in sorted(teams.items()))
            unique.setdefault(key,(pool,teams,path))
        self.work['short_response_states'] += len(unique)
        return list(unique.values())

    def simulate(self,pool,rosters,start,end,mode,seed):
        self.work['simulated_opponent_picks'] += end-start
        later,teams = self.e.simulate(pool,rosters,start,end,mode,seed)
        return set(later),teams

    def tail_gain(self,pool,teams,seat,start,end,seed):
        """Discounted terminal approximation: one greedy pick after the long gap."""
        roster = teams[seat]
        base = self.utility(roster)
        modes = self.e.policy['scenario_modes']
        gains = []
        for i in range(self.p['tail_samples']):
            mode = modes[i*len(modes)//self.p['tail_samples']]
            later,_ = self.simulate(pool,teams,start,end,mode,seed+i*101)
            sid = self.greedy(later,roster)
            gains.append(self.utility(roster+[sid])-base)
        return statistics.mean(gains)

    def pair_for(self,first,pool,teams,seat,a,b,*,tail_pick=None,seed=0):
        ours = teams[seat]+[first]
        after = dict(teams)
        after[seat] = ours
        branches = []
        for later,opponents,response in self.responses(set(pool)-{first},after,a+1,b):
            replies = []
            for reply in self.choices(later,ours,self.p['reply_width']):
                pair_roster = ours+[reply]
                raw = self.utility(pair_roster)
                terminal = 0.0
                if tail_pick is not None:
                    updated = dict(opponents)
                    updated[seat] = pair_roster
                    terminal = self.tail_gain(later-{reply},updated,seat,b+1,tail_pick,seed)
                replies.append({'reply':reply,'score':raw+self.p['tail_weight']*terminal,
                                'pair_utility':raw,'terminal_gain':terminal})
            best = min(replies,key=lambda r:(-r['score'],self.e.market[r['reply']][0],r['reply']))
            branches.append(dict(best,response=response))
        worst = min(branches,key=lambda r:(r['score'],tuple(r['response'])))
        return {'score':worst['score'],'mean':statistics.mean(r['score'] for r in branches),
                'pair_mean':statistics.mean(r['pair_utility'] for r in branches),
                'terminal_mean':statistics.mean(r['terminal_gain'] for r in branches),
                'worst':worst,'branches':branches,'first':first}

    def solve_pair(self,pool,teams,seat,a,b):
        plans = [self.pair_for(s,pool,teams,seat,a,b) for s in
                 self.choices(pool,teams[seat],self.p['future_width'])]
        return min(plans,key=lambda p:(-p['score'],-self.utility(teams[seat]+[p['first']]),
                                      self.e.market[p['first']][0],p['first']))

    def recommend(self,state):
        started = time.monotonic()
        self.e.validate_state(state)
        seat = state['seat']
        picks = upcoming(state['last_pick'],seat,self.e.teams,self.e.rounds)
        kind = phase(state,self.e.teams,self.e.rounds)
        ours = list(state['rosters_by_slot'][str(seat)])
        teams = {int(s):list(r) for s,r in state['rosters_by_slot'].items()}
        pool = set(self.e.players)-set(state['drafted_ids'])
        base = self.utility(ours)
        seed = self.e.policy['seed']+state['last_pick']*1009
        modes = self.e.policy['scenario_modes']
        prefixes = []
        if picks[0]==state['last_pick']+1:
            prefixes = [(pool,teams)]
        else:
            for i in range(self.p['prefix_samples']):
                mode = modes[i*len(modes)//self.p['prefix_samples']]
                prefixes.append(self.simulate(pool,teams,state['last_pick']+1,picks[0],mode,seed+i))
        votes = Counter(s for before,_ in prefixes for s in self.choices(before,ours,self.p['first_width']))
        candidates = sorted(votes,key=lambda s:(-votes[s],-self.utility(ours+[s]),self.e.market[s][0],s))[:self.p['first_width']]
        ranked = []
        for sid in candidates:
            gains,means,pairs,tails = [],[],[],[]
            continuations = Counter()
            by_mode = defaultdict(list)
            worst_cases = []
            survived = 0
            pass_survived,pass_count = 0,0
            for before,opponents in prefixes:
                present = sid in before
                survived += present
                first = sid if present else self.greedy(before,ours)
                if kind=='A':
                    plan = self.pair_for(first,before,opponents,seat,picks[0],picks[1],
                                        tail_pick=picks[2] if len(picks)>2 else None,seed=seed)
                    gains.append(plan['score']-base)
                    means.append(plan['mean']-base)
                    pairs.append(plan['pair_mean']-base)
                    tails.append(plan['terminal_mean'])
                    worst_cases.append(plan['worst'])
                    continuations.update(r['reply'] for r in plan['branches'])
                    if present:
                        alternate = self.e.ecr_pick(before-{sid},ours)
                        changed = dict(opponents)
                        changed[seat] = ours+[alternate]
                        for remaining,_,_ in self.responses(before-{alternate},changed,picks[0]+1,picks[1]):
                            pass_count += 1
                            pass_survived += sid in remaining
                else:
                    changed = dict(opponents)
                    changed[seat] = ours+[first]
                    alternate = self.e.ecr_pick(before-{sid},ours) if present else None
                    for mi,mode in enumerate(modes):
                        for trial in range(self.e.policy['samples_per_mode']):
                            draw_seed = seed+mi*101+trial
                            later,future = self.simulate(before-{first},changed,picks[0]+1,picks[1],mode,draw_seed)
                            plan = self.solve_pair(later,future,seat,picks[1],picks[2])
                            gain = plan['score']-base
                            gains.append(gain)
                            means.append(gain)
                            by_mode[mode].append(gain)
                            continuations[plan['first']] += 1
                            worst_cases.append({'score':plan['score'],'future_a':plan['first'],**plan['worst']})
                            if alternate:
                                passed_teams = dict(opponents)
                                passed_teams[seat] = ours+[alternate]
                                passed,_ = self.simulate(before-{alternate},passed_teams,picks[0]+1,picks[1],mode,draw_seed)
                                pass_count += 1
                                pass_survived += sid in passed
            mean = statistics.mean(means)
            if kind=='A':
                downside = min(gains)
                score = downside
            else:
                count = max(1,math.ceil(len(gains)*self.p['downside_fraction']))
                downside = statistics.mean(sorted(gains)[:count])
                weight = self.e.policy['robust_weight']
                score = (1-weight)*mean+weight*downside
            player = self.e.players[sid]
            ranked.append({'player_id':sid,'name':player['name'],'position':player['position'],
                           'immediate_gain':self.utility(ours+[sid])-base,'horizon_mean_gain':mean,
                           'pair_mean_gain':statistics.mean(pairs) if pairs else None,
                           'terminal_mean_gain':statistics.mean(tails) if tails else None,
                           'downside_gain':downside,'score':score,'mode_mean_gains':{m:statistics.mean(v) for m,v in by_mode.items()},
                           'scenario_survival_to_our_pick':survived/len(prefixes),
                           'scenario_survival_if_pass':pass_survived/pass_count if pass_count else None,
                           'pass_trials':pass_count,'conditional_outcomes':len(gains),
                           'worst_case':min(worst_cases,key=lambda r:r['score']),
                           'likely_continuations':[{'player_id':s,'name':self.e.players[s]['name'],'scenarios':n} for s,n in continuations.most_common(3)],
                           'flags':player.get('flags',[]),'ecr':player.get('ecr'),'adp_rank':player.get('adp_rank'),
                           'override':self.e.policy.get('overrides',{}).get(sid),
                           'bye_conflicts':sum(self.e.players[s].get('bye_week')==player.get('bye_week') for s in ours) if player.get('bye_week') else None})
        ranked.sort(key=lambda r:(-r['score'],-r['immediate_gain'],r['ecr'] or 1000,r['player_id']))
        remainder = self.e.eligible(pool-set(candidates),ours)
        remainder.sort(key=lambda s:(-self.utility(ours+[s]),self.e.market[s][0],s))
        return {'engine_version':ENGINE_VERSION,'planning_mode':'ab','phase':kind,
                'draft_id':state['draft_id'],'based_on_pick':state['last_pick'],'state_fingerprint':fingerprint(state),
                'target_pick':picks[0],'following_pick':picks[1],'horizon_picks':picks[:3],
                'gap_to_next':picks[1]-picks[0]-1,'our_roster':ours,'needs':self.e.needs(ours),
                'opponent_rosters':state['rosters_by_slot'],'policy':self.e.policy,'seed':self.e.policy['seed'],
                'recommendations':ranked,'fallback_order':[r['player_id'] for r in ranked]+remainder,
                'evaluated_candidates':len(ranked),'scenario_count':len(prefixes)*(len(modes)*self.e.policy['samples_per_mode'] if kind=='B' else 1),
                'work':dict(self.work),'runtime_seconds':time.monotonic()-started,
                'assumptions':[
                    'A: maximin within bounded own choices and plausible short responses; discounted one-pick terminal approximation beyond B.',
                    'B: long-gap scenarios followed by a constrained-maximin future A–B pair; mean blended with lower-tail average.',
                    'Opponent plausibility uses near-best adjusted rank under at least one model, not optimal opponent season utility.',
                    'Candidate/response widths bound search; this is not exhaustive minimax over every legal draft.',
                    'A availability fractions count enumerated responses; B fractions count simulated paths. Neither is calibrated probability.',
                    'Virtual starter references and bench values remain partial-projection proxies; injury/news flags require review.',
                    'Before our turn, bounded prefix scenarios forecast preceding picks; recompute when actual picks arrive.']}
