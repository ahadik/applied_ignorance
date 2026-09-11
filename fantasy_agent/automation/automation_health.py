"""Read-only health summaries. Desired, scheduled and completed states remain separate."""
import json
from pathlib import Path
import sqlite3
import time

from fantasy_agent.automation.automation_store import AutomationStore, utc
from fantasy_agent.automation.automation_reconcile import SchedulerStore, read_local
from fantasy_agent.providers.pushover import get_pushover


def health(root, *, clock=time.time):
    root = Path(root).resolve()
    now = clock()
    result = {'schema_version': 1, 'observed_at': utc(now), 'automation': AutomationStore(root, clock=clock).status(),
              'desired': None, 'scheduled': None, 'workflow_receipts': [], 'browser': None,
              'notifications': get_pushover(root).status(), 'external_offline_monitor': 'not_configured',
              'production_ready': False, 'issues': []}
    latest = root / 'data/automation/workflows/latest.json'
    if latest.exists():
        index = json.loads(latest.read_text())
        receipt = json.loads((root / index['path']).read_text())
        for field, name in [('notification', 'notification.json'), ('recovery_required', 'recovery-required.json')]:
            extra = (root / index['path']).parent / name
            if extra.exists():
                receipt[field] = json.loads(extra.read_text())
        result['workflow_receipts'] = [receipt]
        result['desired'] = receipt.get('planning')
        if receipt.get('status') != 'completed':
            result['issues'].append('latest_workflow_incomplete')
    else:
        result['issues'].append('no_workflow_receipt')
    scheduler = SchedulerStore(root, clock=clock)
    if scheduler.path.exists():
        with scheduler.db() as db:
            config = scheduler.config(db)
            pending = db.execute("SELECT COUNT(*) FROM pending WHERE state IN ('pending','reported','unknown')").fetchone()[0]
        inventory = read_local(config['inventory_scope'], clock=clock)
        result['scheduled'] = {'complete_local_inventory': inventory['complete'],
                               'entries': len(inventory['entries']),
                               'enabled_owned_tasks': sum(e['config']['status'] == 'ACTIVE' and bool(e['owner'])
                                                          and e['owner']['installation'] == config['installation'] for e in inventory['entries']),
                               'unresolved_operations': pending, 'deadline_coverage_verified': False}
        if pending:
            result['issues'].append('unresolved_scheduler_operation')
    else:
        result['issues'].append('scheduler_not_initialized')
    browser_path = root / 'data/automation/browser/latest.json'
    if browser_path.exists():
        browser = json.loads(browser_path.read_text())
        browser['age_seconds'] = now - browser['observed_epoch']
        browser['current'] = 0 <= browser['age_seconds'] <= 300 and browser['status'] == 'ready'
        result['browser'] = browser
    if not result['browser'] or not result['browser']['current']:
        result['issues'].append('browser_readiness_unverified')
    if not result['notifications']['phone_delivery_confirmed']:
        result['issues'].append('phone_delivery_unverified')
    dispatcher_path = root / 'data/automation/dispatcher/latest.json'
    result['dispatcher'] = None
    if dispatcher_path.exists():
        from fantasy_agent.automation.automation_dispatch import Dispatcher
        try:
            result['dispatcher'] = Dispatcher(root, clock=clock).coverage()
            if result['scheduled']:
                result['scheduled']['deadline_coverage_verified'] = result['dispatcher']['configuration_coverage_verified']
        except (OSError, ValueError) as error:
            result['dispatcher'] = {'configuration_coverage_verified': False, 'error_type': type(error).__name__}
    if not result['dispatcher'] or not result['dispatcher']['configuration_coverage_verified']:
        result['issues'].append('automatic_deadline_coverage_unverified')
    result['production_ready'] = not result['issues'] and result['automation']['policy']['mode'] != 'disabled'
    return result
