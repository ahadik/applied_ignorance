"""Collect and normalize deadline evidence through shared providers. No platform writes."""
from datetime import datetime, timezone
from pathlib import Path
import json
import time
import uuid
from zoneinfo import ZoneInfo

from automation_store import AutomationStore, InvalidContract, digest, instant, text, utc
from sleeper import get_sleeper
from nflverse import get_nflverse
from player_scoring import team
from storage import save_new


def incorporate_rules(observation, rules, settings):
    """Attach confirmed labels without asserting complete waiver or review coverage."""
    if (rules.get('schema_version') != 1 or rules.get('league_id') != observation['league_id']
            or rules.get('season') != observation['season'] or not rules.get('evidence_refs')
            or not isinstance(rules.get('matched_settings'), dict) or not rules['matched_settings']):
        raise InvalidContract('Verified rule scope or evidence is invalid')
    datetime.strptime(rules['confirmed_on'], '%Y-%m-%d')
    if rules['confirmed_on'] > observation['observed_at'][:10]:
        raise InvalidContract('Rule confirmation is later than the observation')
    if any(settings.get(key) != value for key, value in rules['matched_settings'].items()):
        raise InvalidContract('Saved league settings differ from confirmed waiver rules')
    result = json.loads(json.dumps(observation))
    result['known_waiver_rules'] = rules
    result['rule_settings_checked_at'] = observation['sources']['league']['fetched_at']
    result['issues'] = ['waiver_exceptions_and_review_coverage_unverified'
                        if x == 'waiver_and_review_timing_unverified' else x for x in result['issues']]
    result['complete'] = not result['issues']
    return result


def attach_saved_rules(observation, rules_path, *, root, settings):
    store = AutomationStore(root)
    rule_ref = store.reference(rules_path)
    rules = json.loads((Path(root) / rules_path).read_text())
    evidence = [store.reference(path) for path in rules['evidence_refs']]
    result = incorporate_rules(observation, rules, settings)
    refs = {r['path']: r for r in observation.get('source_checksums', [])}
    refs.update({r['path']: r for r in [rule_ref, *evidence]})
    result['source_checksums'] = [refs[path] for path in sorted(refs)]
    result['source_refs'] = sorted(refs)
    return result


def incorporate_saved(observations_path, rules_path, *, root):
    """Create a new observation from saved evidence. Do not refresh timestamps."""
    root = Path(root).resolve()
    store = AutomationStore(root)
    obs_ref = store.reference(observations_path)
    observation = json.loads((root / observations_path).read_text())
    for ref in observation['source_checksums']:
        if store.reference(ref['path']) != ref:
            raise InvalidContract('Saved observation source changed')
    league_paths = [p for p in observation['source_refs'] if Path(p).name == 'league.json']
    if len(league_paths) != 1:
        raise InvalidContract('Saved league evidence is missing or ambiguous')
    settings = json.loads((root / league_paths[0]).read_text())['data']['settings']
    result = attach_saved_rules(observation, rules_path, root=root, settings=settings)
    result['source_checksums'].append(obs_ref)
    result['source_checksums'].sort(key=lambda r: r['path'])
    result['source_refs'] = [r['path'] for r in result['source_checksums']]
    path = root / 'data/automation/observations' / digest(result) / 'observations.json'
    try:
        save_new(path, result)
    except FileExistsError:
        if json.loads(path.read_text()) != result:
            raise InvalidContract('Existing observation differs') from None
    return {'saved': str(path), 'confirmed_on': result['known_waiver_rules']['confirmed_on'],
            'issues': result['issues'], 'timestamps_refreshed': False, 'platform_changes': False}


def local_instants(naive, zone):
    """Return real UTC instants for a wall time, including both folds."""
    values = set()
    for fold in (0, 1):
        aware = naive.replace(tzinfo=zone, fold=fold)
        if aware.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == naive:
            values.add(aware.timestamp())
    return sorted(values)


def normalize(raw, *, season, week, league_id, username, source_refs, observed_at, timing=None):
    """Normalize a saved collection. Missing evidence produces explicit blockers."""
    issues, events = [], []
    def issue(code):
        issues.append(code)
    league = raw.get('league', {}).get('data', {})
    state = raw.get('state', {}).get('data', {})
    user = raw.get('user', {}).get('data', {})
    rosters = raw.get('rosters', {}).get('data', [])
    players = raw.get('players', {}).get('data', {})
    settings = league.get('settings', {}) if isinstance(league, dict) else {}
    valid_scope = (isinstance(league, dict) and league.get('league_id') == league_id
                   and str(league.get('season')) == str(season) and league.get('sport') == 'nfl'
                   and isinstance(state, dict) and str(state.get('season')) == str(season)
                   and state.get('season_type') == 'regular' and state.get('week') == week)
    if not valid_scope:
        issue('league_or_current_week_unverified')
    ours = [r for r in rosters if isinstance(r, dict) and r.get('owner_id') == user.get('user_id')] if isinstance(rosters, list) and isinstance(user, dict) else []
    roster = ours[0] if len(ours) == 1 and user.get('user_id') else {}
    owned = roster.get('players', [])
    if (not isinstance(owned, list) or not owned or any(not isinstance(p, str) for p in owned)
            or len(set(owned)) != len(owned) or not roster.get('roster_id')
            or not isinstance(rosters, list) or len(rosters) != league.get('total_rosters')):
        issue('ownership_unverified')
        owned = []
    if 'final_league' not in raw or 'final_rosters' not in raw:
        issue('final_ownership_read_missing')
    elif raw['final_league']['data'] != league or raw['final_rosters']['data'] != rosters:
        issue('league_or_rosters_changed_during_collection')
    if not isinstance(settings, dict) or 'max_subs' not in settings or settings['max_subs'] != 0:
        issue('substitution_rules_unsupported')
    if not isinstance(players, dict):
        players = {}
        issue('player_directory_missing')
    relevant = {}
    for sid in sorted(owned):
        player = players.get(sid, {})
        club = team(player.get('team')) if isinstance(player, dict) else None
        if not club:
            issue('owned_player_team_unknown:' + sid)
        else:
            relevant.setdefault(club, []).append(sid)
    schedule = raw.get('schedule', {})
    records = schedule.get('data', [])
    regular = [r for r in records if isinstance(r, dict) and r.get('game_type') == 'REG'
               and str(r.get('season')) == str(season)] if isinstance(records, list) else []
    counts, seen, team_weeks = {}, set(), set()
    for row in regular:
        event_id = str(row.get('game_id', ''))
        try:
            game_week = int(row['week'])
            clubs = [team(row['home_team']), team(row['away_team'])]
            if not event_id or event_id in seen or not 1 <= game_week <= 18 or not all(clubs) or clubs[0] == clubs[1]:
                raise ValueError()
            seen.add(event_id)
            for club in clubs:
                if (club, game_week) in team_weeks:
                    raise ValueError()
                team_weeks.add((club, game_week))
                counts[club] = counts.get(club, 0) + 1
        except (KeyError, TypeError, ValueError):
            issue('invalid_or_duplicate_fixture')
            continue
        ids = sorted({sid for club in clubs for sid in relevant.get(club, [])})
        if not ids or game_week < week:
            continue
        deadline = None
        try:
            wall = datetime.fromisoformat(row['gameday'] + 'T' + row['gametime'])
            if wall.tzinfo is not None:
                raise ValueError()
            instants = local_instants(wall, ZoneInfo('America/New_York'))
            if len(instants) != 1:
                raise ValueError()
            deadline = utc(instants[0])
        except (KeyError, TypeError, ValueError):
            issue('fixture_time_unknown:' + event_id)
        events.append({'event_id': event_id, 'kind': 'game', 'week': game_week,
                       'player_ids': ids, 'deadline_at': deadline,
                       'locked': row.get('home_score') not in (None, '') or row.get('away_score') not in (None, ''),
                       'source': 'schedule', 'published_at': schedule.get('provenance', {}).get('asset_updated_at')})
    if len(regular) != 272 or len(counts) != 32 or any(n != 17 for n in counts.values()):
        issue('season_fixture_coverage_incomplete')
    if any(club not in counts for club in relevant):
        issue('owned_team_not_in_schedule')
    waiver_coverage = None
    if timing is None:
        issue('waiver_and_review_timing_unverified')
    else:
        # Explicit observations avoid inferring undocumented waiver bit masks or processing times.
        try:
            if (timing['schema_version'] != 1 or timing['league_id'] != league_id
                    or timing['season'] != season or timing['week'] != week
                    or timing['settings_hash'] != digest(settings)
                    or timing['complete'] is not True or not timing['evidence_refs']):
                raise ValueError()
            instant(timing['observed_at'])
            if instant(timing['coverage_start']) >= instant(timing['coverage_end']):
                raise ValueError()
            waiver_coverage = {k: timing[k] for k in ('observed_at', 'coverage_start', 'coverage_end', 'evidence_refs')}
            for event in timing['events']:
                if event['kind'] not in ('waiver', 'review') or not week <= event['week'] <= 18:
                    raise ValueError()
                text(event['event_id'], 'event ID')
                if not instant(timing['coverage_start']) <= instant(event['deadline_at']) <= instant(timing['coverage_end']):
                    raise ValueError()
                ids = event['player_ids']
                if not isinstance(ids, list) or any(p not in owned for p in ids):
                    raise ValueError()
                events.append({**{k: event[k] for k in ('event_id', 'kind', 'week', 'deadline_at', 'player_ids')},
                               'source': 'timing', 'published_at': None, 'locked': False})
        except (KeyError, TypeError, ValueError):
            waiver_coverage = None
            issue('waiver_and_review_timing_invalid')
    sources = {}
    for name, value in raw.items():
        meta = value.get('provenance', value)
        sources[name] = {k: v for k, v in meta.items() if k != 'data'}
    return {'schema_version': 1, 'league_id': league_id, 'season': season, 'week': week,
            'roster_id': roster.get('roster_id'), 'observed_at': observed_at,
            'settings_hash': digest(settings), 'owned_player_ids': sorted(owned),
            'source_refs': sorted(source_refs), 'sources': sources, 'timing_coverage': waiver_coverage,
            'complete': not issues, 'issues': sorted(set(issues)),
            'events': sorted(events, key=lambda e: (e['kind'], e['event_id']))}


def collect(config, season, week, *, root, timing_path=None, clock=time.time):
    if type(season) is not int or not 2000 <= season <= 2200 or type(week) is not int or not 1 <= week <= 18:
        raise InvalidContract('Use an explicit regular-season year and week')
    root = Path(root).resolve()
    folder = root / 'data/automation/observations' / uuid.uuid4().hex
    raw, attempts, refs, failures = {}, {}, [], []
    timing = None
    if timing_path:
        store = AutomationStore(root)
        ref = store.reference(timing_path)
        timing = json.loads((root / ref['path']).read_text())
        refs.append(ref['path'])
        for path in timing.get('evidence_refs', []):
            refs.append(store.reference(path)['path'])
    def read(name, provider, call):
        try:
            value = call()
            meta = value.get('provenance', value)
            raw[name] = value
            attempts[name] = {'provider': provider, **{k: meta.get(k) for k in ('network_attempts', 'cache_hit')}}
            path = folder / (name + '.json')
            save_new(path, value)
            refs.append(path.relative_to(root).as_posix())
        except Exception as error:
            attempts[name] = {'provider': provider, 'network_attempts': getattr(error, 'network_attempts', None),
                              'cache_hit': False, 'error': type(error).__name__}
            failures.append('collection_failed:' + name)
            return False
        return True
    league_id, username = config['league_id'], config['username']
    text(league_id, 'league ID')
    text(username, 'username')
    reads = [('league', f'league/{league_id}'), ('state', 'state/nfl'), ('user', f'user/{username}'),
             ('rosters', f'league/{league_id}/rosters'), ('players', 'players/nfl')]
    for name, path in reads:
        if not read(name, 'sleeper', lambda path=path: get_sleeper(path, with_metadata=True, retries=0)):
            break
        if name == 'state':
            league, state = raw['league']['data'], raw['state']['data']
            if (not isinstance(league, dict) or not isinstance(state, dict)
                    or league.get('league_id') != league_id or str(league.get('season')) != str(season)
                    or league.get('sport') != 'nfl' or str(state.get('season')) != str(season)
                    or state.get('week') != week or state.get('season_type') != 'regular'):
                failures.append('league_or_current_week_unverified')
                break
    if not failures:
        read('schedule', 'nflverse', lambda: get_nflverse('schedules', season))
    if not failures:
        for name, path in [('final_league', f'league/{league_id}'), ('final_rosters', f'league/{league_id}/rosters')]:
            if not read(name, 'sleeper', lambda path=path: get_sleeper(path, with_metadata=True, retries=0)):
                break
    try:
        observation = normalize(raw, season=season, week=week, league_id=league_id, username=username,
                                source_refs=refs, observed_at=utc(clock()), timing=timing)
    except (ValueError, TypeError, KeyError, AttributeError):
        observation = {'schema_version': 1, 'league_id': league_id, 'season': season, 'week': week,
                       'roster_id': None, 'observed_at': utc(clock()), 'settings_hash': None,
                       'owned_player_ids': [], 'source_refs': sorted(refs), 'sources': {},
                       'timing_coverage': None, 'complete': False, 'issues': ['invalid_provider_contract'], 'events': []}
    observation['issues'] = sorted(set(observation['issues'] + failures))
    observation['complete'] = not observation['issues']
    observation['acquisition'] = attempts
    observation['source_checksums'] = [AutomationStore(root).reference(path) for path in sorted(set(refs))]
    rules_path = f'data/automation/rules/{league_id}.json'
    if (root / rules_path).is_file() and 'league' in raw:
        try:
            observation = attach_saved_rules(observation, rules_path, root=root, settings=raw['league']['data']['settings'])
        except (KeyError, TypeError, ValueError, OSError):
            observation['issues'].append('confirmed_waiver_rules_need_reverification')
            observation['complete'] = False
    save_new(folder / 'observations.json', observation)
    return {'saved': str(folder / 'observations.json'), 'complete': observation['complete'],
            'issues': observation['issues'], 'acquisition': attempts, 'platform_changes': False}
