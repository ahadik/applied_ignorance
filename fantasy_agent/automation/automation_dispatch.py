"""Bounded recurring dispatch through supported app wakeups and M1 workflow claims."""
from fantasy_agent.paths import ROOT as PROJECT_ROOT
import argparse
import fcntl
import json
from pathlib import Path
import time
import uuid

from fantasy_agent.automation.automation_reconcile import SchedulerStore, read_local, marker
from fantasy_agent.automation.automation_store import AutomationStore, AutomationError, InvalidContract, StaleRevision, digest, instant, utc
from fantasy_agent.automation.automation_run import Workflow, register_workflow, validate_recipe
from fantasy_agent.core.storage import save_new, save_atomic


class Dispatcher:
    def __init__(self, root, *, clock=time.time):
        self.root = Path(root).resolve()
        self.clock = clock
        self.folder = self.root / 'data/automation/dispatcher'
        self.store = AutomationStore(self.root, clock=clock)

    def config(self):
        value = json.loads((self.folder / 'config.json').read_text())
        if value['revision'] != digest(value['contract']):
            raise InvalidContract('Dispatcher contract checksum differs')
        if value['contract']['project'] != str(self.root):
            raise InvalidContract('Dispatcher belongs to another project')
        return value

    def archive_expired(self):
        """Retain the expired contract after verified scheduler removal."""
        with (self.folder / 'tick.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            value = self.config()
            if self.clock() < instant(value['contract']['expires_at']):
                raise InvalidContract('Dispatcher contract has not expired')
            scheduler = SchedulerStore(self.root, clock=self.clock)
            with scheduler.db() as db:
                config = scheduler.config(db)
                pending = db.execute("SELECT COUNT(*) FROM pending WHERE state IN ('pending','reported','unknown')").fetchone()[0]
            inventory = read_local(config['inventory_scope'], clock=self.clock)
            if not inventory['complete'] or pending:
                raise InvalidContract('Scheduler inventory or recovery is incomplete')
            if any(e['owner'] and e['owner']['installation'] == config['installation']
                   and e['owner']['key'] == 'm4-dispatcher' for e in inventory['entries']):
                raise InvalidContract('Remove the expired dispatcher through the supported scheduler control first')
            counts = self.store.status()['runs']
            if counts.get('running', 0) or counts.get('outcome_unknown', 0):
                raise InvalidContract('Resolve workflow outcomes before replacing the dispatcher')
            archive = self.folder / 'retired' / (value['revision'] + '.json')
            if archive.exists():
                if json.loads(archive.read_text()) != value:
                    raise InvalidContract('Retired dispatcher evidence differs')
            else:
                save_new(archive, value)
            (self.folder / 'config.json').unlink()
        return {'archived': str(archive), 'next_step': 'prepare a fresh bounded contract', 'scheduler_changes': False}

    def prepare(self, target, expires):
        """Persist the intended task before the operator calls supported scheduler controls."""
        if (self.folder / 'config.json').exists():
            value = self.config()
            return {'existing': True, 'revision': value['revision'], 'instruction': 'Inspect and bind the existing task. Do not repeat creation.'}
        if not self.clock() + 600 < instant(expires) <= self.clock() + 7 * 86400:
            raise InvalidContract('Dispatcher lifetime must exceed ten minutes and be at most seven days')
        scheduler = SchedulerStore(self.root, clock=self.clock)
        installation = scheduler.init()['installation']
        contract = {'schema_version': 1, 'project': str(self.root), 'target_thread_id': target,
                    'expires_at': expires, 'interval_seconds': 60, 'lateness_allowance_seconds': 120,
                    'max_checks_per_wake': 1, 'installation': installation}
        revision = digest(contract)
        prompt = (f'Continue the Fantasy Football M4 dispatcher in {self.root}. '
                  'First check whether data/automation/m4/live/setup.json exists without live/acceptance.json. '
                  'If that acceptance test is active, read docs/M4_LIVE_ACCEPTANCE.md and run its cycle procedure instead of a separate tick. '
                  f'Otherwise run python3 -m fantasy_agent automation_dispatch tick --revision {revision}. '
                  'This command reads local schedules and executes at most one registered observe/propose workflow. '
                  'Use the central provider permissions if a registered workflow requires network access. '
                  'Do not rerun an uncertain workflow. Save actual scheduler-trigger evidence separately. '
                  'If the result says retire, delete this automation through the supported control. '
                  'Stay quiet while results are unchanged or non-actionable. Notify only on completion, failure or required user action.\n'
                  + marker(installation, 'm4-dispatcher', 'anchor', revision))
        value = {'contract': contract, 'revision': revision, 'prompt': prompt,
                 'name': 'Fantasy Football bounded dispatcher', 'rrule': 'FREQ=MINUTELY;INTERVAL=1'}
        save_new(self.folder / 'config.json', value)
        return {'existing': False, 'revision': revision, 'tool_arguments': {
            'mode': 'create', 'kind': 'heartbeat', 'name': value['name'], 'prompt': prompt,
            'rrule': value['rrule'], 'status': 'ACTIVE', 'targetThreadId': target}}

    def inventory(self):
        value = self.config()
        scheduler = SchedulerStore(self.root, clock=self.clock)
        with scheduler.db() as db:
            config = scheduler.config(db)
            pending = db.execute("SELECT COUNT(*) FROM pending WHERE state IN ('pending','reported','unknown')").fetchone()[0]
        inventory = read_local(config['inventory_scope'], clock=self.clock)
        if not inventory['complete'] or pending:
            raise InvalidContract('Dispatcher inventory is incomplete or a scheduler operation is unresolved')
        owned = [e for e in inventory['entries'] if e['owner'] and e['owner']['installation'] == config['installation']
                 and e['owner']['key'] == 'm4-dispatcher']
        if len(owned) != 1:
            raise InvalidContract('Exactly one dispatcher task is required')
        entry = owned[0]
        if entry['owner']['revision'] != value['revision'] or entry['owner']['role'] != 'anchor':
            raise InvalidContract('Dispatcher task revision differs')
        expected = {'kind': 'heartbeat', 'status': 'ACTIVE', 'rrule': value['rrule'],
                    'name': value['name'], 'prompt_sha256': __import__('hashlib').sha256(value['prompt'].encode()).hexdigest(),
                    'target_thread_id': value['contract']['target_thread_id']}
        if any(entry['config'].get(k) != v for k, v in expected.items()):
            raise InvalidContract('Dispatcher task configuration differs')
        return {'task_id': entry['id'], 'fingerprint': entry['fingerprint'], 'observed_at': inventory['observed_at'],
                'complete_local_inventory': True, 'entries': len(inventory['entries'])}

    def bind(self):
        evidence = self.inventory()
        save_new(self.folder / 'bindings' / (uuid.uuid4().hex + '.json'), evidence)
        save_atomic(self.folder / 'binding.json', evidence)
        return evidence

    def publish(self, checks, horizon, *, plan=None, ignore_run_id=None):
        """Publish exact registered workflow identities, never free-form executable commands."""
        config = self.config()
        if not self.clock() < instant(horizon) <= instant(config['contract']['expires_at']):
            raise InvalidContract('Coverage horizon exceeds dispatcher lifetime')
        seen = set()
        for item in checks:
            if item['check_id'] in seen:
                raise InvalidContract('Duplicate dispatch check')
            seen.add(item['check_id'])
            context = self.store.context(item['check_id'], item['revision'])
            proof = self.store.reference(item['recipe'])
            if proof not in context['check']['sources']:
                raise InvalidContract('Dispatch recipe is not bound to the check')
        value = {'schema_version': 1, 'dispatcher_revision': config['revision'], 'created_at': utc(self.clock()),
                 'horizon_end': horizon, 'checks': checks, 'plan': plan}
        value['publication_id'] = digest(value)
        path = self.folder / 'publications' / (value['publication_id'] + '.json')
        if not path.exists():
            save_new(path, value)
        save_atomic(self.folder / 'latest.json', {'path': path.relative_to(self.root).as_posix()})
        return self.coverage(ignore_run_id=ignore_run_id)

    def publish_plan(self, plan, plan_path, recipe, run):
        """Register executable deadline recipes and the next daily planner from an M2 plan."""
        if digest({k: v for k, v in plan.items() if k != 'plan_id'}) != plan['plan_id']:
            raise InvalidContract('Invalid planner checksum')
        base_path = self.store.reference(recipe['dispatcher_check_recipe'])['path']
        base = json.loads((self.root / base_path).read_text())
        operation, scope = validate_recipe(base)
        if scope != plan['scope']:
            raise InvalidContract('Dispatcher check recipe belongs to another scope')
        checks = []
        folder = self.folder / 'recipes' / plan['plan_id']
        for desired in plan['desired_checks']:
            spec = desired['spec']
            if spec['operation'] != operation:
                raise InvalidContract('Desired check has no matching executable recipe')
            if (spec['season'], spec['week']) != (base['season'], base['week']):
                raise InvalidContract('Future week requires a matching executable recipe and proposal')
            path = folder / (desired['check_id'] + '.json')
            if not path.exists():
                save_new(path, {**base, 'source_plan': plan_path})
            relative = path.relative_to(self.root).as_posix()
            with self.store.transaction() as db:
                row = db.execute('SELECT revision FROM current_checks WHERE check_id=?', (desired['check_id'],)).fetchone()
            result = register_workflow(self.root, relative, desired['check_id'], spec['run_at'],
                                       spec['latest_start_at'], spec['expires_at'], row[0] if row else None)
            checks.append({**{k: result[k] for k in ('check_id', 'revision')}, 'recipe': relative})
        next_at = instant(plan['next_daily_at'])
        next_id = 'daily-' + digest([plan['scope'], plan['next_daily_at']])[:32]
        next_recipe = {**recipe, 'previous_plan': plan_path}
        path = folder / (next_id + '.json')
        if not path.exists():
            save_new(path, next_recipe)
        relative = path.relative_to(self.root).as_posix()
        with self.store.transaction() as db:
            row = db.execute('SELECT revision FROM current_checks WHERE check_id=?', (next_id,)).fetchone()
        result = register_workflow(self.root, relative, next_id, utc(next_at), utc(next_at + 600), utc(next_at + 900), row[0] if row else None)
        checks.append({**{k: result[k] for k in ('check_id', 'revision')}, 'recipe': relative})
        coverage = self.publish(checks, plan['horizon']['end'], plan=plan_path, ignore_run_id=run['run_id'])
        if plan['issues']:
            coverage['configuration_coverage_verified'] = False
            coverage['issues'] += ['plan_issue:' + issue for issue in plan['issues']]
        return coverage

    def publication(self):
        index = json.loads((self.folder / 'latest.json').read_text())
        proof = self.store.reference(index['path'])
        value = json.loads((self.root / proof['path']).read_text())
        if value['publication_id'] != digest({k: v for k, v in value.items() if k != 'publication_id'}):
            raise InvalidContract('Dispatch publication checksum differs')
        if value['dispatcher_revision'] != self.config()['revision']:
            raise StaleRevision('Dispatch publication was superseded')
        return value

    def coverage(self, *, ignore_run_id=None):
        config, publication = self.config(), self.publication()
        inventory = self.inventory()
        now = self.clock()
        issues, details = [], []
        if publication.get('plan'):
            self.store.reference(publication['plan'])
            plan = json.loads((self.root / publication['plan']).read_text())
            if plan.get('plan_id') != digest({k: v for k, v in plan.items() if k != 'plan_id'}):
                raise InvalidContract('Published plan checksum differs')
            issues += ['plan_issue:' + issue for issue in plan['issues']]
        if not now < instant(publication['horizon_end']) <= instant(config['contract']['expires_at']):
            issues.append('dispatcher_horizon_expired')
        with self.store.transaction() as db:
            policy = self.store.policy(db)
        if policy['mode'] == 'disabled':
            issues.append('automation_disabled')
        # Conservative serial service estimate, including one wake interval and allowed dispatch delay.
        delay = config['contract']['interval_seconds'] + config['contract']['lateness_allowance_seconds']
        available = now
        pending = []
        for item in publication['checks']:
            context = self.store.context(item['check_id'], item['revision'])
            payload = context['check']
            spec = payload['spec']
            for ref in payload['sources']:
                if self.store.reference(ref['path']) != ref:
                    raise StaleRevision('Published workflow source changed')
            self.store.gate(policy, spec['operation'])
            with self.store.transaction() as db:
                complete = db.execute("SELECT 1 FROM runs WHERE check_id=? AND revision=? AND state='completed'",
                                      (item['check_id'], item['revision'])).fetchone()
            if complete:
                details.append({**item, 'state': 'completed'})
            elif any(r['run_id'] != ignore_run_id for r in context['unresolved']):
                issues.append('unresolved_scope:' + spec['scope'])
                details.append({**item, 'state': 'unresolved'})
            else:
                pending.append((instant(spec['latest_start_at']), item, spec))
        for _, item, spec in sorted(pending, key=lambda x: (x[0], x[1]['check_id'])):
            start = max(available, instant(spec['run_at'])) + delay
            finish = start + policy['lease_seconds']
            covered = start <= instant(spec['latest_start_at']) and finish <= instant(spec['expires_at'])
            if not covered:
                issues.append('window_uncovered:' + item['check_id'])
            details.append({**item, 'state': 'pending', 'configuration_covered': covered,
                            'estimated_start_bound': utc(start), 'estimated_finish_bound': utc(finish)})
            available = finish
        return {'schema_version': 1, 'publication_id': publication['publication_id'], 'observed_at': utc(now),
                'horizon_end': publication['horizon_end'], 'inventory': inventory, 'checks': details,
                'configuration_coverage_verified': not issues, 'issues': sorted(set(issues)),
                'timing_assumption': 'At most 120 seconds of dispatch delay after each 60-second wake interval. This is not an uptime or punctuality guarantee.'}

    def tick(self, revision):
        config = self.config()
        if revision != config['revision']:
            raise StaleRevision('Dispatcher prompt was superseded')
        if self.clock() >= instant(config['contract']['expires_at']):
            return {'retire': True, 'reason': 'dispatcher_lifetime_expired'}
        self.folder.mkdir(parents=True, exist_ok=True)
        with (self.folder / 'tick.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {'status': 'another_dispatcher_active'}
            self.inventory()
            publication = self.publication()
            if self.clock() >= instant(publication['horizon_end']):
                return {'status': 'expired_publication', 'retire': False}
            # Validate all identities before any workflow can start.
            choices = []
            for item in publication['checks']:
                context = self.store.context(item['check_id'], item['revision'])
                spec = context['check']['spec']
                for ref in context['check']['sources']:
                    if self.store.reference(ref['path']) != ref:
                        raise StaleRevision('Published workflow source changed')
                with self.store.transaction() as db:
                    self.store.gate(self.store.policy(db), spec['operation'])
                    done = db.execute("SELECT 1 FROM runs WHERE check_id=? AND revision=? AND state='completed'",
                                      (item['check_id'], item['revision'])).fetchone()
                if done:
                    continue
                if context['unresolved']:
                    return {'status': 'recovery_required', 'check_id': item['check_id']}
                if instant(spec['run_at']) <= self.clock() <= instant(spec['latest_start_at']):
                    choices.append((instant(spec['latest_start_at']), item))
                elif self.clock() > instant(spec['latest_start_at']):
                    return {'status': 'missed_window', 'check_id': item['check_id']}
            receipt = {'schema_version': 1, 'observed_at': utc(self.clock()), 'publication_id': publication['publication_id'],
                       'trigger_basis': 'caller_invocation_only', 'status': 'idle'}
            if choices:
                item = sorted(choices, key=lambda x: (x[0], x[1]['check_id']))[0][1]
                receipt['workflow'] = Workflow(self.root, clock=self.clock).execute(item['check_id'], item['revision'], item['recipe'], 'scheduled')
                receipt['status'] = receipt['workflow']['status']
            save_new(self.folder / 'ticks' / (uuid.uuid4().hex + '.json'), receipt)
            return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=PROJECT_ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--target', required=True)
    prepare.add_argument('--expires', required=True)
    sub.add_parser('bind')
    sub.add_parser('coverage')
    sub.add_parser('archive-expired')
    publish = sub.add_parser('publish')
    publish.add_argument('--file', type=Path, required=True)
    tick = sub.add_parser('tick')
    tick.add_argument('--revision', required=True)
    args = parser.parse_args(argv)
    dispatcher = Dispatcher(args.root)
    try:
        if args.command == 'prepare':
            result = dispatcher.prepare(args.target, args.expires)
        elif args.command == 'publish':
            value = json.loads(args.file.read_text())
            result = dispatcher.publish(value['checks'], value['horizon_end'], plan=value.get('plan'))
        elif args.command == 'tick':
            result = dispatcher.tick(args.revision)
        elif args.command == 'archive-expired':
            result = dispatcher.archive_expired()
        else:
            result = getattr(dispatcher, args.command)()
        print(json.dumps(result, indent=2))
        return 0
    except (AutomationError, OSError, ValueError) as error:
        print(json.dumps({'status': 'blocked', 'error_type': type(error).__name__,
                          'detail': str(error) if isinstance(error, AutomationError) else 'Inspect local evidence'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
