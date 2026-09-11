"""Pure weekly validation, lock-aware exact assignment, and contingency analysis."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from functools import lru_cache

from fantasy_agent.core.player_scoring import (POSITIONS, index, unique, rows, position, team,
                            match_player, scoring, number)
from fantasy_agent.weekly.weekly_data import fingerprint, state_key, acquisition_summary

ELIGIBLE = {p: {p} for p in POSITIONS} | {
    'FLEX': {'RB','WR','TE'}, 'SUPER_FLEX': {'QB','RB','WR','TE'},
    'REC_FLEX': {'WR','TE'}, 'WRRB_FLEX': {'WR','RB'}}


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone required')
    return result


def fresh(value, now, age, label):
    delta = (now-timestamp(value)).total_seconds()
    if delta < 0 or delta > age:
        raise ValueError('Stale/future '+label+'; run live collection')


def schedule_games(records, season, week):
    """Validate whole regular season so absent weekly team means a real bye.

    gametime in nfldata is US Eastern. No actual-start endpoint is claimed.
    Uncertain/postponed kickoff is fail-closed rather than assumed unlocked.
    """
    regular = [r for r in records if r['game_type'] == 'REG' and str(r['season']) == str(season)]
    if len(regular) != 272 or len({r['game_id'] for r in regular}) != 272:
        raise ValueError('Incomplete/duplicate 32-team, 17-game regular-season schedule')
    counts, games = {}, {}
    for r in regular:
        for club in (team(r['home_team']), team(r['away_team'])):
            counts[club] = counts.get(club, 0)+1
        if int(r['week']) != week:
            continue
        try:
            kickoff = datetime.fromisoformat(r['gameday']+'T'+r['gametime']).replace(
                tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)
        except ValueError:
            raise ValueError('Unknown/postponed kickoff needs verified schedule: '+r['game_id']) from None
        for club, opponent in ((team(r['home_team']), team(r['away_team'])),
                               (team(r['away_team']), team(r['home_team']))):
            if club in games:
                raise ValueError('Multiple games for a team in the selected week')
            games[club] = {'game_id': r['game_id'], 'kickoff': kickoff.isoformat(),
                           'opponent': opponent, 'home': club == team(r['home_team']),
                           'has_score': number(r.get('home_score')) is not None or number(r.get('away_score')) is not None}
    if len(counts) != 32 or any(n != 17 for n in counts.values()) or not games:
        raise ValueError('Incomplete season/team schedule coverage')
    return games, set(counts)


def optimize(players, slots, current, *, excluded=()):
    """Exact DP over all legal assignments. Fixed slots earn no variable utility.

    Tie order: points, latest kickoff in flexible slots, fewest changes, IDs.
    Empty slots are allowed only when no productive legal assignment is better;
    filling slots is first priority so a negative projection is not auto-benched.
    """
    if len(slots) != len(current) or any(s not in ELIGIBLE for s in slots):
        raise ValueError('Unsupported or mismatched starting slots')
    ids = sorted(players)
    bit = {sid: 1 << i for i, sid in enumerate(ids)}
    fixed = {i: sid for i, sid in enumerate(current) if sid and players[sid]['locked']}
    initial = 0
    for sid in fixed.values():
        initial |= bit[sid]
    @lru_cache(None)
    def solve(i, used):
        if i == len(slots):
            return (0, 0.0, 0.0, 0), ()
        if i in fixed:
            score, rest = solve(i+1, used)
            return score, (fixed[i],)+rest
        choices = [None]+[sid for sid in ids if not used & bit[sid]
            and sid not in excluded and players[sid]['owned'] and not players[sid]['locked']
            and not players[sid]['unavailable'] and players[sid]['points'] is not None
            and set(players[sid]['positions']) & ELIGIBLE[slots[i]]]
        best = None
        for sid in choices:
            score, rest = solve(i+1, used | (bit[sid] if sid else 0))
            p = players[sid] if sid else None
            bonus = timestamp(p['game']['kickoff']).timestamp() if p and len(ELIGIBLE[slots[i]]) > 1 else 0
            value = (score[0]+bool(sid), score[1]+(p['points'] if p else 0),
                     score[2]+bonus, score[3]-(sid != current[i]))
            candidate = value, (sid,)+rest
            if best is None or value > best[0] or value == best[0] and tuple(x or '' for x in candidate[1]) < tuple(x or '' for x in best[1]):
                best = candidate
        return best
    value, lineup = solve(0, initial)
    return {'starters': list(lineup), 'adjustable_projected_points': round(value[1], 4),
            'filled_slots': sum(bool(x) for x in lineup), 'fixed_slots': fixed}


def build(inputs, now, previous_locks=(), previous_kickoffs=None, *, analysis_pool=False):
    ctx = inputs['final_context']
    season, week = ctx['season'], ctx['week']
    for meta in ctx['evidence'].values():
        fresh(meta['fetched_at'], now, 300, 'league state')
    fresh(inputs['schedule']['provenance']['metadata_checked_at'], now, 300, 'schedule check')
    fresh(inputs['sleeper_players']['fetched_at'], now, 900, 'player status')
    for name, age in [('fp_external', 86400), ('injuries', 900), ('news', 900)]:
        fresh(inputs[name]['fetched_at'], now, age, name)
    for key in ('year', 'week'):
        expected = season if key == 'year' else week
        if str(inputs['injuries']['request']['params'].get(key)) != str(expected):
            raise ValueError('Wrong injury scope')
    if str(inputs['fp_external']['data'].get('season')) != str(season):
        raise ValueError('Wrong player identity season')
    games, teams = schedule_games(inputs['schedule']['data'], season, week)
    sl = inputs['sleeper_players']['data']
    if not isinstance(sl, dict) or any(str(p.get('player_id')) != sid for sid, p in sl.items()):
        raise ValueError('Sleeper player IDs invalid')
    owned = ctx['roster']['players']
    current = [None if x in ('0', '', None) else str(x) for x in ctx['matchup']['starters']]
    if len(set(owned)) != len(owned) or len({x for x in current if x}) != len([x for x in current if x]):
        raise ValueError('Duplicate owned/starting players')
    slots = [x for x in ctx['league']['roster_positions'] if x not in ('BN','IR','TAXI')]
    if any(x not in sl for x in set(owned) | {x for x in current if x}):
        raise ValueError('Owned/starting player identity missing')
    fp = unique(rows(inputs['fp_external']['data'], 'players'), 'player_id')
    injuries = unique(rows(inputs['injuries']['data'], 'injuries'), 'player_id')
    for injury in injuries.values():
        probability = number(injury.get('probability_of_playing'))
        if probability is not None and not 0 <= probability <= 1:
            raise ValueError('Invalid injury probability')
    indices = {f: index(sl.values(), f, 'player_id') for f in ('sportradar_id','espn_id','yahoo_id')}
    projected, quarantine, sources = {}, [], []
    for pos in ('QB','RB','WR','TE','K','DST'):
        entry = inputs['projections_'+pos]
        fresh(entry['fetched_at'], now, 21600, pos+' projection')
        data, request = entry['data'], entry['request']['params']
        if (str(data.get('season')) != str(season) or str(data.get('week')) != str(week)
                or data.get('positions') != pos or str(request.get('week')) != str(week)
                or request.get('position') != pos or request.get('ros')):
            raise ValueError('Wrong weekly projection scope: '+pos)
        updated = data.get('last_updated_ts')
        if updated is not None:
            updated = datetime.fromtimestamp(number(updated), timezone.utc).isoformat()
            fresh(updated, now, 86400, pos+' provider publication')
        sources.append({'position': pos, 'fetched_at': entry['fetched_at'], 'source_updated_at': updated})
        for fpid, row in unique(rows(data, 'players'), 'fpid').items():
            if position(row.get('position_id')) != position(pos) or not isinstance(row.get('stats'), dict):
                raise ValueError('Invalid projection row')
            for value in row['stats'].values():
                number(value)
            sid, basis = match_player([row, fp.get(fpid, {})], position(pos), team(row.get('team_id')), sl, indices)
            if not sid:
                quarantine.append({'fpid': fpid, 'name': row.get('name'), 'reason': basis})
                continue
            if sid in projected:
                raise ValueError('Duplicate projected identity')
            if team(sl[sid].get('team') or sid) != team(row.get('team_id')):
                quarantine.append({'fpid': fpid, 'name': row.get('name'), 'reason': ['team_conflict']})
                continue
            projected[sid] = {'row': row, 'fpid': fpid, 'identity_basis': basis}
    players, blockers, warnings = {}, [], []
    lock_set = set(previous_locks)
    # Once an earlier observed kickoff has passed, a later schedule edit cannot
    # automatically unlock the player. Native Sleeper review is needed for an
    # exceptional postponement; normal re-runs are conservative.
    for sid, kickoff in (previous_kickoffs or {}).items():
        if timestamp(kickoff) <= now:
            lock_set.add(sid)
    pool = set(projected) if analysis_pool else set()
    for sid in sorted(set(owned) | {x for x in current if x} | pool):
        p, projection = sl[sid], projected.get(sid)
        club = team(p.get('team') or (sid if p.get('position') == 'DEF' else None))
        game = games.get(club)
        if game and (timestamp(game['kickoff']) <= now or game['has_score']):
            lock_set.add(sid)
        locked = sid in lock_set
        if club not in teams:
            blockers.append('Unknown current NFL team for '+sid)
        if locked and game and timestamp(game['kickoff']) > now:
            warnings.append('Prior kickoff passed but schedule moved later; conservatively locked: '+sid)
        if sid in current and sid not in owned and not locked:
            blockers.append('Off-roster starter is not confirmed locked: '+sid)
        fpid = projection['fpid'] if projection else None
        injury = injuries.get(fpid, {})
        statuses = [str(x or '').lower() for x in (p.get('injury_status'), injury.get('status'))]
        unavailable = game is None or any(s in ('out','o','ir','injured reserve','suspended','pup','inactive') for s in statuses)
        review = any(s in ('questionable','q','doubtful','d') for s in statuses)
        # A two-way player's primary roster position can differ from the
        # verified projection position (for example DB with WR eligibility).
        scored = scoring(projection['row']['stats'], position(projection['row']['position_id']), ctx['league']['scoring_settings']) if projection else None
        if not locked and not unavailable and (scored is None or not scored['core_fields_complete']):
            blockers.append('Missing usable weekly projection for '+sid)
        points = scored['supported_points'] if scored and scored['core_fields_complete'] else None
        if review and not locked:
            warnings.append('Availability/workload review required: '+sid)
        if scored and not scored['exact_league_total']:
            warnings.append('Partial league scoring for '+sid+': '+', '.join(scored['uncovered_rules']))
        players[sid] = {'id': sid, 'name': p.get('full_name') or ' '.join(filter(None, [p.get('first_name'),p.get('last_name')])) or sid,
            'positions': [position(x) for x in (p.get('fantasy_positions') or [p.get('position')])],
            'team': club, 'owned': sid in owned, 'game': game, 'locked': locked,
            'unavailable': unavailable, 'availability_review': review, 'injury': injury,
            'sleeper_injury_status': p.get('injury_status'), 'points': points, 'scoring': scored,
            'news': [n for n in rows(inputs['news']['data'], 'items') if str(n.get('player_id')) == fpid]}
    if len(slots) != len(current):
        raise ValueError('Starter slot count mismatch')
    for i, sid in enumerate(current):
        if sid and not set(players[sid]['positions']) & ELIGIBLE.get(slots[i], set()):
            blockers.append('Current starter eligibility mismatch: '+sid)
    result = {'schema_version': 1, 'engine_version': 1, 'season': season, 'week': week,
        'generated_at': now.isoformat(), 'league_id': ctx['league']['league_id'], 'state_key': state_key(ctx),
        'input_hash': fingerprint(inputs), 'slots': slots, 'current_starters': current,
        'players': players, 'locked_player_ids': sorted(lock_set), 'blockers': blockers,
        'warnings': sorted(set(warnings)), 'projection_sources': sources, 'quarantine': quarantine,
        'objective': 'Maximize supported weekly projected components, subject to filling legal slots and fixed locks',
        'applied': False, 'uncertainty': 'Not calibrated; forecasts may omit scoring categories and already include injury/matchup effects.'}
    result['acquisition'] = acquisition_summary(inputs)
    if analysis_pool:
        result.update(status='analysis_only', operational_export=False)
        return result
    if blockers:
        result['status'] = 'blocked'
        return result
    best = optimize(players, slots, current)
    result.update(status='review_required', recommendation=best)
    result['changes'] = [{'slot_index': i, 'slot': slots[i], 'from': old, 'to': new}
        for i, (old, new) in enumerate(zip(current, best['starters'])) if old != new]
    result['alternatives'] = []
    for sid in best['starters']:
        if not sid or players[sid]['locked']:
            continue
        alternate = optimize(players, slots, current, excluded=(sid,))
        result['alternatives'].append({'without': sid, 'reason': 'If unavailable / bench alternative',
            'projected_component_loss': round(best['adjustable_projected_points']-alternate['adjustable_projected_points'], 4),
            'decision_deadline': min([players[x]['game']['kickoff']
                for i, x in enumerate(alternate['starters']) if x and x != best['starters'][i] and not players[x]['locked']]
                + [players[sid]['game']['kickoff']]),
            **alternate})
    current_variable = [players[x] for x in current if x and not players[x]['locked']]
    if all(p['points'] is not None or p['unavailable'] for p in current_variable):
        subtotal = sum(0 if p['unavailable'] else p['points'] for p in current_variable)
        result['current_adjustable_projected_points'] = round(subtotal, 4)
        result['projected_component_gain'] = round(best['adjustable_projected_points']-subtotal, 4)
    if best['filled_slots'] < len(slots):
        result['warnings'].append('Roster cannot fill every slot; acquisition may be required')
    future = sorted({p['game']['kickoff'] for p in players.values() if p['game'] and not p['locked']})
    result['next_player_lock'] = future[0] if future else None
    result['weekly_matchup_points_observed'] = ctx['matchup'].get('points')
    return result
