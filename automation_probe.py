"""Record M0 capability evidence without changing Sleeper or scheduling tasks."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tomllib
import uuid

from sleeper import SleeperError, get_sleeper
from storage import save_new

ROOT = Path(__file__).resolve().parent
CAPABILITIES = (
    'local_command', 'sleeper_read', 'scheduled_start', 'browser_inspection',
    'task_inventory', 'task_create', 'task_update', 'task_cancel',
    'one_off_timing', 'timezone', 'chat_closed', 'app_restart',
    'notification_delivery',
)
STATUSES = ('verified', 'unsupported', 'unavailable', 'untested')


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Use a timestamp with a time zone')
    return result.astimezone(timezone.utc)


def revision(root):
    try:
        return subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=root, text=True,
            stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def probe(root=ROOT, *, trigger='interactive', task_id=None, expected_at=None,
          live=False, request=get_sleeper, now=None):
    if trigger not in ('interactive', 'scheduled'):
        raise ValueError('Invalid trigger')
    if trigger == 'scheduled' and not task_id:
        raise ValueError('A claimed scheduled run requires its task ID')
    started = now or datetime.now(timezone.utc)
    if started.tzinfo is None:
        raise ValueError('Use an aware clock')
    expected = timestamp(expected_at) if expected_at else None
    source_hash = hashlib.sha256()
    for path in sorted(root.glob('*.py')):
        source_hash.update(path.name.encode())
        source_hash.update(path.read_bytes())
    result = {
        'schema_version': 1, 'kind': 'run', 'run_id': uuid.uuid4().hex,
        'started_at': started.isoformat(),
        'context': {
            'project': str(root.resolve()), 'cwd': str(Path.cwd().resolve()),
            'cwd_matches': Path.cwd().resolve() == root.resolve(),
            'host': platform.node(), 'os': platform.platform(),
            'python': platform.python_version(), 'executable': sys.executable,
            'commit': revision(root), 'python_source_sha256': source_hash.hexdigest(),
            'app_version': None, 'account_workspace': None,
        },
        'trigger_claim': trigger, 'task_id_claim': task_id,
        'expected_at_claim': expected.isoformat() if expected else None,
        'start_delay_seconds': (started - expected).total_seconds() if expected else None,
        'capabilities': {name: {'status': 'untested', 'basis': 'none'} for name in CAPABILITIES},
        'external_writes': False,
    }
    result['capabilities']['local_command'] = {
        'status': 'verified', 'basis': 'script_execution',
        'scope': 'this process only; trigger is a caller claim',
    }
    if live:
        try:
            config = json.loads((root / 'config.json').read_text())
            league_id = config['league_id']
            if not isinstance(league_id, str) or not re.fullmatch(r'\d+', league_id):
                raise ValueError('Invalid configured league ID')
            response = request(f'league/{league_id}', with_metadata=True, retries=0)
            data = response['data']
            if not isinstance(data, dict) or data.get('league_id') != league_id or data.get('sport') != 'nfl':
                raise ValueError('Unexpected league response')
            result['capabilities']['sleeper_read'] = {
                'status': 'verified', 'basis': 'central_sleeper_client',
                'league_id': league_id,
                'acquisition': {key: response.get(key) for key in (
                    'cache_hit', 'network_attempts', 'fetched_at', 'source_updated_at')},
                'scope': 'public league read only; not browser login or roster verification',
            }
        except (OSError, ValueError, KeyError, TypeError) as error:
            # Do not persist arbitrary transport messages or credentials in logs.
            result['capabilities']['sleeper_read'] = {
                'status': 'unavailable', 'basis': 'central_sleeper_client',
                'error_type': type(error).__name__,
                'acquisition': error.diagnostic() if isinstance(error, SleeperError) else None,
                'scope': 'failed read; unknown diagnostic fields remain null',
            }
    return result


def validate_record(record):
    if record.get('schema_version') != 1 or record.get('kind') != 'run':
        raise ValueError('Unsupported probe record')
    if not re.fullmatch(r'[a-f0-9]{32}', record.get('run_id', '')):
        raise ValueError('Invalid run ID')
    timestamp(record['started_at'])
    if set(record['capabilities']) != set(CAPABILITIES):
        raise ValueError('Incomplete capability matrix')
    if record.get('external_writes') is not False:
        raise ValueError('M0 cannot authorize external writes')
    for value in record['capabilities'].values():
        if value.get('status') not in STATUSES or not value.get('basis'):
            raise ValueError('Invalid capability evidence')
    # Flags supplied by the caller never establish scheduler or browser success.
    for name in set(CAPABILITIES) - {'local_command', 'sleeper_read'}:
        if record['capabilities'][name]['status'] != 'untested':
            raise ValueError('Run receipt cannot certify external capabilities')


def save_run(record, root=ROOT):
    validate_record(record)
    path = root / 'data/automation/m0/runs' / f"{record['run_id']}.json"
    save_new(path, record)
    return path


def observe(root, run_id, capability, status, evidence_file):
    if not re.fullmatch(r'[a-f0-9]{32}', run_id):
        raise ValueError('Invalid run ID')
    if capability not in CAPABILITIES or status not in STATUSES:
        raise ValueError('Invalid observation')
    run = json.loads((root / 'data/automation/m0/runs' / f'{run_id}.json').read_text())
    validate_record(run)
    evidence = json.loads(evidence_file.read_text())
    required = ('observed_at', 'surface', 'execution_mode', 'result', 'reference')
    if any(not isinstance(evidence.get(k), str) or not evidence[k].strip() for k in required):
        raise ValueError('Evidence needs time, surface, mode, result and reference')
    timestamp(evidence['observed_at'])
    if evidence['execution_mode'] not in ('interactive', 'scheduled'):
        raise ValueError('Invalid evidence mode')
    if status == 'verified' and capability == 'scheduled_start' and evidence['execution_mode'] != 'scheduled':
        raise ValueError('Interactive evidence cannot verify a scheduled start')
    observation_id = uuid.uuid4().hex
    path = root / 'data/automation/m0/observations' / f'{observation_id}.json'
    save_new(path, {
        'schema_version': 1, 'kind': 'observation', 'observation_id': observation_id,
        'run_id': run_id, 'capability': capability, 'reported_status': status,
        'provenance': 'operator_supplied_evidence; requires review',
        'evidence': evidence, 'evidence_sha256': hashlib.sha256(evidence_file.read_bytes()).hexdigest(),
    })
    return path


def read_inventory(directory):
    """Read local schedule records; cloud inventory and run history are outside scope."""
    directory = Path(directory)
    result = {'observed_at': datetime.now(timezone.utc).isoformat(),
              'surface': 'documented local automation.toml files',
              'execution_mode': 'interactive',
              'scope': 'All direct local automation directories; excludes cloud tasks and run history',
              'reference': str(directory), 'complete': False, 'entries': [], 'errors': []}
    try:
        children = sorted(directory.iterdir())
        for child in children:
            if not child.is_dir():
                continue
            try:
                path = child / 'automation.toml'
                if child.is_symlink() or path.is_symlink():
                    raise ValueError('Symlink inventory requires separate review')
                raw = path.read_bytes()
                value = tomllib.loads(raw.decode('utf-8'))
                if value.get('id') != child.name or not all(k in value for k in ('kind', 'status', 'rrule', 'prompt')):
                    raise ValueError('Incomplete schedule')
                result['entries'].append({
                    **{key: value.get(key) for key in ('id', 'kind', 'status', 'rrule', 'target_thread_id')},
                    'project_id': value.get('target', {}).get('project_id', value.get('project_id')),
                    'cwds': value.get('cwds', []),
                    'file_sha256': hashlib.sha256(raw).hexdigest(),
                    'prompt_sha256': hashlib.sha256(value['prompt'].encode()).hexdigest(),
                })
            except (OSError, ValueError, TypeError, AttributeError) as error:
                result['errors'].append({'directory': child.name, 'error_type': type(error).__name__})
        if sorted(directory.iterdir()) != children:
            result['errors'].append({'error_type': 'InventoryChanged'})
        result['complete'] = not result['errors']
    except OSError as error:
        result['errors'].append({'error_type': type(error).__name__})
    result['result'] = 'Complete local file enumeration' if result['complete'] else 'Incomplete local file enumeration'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run')
    run.add_argument('--trigger', choices=('interactive', 'scheduled'), default='interactive')
    run.add_argument('--task-id')
    run.add_argument('--expected-at')
    run.add_argument('--sleeper-read', action='store_true')
    obs = sub.add_parser('observe')
    obs.add_argument('--run-id', required=True)
    obs.add_argument('--capability', required=True, choices=CAPABILITIES)
    obs.add_argument('--status', required=True, choices=STATUSES)
    obs.add_argument('--evidence-file', required=True, type=Path)
    inventory = sub.add_parser('inventory', help='Record the local automation file inventory without network access')
    inventory.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'inventory':
            directory = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'automations'
            record = read_inventory(directory)
            save_new(args.output, record)
            print(json.dumps({'saved': str(args.output), 'complete': record['complete'],
                              'entries': record['entries'], 'errors': record['errors'],
                              'scope': record['scope']}, indent=2))
            return int(not record['complete'])
        if args.command == 'run':
            record = probe(trigger=args.trigger, task_id=args.task_id,
                           expected_at=args.expected_at, live=args.sleeper_read)
            path = save_run(record)
            print(json.dumps({'saved': str(path), 'run_id': record['run_id'],
                              'capabilities': record['capabilities']}, indent=2))
            return int(args.sleeper_read and record['capabilities']['sleeper_read']['status'] != 'verified')
        path = observe(ROOT, args.run_id, args.capability, args.status, args.evidence_file)
        print(json.dumps({'saved': str(path), 'scope': 'reported evidence; not automatic M0 acceptance'}))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f'Probe failed: {type(error).__name__}. No external changes.\n')


if __name__ == '__main__':
    raise SystemExit(main())
