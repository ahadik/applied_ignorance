"""Offline, auditable draft board: IDs, scoring coverage, history and starter value.

No provider reads. Rebuilds use checked input snapshots and nflverse's offline
builder. Export supplies a reviewable candidate file; it never applies a queue.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path

from draft_inputs import ROOT, load_inputs
from draft_history_analysis import build as build_history, timestamp
from storage import save_atomic

from player_scoring import (POSITIONS, OFFENSE, STAT_MAP, OFFENSE_EXTRA, DEFENSE_STATS,
    KICK_STATS, DEF_MAP, ident, number, positive, position, team, rows, unique, index,
    match_player, scoring)


def starter_values(players, roster_positions, teams):
    """Deterministic single-position baseline, with remaining RB/WR/TE filling FLEX."""
    if any(p not in (*POSITIONS,'BN','FLEX') for p in roster_positions):
        raise ValueError('Unsupported roster allocation')
    pools = {p: sorted([r for r in players if r['position'] == p and r.get('scoring') and r['scoring']['core_fields_complete'] and not r['exclude']],
                       key=lambda r: (-r['scoring']['supported_points'], r['player_id'])) for p in OFFENSE}
    counts = {p: roster_positions.count(p)*teams for p in OFFENSE}
    if any(len(pools[p]) <= counts[p] for p in OFFENSE):
        raise ValueError('Insufficient projected players for starter/replacement baseline')
    flex = sorted([r for p in ('RB','WR','TE') for r in pools[p][counts[p]:]],
                  key=lambda r: (-r['scoring']['supported_points'], r['player_id']))
    flex_slots = roster_positions.count('FLEX')*teams
    if len(flex) < flex_slots:
        raise ValueError('Insufficient players for FLEX allocation')
    for row in flex[:flex_slots]:
        counts[row['position']] += 1
    baselines = {}
    for pos, pool in pools.items():
        if counts[pos] >= len(pool):
            raise ValueError('No replacement player for '+pos)
        replacement = pool[counts[pos]]
        baselines[pos] = {'starter_count': counts[pos], 'replacement_player_id': replacement['player_id'],
                          'replacement_name': replacement['name'], 'supported_points': replacement['scoring']['supported_points']}
        for row in pool:
            row['starter_value'] = row['scoring']['supported_points']-replacement['scoring']['supported_points']
    return baselines


def validate_sources(inputs, season, as_of):
    required = {'context','sleeper_players','nfl_state','fp_external','ecr','adp','news','injuries'} | {'projections_'+p for p in ('QB','RB','WR','TE','K','DST')}
    if required-set(inputs):
        raise ValueError('Required input datasets missing: '+', '.join(sorted(required-set(inputs))))
    context = inputs['context']
    if str(context['league']['season']) != str(season) or str(context['draft']['season']) != str(season):
        raise ValueError('League/draft season mismatch')
    rec = context['league']['scoring_settings'].get('rec', 0)
    label = {0:'STD', .5:'HALF', 1:'PPR'}.get(rec)
    if not label:
        raise ValueError('Unsupported reception-scoring consensus baseline')
    state = inputs['nfl_state']['data']
    request = inputs['injuries'].get('request', {}).get('params', {})
    if str(state.get('season')) != str(season) or state.get('season_type') != 'regular' or not 1 <= int(state['week']) <= 18 or str(request.get('year')) != str(season) or str(request.get('week')) != str(state['week']):
        raise ValueError('Injury request does not match current season/week')
    sources = []
    for name, entry in inputs.items():
        fetched = timestamp(entry['fetched_at'])
        if fetched > as_of:
            raise ValueError('Input fetched after analysis time: '+name)
        data = entry.get('data', {})
        if name.startswith('projections_'):
            pos = name.split('_',1)[1]
            if str(data.get('season')) != str(season) or str(data.get('week')) != '0' or data.get('positions') != pos:
                raise ValueError('Projection season/period/position mismatch: '+name)
            params = entry.get('request', {}).get('params', {})
            if str(params.get('week')) != '0' or params.get('position') != pos or params.get('ros'):
                raise ValueError('Projection request is not the selected preseason position')
        if name in ('ecr','adp'):
            if str(data.get('year')) != str(season) or str(data.get('week')) != '0' or data.get('scoring') != label or data.get('ranking_type_name') != ('draft' if name == 'ecr' else 'adp'):
                raise ValueError('Ranking scope mismatch: '+name)
        if name.startswith('fp_') and str(data.get('season')) != str(season):
            raise ValueError('Player directory season mismatch')
        max_age = 900 if name in ('news','injuries') else 3600 if name == 'context' else 21600 if name.startswith('projections_') or name in ('ecr','adp','nfl_state') else 86400
        provider_updated = data.get('last_updated_ts')
        if provider_updated is not None:
            provider_updated = datetime.fromtimestamp(number(provider_updated), timezone.utc)
            if provider_updated > as_of:
                raise ValueError('Provider timestamp is in the future: '+name)
        age = (as_of-fetched).total_seconds()
        sources.append({'name': name, 'fetched_at': entry['fetched_at'], 'cache_hit_at_collection': entry.get('cache_hit'),
                        'source_updated_at': provider_updated.isoformat() if provider_updated else None,
                        'fetch_age_hours': age/3600, 'max_fetch_age_hours': max_age/3600,
                        'stale': age > max_age, 'provider_tier': data.get('tier'),
                        'public_api_limited': data.get('public_api_limited'),
                        'freshness_note': 'Unknown publication time is not replaced with retrieval time.'})
    return sources


def make_board(inputs, history, season, as_of):
    sources = validate_sources(inputs, season, as_of)
    context = inputs['context']
    sleeper = inputs['sleeper_players']['data']
    if any(ident(p.get('player_id')) != sid for sid,p in sleeper.items()):
        raise ValueError('Sleeper player key/ID mismatch')
    indices = {f:index(sleeper.values(), f, 'player_id') for f in ('sportradar_id','espn_id','yahoo_id')}
    fp = unique(rows(inputs['fp_external']['data'], 'players'), 'player_id')
    ecr = unique(rows(inputs['ecr']['data'], 'players'), 'player_id')
    adp = unique(rows(inputs['adp']['data'], 'players'), 'player_id')
    injuries = unique(rows(inputs['injuries']['data'], 'injuries'), 'player_id')
    news = defaultdict(list)
    for item in rows(inputs['news']['data'], 'items'):
        news[ident(item.get('player_id'))].append({k:item.get(k) for k in ('id','title','created','updated','link','categories','desc','impact')})
    for injury in injuries.values():
        probability = number(injury.get('probability_of_playing'))
        if probability is not None and not 0 <= probability <= 1:
            raise ValueError('Injury probability outside zero to one')
    projections = {}
    counts = {}
    for pos in POSITIONS:
        values = rows(inputs['projections_'+('DST' if pos=='DEF' else pos)]['data'], 'players')
        counts[pos] = len(values)
        for fpid, row in unique(values, 'fpid').items():
            if position(row.get('position_id')) != pos or fpid in projections or not isinstance(row.get('stats'), dict):
                raise ValueError('Invalid/duplicate projection position or stat shape')
            # Validate every supplied numeric stat, including unused fields.
            for value in row['stats'].values():
                number(value)
            projections[fpid] = row
    historical = unique(history['players'], 'gsis_id')
    espn_to_history = index(history['players'], 'espn_id', 'gsis_id')
    players, issues = [], []
    for fpid in sorted(set(ecr)|set(adp)|set(projections)):
        records = [r for r in (fp.get(fpid),ecr.get(fpid),adp.get(fpid),projections.get(fpid)) if r]
        base = fp.get(fpid) or projections.get(fpid) or ecr.get(fpid) or adp[fpid]
        pos = position(base.get('position_id', base.get('player_position_id')))
        if pos not in POSITIONS:
            continue
        name = base.get('player_name', base.get('name', ''))
        club = team(base.get('team_id', base.get('player_team_id')))
        sid, match_basis = match_player(records, pos, club, sleeper, indices)
        rank = positive(ecr.get(fpid, {}).get('rank_ecr'))
        market = positive(adp.get(fpid, {}).get('rank_ecr'))
        if not sid:
            issues.append({'fpid':fpid,'name':name,'ecr':rank,'adp_rank':market,'reason':match_basis})
            continue
        sl = sleeper[sid]
        flags = []
        for row in records:
            p = position(row.get('position_id',row.get('player_position_id')))
            if p and p != pos:
                flags.append('provider_position_conflict')
        if club and team(sl.get('team') or sid) != club:
            flags.append('provider_team_difference')
        ids = set()
        if ident(sl.get('gsis_id')) in historical:
            ids.add(ident(sl['gsis_id']))
        for row in [sl, *records]:
            ids |= espn_to_history.get(ident(row.get('espn_id')), set())
        hist = historical[next(iter(ids))] if len(ids) == 1 else None
        if len(ids) > 1:
            flags.append('conflicting_history_ids')
        if hist is None and pos != 'DEF':
            flags.append('no_matched_nflverse_evidence')
        injury = injuries.get(fpid)
        if sl.get('injury_status') or injury and any(injury.get(k) for k in ('status','injury_type','practice_report_injury_type')):
            flags.append('injury_review')
        if sl.get('status') not in ('Active', None) or sl.get('active') is False:
            flags.append('sleeper_status_review')
        if hist and hist.get('current_team_not_in_latest_history'):
            flags.append('team_changed_since_history')
        if hist and hist.get('no_recorded_history'):
            flags.append('no_recorded_nfl_history')
        projection = projections.get(fpid)
        if projection and ident(projection.get('mflid')) and ident(fp.get(fpid,{}).get('mfl_id')) and ident(projection['mflid']) != ident(fp[fpid]['mfl_id']):
            flags.append('projection_mfl_conflict')
        points = scoring(projection['stats'], pos, context['league']['scoring_settings']) if projection else None
        if points is None:
            flags.append('no_projection')
        elif not points['core_fields_complete']:
            flags.append('missing_core_projection_stats')
        if points and points['ppr_reception_check_error'] is not None and abs(points['ppr_reception_check_error']) > .1:
            flags.append('ppr_arithmetic_mismatch')
        years = hist.get('seasons', {}) if hist else {}
        compact_history = {year:{'recorded_games':value['stats_recorded_games'], 'teams':value['teams'],
                        'metrics': {k:value['metrics'].get(k) for k in ('targets','carries','receptions','fantasy_points_ppr')},
                        'snap_share':value['snaps']['mean_game_offense_snap_share'],
                        'late_weeks':value['late_window_weeks'], 'late_snap_share':value['late_snaps']['mean_game_offense_snap_share']} for year,value in years.items()}
        depth = hist.get('current_depth', []) if hist else []
        depth = [r | {'usable': r['usable'] and 0 <= (as_of-timestamp(r['observed_at'])).total_seconds() <= 36*3600} for r in depth]
        players.append({'player_id':sid, 'fpid':fpid,'gsis_id':hist['gsis_id'] if hist else None,
                        'name':sl.get('full_name') or name, 'position':pos, 'team':sl.get('team'),
                        'eligibility':sl.get('fantasy_positions') or [pos], 'match_basis':match_basis,
                        'ecr':rank,'ecr_tier':ecr.get(fpid,{}).get('tier'),
                        'ecr_rank_std':number(ecr.get(fpid,{}).get('rank_std')),
                        'adp_rank':market,'adp_source_average_rank':positive(adp.get(fpid,{}).get('rank_ave')),
                        'bye_week':positive(ecr.get(fpid,{}).get('player_bye_week')),
                        'projection_stats':projection['stats'] if projection else None,'scoring':points,
                        'history':compact_history,'depth':depth,'injury':injury,
                        'sleeper_status':{k:sl.get(k) for k in ('status','active','injury_status','injury_notes','news_updated')},
                        'news':news.get(fpid,[]), 'flags':flags,
                        'exclude':bool(set(flags) & {'provider_position_conflict','ppr_arithmetic_mismatch','projection_mfl_conflict'})})
    # Duplicate cross-platform claims cannot enter the candidate pool.
    duplicates = {sid for sid,n in Counter(r['player_id'] for r in players).items() if n > 1}
    for row in players:
        if row['player_id'] in duplicates:
            issues.append({'fpid':row['fpid'],'name':row['name'],'ecr':row['ecr'],'reason':['duplicate_sleeper_claim']})
    players = [r for r in players if r['player_id'] not in duplicates]
    baselines = starter_values(players, context['league']['roster_positions'], context['draft']['settings']['teams'])
    players.sort(key=lambda r: (r['ecr'] if r['ecr'] is not None else 10000, r['adp_rank'] or 10000, r['player_id']))
    for i,row in enumerate(players,1):
        row['board_rank'] = i
    top_cutoff = context['draft']['settings']['teams']*context['draft']['settings']['rounds']
    critical = [r for r in issues if (r.get('ecr') is not None and r['ecr'] <= top_cutoff) or
                (r.get('adp_rank') is not None and r['adp_rank'] <= top_cutoff)]
    primary = [p for p in players if p['ecr'] is not None and p['ecr'] <= top_cutoff]
    coverage = {'draft_range':top_cutoff,'ecr_players_in_range':sum(positive(p.get('rank_ecr')) is not None and positive(p.get('rank_ecr'))<=top_cutoff for p in ecr.values()),
                'matched_in_range':len(primary),'projected_in_range':sum(p['scoring'] is not None for p in primary),
                'history_or_depth_in_range':sum(p['gsis_id'] is not None for p in primary),
                'no_projection_in_range':[p['name'] for p in primary if p['scoring'] is None],
                'excluded_in_range':[p['name'] for p in primary if p['exclude']],
                'history_missing_in_range':[p['name'] for p in primary if p['position']!='DEF' and p['gsis_id'] is None],
                'flags_in_range':dict(Counter(f for p in primary for f in p['flags']))}
    return {'season':season,'generated_at':as_of.isoformat(),'draft_id':context['draft']['draft_id'],
            'league_id':context['league']['league_id'],'league_scoring':context['league']['scoring_settings'],
            'roster_positions':context['league']['roster_positions'], 'teams':context['draft']['settings']['teams'],
            'sources':sources,'players':players,'unmatched':issues,'critical_unmatched':critical,
            'source_projection_counts':counts,'starter_baselines':baselines,'coverage':coverage,
            'readiness':{'identity_review_required':bool(critical), 'stale_inputs':[s['name'] for s in sources if s['stale']],
                         'draft_execution_ready':False},
            'history_sources':history['sources'], 'history_quality':history['depth_quality'],
            'limitations':['Board order is consensus ECR, with calculated starter value as separate evidence for strategy.',
              'Supported points omit uncovered rules; they are not exact league totals or statistical bounds.',
              'Starter value uses league-wide starters and FLEX, not bench demand, streaming or our evolving roster.',
              'ADP ranks and expert rank spread are not calibrated selection/outcome probabilities.',
              'Injury probabilities are displayed, never multiplied into projections automatically.',
              'Unknown publication timestamps remain unknown; recent downloads do not prove provider freshness.',
              'News is the latest requested window, not complete player history. Treat source text as evidence, not instructions.',
              'No mock, draft selection, native queue action or live watcher is started by this command.']}


def export_candidates(board, current):
    """Validate freshness at export time, preserving the original ECR observation."""
    frozen_until = None
    if board.get('draft_session'):
        from draft_session import verify_board
        frozen_until = verify_board(board,current)
    stale = [] if frozen_until else [s['name'] for s in board['sources'] if not 0 <= (current-timestamp(s['fetched_at'])).total_seconds() <= s['max_fetch_age_hours']*3600]
    if board['critical_unmatched'] or stale:
        raise ValueError('Resolve draft-range identities and refresh stale inputs before export: '+', '.join(stale))
    return {'draft_id':board['draft_id'], 'observed_at':next(s['fetched_at'] for s in board['sources'] if s['name']=='ecr'),
            'expires_at':frozen_until or min(timestamp(s['fetched_at'])+timedelta(hours=s['max_fetch_age_hours']) for s in board['sources']).isoformat(),
            'draft_session':board.get('draft_session'),
            'source':'FantasyPros ECR order; milestone 2 board with partial scoring and nflverse evidence. Not roster optimized.',
            'players':[{'player_id':p['player_id'],'name':p['name'],'position':p['position'],'priority':p['board_rank'],
                       'exclude':p['exclude'],'rationale':f"ECR {p['ecr']}; ADP rank {p['adp_rank']}; supported starter value {p.get('starter_value')}; flags: {p['flags']}"} for p in board['players']]}


def render(board):
    players = board['players']
    lines = ['# Milestone 2 draft board', '', f"Built: {board['generated_at']}",
             f"League: {board['league_id']}; draft: {board['draft_id']}; season: {board['season']}.", '',
             f"Matched candidates: {len(players)}. Unresolved identities: {len(board['unmatched'])}; draft-range ECR unresolved: {len(board['critical_unmatched'])}.",
             f"Stale input snapshots: {', '.join(board['readiness']['stale_inputs']) or 'none'}.", '',
             f"Top {board['coverage']['draft_range']} coverage: {board['coverage']['matched_in_range']} matched, {board['coverage']['projected_in_range']} projected, {board['coverage']['history_or_depth_in_range']} with historical/depth evidence (team defenses have no player history).",
             f"Top-range missing projections: {board['coverage']['no_projection_in_range'] or 'none'}. Excluded for validation: {board['coverage']['excluded_in_range'] or 'none'}.", '',
             '## Collection and coverage', '', '| Position | Projections returned | Matched projections |', '|---|---:|---:|']
    for pos in POSITIONS:
        lines.append(f"| {pos} | {board['source_projection_counts'][pos]} | {sum(p['position']==pos and p['scoring'] is not None for p in players)} |")
    lines += ['', '## First 50 by consensus', '',
              'Points below are the supported scoring subtotal, not an exact league forecast. Value is the subtotal above the next player outside our modeled league-wide starting pool.', '',
              '| ECR | Player | Pos | Team | ADP rank | Supported points | Starter value | Review flags |', '|---:|---|---|---|---:|---:|---:|---|']
    def fmt(value):
        return '—' if value is None else f'{value:.1f}'
    for row in players[:50]:
        lines.append(f"| {fmt(row['ecr'])} | {row['name']} | {row['position']} | {row['team']} | {fmt(row['adp_rank'])} | {fmt(row['scoring']['supported_points'] if row['scoring'] else None)} | {fmt(row.get('starter_value'))} | {', '.join(row['flags'])} |")
    lines += ['', '## Replacement assumptions', '', '| Pos | Starters incl. FLEX | Next player | Supported points |','|---|---:|---|---:|']
    for pos, value in board['starter_baselines'].items():
        lines.append(f"| {pos} | {value['starter_count']} | {value['replacement_name']} | {fmt(value['supported_points'])} |")
    lines += ['', '## Scoring gaps by position', '']
    for pos in POSITIONS:
        counts = Counter(k for p in players if p['position']==pos and p['scoring'] for k in p['scoring']['uncovered_rules'])
        lines.append(f"- {pos}: "+', '.join(f'{k} ({v} players)' for k,v in sorted(counts.items())))
    lines += ['', '## Freshness', '', '| Source | Retrieved | Published | Stale |', '|---|---|---|---|']
    for s in board['sources']:
        lines.append(f"| {s['name']} | {s['fetched_at']} | {s['source_updated_at'] or 'unknown'} | {s['stale']} |")
    lines += ['', '## Draft-range unmatched identities', '']
    lines += [f"- {p['name']} (ECR {p['ecr']}): {', '.join(p['reason'])}" for p in board['critical_unmatched']] or ['None.']
    lines += ['', '## Interpretation and checkpoint', ''] + ['- '+x for x in board['limitations']]
    lines += ['', 'Review `board.json` for per-player raw projections, scoring contributions, identity evidence, history, depth, injury and news links. Run the offline `player` command for a compact individual review.']
    return '\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('build','player','issues','summary','export'))
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--as-of')
    parser.add_argument('--player')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--all', action='store_true', help='Include all flagged players in issues, not just draft range')
    args = parser.parse_args()
    folder = ROOT / 'data/draft_board' / str(args.season)
    try:
        if args.command == 'build':
            from provider_freeze import LOCK
            if LOCK.exists() and json.loads(LOCK.read_text())['active']:
                raise ValueError('Draft snapshot frozen; use the pinned board instead of overwriting it')
            manifest, inputs = load_inputs(ROOT / 'data/draft_inputs' / str(args.season))
            if manifest['season'] != args.season:
                raise ValueError('Manifest season mismatch')
            as_of = timestamp(args.as_of) if args.as_of else datetime.now(timezone.utc)
            history, _ = build_history(ROOT / 'data/nflverse/draft' / str(args.season), as_of)
            board = make_board(inputs, history, args.season, as_of)
            board['input_manifest_sha256'] = hashlib.sha256((ROOT / 'data/draft_inputs' / str(args.season) / 'collection.json').read_bytes()).hexdigest()
            board['history_manifest_sha256'] = hashlib.sha256((ROOT / 'data/nflverse/draft' / str(args.season) / 'collection.json').read_bytes()).hexdigest()
            save_atomic(folder / 'board.json', board)
            (folder / 'MILESTONE_2.md').write_text(render(board))
            print(json.dumps({'saved':str(folder),'candidates':len(board['players']), 'critical_unmatched':board['critical_unmatched'], 'readiness':board['readiness']}, indent=2))
        else:
            board = json.loads((folder / 'board.json').read_text())
            if args.command == 'player':
                if not args.player:
                    raise ValueError('--player is required')
                print(json.dumps([p for p in board['players'] if args.player in (p['player_id'],p['fpid']) or args.player.lower() in p['name'].lower()], indent=2))
            elif args.command == 'issues':
                print(json.dumps({'unmatched':board['unmatched'], 'flagged':[{'name':p['name'],'ecr':p['ecr'],'flags':p['flags']} for p in board['players'] if p['flags'] and (args.all or p['ecr'] is not None and p['ecr']<=board['coverage']['draft_range'])]}, indent=2))
            elif args.command == 'summary':
                print(json.dumps({'built':board['generated_at'],'candidates':len(board['players']),'coverage':board['coverage'],
                                  'projection_counts':board['source_projection_counts'],'unmatched':board['unmatched'],
                                  'readiness_at_build':board['readiness']}, indent=2))
            else:
                if not args.output:
                    raise ValueError('--output is required; export never implicitly installs controller candidates')
                result = export_candidates(board, datetime.now(timezone.utc))
                save_atomic(args.output, result)
                print('Saved reviewable candidates: '+str(args.output))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f'Board command failed: {error}\n')


if __name__ == '__main__':
    main()
