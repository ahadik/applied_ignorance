"""Explicit live scheduler acceptance. Never imported by automatic test discovery."""
import argparse
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from automation_dispatch import Dispatcher
from automation_run import register_workflow
from automation_store import InvalidContract, utc
from storage import save_new, save_atomic

FOLDER = ROOT / 'data/automation/m4/live'


def setup():
    if (FOLDER / 'setup.json').exists():
        raise InvalidContract('Live setup already exists. Inspect it instead of repeating setup.')
    dispatcher = Dispatcher(ROOT)
    status = dispatcher.store.status()
    if status['checks'] or status['runs']:
        raise InvalidContract('Live smoke setup requires an unused workflow ledger')
    now = time.time()
    proof = {'scope': 'harmless M4 local workflow acceptance', 'authorized_by': 'Finish m4',
             'provider_requests': False, 'sleeper_writes': False, 'prior_mode': status['policy']['mode']}
    save_new(FOLDER / 'authorization.json', proof)
    dispatcher.store.set_mode('observe', 'data/automation/m4/live/authorization.json')
    league = json.loads((ROOT / 'config.json').read_text())['league_id']
    checks = []
    for name, offset in [('cycle-1', 0), ('cycle-2', 60), ('future-sentinel', 3600)]:
        path = FOLDER / (name + '.json')
        save_new(path, {'schema_version': 1, 'kind': 'inspection', 'league_id': league, 'season': 2026,
                        'week': 1, 'roster_id': 999999, 'notify_on_failure': False,
                        'purpose': 'Synthetic inspection scope. No real roster facts or advice.'})
        relative = path.relative_to(ROOT).as_posix()
        check_id = 'm4-live-' + name
        result = register_workflow(ROOT, relative, check_id, utc(now + offset),
                                   utc(now + offset + 1800), utc(now + offset + 2400))
        checks.append({'check_id': check_id, 'revision': result['revision'], 'recipe': relative})
    value = {'schema_version': 1, 'started_at': utc(now), 'checks': checks,
             'horizon_end': utc(now + 7200), 'prior_mode': proof['prior_mode']}
    save_new(FOLDER / 'setup.json', value)
    return {'setup': value, 'coverage': dispatcher.publish(checks, value['horizon_end'])}


def cycle(automation_id, evidence):
    dispatcher = Dispatcher(ROOT)
    proof = dispatcher.store.reference(evidence)
    observation = json.loads((ROOT / evidence).read_text())
    if observation.get('automation_id') != automation_id or observation.get('basis') != 'observed_scheduler_injected_message':
        raise InvalidContract('Actual scheduler message observation is required')
    binding = dispatcher.inventory()
    if binding['task_id'] != automation_id:
        raise InvalidContract('Scheduler trigger and bound task differ')
    existing = list((FOLDER / 'cycles').glob('*.json')) if (FOLDER / 'cycles').exists() else []
    if len(existing) >= 2:
        return {'retire': True, 'reason': 'two_live_cycles_already_recorded'}
    if any(json.loads(p.read_text())['trigger_evidence'] == proof for p in existing):
        raise InvalidContract('Scheduler trigger evidence was already used')
    config = dispatcher.config()
    result = dispatcher.tick(config['revision'])
    if result['status'] != 'completed':
        return {'tick': result, 'retire': False}
    if result['workflow']['check_id'] not in ('m4-live-cycle-1', 'm4-live-cycle-2'):
        raise InvalidContract('Unexpected acceptance workflow executed')
    setup = json.loads((FOLDER / 'setup.json').read_text())
    # Each actual scheduled cycle republishes the remaining future obligations and checks fresh inventory.
    coverage = dispatcher.publish(setup['checks'], utc(time.time() + 7200))
    receipt = {'schema_version': 1, 'observed_at': utc(time.time()), 'trigger_evidence': proof,
               'trigger_basis': 'operator_observation_of_actual_scheduler_message',
               'workflow': result['workflow'], 'coverage': coverage,
               'real_provider_data': False, 'scope': 'harmless local workflow and scheduler integration'}
    save_new(FOLDER / 'cycles' / (uuid.uuid4().hex + '.json'), receipt)
    return {'cycles_recorded': len(existing) + 1, 'retire': len(existing) + 1 == 2,
            'configuration_coverage_verified': coverage['configuration_coverage_verified'],
            'workflow_run_id': result['workflow']['run_id']}


def finish():
    dispatcher = Dispatcher(ROOT)
    records = [json.loads(p.read_text()) for p in (FOLDER / 'cycles').glob('*.json')]
    if len(records) != 2 or {r['workflow']['check_id'] for r in records} != {'m4-live-cycle-1', 'm4-live-cycle-2'}:
        raise InvalidContract('Two distinct scheduled workflow cycles are required')
    if not all(r['coverage']['configuration_coverage_verified'] for r in records):
        raise InvalidContract('A live cycle lacked verified future configuration coverage')
    from automation_reconcile import SchedulerStore, read_local
    scheduler = SchedulerStore(ROOT)
    with scheduler.db() as db:
        inventory = read_local(scheduler.config(db)['inventory_scope'])
    if not inventory['complete'] or any(e['owner'] and e['owner']['key'] == 'm4-dispatcher' for e in inventory['entries']):
        raise InvalidContract('Delete the acceptance dispatcher and verify cleanup before finishing')
    setup = json.loads((FOLDER / 'setup.json').read_text())
    if setup['prior_mode'] != 'disabled':
        raise InvalidContract('Unexpected prior mode requires explicit review')
    dispatcher.store.set_mode('disabled')
    value = {'schema_version': 1, 'status': 'passed', 'finished_at': utc(time.time()), 'cycles': records,
             'cleanup_inventory': inventory, 'automation_mode': 'disabled',
             'scope': 'M4 bounded recurring dispatcher and harmless workflow acceptance',
             'limits': ['configuration coverage assumes stated dispatch delay', 'no production football coverage or browser freshness assertion',
                        'natural one-time expiration remains unverified', 'offline Mac monitor is not configured']}
    save_new(FOLDER / 'acceptance.json', value)
    return {'status': 'passed', 'cycles': 2, 'cleanup_verified': True, 'automation_mode': 'disabled'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('setup')
    sub.add_parser('finish')
    cyc = sub.add_parser('cycle')
    cyc.add_argument('--automation-id', required=True)
    cyc.add_argument('--trigger-evidence', required=True)
    args = parser.parse_args()
    result = cycle(args.automation_id, args.trigger_evidence) if args.command == 'cycle' else globals()[args.command]()
    print(json.dumps(result, indent=2))
