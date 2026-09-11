"""Persistent league lifecycle and inference handoff. Scheduler writes use app tools."""
from fantasy_agent.paths import ROOT as PROJECT_ROOT
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from fantasy_agent.automation.automation_reconcile import read_local
from fantasy_agent.automation.automation_run import wall_budget
from fantasy_agent.automation.automation_store import InvalidContract, utc
from fantasy_agent.core.project_config import load_config, check_user
from fantasy_agent.providers.sleeper import get_sleeper
from fantasy_agent.core.storage import save_atomic, save_new

ROOT = PROJECT_ROOT
INTERVAL = 300


def discover(config):
    """Determine phase from current league, draft, NFL state and owned roster."""
    evidence = {}
    def read(name, endpoint):
        response = get_sleeper(endpoint, with_metadata=True, retries=0)
        evidence[name] = response
        return response['data']
    league = read('league', 'league/' + config['league_id'])
    if not isinstance(league, dict) or league.get('league_id') != config['league_id'] or league.get('sport') != 'nfl':
        raise InvalidContract('Configured league response differs')
    user = read('user', 'user/' + config['user_id'])
    check_user(config, user)
    if user.get('username') != config.get('username'):
        raise InvalidContract('Update the configured username to match the expected account profile')
    rosters = read('rosters', 'league/' + config['league_id'] + '/rosters')
    if not isinstance(rosters, list) or len(rosters) != league.get('total_rosters'):
        raise InvalidContract('Incomplete league rosters')
    owned = [r for r in rosters if r.get('owner_id') == config['user_id']]
    if len(owned) != 1:
        raise InvalidContract('Expected user must own exactly one roster')
    nfl = read('nfl_state', 'state/nfl')
    draft = read('draft', 'draft/' + league['draft_id']) if league.get('draft_id') else None
    if draft and (draft.get('draft_id') != league['draft_id'] or draft.get('league_id') != config['league_id']):
        raise InvalidContract('Draft belongs to another league')
    season = int(league['season'])
    if league.get('status') == 'complete':
        phase = 'season_complete'
    elif draft and draft.get('status') in ('drafting', 'paused'):
        phase = 'live_draft' if draft['status'] == 'drafting' else 'paused_draft'
    elif draft and draft.get('status') == 'pre_draft':
        phase = 'pre_draft'
    elif draft and draft.get('status') == 'complete':
        phase = 'regular_season' if (str(nfl.get('season')) == str(season) and nfl.get('season_type') == 'regular'
                                     and 1 <= int(nfl.get('week') or 0) <= 18) else 'post_draft_waiting'
    else:
        phase = 'unresolved_phase'
    return {'league_id': config['league_id'], 'user_id': config['user_id'], 'roster_id': owned[0]['roster_id'],
            'season': season, 'week': nfl.get('week'), 'phase': phase, 'draft_id': league.get('draft_id'),
            'draft_start_time': draft.get('start_time') if draft else None, 'evidence': evidence,
            'acquisition': {'network_attempts': sum(m.get('network_attempts', 0) for m in evidence.values()),
                            'cache_hits': sum(bool(m.get('cache_hit')) for m in evidence.values())}}


class Manager:
    def __init__(self, root=ROOT, *, clock=time.time, inventory_path=None):
        self.root = Path(root).resolve()
        self.folder = self.root / 'data/manager'
        self.clock = clock
        self.inventory_path = Path(inventory_path or Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'automations')

    @contextmanager
    def lock(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        with (self.folder / 'manager.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def state(self):
        value = json.loads((self.folder / 'state.json').read_text())
        if value.get('schema_version') != 1 or value['project'] != str(self.root):
            raise InvalidContract('Unknown manager state or different project')
        return value

    def save(self, value):
        save_atomic(self.folder / 'state.json', value)

    def prompt(self, value):
        return ((self.root / 'templates/automation/manager-v1.txt').read_text()
                .replace('{project}', str(self.root)) + '\nManager installation: ' + value['installation'])

    def start(self, target):
        with self.lock():
            path = self.folder / 'state.json'
            value = self.state() if path.exists() else {
                'schema_version': 1, 'project': str(self.root), 'installation': uuid.uuid4().hex,
                'created_at': utc(self.clock()), 'next_review_at': 0, 'failures': 0, 'pending': None, 'obligations': {}}
            if value.get('target') and value['target'] != target:
                raise InvalidContract('Resume the existing manager task or explicitly stop it before transferring')
            value.update(enabled=True, target=target)
            self.save(value)
        return self.status()

    def transfer(self, target):
        """Move management to the owner's selected task without removing saved work."""
        if not target or not target.strip():
            raise InvalidContract('Specify the destination task ID')
        with self.lock():
            value = self.state()
            if not value['enabled']:
                raise InvalidContract('Start management before transferring it')
            if value['target'] != target:
                value.setdefault('transfers', []).append({
                    'from': value['target'], 'to': target, 'at': utc(self.clock())})
                value['target'] = target
                self.save(value)
        return self.status()

    def scheduler(self, value):
        inventory = read_local(self.inventory_path, clock=self.clock)
        if not inventory['complete']:
            return {'verified': False, 'reason': 'scheduler_inventory_incomplete', 'tool_arguments': None}
        marker = 'Manager installation: ' + value['installation']
        # read_local supplies hashes. Read candidate prompts to locate only this installation.
        candidates = []
        import tomllib
        for entry in inventory['entries']:
            path = self.inventory_path / entry['id'] / 'automation.toml'
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != entry['file_sha256']:
                return {'verified': False, 'reason': 'scheduler_inventory_changed', 'tool_arguments': None}
            doc = tomllib.loads(raw.decode())
            if marker in doc['prompt']:
                candidates.append(entry)
        desired = {'kind': 'heartbeat', 'name': 'Fantasy Football league manager', 'status': 'ACTIVE',
                   'rrule': 'FREQ=MINUTELY;INTERVAL=5', 'prompt': self.prompt(value), 'targetThreadId': value['target']}
        if len(candidates) > 1:
            return {'verified': False, 'reason': 'duplicate_manager_tasks', 'tool_arguments': None}
        if candidates:
            entry = candidates[0]
            cfg = entry['config']
            good = (cfg['status'] == 'ACTIVE' and cfg['kind'] == 'heartbeat' and cfg['rrule'] == desired['rrule']
                    and cfg['target_thread_id'] == value['target']
                    and cfg['prompt_sha256'] == hashlib.sha256(desired['prompt'].encode()).hexdigest())
            return {'verified': good, 'task_id': entry['id'], 'observed_at': inventory['observed_at'],
                    'reason': 'recurring_wakeup_configured' if good else 'manager_schedule_differs',
                    'tool_arguments': None if good else {'mode': 'update', 'id': entry['id'], **desired}}
        # One heartbeat per task: present replacement as an explicit update, never duplicate it.
        same_thread = [e for e in inventory['entries'] if e['config']['kind'] == 'heartbeat'
                       and e['config']['target_thread_id'] == value['target']]
        args = {'mode': 'create', **desired} if not same_thread else None
        return {'verified': False, 'reason': 'manager_schedule_missing', 'tool_arguments': args,
                'existing_task_ids': [e['id'] for e in same_thread]}

    def status(self):
        value = self.state()
        schedule = self.scheduler(value)
        last = value.get('last_wake_at')
        return {'enabled': value['enabled'], 'schedule': schedule,
                'last_wake_at': utc(last) if last else None,
                'overdue_wakeup': bool(value['enabled'] and last and self.clock() - last > INTERVAL * 3),
                'next_review_at': utc(value['next_review_at']), 'phase': value.get('phase'),
                'pending': value.get('pending'), 'last_result': value.get('last_result'),
                'exception': value.get('exception'), 'missed_wakeups': value.get('missed_wakeups', 0),
                'obligations': value.get('obligations', {}), 'last_decision': value.get('last_decision'),
                'external_monitor': 'out_of_scope_by_owner', 'platform_changes': False}

    def retire_unused(self):
        from fantasy_agent.execution.lineup_execution import Execution
        from fantasy_agent.execution.roster_operations import RosterOperations, tables
        from fantasy_agent.automation.automation_store import instant
        engine = Execution(self.root, clock=self.clock)
        roster = RosterOperations(self.root, clock=self.clock)
        with engine.db() as db:
            tables(db)
            candidates = [('lineup', row['id'], json.loads(row['value'])) for row in db.execute("SELECT id,value FROM actions WHERE state='armed'")]
            candidates += [('roster', row['id'], json.loads(row['value'])) for row in db.execute("SELECT id,value FROM roster_actions WHERE state='armed'")]
        retired = []
        for kind, action_id, action in candidates:
            if self.clock() < instant(action['expires_at']):
                continue
            path = self.folder / 'recovery' / (uuid.uuid4().hex + '.json')
            save_new(path, {'basis': 'automatic_unused_token_recovery', 'action_id': action_id,
                            'reason': 'Saved token expired without dispatch. Require fresh preparation.', 'at': utc(self.clock())})
            method = engine.recover if kind == 'lineup' else roster.retire_unused
            retired.append(method(action_id, path.relative_to(self.root).as_posix()))
        return retired

    def tick(self):
        with self.lock():
            value = self.state()
            if not value['enabled']:
                return {'status': 'stopped', 'delete_task': self.scheduler(value).get('task_id')}
            schedule = self.scheduler(value)
            if not schedule['verified']:
                return {'status': 'repair_schedule_first', 'schedule': schedule}
            now = self.clock()
            if value.get('last_wake_at') and now - value['last_wake_at'] > INTERVAL * 3:
                value['missed_wakeups'] = value.get('missed_wakeups', 0) + 1
            value['last_wake_at'] = now
            # The standing schedule survives process exit, collection failures and pending decisions.
            self.save(value)
            from fantasy_agent.notifications.team_notifications import Notices
            notices = Notices(self.root, clock=self.clock)
            try:
                notification_work = notices.tick()
            except Exception as error:
                notification_work = {'error': type(error).__name__, 'requires_attention': True}
            recovery = self.retire_unused()
            if value.get('pending'):
                return {'status': 'inference_required', 'pending': value['pending'], 'schedule': schedule, 'unused_token_recovery': recovery, 'notifications': notification_work}
            earliest = min([value['next_review_at']] + [o['at'] for o in value.get('obligations', {}).values()])
            if now < earliest:
                return {'status': 'waiting', 'next_review_at': utc(value['next_review_at']), 'schedule': schedule, 'notifications': notification_work}
            run_id = uuid.uuid4().hex
            pending = {'id': run_id, 'status': 'collecting', 'started_at': utc(now),
                       'path': 'data/manager/runs/' + run_id + '.json'}
            value['pending'] = pending
            self.save(value)
            result = {'id': run_id, 'started_at': utc(now), 'platform_changes': False}
            try:
                config = load_config(self.root)
                result['context'] = discover(config)
                result['due_obligations'] = {key: o for key, o in value.get('obligations', {}).items() if o['at'] <= now}
                phase = result['context']['phase']
                value['phase'] = phase
                if phase == 'regular_season':
                    from fantasy_agent.automation.agent_cycle import review
                    result['review'] = review(self.root, result['context']['season'], int(result['context']['week']))
                    if notices.policy() and result['review'].get('snapshot'):
                        notices.plan(Path(result['review']['snapshot']))
                    result['status'] = 'inference_required' if result['review']['status'] != 'blocked' else 'exception'
                elif phase in ('pre_draft', 'live_draft', 'paused_draft'):
                    result.update(status='inference_required', procedure='docs/DRAFT_RUNBOOK.md',
                                  instruction='Prepare or resume the actual discovered draft. Never restart a completed draft or create a mock.')
                elif phase in ('post_draft_waiting', 'season_complete'):
                    result.update(status='inference_required', instruction='Review roster and future obligations without using an unsupported weekly forecast.')
                else:
                    raise InvalidContract('Resolve the league phase from actual platform evidence')
                value['failures'] = 0
            except Exception as error:
                result.update(status='exception', error_type=type(error).__name__,
                              detail=str(error) if isinstance(error, (InvalidContract, ValueError)) else 'Inspect provider evidence and retry through central clients')
                value['failures'] += 1
                result['finished_at'] = utc(self.clock())
            save_new(self.root / pending['path'], result)
            pending['status'] = result['status']
            value['last_result'] = pending['path']
            self.save(value)
            return {'status': result['status'], 'pending': pending, 'result': result, 'schedule': schedule, 'notifications': notification_work}

    def finish(self, decision_path):
        """Save the inference outcome only after verifying future scheduling and evidence."""
        with self.lock():
            value = self.state()
            schedule = self.scheduler(value)
            if not schedule['verified']:
                raise InvalidContract('Repair future scheduling before ending this review')
            decision_path = Path(decision_path).resolve()
            decision_path.relative_to(self.root)
            decision = json.loads(decision_path.read_text())
            pending = value.get('pending')
            if not pending or decision.get('run_id') != pending['id']:
                raise InvalidContract('Decision does not match the pending review')
            if decision.get('outcome') not in ('no_change', 'completed', 'exception', 'retry') or not decision.get('reason'):
                raise InvalidContract('Record a reason and a supported decision outcome')
            due = float(decision['next_review_at'])
            if not self.clock() < due <= self.clock() + 3600:
                raise InvalidContract('Next review must be within one hour')
            if not isinstance(decision.get('evidence'), list) or not decision['evidence']:
                raise InvalidContract('Decision requires saved evidence')
            from fantasy_agent.automation.automation_store import AutomationStore
            references = AutomationStore(self.root)
            proofs = [references.reference(p) for p in decision['evidence']]
            obligations = dict(value.get('obligations', {}))
            for key in decision.get('resolved_obligations', []):
                if key not in obligations:
                    raise InvalidContract('Unknown follow-up obligation')
                del obligations[key]
            for item in decision.get('followups', []):
                if not isinstance(item.get('id'), str) or not item['id'] or not item.get('reason'):
                    raise InvalidContract('Follow-up requires an ID and reason')
                if not self.clock() < float(item['at']):
                    raise InvalidContract('New follow-up must be in the future')
                obligations[item['id']] = item
            future = [o['at'] for o in obligations.values() if o['at'] > self.clock()]
            if future:
                due = min(due, min(future))
            # Interrupted collection can only be retired into a retry or explicit exception.
            if pending['status'] == 'collecting' and decision['outcome'] not in ('retry', 'exception'):
                raise InvalidContract('Interrupted collection cannot count as a completed review')
            if pending['status'] == 'exception' and decision['outcome'] not in ('retry', 'exception'):
                raise InvalidContract('Failed collection cannot count as a completed review')
            if decision['outcome'] in ('no_change', 'completed'):
                from fantasy_agent.execution.lineup_execution import Execution
                from fantasy_agent.execution.roster_operations import RosterOperations
                if any(e['state'] != 'completed' for e in Execution(self.root).status()['executions']):
                    raise InvalidContract('Unresolved lineup execution cannot count as a completed review')
                if any(a['state'] in ('armed', 'outcome_unknown') for a in RosterOperations(self.root).roster_status()['actions']):
                    raise InvalidContract('Unresolved roster action cannot count as a completed review')
            receipt = {**decision, 'recorded_at': utc(self.clock()), 'proofs': proofs, 'schedule': schedule}
            save_new(self.folder / 'decisions' / (pending['id'] + '.json'), receipt)
            value.update(pending=None, next_review_at=due, last_decision='data/manager/decisions/' + pending['id'] + '.json',
                         obligations=obligations, exception=decision['reason'] if decision['outcome'] == 'exception' else None)
            self.save(value)
            if decision['outcome'] == 'exception':
                from fantasy_agent.automation.automation_run import alert
                incident = 'manager-' + hashlib.sha256(decision['reason'].encode()).hexdigest()[:24]
                notice = alert(self.root, incident, decision['reason'])
                save_new(self.folder / 'notifications' / (pending['id'] + '.json'), notice)
            return self.status()

    def obligation(self, path):
        """Keep a deadline until an inference decision explicitly resolves it."""
        item = json.loads(Path(path).read_text())
        if not item.get('id') or not item.get('reason') or not self.clock() < float(item['at']):
            raise InvalidContract('Follow-up requires an ID, reason and future time')
        with self.lock():
            value = self.state()
            value.setdefault('obligations', {})[item['id']] = item
            value['next_review_at'] = min(value['next_review_at'], item['at'])
            self.save(value)
        return self.status()

    def adopt_schedule(self, task_id):
        """Prepare an explicit replacement of this task's heartbeat, preserving its instructions."""
        value = self.state()
        inventory = read_local(self.inventory_path, clock=self.clock)
        entries = [e for e in inventory['entries'] if e['id'] == task_id and e['config']['kind'] == 'heartbeat'
                   and e['config']['target_thread_id'] == value['target']]
        if not inventory['complete'] or len(entries) != 1:
            raise InvalidContract('Select the exact existing heartbeat for this task')
        import tomllib
        prior = tomllib.loads((self.inventory_path / task_id / 'automation.toml').read_text())
        save_atomic(self.folder / 'prior-schedules' / (task_id + '.json'), prior)
        return {'mode': 'update', 'id': task_id, 'kind': 'heartbeat', 'name': 'Fantasy Football league manager',
                'status': 'ACTIVE', 'rrule': 'FREQ=MINUTELY;INTERVAL=5', 'prompt': self.prompt(value),
                'targetThreadId': value['target'], 'notificationPolicy': prior.get('notification_policy')}

    def stop(self):
        with self.lock():
            value = self.state()
            value['enabled'] = False
            self.save(value)
        return {'status': 'stopped', 'delete_task': self.scheduler(value).get('task_id'),
                'pending_preserved': value.get('pending')}

    def decide(self, outcome, reason, after, evidence):
        pending = self.state().get('pending')
        if not pending:
            raise InvalidContract('No pending review to decide')
        path = self.folder / 'decision-inputs' / (uuid.uuid4().hex + '.json')
        save_new(path, {'run_id': pending['id'], 'outcome': outcome, 'reason': reason,
                        'next_review_at': self.clock() + after, 'evidence': evidence})
        return self.finish(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    start = sub.add_parser('start')
    start.add_argument('--target', required=True)
    transfer = sub.add_parser('transfer', help='Move management after an explicit owner request')
    transfer.add_argument('--target', required=True)
    sub.add_parser('status')
    sub.add_parser('tick')
    sub.add_parser('stop')
    finish = sub.add_parser('finish')
    finish.add_argument('--decision', type=Path, required=True)
    obligation = sub.add_parser('obligation')
    obligation.add_argument('--file', type=Path, required=True)
    adopt = sub.add_parser('adopt-schedule')
    adopt.add_argument('--id', required=True)
    decide = sub.add_parser('decide')
    decide.add_argument('--outcome', choices=('no_change', 'completed', 'retry', 'exception'), required=True)
    decide.add_argument('--reason', required=True)
    decide.add_argument('--after', type=int, required=True)
    decide.add_argument('--evidence', action='append', required=True)
    args = parser.parse_args()
    manager = Manager(args.root)
    try:
        with wall_budget(300):
            if args.command == 'start':
                result = manager.start(args.target)
            elif args.command == 'transfer':
                result = manager.transfer(args.target)
            elif args.command == 'finish':
                result = manager.finish(args.decision)
            elif args.command == 'obligation':
                result = manager.obligation(args.file)
            elif args.command == 'adopt-schedule':
                result = manager.adopt_schedule(args.id)
            elif args.command == 'decide':
                result = manager.decide(args.outcome, args.reason, args.after, args.evidence)
            else:
                result = getattr(manager, args.command)()
        print(json.dumps(result, indent=2))
        return 0
    except Exception as error:
        print(json.dumps({'status': 'exception', 'error_type': type(error).__name__,
                          'detail': str(error) if isinstance(error, (InvalidContract, ValueError)) else 'Inspect local records',
                          'continuity_instruction': 'Keep the recurring task active. Repair or retry on its next wakeup.'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
