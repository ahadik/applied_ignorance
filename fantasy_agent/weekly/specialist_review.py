"""Offline specialist-versus-bench review; not an operational draft ranking."""
from fantasy_agent.paths import ROOT as PROJECT_ROOT
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from fantasy_agent.drafting.draft_strategy import Engine, load_policy
from fantasy_agent.core.storage import save_atomic

ROOT = PROJECT_ROOT


def review(board, state):
    if (board['draft_id'], board['league_id']) != (state['draft_id'], state['league_id']):
        raise ValueError('Board and live draft identity differ')
    engine = Engine(board, load_policy())
    engine.validate_state(state)
    drafted = set(state['drafted_ids'])
    ours = state['rosters_by_slot'][str(state['seat'])]
    sections = {}
    for pos in ('K', 'DEF'):
        available = sorted((p for p in board['players'] if p['position'] == pos
                            and p['player_id'] not in drafted and not p.get('exclude')),
                           key=lambda p: (p.get('ecr') or 1000, p['player_id']))
        need = sum(engine.needs(r)[pos] for seat,r in state['rosters_by_slot'].items()
                   if seat != str(state['seat']))
        def row(p):
            scoring = p.get('scoring') or {}
            return dict(name=p['name'], player_id=p['player_id'], ecr=p.get('ecr'),
                        partial_points=scoring.get('supported_points'),
                        provider_points=scoring.get('provider_points'),
                        uncovered_rules=scoring.get('uncovered_rules'),
                        flags=p.get('flags',[]))
        # A stress scenario, not a forecast: each opponent fills its open slot
        # before our next specialist choice, selecting by consensus rank.
        stress = available[min(need,len(available)-1)] if available else None
        sections[pos] = dict(available_count=len(available),opponents_with_open_slot=need,
                             leaders=[row(p) for p in available[:5]],
                             stress_remainder=row(stress) if stress else None)
    bench = sorted((s for s in engine.usable-drafted if engine.position[s] in ('RB','WR','TE')),
                   key=lambda s:(-engine.marginal(s,ours),engine.market[s][0],s))[:6]
    return dict(draft_id=state['draft_id'], based_on_pick=state['last_pick'],
                observed_at=state['observed_at'],next_pick=state['next_pick'],
                specialists=sections,bench=[dict(name=engine.players[s]['name'],player_id=s,
                    marginal_utility=engine.marginal(s,ours)) for s in bench],
                limitations=['Advisory only; no queue or policy changes.',
                    'Partial specialist points and provider totals are not exact league totals.',
                    'Stress remainder assumes opponents fill one open specialist slot by ECR; not a probability.',
                    'Bench utility uses existing uncalibrated weights; no cross-position specialist comparison is asserted.',
                    'No weekly matchup or streaming projection is available in this report.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--draft',default='1400628785413394432')
    args = parser.parse_args()
    folder = ROOT/'data/drafts'/args.draft
    health = json.loads((folder/'health.json').read_text())
    if not health.get('ok'):
        raise ValueError('Live watcher is unhealthy')
    state = json.loads((folder/'state.json').read_text())
    age = (datetime.now(timezone.utc)-datetime.fromisoformat(state['observed_at'])).total_seconds()
    if not 0 <= age <= 20:
        raise ValueError('Live state expired')
    board = json.loads((ROOT/'data/draft_session'/args.draft/'board.json').read_text())
    result = review(board,state)
    save_atomic(folder/'specialist_review.json',result)
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
