"""Standing owner delegation for manager decisions, checked again before dispatch."""
import argparse
import json
from pathlib import Path
import uuid

from fantasy_agent.automation.automation_store import InvalidContract, instant, utc
from fantasy_agent.core.project_config import load_config
from fantasy_agent.core.storage import save_new, save_atomic
from fantasy_agent.maintenance.system_acceptance import source_digest
from fantasy_agent.weekly.weekly_data import fingerprint

ALLOWED = {'unlocked_starters', 'free_agent', 'waiver', 'cancel_claim', 'ir_place', 'ir_activate'}


def install(engine, request_path):
    request, proof = engine.read(request_path)
    config = load_config(engine.root)
    if (request.get('basis') != 'explicit_owner_management_request' or not request.get('owner_statement')
            or request.get('league_id') != config['league_id'] or request.get('user_id') != config['user_id']
            or not isinstance(request.get('season'), int) or not isinstance(request.get('roster_id'), int)):
        raise InvalidContract('Record the actual owner request and exact league, user, roster and season')
    operations = request.get('operations', [])
    if not operations or not set(operations) <= ALLOWED:
        raise InvalidContract('Unsupported management authority. Trades and standalone drops require separate permission')
    for key, ceiling in [('lineup_actions_per_day', 20), ('roster_actions_per_day', 5)]:
        if type(request.get(key)) is not int or not 1 <= request[key] <= ceiling:
            raise InvalidContract('Set a supported daily action limit')
    value = {'enabled': True, 'generation': uuid.uuid4().hex, 'request': proof, 'installed_at': utc(engine.clock())}
    save_atomic(engine.root / 'data/manager/authority.json', value)
    return value


def policy(engine, proposal, operation):
    from fantasy_agent.automation.league_manager import Manager
    state = Manager(engine.root, clock=engine.clock).state()
    if not state['enabled'] or not Manager(engine.root, clock=engine.clock).scheduler(state)['verified']:
        raise InvalidContract('Manager must be enabled with verified future scheduling')
    value, _ = engine.read('data/manager/authority.json')
    if not value['enabled']:
        raise InvalidContract('Manager authority is revoked')
    request, proof = engine.read(value['request']['path'])
    if proof != value['request']:
        raise InvalidContract('Owner management request changed')
    config = load_config(engine.root)
    if request['user_id'] != config['user_id'] or request['league_id'] != config['league_id']:
        raise InvalidContract('Configured account differs from standing permission')
    if any(request[k] != proposal[k] for k in ('league_id', 'roster_id', 'season')) or operation not in request['operations']:
        raise InvalidContract('Decision is outside standing management permission')
    tests, _ = engine.read('data/manager/acceptance.json')
    if (tests.get('failed') != 0 or not tests.get('passed') or tests.get('source_digest') != source_digest(engine.root)
            or tests.get('basis') != 'verified_failure_exercises' or tests.get('command') != 'python3 -m unittest discover -v'):
        raise InvalidContract('Run offline acceptance for the current source version')
    return value, request


def readiness(engine, db, proposal, operation):
    value, request = policy(engine, proposal, operation)
    prefix = ':'.join(str(proposal[k]) for k in ('league_id', 'roster_id', 'season')) + ':'
    windows = set()
    for row in db.execute("SELECT value FROM events WHERE kind='supervised_window'"):
        event = json.loads(row[0])
        if event['scope'].startswith(prefix):
            for proof in [event['evidence'], *event['completion']['evidence']]:
                if engine.references.reference(proof['path']) != proof:
                    raise InvalidContract('Live game-window evidence changed')
            windows.add(event['kickoff'])
    if len(windows) < 2:
        raise InvalidContract('Two supervised game windows remain required before automatic changes')
    if operation != 'unlocked_starters':
        # Roster authority expands only after a real supervised transaction completes.
        rows = db.execute("SELECT a.state,p.value FROM roster_actions a JOIN roster_plans p ON a.plan_id=p.id WHERE p.scope LIKE ?", (prefix + '%',)).fetchall()
        accepted = False
        for state, raw in rows:
            record = json.loads(raw)
            approval, _ = engine.read(record['approval']['path'])
            accepted |= state in ('won', 'applied') and approval.get('basis') == 'explicit_owner_transaction_approval'
        if not accepted:
            raise InvalidContract('A successful supervised roster transaction remains required')
    return value, request


def verify(engine, db, proposal, authority, operation, *, dispatch=False):
    value, request = readiness(engine, db, proposal, operation)
    if authority.get('generation') != value['generation'] or authority.get('subject_hash') != fingerprint(proposal):
        raise InvalidContract('Manager decision authority was superseded or changed')
    if not instant(authority['issued_at']) <= engine.clock() < instant(authority['expires_at']):
        raise InvalidContract('Manager decision authority expired')
    decision, proof = engine.read(authority['decision']['path'])
    if proof != authority['decision']:
        raise InvalidContract('Final decision evidence changed')
    if dispatch:
        rows = db.execute("SELECT value FROM events WHERE kind='manager_dispatch'").fetchall()
        count = sum(json.loads(row[0])['operation_group'] == ('lineup' if operation == 'unlocked_starters' else 'roster')
                    and instant(json.loads(row[0])['at']) > engine.clock() - 86400 for row in rows)
        limit = request['lineup_actions_per_day' if operation == 'unlocked_starters' else 'roster_actions_per_day']
        if count >= limit:
            raise InvalidContract('Standing management daily action limit reached')
        engine.event(db, 'manager_dispatch', {'at': utc(engine.clock()), 'operation_group': 'lineup' if operation == 'unlocked_starters' else 'roster'})
    return request


def authorize(engine, subject_path, decision_path, operation):
    proposal, _ = engine.read(subject_path)
    decision, proof = engine.read(decision_path)
    if (decision.get('subject_hash') != fingerprint(proposal) or not decision.get('reason')
            or decision.get('unresolved_concerns') != [] or not decision.get('evidence')):
        raise InvalidContract('Save a reasoned final decision with evidence and no unresolved concerns')
    for path in decision['evidence']:
        engine.references.reference(path)
    if operation != 'unlocked_starters' and (not decision.get('season_impact') or not decision.get('alternatives_considered')):
        raise InvalidContract('Roster decisions require season consequences and considered alternatives')
    with engine.db() as db:
        if operation != 'unlocked_starters':
            from fantasy_agent.execution.roster_operations import tables
            tables(db)
        value, request = readiness(engine, db, proposal, operation)
    authority = {'schema_version': 1, 'mode': 'manager', 'basis': 'standing_manager_authority',
                 **{k: proposal[k] for k in ('league_id', 'roster_id', 'season', 'week')},
                 'generation': value['generation'], 'subject_hash': fingerprint(proposal), 'decision': proof,
                 'proposal_hash': fingerprint(proposal), 'plan_hash': fingerprint(proposal),
                 'issued_at': utc(engine.clock()), 'expires_at': utc(engine.clock() + 600),
                 'owner_approval': value['request']['path'], 'operation': operation,
                 'owner_statement': request['owner_statement']}
    path = engine.root / 'data/manager/authorizations' / (uuid.uuid4().hex + '.json')
    save_new(path, authority)
    return {'saved': path.relative_to(engine.root).as_posix(), 'platform_changes': False}


def main():
    from fantasy_agent.execution.lineup_execution import Execution
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    install_parser = sub.add_parser('install')
    install_parser.add_argument('--request', required=True)
    authorize_parser = sub.add_parser('authorize')
    authorize_parser.add_argument('--subject', required=True)
    authorize_parser.add_argument('--decision', required=True)
    authorize_parser.add_argument('--operation', choices=sorted(ALLOWED), required=True)
    sub.add_parser('revoke')
    acceptance = sub.add_parser('accept-tests')
    acceptance.add_argument('--evidence', required=True)
    args = parser.parse_args()
    engine = Execution()
    if args.command == 'install':
        result = install(engine, args.request)
    elif args.command == 'authorize':
        result = authorize(engine, args.subject, args.decision, args.operation)
    elif args.command == 'accept-tests':
        record, proof = engine.read(args.evidence)
        if (record.get('failed') != 0 or not record.get('passed') or record.get('source_digest') != source_digest(engine.root)
                or record.get('basis') != 'verified_failure_exercises' or record.get('command') != 'python3 -m unittest discover -v'):
            raise InvalidContract('Require passing full-suite evidence for this source version')
        save_atomic(engine.root / 'data/manager/acceptance.json', {**record, 'source_record': proof})
        result = {'offline_acceptance_current': True, 'live_acceptance_granted': False}
    else:
        value, _ = engine.read('data/manager/authority.json')
        value['enabled'] = False
        save_atomic(engine.root / 'data/manager/authority.json', value)
        result = {'enabled': False}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
