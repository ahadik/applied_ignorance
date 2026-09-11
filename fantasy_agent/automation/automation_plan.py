"""Pure, deterministic deadline planning and immutable plan persistence."""
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fantasy_agent.automation.automation_deadlines import local_instants
from fantasy_agent.automation.automation_store import AutomationStore, InvalidContract, UnknownSchema, digest, instant, text, utc, validate_check
from fantasy_agent.core.storage import save_new

DEFAULT_PLAN_POLICY = {
    'schema_version': 1, 'timezone': 'America/New_York', 'daily_time': '09:00',
    'horizon_hours': 48, 'recovery_overlap_hours': 24, 'lateness_minutes': 10,
    'execution_buffer_minutes': 15, 'task_cap': 10, 'reserved_slots': 2,
    'retry_minutes': 15, 'source_max_age_seconds': 300, 'timing_max_age_seconds': 86400,
    'offsets_minutes': {'game': [90, 30], 'waiver': [1440, 60], 'review': [30]},
    'allowed_operations': ['inspect_sleeper', 'validate_lineup']
}
OPERATIONS = {'game': 'validate_lineup', 'waiver': 'inspect_sleeper', 'review': 'validate_lineup'}


def validate_policy(value):
    if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != 1:
        raise UnknownSchema('Unsupported planning policy')
    if set(value) != set(DEFAULT_PLAN_POLICY):
        raise InvalidContract('Unexpected planning policy fields')
    for key, low, high in [('horizon_hours', 1, 168), ('recovery_overlap_hours', 1, 72),
                           ('lateness_minutes', 1, 60), ('execution_buffer_minutes', 1, 120),
                           ('task_cap', 2, 100), ('reserved_slots', 2, 100), ('retry_minutes', 1, 60),
                           ('source_max_age_seconds', 1, 300), ('timing_max_age_seconds', 1, 86400)]:
        if type(value[key]) is not int or not low <= value[key] <= high:
            raise InvalidContract('Invalid policy field: ' + key)
    if value['reserved_slots'] > value['task_cap']:
        raise InvalidContract('Reserved slots exceed task cap')
    try:
        ZoneInfo(value['timezone'])
        if len(value['daily_time']) != 5 or datetime.strptime(value['daily_time'], '%H:%M').strftime('%H:%M') != value['daily_time']:
            raise ValueError()
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        raise InvalidContract('Invalid daily time or time zone') from None
    offsets = value['offsets_minutes']
    if not isinstance(offsets, dict) or set(offsets) != set(OPERATIONS):
        raise InvalidContract('Offsets must cover game, waiver and review deadlines')
    for items in offsets.values():
        if (not isinstance(items, list) or not items or len(items) > 8
                or any(type(x) is not int or not value['execution_buffer_minutes'] < x <= 10080 for x in items)
                or len(set(items)) != len(items)):
            raise InvalidContract('Invalid offsets')
    allowed = value['allowed_operations']
    if (not isinstance(allowed, list) or not allowed
            or any(not isinstance(x, str) or x not in set(OPERATIONS.values()) for x in allowed)
            or len(set(allowed)) != len(allowed)):
        raise InvalidContract('Unsupported planning operation')
    result = json.loads(json.dumps(value))
    result['allowed_operations'] = sorted(allowed)
    result['offsets_minutes'] = {k: sorted(v, reverse=True) for k, v in sorted(offsets.items())}
    return result


def next_daily(now, policy):
    zone = ZoneInfo(policy['timezone'])
    date = datetime.fromtimestamp(now, zone).date()
    hour, minute = map(int, policy['daily_time'].split(':'))
    for day in range(3):
        wall = datetime.combine(date + timedelta(days=day), datetime.min.time()).replace(hour=hour, minute=minute)
        # A missing wall time advances to the first real minute. A repeated time uses its first occurrence.
        for _ in range(181):
            choices = local_instants(wall, zone)
            if choices:
                if choices[0] > now:
                    return choices[0]
                break
            wall += timedelta(minutes=1)
    raise InvalidContract('Cannot resolve next daily time')


def validate_observation(obs):
    if not isinstance(obs, dict) or type(obs.get('schema_version')) is not int or obs['schema_version'] != 1:
        raise UnknownSchema('Unsupported deadline observation')
    text(obs.get('league_id'), 'league ID')
    if type(obs.get('season')) is not int or not 2000 <= obs['season'] <= 2200 or type(obs.get('week')) is not int or not 1 <= obs['week'] <= 18:
        raise InvalidContract('Invalid observation season or week')
    instant(obs.get('observed_at'))
    if type(obs.get('complete')) is not bool or not isinstance(obs.get('issues'), list) or not isinstance(obs.get('sources'), dict):
        raise InvalidContract('Missing observation completeness evidence')
    if (any(not isinstance(x, str) for x in obs['issues'])
            or any(not isinstance(x, dict) for x in obs['sources'].values())):
        raise InvalidContract('Invalid source or issue records')
    owned = obs.get('owned_player_ids')
    if (not isinstance(owned, list) or any(not isinstance(x, str) for x in owned)
            or len(set(owned)) != len(owned)
            or (obs.get('roster_id') is not None and (type(obs['roster_id']) is not int or obs['roster_id'] < 1))):
        raise InvalidContract('Invalid roster identity')
    if not isinstance(obs.get('events'), list) or len(obs['events']) > 2000:
        raise InvalidContract('Invalid deadline list')
    seen = set()
    for event in obs['events']:
        if not isinstance(event, dict) or not isinstance(event.get('kind'), str) or event['kind'] not in OPERATIONS:
            raise InvalidContract('Unknown deadline kind')
        text(event.get('event_id'), 'event ID')
        key = (event['kind'], event['event_id'])
        if key in seen:
            raise InvalidContract('Duplicate deadline identity')
        seen.add(key)
        if type(event.get('week')) is not int or not obs['week'] <= event['week'] <= 18:
            raise InvalidContract('Invalid event week')
        if event.get('deadline_at') is not None:
            instant(event['deadline_at'])
        if (not isinstance(event.get('player_ids'), list) or type(event.get('locked')) is not bool
                or any(not isinstance(p, str) or p not in obs.get('owned_player_ids', []) for p in event['player_ids'])):
            raise InvalidContract('Invalid event ownership')
        if event['kind'] == 'game' and not event['player_ids']:
            raise InvalidContract('Game deadline requires owned players')
    return obs


def build(obs, policy, as_of, *, references, previous=None):
    obs = validate_observation(obs)
    policy = validate_policy(policy)
    now = instant(as_of)
    as_of = utc(now)
    next_anchor = next_daily(now, policy)
    end = max(now + policy['horizon_hours'] * 3600, next_anchor + policy['recovery_overlap_hours'] * 3600)
    scope = f"{obs['league_id']}:{obs['season']}:{obs.get('roster_id')}"
    if previous is not None and not obs.get('roster_id'):
        if previous.get('league_id') == obs['league_id'] and previous.get('season') == obs['season']:
            scope = previous['scope']
    refs = sorted(references, key=lambda r: r['path'])
    if not refs or len(refs) > 20 or len({r['path'] for r in refs}) != len(refs):
        raise InvalidContract('Use 1 to 20 unique input references')
    issues = list(obs['issues'])
    if not obs['complete']:
        issues.append('incomplete_observation')
    if not obs.get('roster_id') or not obs.get('owned_player_ids'):
        issues.append('ownership_unverified')
    def freshness(stamp, age, label):
        try:
            if not 0 <= now - instant(stamp) <= age:
                raise ValueError()
        except ValueError:
            issues.append('stale_or_missing:' + label)
    freshness(obs['observed_at'], policy['source_max_age_seconds'], 'observation')
    for name in ('league', 'state', 'user', 'rosters', 'players', 'schedule', 'final_league', 'final_rosters'):
        meta = obs['sources'].get(name, {})
        freshness(meta.get('metadata_checked_at') if name == 'schedule' else meta.get('fetched_at'),
                  policy['source_max_age_seconds'], name)
        for field in ('asset_updated_at', 'source_updated_at'):
            if meta.get(field) is not None:
                try:
                    if instant(meta[field]) > now:
                        raise ValueError()
                except ValueError:
                    issues.append('invalid_publication_time:' + name)
    coverage = obs.get('timing_coverage')
    if not coverage:
        issues.append('waiver_exceptions_and_review_coverage_missing' if obs.get('known_waiver_rules')
                      else 'waiver_and_review_coverage_missing')
    else:
        freshness(coverage.get('observed_at'), policy['timing_max_age_seconds'], 'timing')
        try:
            if instant(coverage['coverage_start']) > now or instant(coverage['coverage_end']) < end:
                issues.append('waiver_and_review_coverage_short')
        except (KeyError, ValueError):
            issues.append('waiver_and_review_coverage_invalid')
    locks = {}
    if previous is not None:
        if previous.get('schema_version') != 1 or previous.get('scope') != scope or instant(previous['as_of']) > now:
            raise InvalidContract('Previous plan scope or time mismatch')
        if digest({k: v for k, v in previous.items() if k != 'plan_id'}) != previous.get('plan_id'):
            raise InvalidContract('Previous plan checksum mismatch')
        locks.update(previous.get('lock_history', {}))
    obligations = []
    policy_hash, input_hash = digest(policy), digest(obs)
    for event in sorted(obs['events'], key=lambda e: (e['week'], e['kind'], e['event_id'])):
        event_key = digest([obs['league_id'], obs['season'], event['week'], event['kind'], event['event_id']])
        if event['deadline_at'] is None:
            issues.append('unknown_deadline:' + event_key)
            continue
        deadline = instant(event['deadline_at'])
        old = locks.get(event_key)
        locked = event['locked'] or (old is not None and instant(old) <= now)
        if event['kind'] == 'game':
            conservative = min(instant(old), deadline) if old and instant(old) <= now else deadline
            locks[event_key] = utc(min(now, conservative) if event['locked'] else conservative)
        for offset in policy['offsets_minutes'][event['kind']]:
            due = deadline - offset * 60
            expiry = deadline - policy['execution_buffer_minutes'] * 60
            latest = min(due + policy['lateness_minutes'] * 60, expiry - 1)
            if due > end:
                continue
            identity = [obs['league_id'], obs['season'], event['week'], event['event_id'], event['kind'], offset]
            check_id = 'm2-' + digest(identity)
            run_at = max(due, now) if now <= latest else due
            spec = validate_check({'schema_version': 1, 'check_id': check_id, 'scope': scope,
                                   'operation': OPERATIONS[event['kind']], 'season': obs['season'], 'week': event['week'],
                                   'run_at': utc(run_at), 'latest_start_at': utc(latest), 'expires_at': utc(expiry),
                                   'source_refs': [r['path'] for r in refs]})
            disposition = 'locked' if locked else 'missed' if now > latest else 'due' if due < now else 'planned'
            if spec['operation'] not in policy['allowed_operations']:
                disposition = 'operation_blocked'
            obligations.append({'check_id': check_id, 'event_id': event['event_id'], 'event_key': event_key,
                                'kind': event['kind'], 'offset_minutes': offset, 'deadline_at': utc(deadline),
                                'player_ids': sorted(event['player_ids']), 'nominal_run_at': utc(due),
                                'disposition': disposition, 'spec': spec,
                                'revision': digest({'spec': spec, 'sources': refs}),
                                'policy_hash': policy_hash, 'input_hash': input_hash})
    issues = sorted(set(issues))
    obligations.sort(key=lambda x: (x['spec']['latest_start_at'], x['nominal_run_at'], x['check_id']))
    eligible = [o for o in obligations if o['disposition'] in ('planned', 'due')]
    slots = policy['task_cap'] - policy['reserved_slots']
    selected = []
    for item in eligible:
        if issues:
            item['disposition'] = 'input_blocked'
        elif len(selected) >= slots:
            item['disposition'] = 'capacity_blocked'
        else:
            selected.append(item)
    desired = []
    for item in selected:
        spec = item['spec']
        desired.append({**item, 'template_version': 1,
                        'prompt': ('Read docs/M2_AUTOMATION.md. This is a record-only check. '
                                   'Run python3 -m fantasy_agent automation context --check-id ' + item['check_id'] +
                                   ' --revision ' + item['revision'] + '. '
                                   'Stop if the check is missing, stale, expired or blocked. '
                                   'No platform write is authorized by this task.'),
                        'display_time': datetime.fromtimestamp(instant(spec['run_at']), ZoneInfo(policy['timezone'])).isoformat()})
    current_ids = {o['check_id'] for o in obligations}
    preserved = []
    if previous:
        for old in previous.get('obligations', []) + previous.get('preserved_obligations', []):
            if old['check_id'] not in current_ids:
                preserved.append(old)
                current_ids.add(old['check_id'])
    if preserved:
        issues = sorted(set(issues + ['prior_obligations_require_review']))
    # A missing observation never authorizes deleting a previously desired scheduler task.
    gaps = [{'check_id': o['check_id'], 'reason': o['disposition'], 'start': o['spec']['run_at'],
             'end': o['spec']['latest_start_at']} for o in obligations if o['disposition'] not in ('planned', 'due', 'locked')]
    record = {'schema_version': 1, 'league_id': obs['league_id'], 'season': obs['season'],
              'scope': scope, 'as_of': as_of, 'horizon': {'start': as_of, 'end': utc(end)},
              'next_daily_at': utc(next_anchor), 'policy_hash': policy_hash, 'input_hash': input_hash,
              'source_references': refs, 'source_timestamps': obs['sources'], 'issues': issues,
              'known_waiver_rules': obs.get('known_waiver_rules'),
              'rule_settings_checked_at': obs.get('rule_settings_checked_at'),
              'obligations': obligations, 'desired_checks': desired, 'preserved_obligations': preserved,
              'lock_history': dict(sorted(locks.items())),
              'capacity': {'task_cap': policy['task_cap'], 'reserved_slots': policy['reserved_slots'],
                           'available': slots, 'required': len(eligible), 'selected': len(selected),
                           'uncovered': len(eligible) - len(selected), 'inventory_verified': False},
              'coverage': {'basis': 'desired_only', 'scheduler_verified': False,
                           'intervals': [{'check_id': x['check_id'], 'start': x['spec']['run_at'],
                                          'end': x['spec']['latest_start_at']} for x in desired], 'gaps': gaps,
                           'unknown_intervals': [{'start': as_of, 'end': utc(end)}] if issues or preserved else []},
              'retry_obligation': {'run_at': utc(now + policy['retry_minutes'] * 60),
                                   'expires_at': utc(now + policy['retry_minutes'] * 120),
                                   'max_attempts': 1, 'operation': 'collect_deadlines', 'scheduled': False} if issues else None,
              'deletion_authorized': False, 'external_execution': False}
    record['plan_id'] = digest(record)
    return record


def plan_files(observations, policy_path, as_of, *, root, previous_path=None, output_dir=None):
    root = Path(root).resolve()
    store = AutomationStore(root)
    def relative(path):
        path = Path(path).resolve()
        if not path.is_relative_to(root):
            raise InvalidContract('Plan inputs must be saved inside the project')
        return path.relative_to(root).as_posix()
    obs_path, policy_ref = relative(observations), relative(policy_path)
    obs_bytes, policy_bytes = (root / obs_path).read_bytes(), (root / policy_ref).read_bytes()
    obs = json.loads(obs_bytes)
    policy = json.loads(policy_bytes)
    paths = sorted(set([obs_path, policy_ref] + obs.get('source_refs', [])))
    refs = [store.reference(path) for path in paths]
    hashes = {ref['path']: ref['sha256'] for ref in refs}
    if (hashes[obs_path] != hashlib.sha256(obs_bytes).hexdigest()
            or hashes[policy_ref] != hashlib.sha256(policy_bytes).hexdigest()):
        raise InvalidContract('Plan inputs changed during loading')
    actual_sources = [store.reference(path) for path in sorted(set(obs.get('source_refs', [])))]
    if actual_sources != obs.get('source_checksums'):
        raise InvalidContract('Observation source checksums differ or are missing')
    previous = json.loads(Path(previous_path).read_text()) if previous_path else None
    record = build(obs, policy, as_of, references=refs, previous=previous)
    output = Path(output_dir) if output_dir else root / 'data/automation/plans'
    path = output / (record['plan_id'] + '.json')
    try:
        save_new(path, record)
    except FileExistsError:
        if json.loads(path.read_text()) != record:
            raise InvalidContract('Existing immutable plan differs') from None
    return {'saved': str(path), 'plan_id': record['plan_id'], 'issues': record['issues'],
            'desired_checks': len(record['desired_checks']), 'capacity': record['capacity'],
            'scheduler_verified': False, 'external_execution': False}
