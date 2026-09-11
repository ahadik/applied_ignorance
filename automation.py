"""Manage automation records, plans and bounded workflows. Collection/workflow commands can read providers."""
import argparse
import json
from pathlib import Path
import sqlite3

from automation_store import AutomationStore, AutomationError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, help='Project root; defaults to this installed project')
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init')
    init.add_argument('--policy', type=Path)
    sub.add_parser('status')
    health_command = sub.add_parser('health')
    health_command.add_argument('--output', type=Path)
    sub.add_parser('pause')
    resume = sub.add_parser('resume')
    resume.add_argument('--mode', choices=('observe', 'propose'), default='observe')
    resume.add_argument('--evidence', required=True)
    workflow_register = sub.add_parser('workflow-register')
    workflow_register.add_argument('--recipe', required=True)
    workflow_register.add_argument('--check-id', required=True)
    workflow_register.add_argument('--run-at', required=True)
    workflow_register.add_argument('--latest-start', required=True)
    workflow_register.add_argument('--expires', required=True)
    workflow_register.add_argument('--expected-revision')
    workflow_run = sub.add_parser('workflow-run')
    workflow_run.add_argument('--recipe', required=True)
    workflow_run.add_argument('--check-id', required=True)
    workflow_run.add_argument('--revision', required=True)
    workflow_run.add_argument('--trigger', choices=('interactive', 'scheduled'), default='interactive')
    browser = sub.add_parser('browser-observation')
    browser.add_argument('--status', choices=('ready', 'login_required', 'unavailable'), required=True)
    browser.add_argument('--evidence', required=True)
    scheduler_init = sub.add_parser('schedule-init')
    scheduler_init.add_argument('--inventory-directory', type=Path)
    scheduler_import = sub.add_parser('schedule-import')
    scheduler_import.add_argument('--file', type=Path, help='Import untrusted evidence instead of reading local records')
    scheduler_spec = sub.add_parser('schedule-spec')
    scheduler_spec.add_argument('--target-thread', required=True)
    scheduler_spec.add_argument('--plan', type=Path)
    scheduler_spec.add_argument('--probe-version', type=int, default=1)
    scheduler_spec.add_argument('--retire-probe', action='store_true')
    scheduler_spec.add_argument('--output', type=Path, required=True)
    scheduler_diff = sub.add_parser('schedule-diff')
    scheduler_diff.add_argument('--desired', type=Path, required=True)
    scheduler_diff.add_argument('--inventory-id', required=True)
    scheduler_begin = sub.add_parser('schedule-begin')
    scheduler_begin.add_argument('--diff-id', required=True)
    scheduler_begin.add_argument('--index', type=int, default=0)
    scheduler_record = sub.add_parser('schedule-record')
    scheduler_record.add_argument('--operation-id', required=True)
    scheduler_record.add_argument('--token', required=True)
    scheduler_record.add_argument('--outcome', choices=('success', 'unknown', 'failed'), required=True)
    scheduler_record.add_argument('--task-id')
    scheduler_record.add_argument('--evidence', required=True)
    scheduler_verify = sub.add_parser('schedule-verify')
    scheduler_verify.add_argument('--operation-id', required=True)
    scheduler_verify.add_argument('--inventory-id', required=True)
    scheduler_export = sub.add_parser('schedule-export')
    scheduler_export.add_argument('--output', type=Path, required=True)
    scheduler_resolve = sub.add_parser('schedule-resolve')
    scheduler_resolve.add_argument('--operation-id', required=True)
    scheduler_resolve.add_argument('--inventory-id', required=True)
    scheduler_resolve.add_argument('--evidence', required=True)
    scheduler_resolve.add_argument('--reason', required=True)
    incorporate = sub.add_parser('incorporate-rules')
    incorporate.add_argument('--observations', required=True)
    incorporate.add_argument('--rules', required=True)
    collect = sub.add_parser('collect-deadlines')
    collect.add_argument('--season', required=True, type=int)
    collect.add_argument('--week', required=True, type=int)
    collect.add_argument('--config', type=Path)
    collect.add_argument('--timing', help='Project-relative verified waiver/review evidence JSON')
    plan = sub.add_parser('plan')
    plan.add_argument('--observations', required=True, type=Path)
    plan.add_argument('--policy', required=True, type=Path)
    plan.add_argument('--as-of', required=True)
    plan.add_argument('--previous', type=Path)
    plan.add_argument('--output-dir', type=Path)
    mode = sub.add_parser('mode')
    mode.add_argument('mode', choices=('disabled', 'observe', 'propose'))
    mode.add_argument('--evidence', help='Project-relative setup evidence file')
    register = sub.add_parser('register')
    register.add_argument('--check', required=True, type=Path)
    register.add_argument('--expected-revision')
    for name in ('begin', 'context'):
        command = sub.add_parser(name)
        command.add_argument('--check-id', required=True)
        command.add_argument('--revision', required=True)
        if name == 'context':
            command.add_argument('--output', type=Path)
    for name in ('renew', 'reference', 'finish'):
        command = sub.add_parser(name)
        command.add_argument('--run-id', required=True)
        command.add_argument('--token', required=True)
        if name == 'reference':
            command.add_argument('--kind', required=True, choices=('proposal', 'action', 'evidence'))
            command.add_argument('--path', required=True)
        elif name == 'finish':
            command.add_argument('--outcome', required=True, choices=('completed', 'failed', 'outcome_unknown'))
            command.add_argument('--summary', required=True)
            command.add_argument('--artifact', action='append', default=[])
    recover = sub.add_parser('recover')
    recover.add_argument('--run-id', required=True)
    recover.add_argument('--resolution', required=True, choices=('safe_to_retry', 'completed'))
    recover.add_argument('--evidence', required=True)
    recover.add_argument('--reason', required=True)
    export = sub.add_parser('export')
    export.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    store = AutomationStore(args.root)
    try:
        if args.command.startswith('schedule-'):
            from automation_reconcile import SchedulerStore
            from storage import save_new
            scheduler = SchedulerStore(store.root)
            if args.command == 'schedule-init':
                result = scheduler.init(args.inventory_directory)
            elif args.command == 'schedule-import':
                result = scheduler.inventory(json.loads(args.file.read_text()) if args.file else None)
            elif args.command == 'schedule-spec':
                result = (scheduler.from_plan(json.loads(args.plan.read_text()), args.target_thread) if args.plan
                          else scheduler.probe_spec(args.target_thread, args.probe_version, args.retire_probe))
                save_new(args.output, result)
                result = {'saved': str(args.output), 'checks': len(result['checks']), 'automatic_execution': False}
            elif args.command == 'schedule-diff':
                result = scheduler.diff(json.loads(args.desired.read_text()), args.inventory_id)
            elif args.command == 'schedule-begin':
                result = scheduler.begin(args.diff_id, args.index)
            elif args.command == 'schedule-record':
                result = scheduler.record(args.operation_id, args.token, args.outcome, args.task_id, args.evidence)
            elif args.command == 'schedule-verify':
                result = scheduler.verify(args.operation_id, args.inventory_id)
            elif args.command == 'schedule-resolve':
                result = scheduler.resolve_not_applied(args.operation_id, args.inventory_id, args.evidence, args.reason)
            else:
                result = scheduler.export(args.output)
        elif args.command == 'init':
            result = store.initialize(json.loads(args.policy.read_text()) if args.policy else None)
        elif args.command == 'status':
            result = store.status()
        elif args.command == 'health':
            from automation_health import health
            result = health(store.root)
            if args.output:
                store.save_report(args.output, result)
        elif args.command == 'pause':
            result = store.set_mode('disabled')
        elif args.command == 'resume':
            result = store.set_mode(args.mode, args.evidence)
        elif args.command == 'workflow-register':
            from automation_run import register_workflow
            result = register_workflow(store.root, args.recipe, args.check_id, args.run_at, args.latest_start,
                                       args.expires, args.expected_revision)
        elif args.command == 'workflow-run':
            from automation_run import Workflow
            result = Workflow(store.root).execute(args.check_id, args.revision, args.recipe, args.trigger)
        elif args.command == 'browser-observation':
            from automation_run import browser_observation
            result = browser_observation(store.root, args.status, args.evidence)
        elif args.command == 'incorporate-rules':
            from automation_deadlines import incorporate_saved
            result = incorporate_saved(args.observations, args.rules, root=store.root)
        elif args.command == 'collect-deadlines':
            from automation_deadlines import collect
            config = json.loads((args.config or store.root / 'config.json').read_text())
            result = collect(config, args.season, args.week, root=store.root, timing_path=args.timing)
        elif args.command == 'plan':
            from automation_plan import plan_files
            result = plan_files(args.observations, args.policy, args.as_of, root=store.root,
                                previous_path=args.previous, output_dir=args.output_dir)
        elif args.command == 'mode':
            result = store.set_mode(args.mode, args.evidence)
        elif args.command == 'register':
            result = store.register(json.loads(args.check.read_text()), args.expected_revision)
        elif args.command == 'begin':
            result = store.claim(args.check_id, args.revision)
        elif args.command == 'context':
            result = store.context(args.check_id, args.revision)
            if args.output:
                store.save_report(args.output, result)
                result = {'saved': str(args.output)}
        elif args.command == 'renew':
            result = store.renew(args.run_id, args.token)
        elif args.command == 'reference':
            result = store.add_reference(args.run_id, args.token, args.kind, args.path)
        elif args.command == 'finish':
            result = store.finish(args.run_id, args.token, args.outcome, args.summary, args.artifact)
        elif args.command == 'recover':
            result = store.recover(args.run_id, args.resolution, args.evidence, args.reason)
        else:
            result = store.export(args.output)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (AutomationError, OSError, ValueError, sqlite3.Error) as error:
        # Contract errors contain controlled descriptions; other exceptions may contain private file contents.
        message = str(error) if isinstance(error, AutomationError) else 'Local operation failed'
        print(json.dumps({'error': type(error).__name__, 'message': message,
                          'external_execution': 'unverified' if args.command in ('workflow-run', 'browser-observation', 'collect-deadlines') else False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
