"""Bounded observe/propose workflows. No browser or Sleeper account writes."""
from fantasy_agent.core.project_config import load_config
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import signal
import time
import uuid

from fantasy_agent.automation.automation_store import AutomationStore, AutomationError, InvalidContract, digest, instant, text, utc
from fantasy_agent.core.storage import save_new, save_atomic
from fantasy_agent.providers.pushover import get_pushover


class WorkflowTimeout(RuntimeError):
    pass


@contextmanager
def wall_budget(seconds):
    """Enforce one process budget on the supported Mac main-thread runtime."""
    if seconds <= 0:
        raise WorkflowTimeout('Workflow time budget expired')
    previous = signal.getsignal(signal.SIGALRM)
    def timeout(signum, frame):
        raise WorkflowTimeout('Workflow time budget expired')
    signal.signal(signal.SIGALRM, timeout)
    timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *timer)
        signal.signal(signal.SIGALRM, previous)


def validate_recipe(recipe):
    if recipe.get('schema_version') != 1 or recipe.get('kind') not in ('daily', 'deadline', 'inspection'):
        raise InvalidContract('Unsupported workflow recipe')
    text(recipe.get('league_id'), 'league ID')
    if type(recipe.get('season')) is not int or type(recipe.get('week')) is not int or not 1 <= recipe['week'] <= 18:
        raise InvalidContract('Invalid workflow season or week')
    if type(recipe.get('roster_id')) is not int or recipe['roster_id'] < 1:
        raise InvalidContract('Invalid workflow roster')
    operation = {'daily': 'collect_inputs', 'inspection': 'inspect_sleeper'}.get(recipe['kind'], recipe.get('operation'))
    if recipe['kind'] == 'deadline' and operation not in ('validate_lineup', 'propose_lineup', 'integrated_review'):
        raise InvalidContract('Unsupported deadline operation')
    if type(recipe.get('notify_on_failure')) is not bool:
        raise InvalidContract('Notification policy must be explicit')
    if recipe['kind'] == 'daily':
        text(recipe.get('planning_policy'), 'planning policy path')
        text(recipe.get('target_thread_id'), 'target task ID')
        if recipe.get('decision_operation', 'propose_lineup') not in ('propose_lineup', 'integrated_review'):
            raise InvalidContract('Unsupported daily decision operation')
    if recipe['kind'] == 'deadline' and operation == 'validate_lineup':
        text(recipe.get('proposal'), 'proposal path')
    return operation, f"{recipe['league_id']}:{recipe['season']}:{recipe['roster_id']}"


def register_workflow(root, recipe_path, check_id, run_at, latest_start, expires, previous=None):
    root = Path(root).resolve()
    store = AutomationStore(root)
    proof = store.reference(recipe_path)
    recipe = json.loads((root / recipe_path).read_text())
    operation, scope = validate_recipe(recipe)
    refs = [proof['path'], store.reference('config.json')['path']]
    for name in ('planning_policy', 'previous_plan', 'timing', 'proposal', 'dispatcher_check_recipe', 'source_plan'):
        if recipe.get(name):
            refs.append(store.reference(recipe[name])['path'])
    return store.register({'schema_version': 1, 'check_id': check_id, 'scope': scope, 'operation': operation,
                           'season': recipe['season'], 'week': recipe['week'], 'run_at': run_at,
                           'latest_start_at': latest_start, 'expires_at': expires, 'source_refs': sorted(set(refs))}, previous)


def alert(root, incident, cause):
    try:
        return get_pushover(root).send(incident, 'Fantasy Football automation needs attention: ' + cause + '. Open the task for saved evidence.')
    except Exception as error:
        return {'state': 'unavailable', 'error_type': type(error).__name__, 'phone_delivery_confirmed': False}


def browser_observation(root, status, evidence, *, clock=time.time):
    if status not in ('ready', 'login_required', 'unavailable'):
        raise InvalidContract('Invalid browser status')
    root = Path(root).resolve()
    proof = AutomationStore(root).reference(evidence)
    value = {'schema_version': 1, 'status': status, 'observed_epoch': clock(), 'observed_at': utc(clock()),
             'evidence': proof, 'basis': 'operator_browser_observation'}
    if status != 'ready':
        value['notification'] = alert(root, 'browser-' + digest([status, proof['sha256']]), status)
    save_new(root / 'data/automation/browser' / (uuid.uuid4().hex + '.json'), value)
    save_atomic(root / 'data/automation/browser/latest.json', value)
    return value


class Workflow:
    def __init__(self, root, *, clock=time.time):
        self.root = Path(root).resolve()
        self.clock = clock
        self.store = AutomationStore(root, clock=clock)

    def checkpoint(self, run):
        with self.store.transaction() as db:
            row = self.store.owned(db, run['run_id'], run['token'])
            policy = self.store.policy(db)
            spec = self.store.current(db, row['check_id'], row['revision'])['spec']
            if spec['scope'].split(':')[0] != load_config(self.root)['league_id']:
                raise InvalidContract('Workflow league differs from project configuration')
            self.store.gate(policy, spec['operation'])
        return spec

    def operation_gate(self, operation):
        with self.store.transaction() as db:
            self.store.gate(self.store.policy(db), operation)

    def daily(self, recipe, run, folder):
        from fantasy_agent.automation.automation_deadlines import collect
        from fantasy_agent.automation.automation_plan import plan_files
        from fantasy_agent.automation.automation_reconcile import SchedulerStore
        config = load_config(self.root)
        collection = collect(config, recipe['season'], recipe['week'], root=self.root, timing_path=recipe.get('timing'), clock=self.clock)
        self.checkpoint(run)
        observation = json.loads(Path(collection['saved']).read_text())
        if observation.get('roster_id') != recipe['roster_id']:
            raise InvalidContract('Collected roster differs from the workflow scope')
        planned = plan_files(collection['saved'], self.root / recipe['planning_policy'], utc(self.clock()), root=self.root,
                             previous_path=self.root / recipe['previous_plan'] if recipe.get('previous_plan') else None)
        self.checkpoint(run)
        plan = json.loads(Path(planned['saved']).read_text())
        scheduler = SchedulerStore(self.root, clock=self.clock)
        desired = scheduler.from_plan(plan, recipe['target_thread_id'])
        inventory = scheduler.inventory()
        compared = scheduler.diff(desired, inventory['inventory_id'])
        result = {'collection': collection, 'planning': planned,
                  'scheduler': {'inventory': inventory, 'diff_id': compared['diff_id'], 'findings': compared['findings'],
                                'deadline_coverage_verified': False},
                  'acquisition': collection['acquisition'], 'status': 'blocked',
                  'cause': 'future_deadline_coverage_unverified',
                  'decisions_prepared': False}
        if recipe.get('dispatcher_check_recipe'):
            from fantasy_agent.automation.automation_dispatch import Dispatcher
            coverage = Dispatcher(self.root, clock=self.clock).publish_plan(
                plan, Path(planned['saved']).relative_to(self.root).as_posix(), recipe, run)
            result['scheduler']['dispatcher'] = coverage
            result['scheduler']['deadline_coverage_verified'] = coverage['configuration_coverage_verified']
            if coverage['configuration_coverage_verified']:
                result.update(status='completed', cause=None)
        with self.store.transaction() as db:
            mode = self.store.policy(db)['mode']
        if mode == 'propose':
            result['decision_preparation'] = self.deadline({**recipe, 'operation': recipe.get('decision_operation', 'propose_lineup')}, run, folder)
            result['decisions_prepared'] = True
        elif recipe.get('proposal'):
            result['decision_preparation'] = self.deadline({**recipe, 'operation': 'validate_lineup'}, run, folder)
            result['decisions_prepared'] = True
        if result.get('decision_preparation', {}).get('status') == 'blocked':
            result.update(status='blocked', cause=result['decision_preparation']['cause'])
        # M0/M3 manual timing boundary cannot be promoted by a successful collection.
        save_new(folder / 'daily.json', result)
        return result

    def deadline(self, recipe, run, folder):
        if recipe['operation'] == 'integrated_review':
            from fantasy_agent.automation.agent_cycle import review
            self.operation_gate('integrated_review')
            result = review(self.root, recipe['season'], recipe['week'], checkpoint=lambda: self.checkpoint(run))
            return {'status': 'completed' if result['status'] == 'owner_review_required' else 'blocked',
                    'cause': result.get('cause'), 'integrated_review': result, 'owner_action_required': True,
                    'acquisition': result.get('acquisition', {}), 'lineup_applied': False}
        from fantasy_agent.weekly.weekly_data import collect, load, acquisition_summary
        from fantasy_agent.weekly.weekly_model import build
        from fantasy_agent.weekly.lineup_validation import proposal_from_report, validate, check_document
        from fantasy_agent.weekly.lineup_history import append_proposal
        config = load_config(self.root)
        self.operation_gate(recipe['operation'])
        weekly = self.root / 'data/weekly' / str(recipe['season']) / str(recipe['week'])
        weekly.mkdir(parents=True, exist_ok=True)
        with (weekly / 'operation.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise InvalidContract('Another weekly operation is active') from None
            snapshot = collect(config, recipe['season'], recipe['week'], root=self.root,
                               validation_only=recipe['operation'] == 'validate_lineup')
            self.checkpoint(run)
            inputs = load(snapshot)
            if inputs['final_context']['roster']['roster_id'] != recipe['roster_id']:
                raise InvalidContract('Collected roster differs from workflow scope')
            history_path = weekly / 'locks.json'
            history = json.loads(history_path.read_text()) if history_path.exists() else {}
            if history and history.get('league_id') != recipe['league_id']:
                raise InvalidContract('Weekly lock history belongs to another league')
            now = datetime.fromtimestamp(self.clock(), timezone.utc)
            proposal_path = None
            if recipe['operation'] == 'propose_lineup':
                report = build(inputs, now, history.get('players', []), history.get('kickoffs', {}))
                self.checkpoint(run)
                save_new(folder / 'weekly-report.json', report)
                if report['blockers']:
                    return {'status': 'blocked', 'cause': 'weekly_analysis_blocked', 'acquisition': acquisition_summary(inputs),
                            'snapshot': str(snapshot), 'report': str(folder / 'weekly-report.json')}
                proposal = proposal_from_report(report, recipe['roster_id'])
                self.checkpoint(run)
                self.operation_gate('propose_lineup')
                proposal_path = append_proposal(weekly, proposal)
                proposal = json.loads(proposal_path.read_text())
            else:
                proposal = json.loads((self.root / recipe['proposal']).read_text())
                check_document(proposal)
                if (proposal['league_id'] != recipe['league_id'] or proposal['season'] != recipe['season']
                        or proposal['week'] != recipe['week']):
                    raise InvalidContract('Proposal differs from workflow scope')
            self.checkpoint(run)
            validation = validate(proposal, inputs, now, history)
            save_new(folder / 'validation.json', validation)
            self.checkpoint(run)
            if validation['status'] != 'FAIL':
                save_atomic(history_path, {'league_id': recipe['league_id'],
                    'players': validation['locked_player_ids'],
                    'kickoffs': history.get('kickoffs', {}) | {
                        p['player_id']: p['game']['kickoff'] for p in validation['players'] if p['game']}})
            return {'status': 'completed' if validation['status'] == 'PASS' else 'blocked',
                    'cause': None if validation['status'] == 'PASS' else 'lineup_' + validation['status'].lower(),
                    'proposal': str(proposal_path) if proposal_path else recipe['proposal'],
                    'validation': str(folder / 'validation.json'), 'snapshot': str(snapshot),
                    'acquisition': acquisition_summary(inputs), 'lineup_applied': False}

    def execute(self, check_id, revision, recipe_path, trigger='interactive'):
        proof = self.store.reference(recipe_path)
        recipe = json.loads((self.root / recipe_path).read_text())
        operation, scope = validate_recipe(recipe)
        # All identity and revision checks precede network, alerts and workflow writes.
        context = self.store.context(check_id, revision)
        spec = context['check']['spec']
        if (spec['scope'] != scope or spec['operation'] != operation or spec['season'] != recipe['season']
                or spec['week'] != recipe['week'] or proof not in context['check']['sources']):
            raise InvalidContract('Workflow recipe does not match the registered check')
        config = load_config(self.root)
        if config['league_id'] != recipe['league_id']:
            raise InvalidContract('Workflow league differs from project configuration')
        if trigger not in ('interactive', 'scheduled'):
            raise InvalidContract('Invalid trigger claim')
        run = self.store.claim(check_id, revision)
        folder = self.root / 'data/automation/workflows/runs' / run['run_id']
        receipt = {'schema_version': 1, 'run_id': run['run_id'], 'check_id': check_id, 'revision': revision,
                   'kind': recipe['kind'], 'started_at': utc(self.clock()), 'trigger_claim': trigger,
                   'scheduled_execution_verified': False, 'status': 'running', 'sleeper_writes': False}
        save_new(folder / 'started.json', receipt)
        try:
            with wall_budget(max(0, instant(run['lease_until']) - self.clock() - 2)):
                self.checkpoint(run)
                if recipe['kind'] == 'daily':
                    result = self.daily(recipe, run, folder)
                elif recipe['kind'] == 'deadline':
                    result = self.deadline(recipe, run, folder)
                else:
                    result = {'status': 'completed', 'acquisition': {}, 'inspection': self.store.status()}
                self.checkpoint(run)
            receipt.update(result)
        except Exception as error:
            receipt.update(status='failed', cause=type(error).__name__,
                           acquisition={'complete': False, 'note': 'Inspect provider ledgers and partial snapshot evidence'})
            if isinstance(error, AutomationError):
                receipt['failure_detail'] = str(error)
        receipt['finished_at'] = utc(self.clock())
        save_new(folder / 'result.json', receipt)
        try:
            self.store.finish(run['run_id'], run['token'], 'outcome_unknown' if receipt['status'] == 'failed' else 'completed',
                              receipt.get('cause') or 'Workflow completed',
                              [(folder / 'result.json').relative_to(self.root).as_posix()])
        except Exception as error:
            receipt['recovery_required'] = type(error).__name__
            save_new(folder / 'recovery-required.json', {'error_type': type(error).__name__, 'run_id': run['run_id']})
        save_atomic(self.root / 'data/automation/workflows/latest.json',
                    {'path': (folder / 'result.json').relative_to(self.root).as_posix()})
        if receipt['status'] != 'completed' and recipe['notify_on_failure']:
            notification = alert(self.root, 'workflow-' + digest([scope, revision, receipt.get('cause')]), receipt.get('cause') or 'workflow_incomplete')
            save_new(folder / 'notification.json', notification)
            receipt['notification'] = notification
        return receipt
