"""Independent proposed-lineup validation against provider inputs, without scoring.

The proposed document supplies only scope and slot/player assignments. Never
trust health/ownership/lock flags from an inference or optimization result.
"""
from datetime import timedelta
import re

from player_scoring import index, match_player, position, team, unique, rows, number
from weekly_data import fingerprint, state_key, acquisition_summary
from weekly_model import ELIGIBLE, timestamp, fresh, schedule_games


def proposal_from_report(report, roster_id, rationale=None):
    if report['blockers'] or 'recommendation' not in report:
        raise ValueError('Cannot export a blocked recommendation')
    if rationale is None:
        rationale = ('This lineup fills the available legal starting slots and maximizes the supported '
            'weekly projected scoring components while preserving locked starters. ')
        changes = report.get('changes', [])
        name = lambda sid: report['players'][sid]['name'] if sid else 'an empty slot'
        rationale += ('Compared with the observed lineup, it changes '+ '; '.join(
            name(c['from'])+' to '+name(c['to'])+' at '+c['slot'] for c in changes)+'. ') if changes else 'It retains the observed starting assignments. '
        if 'projected_component_gain' in report:
            rationale += f"The modeled gain is {report['projected_component_gain']:.2f} supported points. "
        flagged = [report['players'][sid]['name'] for sid in report['recommendation']['starters']
                   if sid and report['players'][sid].get('availability_review')]
        if flagged:
            rationale += 'Availability still needs review for '+', '.join(flagged)+'. '
        rationale += 'These forecasts omit some league scoring categories; this proposal requires fresh validation and has not been applied.'
        source = 'deterministic_report_summary'
    else:
        source = 'supplied_free_text'
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError('A nonempty overall lineup rationale is required')
    return {'schema_version': 2, 'rationale': rationale.strip(), 'rationale_source': source,
        'league_id': report['league_id'], 'roster_id': roster_id,
        'season': report['season'], 'week': report['week'], 'created_at': report['generated_at'],
        'origin': {'kind': 'optimizer', 'input_hash': report['input_hash'], 'engine_version': report['engine_version']},
        'assignments': [{'slot_index': i, 'slot': slot, 'player_id': sid}
            for i, (slot, sid) in enumerate(zip(report['slots'], report['recommendation']['starters']))]}


def check_document(proposal):
    if not isinstance(proposal, dict) or type(proposal.get('schema_version')) is not int or proposal['schema_version'] not in (1, 2):
        raise ValueError('Unsupported lineup document schema_version')
    if proposal['schema_version'] == 2 and (not isinstance(proposal.get('rationale'), str) or not proposal['rationale'].strip()):
        raise ValueError('A nonempty overall lineup rationale is required')
    if (not isinstance(proposal.get('league_id'), str) or not proposal['league_id']
            or type(proposal.get('roster_id')) is not int
            or type(proposal.get('season')) is not int
            or type(proposal.get('week')) is not int or not 1 <= proposal['week'] <= 18):
        raise ValueError('Invalid lineup scope')
    timestamp(proposal['created_at'])
    assignments = proposal.get('assignments')
    if not isinstance(assignments, list) or not assignments:
        raise ValueError('Lineup assignments must be a nonempty list')
    for a in assignments:
        if (not isinstance(a, dict) or type(a.get('slot_index')) is not int or a['slot_index'] < 0
                or not isinstance(a.get('slot'), str)
                or not (a.get('player_id') is None or isinstance(a.get('player_id'), str))
                or 'player_id' not in a):
            raise ValueError('Invalid lineup assignment')


UNAVAILABLE = {'out','o','ir','injured reserve','inactive','suspended','sus','pup','physically unable to perform','reserve/pup','reserve/ir','nfi'}
UNCERTAIN = {'q','questionable','d','doubtful','probable'}
CLEAR_LABELS = {'','healthy','active','none'}
CONCERN = re.compile(r'\b(ruled out|will not play|won.t play|surgery|torn|concussion|injury|injured|limited|questionable|doubtful|snap count|game.time decision)\b', re.I)


def validate(proposal, inputs, now, history=None):
    check_document(proposal)
    history = history or {}
    ctx = inputs['final_context']
    issues, details = [], []
    def issue(level, code, message, sid=None, slot=None):
        issues.append({'level': level, 'code': code, 'message': message, 'player_id': sid, 'slot_index': slot})
    if (proposal['league_id'] != ctx['league']['league_id'] or proposal['roster_id'] != ctx['roster']['roster_id']
            or proposal['season'] != ctx['season'] or proposal['week'] != ctx['week']):
        issue('error', 'scope_mismatch', 'Proposal does not belong to the observed league, roster and week')
    if timestamp(proposal['created_at']) > now:
        issue('error', 'future_proposal', 'Proposal creation time is in the future')
    try:
        for meta in ctx['evidence'].values():
            fresh(meta['fetched_at'], now, 300, 'live league state')
        fresh(inputs['sleeper_players']['fetched_at'], now, 900, 'player status')
        fresh(inputs['schedule']['provenance']['metadata_checked_at'], now, 300, 'schedule')
        for name, age in [('fp_external',86400), ('injuries',900), ('news',900)]:
            fresh(inputs[name]['fetched_at'], now, age, name)
    except ValueError as error:
        issue('error', 'stale_evidence', str(error))
    if str(inputs['fp_external']['data'].get('season')) != str(ctx['season']):
        issue('error', 'identity_scope', 'Wrong identity season')
    injury_scope = inputs['injuries']['request']['params']
    if str(injury_scope.get('year')) != str(ctx['season']) or str(injury_scope.get('week')) != str(ctx['week']):
        issue('error', 'injury_scope', 'Wrong injury season/week')
    for key, expected in [('year',ctx['season']), ('week',ctx['week'])]:
        value = inputs['injuries']['data'].get(key)
        if value is not None and str(value) != str(expected):
            issue('error', 'injury_scope', 'Injury response scope differs from current week')
    games, teams = schedule_games(inputs['schedule']['data'], ctx['season'], ctx['week'])
    sl = inputs['sleeper_players']['data']
    if not isinstance(sl, dict) or any(str(p.get('player_id')) != sid for sid,p in sl.items()):
        raise ValueError('Invalid player directory')
    slots = [s for s in ctx['league']['roster_positions'] if s not in ('BN','IR','TAXI')]
    current = [None if x in ('0','',None) else str(x) for x in ctx['matchup']['starters']]
    if len(current) != len(slots) or any(s not in ELIGIBLE for s in slots):
        raise ValueError('Unsupported observed lineup slots')
    assignments = proposal['assignments']
    indices = [a['slot_index'] for a in assignments]
    if sorted(indices) != list(range(len(slots))):
        issue('error', 'slot_coverage', 'Every starting slot must appear exactly once')
    target = {a['slot_index']: a['player_id'] for a in assignments}
    ids = [a['player_id'] for a in assignments if a['player_id']]
    if len(ids) != len(set(ids)):
        issue('error', 'duplicate_player', 'A player is assigned more than once')
    owned = set(ctx['roster']['players'])
    if history and history.get('league_id') != ctx['league']['league_id']:
        raise ValueError('Lock history belongs to another league')
    locked = set(history.get('players', []))
    for sid, kickoff in history.get('kickoffs', {}).items():
        if timestamp(kickoff) <= now:
            locked.add(sid)
    for sid in set(current+ids)-{None}:
        p = sl.get(sid)
        if not p:
            issue('error','unknown_identity','Player absent from current directory',sid)
            continue
        game = games.get(team(p.get('team') or (sid if p.get('position') == 'DEF' else None)))
        if game and (timestamp(game['kickoff']) <= now or game['has_score']):
            locked.add(sid)
    for i, sid in enumerate(current):
        if sid in locked and target.get(i) != sid:
            issue('error','locked_starter_moved','Existing locked starter must remain in the exact slot',sid,i)
    fp_indices = {f: index(sl.values(), f, 'player_id') for f in ('sportradar_id','espn_id','yahoo_id')}
    crosswalk = {}
    for fpid, p in unique(rows(inputs['fp_external']['data'], 'players'), 'player_id').items():
        sid, _ = match_player([p], position(p.get('position_id')), team(p.get('team_id')), sl, fp_indices)
        if sid:
            crosswalk.setdefault(sid, []).append(fpid)
    injuries = unique(rows(inputs['injuries']['data'], 'injuries'), 'player_id')
    news = rows(inputs['news']['data'], 'items')
    for a in assignments:
        i, sid = a['slot_index'], a['player_id']
        if i >= len(slots):
            continue
        if a['slot'] != slots[i]:
            issue('error','slot_label','Slot label differs from league slot order',sid,i)
        if not sid or sid == '0':
            issue('error','empty_slot','Starting slot is empty',sid,i)
            continue
        if sid not in sl:
            continue
        p = sl[sid]
        fixed = sid in locked and current[i] == sid
        if sid not in owned and not fixed:
            issue('error','not_owned','Proposed starter is not owned',sid,i)
        if sid in locked and not fixed:
            issue('error','started_player_added','Cannot add or move a started player into this slot',sid,i)
        if not set(p.get('fantasy_positions') or [p.get('position')]) & ELIGIBLE[slots[i]]:
            issue('error','ineligible_position','Player cannot fill this slot',sid,i)
        club = team(p.get('team') or (sid if p.get('position') == 'DEF' else None))
        game = games.get(club)
        if club not in teams:
            issue('error','unknown_team','Cannot establish a current NFL team',sid,i)
        elif not game:
            issue('warning' if fixed else 'error','no_game','Player has no scheduled game in this week',sid,i)
        fpids = crosswalk.get(sid, [])
        injury = injuries.get(fpids[0], {}) if len(fpids) == 1 else {}
        if len(fpids) != 1 and not fixed:
            issue('review','injury_identity','Cannot uniquely cross-check injury feed identity',sid,i)
        statuses = [str(v or '').strip().lower() for v in (p.get('injury_status'), injury.get('status'))]
        if not fixed:
            if any(s in UNAVAILABLE for s in statuses):
                issue('error','unavailable','A provider reports out, inactive, suspended or reserve status',sid,i)
            elif any(s in UNCERTAIN for s in statuses):
                issue('review','uncertain_availability','Questionable/doubtful availability requires review',sid,i)
            if any(s not in UNAVAILABLE | UNCERTAIN | CLEAR_LABELS for s in statuses):
                issue('review','unknown_status','Unrecognized injury designation; do not assume healthy',sid,i)
            roster_status = str(p.get('status') or '').strip().lower()
            if roster_status in UNAVAILABLE or p.get('active') is False:
                issue('review','roster_status','Player is not clearly active in the directory',sid,i)
            probability = number(injury.get('probability_of_playing'))
            if probability is not None:
                if not 0 <= probability <= 1:
                    issue('error','invalid_probability','Provider probability is outside 0–1',sid,i)
                elif probability < .5:
                    issue('review','low_play_probability','Provider play probability below 0.5; uncalibrated review trigger',sid,i)
            if game and 0 < (timestamp(game['kickoff'])-now).total_seconds() <= 90*60:
                issue('review','pregame_confirmation','Within 90 minutes of kickoff: confirm official active/inactive list and native lock',sid,i)
        relevant_news = [n for n in news if str(n.get('player_id')) in fpids]
        concerning = [n for n in relevant_news if CONCERN.search(' '.join(str(n.get(k) or '') for k in ('title','desc','impact')))]
        if concerning and not fixed:
            issue('review','concerning_news','News contains availability/workload language; inspect dates and context (not a medical diagnosis)',sid,i)
        if fixed and any(s in UNAVAILABLE | UNCERTAIN for s in statuses):
            issue('review','locked_health_flag','Health flag on an already locked starter; cannot repair by substituting',sid,i)
        details.append({'slot_index': i, 'player_id': sid,
            'name': p.get('full_name') or ' '.join(filter(None,[p.get('first_name'),p.get('last_name')])),
            'locked': sid in locked, 'fixed_existing_starter': fixed, 'game': game,
            'sleeper_injury_status': p.get('injury_status'), 'injury': injury,
            'concerning_news': concerning})
    status = 'FAIL' if any(x['level'] == 'error' for x in issues) else 'REVIEW' if any(x['level'] == 'review' for x in issues) else 'PASS'
    deadlines = [now+timedelta(minutes=5)]
    deadlines += [timestamp(meta['fetched_at'])+timedelta(seconds=300) for meta in ctx['evidence'].values()]
    deadlines += [timestamp(inputs[n]['fetched_at'])+timedelta(seconds=900) for n in ('injuries','news','sleeper_players')]
    deadlines += [timestamp(inputs['schedule']['provenance']['metadata_checked_at'])+timedelta(seconds=300)]
    deadlines += [timestamp(d['game']['kickoff']) for d in details if d['game'] and timestamp(d['game']['kickoff']) > now]
    return {'schema_version': 1, 'status': status, 'checks_passed': status == 'PASS',
        'checked_at': now.isoformat(), 'expires_at': min(deadlines).isoformat(),
        'proposal_hash': fingerprint(proposal), 'input_hash': fingerprint(inputs), 'state_key': state_key(ctx),
        'league_id': ctx['league']['league_id'], 'season': ctx['season'], 'week': ctx['week'],
        'issues': issues, 'players': details, 'acquisition': acquisition_summary(inputs),
        'locked_player_ids': sorted(locked),
        'meaning': 'No detected error at check time is not guaranteed participation, medical clearance, optimality, or native unlock confirmation.',
        'source_limits': ['Provider publication times may be unknown; retrieval freshness is not source completeness.',
                          'News keyword screening is conservative and can miss subtle reports or flag old/negated reports.',
                          'Official inactives are not directly integrated. Repeat after new news or state changes.'],
        'applied': False}
