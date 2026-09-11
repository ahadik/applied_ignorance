"""Durable lineup execution gates. Browser actions remain separate, supervised operations."""
import argparse
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time
import uuid

from automation_store import AutomationStore, InvalidContract, instant, utc
from weekly_data import context, state_key, fingerprint, load, collect, acquisition_summary
from lineup_validation import check_document, validate
from storage import save_new
from weekly_model import ELIGIBLE
from lineup_review import resolve

ROOT = Path(__file__).resolve().parent


class Execution:
    def __init__(self, root=ROOT, *, clock=time.time):
        self.root = Path(root).resolve()
        self.clock = clock
        self.folder = self.root / 'data/lineup_execution'
        self.references = AutomationStore(self.root)

    def read(self, path):
        proof = self.references.reference(path)
        return json.loads((self.root / proof['path']).read_text()), proof

    @contextmanager
    def db(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.folder / 'state.sqlite3', timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2):
                raise InvalidContract('Unknown lineup execution database version')
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS executions(id TEXT PRIMARY KEY, scope TEXT NOT NULL, proposal_hash TEXT UNIQUE NOT NULL, state TEXT NOT NULL, value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY, execution_id TEXT NOT NULL, state TEXT NOT NULL, value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, value TEXT NOT NULL)')
            db.execute('PRAGMA user_version=2')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def event(self, db, kind, value):
        db.execute('INSERT INTO events(at,kind,value) VALUES (?,?,?)', (utc(self.clock()), kind, json.dumps(value)))

    def roster_conflict(self, db, scope):
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='roster_actions'").fetchone():
            if db.execute("SELECT 1 FROM roster_actions a JOIN roster_plans p ON a.plan_id=p.id WHERE p.scope=? AND a.state IN ('armed','outcome_unknown')", (scope,)).fetchone():
                raise InvalidContract('A roster transaction requires reconciliation before lineup execution')

    def active(self, db, execution_id):
        row = db.execute('SELECT * FROM executions WHERE id=?', (execution_id,)).fetchone()
        if not row or row['state'] == 'completed':
            raise InvalidContract('Execution is missing or already complete')
        value = json.loads(row['value'])
        self.roster_conflict(db, value['scope'])
        for proof in (value['proposal'], value['authority'], value['config'], value['owner_approval']):
            if self.references.reference(proof['path']) != proof:
                raise InvalidContract('Execution source changed')
        authority, _ = self.read(value['authority']['path'])
        if not instant(authority['issued_at']) <= self.clock() < instant(authority['expires_at']):
            raise InvalidContract('Supervised execution authority expired')
        if authority['mode'] == 'delegated':
            from lineup_authority import verify
            proposal, _ = self.read(value['proposal']['path'])
            verify(self, db, proposal, authority)
        return row, value

    def register(self, proposal_path, authority_path):
        proposal, proof = self.read(proposal_path)
        authority, authority_proof = self.read(authority_path)
        config, config_proof = self.read('config.json')
        check_document(proposal)
        phash = fingerprint(proposal)
        fields = ('league_id', 'roster_id', 'season', 'week')
        if proposal['league_id'] != config['league_id'] or any(authority.get(k) != proposal[k] for k in fields):
            raise InvalidContract('Execution authority has the wrong league or roster scope')
        if authority.get('schema_version') != 1 or authority.get('mode') not in ('supervised', 'delegated') or authority.get('proposal_hash') != phash:
            raise InvalidContract('Exact proposal approval in supervised mode is required')
        issued, expires = instant(authority['issued_at']), instant(authority['expires_at'])
        if not issued <= self.clock() < expires <= issued + 600:
            raise InvalidContract('Supervised authority must be current and expire within ten minutes')
        owner, owner_proof = self.read(authority['owner_approval'])
        if authority['mode'] == 'supervised' and (owner.get('basis') != 'explicit_owner_approval' or owner.get('proposal_hash') != phash):
            raise InvalidContract('Save owner approval of the exact proposal')
        scope = ':'.join(str(proposal[k]) for k in fields)
        value = {'id': uuid.uuid4().hex, 'proposal': proof, 'authority': authority_proof, 'config': config_proof,
                 'owner_approval': owner_proof, 'proposal_hash': phash, 'scope': scope,
                 'target': [a['player_id'] for a in sorted(proposal['assignments'], key=lambda a: a['slot_index'])]}
        with self.db() as db:
            self.roster_conflict(db, scope)
            if authority['mode'] == 'delegated':
                from lineup_authority import verify
                verify(self, db, proposal, authority)
            if db.execute("SELECT 1 FROM executions WHERE scope=? AND state!='completed'", (scope,)).fetchone():
                raise InvalidContract('Another execution in this scope requires completion or recovery')
            if db.execute('SELECT 1 FROM executions WHERE proposal_hash=?', (phash,)).fetchone():
                raise InvalidContract('This exact proposal already has an execution record')
            db.execute('INSERT INTO executions VALUES (?,?,?,?,?)', (value['id'], scope, phash, 'planned', json.dumps(value)))
            self.event(db, 'registered', value)
        return value

    def paired(self, api_path, native_path, proposal, *, after=None):
        api, api_proof = self.read(api_path)
        native, native_proof = self.read(native_path)
        self.check_pair(api, native, proposal, after=after)
        return api, native, [api_proof, native_proof]

    def check_pair(self, api, native, proposal, *, after=None):
        now = self.clock()
        if not api['evidence'] or any(not 0 <= now - instant(m['fetched_at']) <= (300 if name == 'user' else 60)
                                      for name, m in api['evidence'].items()):
            raise InvalidContract('API observation exceeds its freshness limit')
        if not 0 <= now - instant(native['observed_at']) <= 60 or native.get('full_reload') is not True:
            raise InvalidContract('Fresh full-reload browser evidence is required')
        if after and (instant(native['observed_at']) < after or any(instant(m['fetched_at']) < after for name, m in api['evidence'].items() if name != 'user')):
            raise InvalidContract('Reconciliation observations must follow the dispatched action')
        config, _ = self.read('config.json')
        if native.get('account') != config['username'] or native.get('url') != f"https://sleeper.com/leagues/{proposal['league_id']}/team":
            raise InvalidContract('Native account or team page differs')
        if any(native.get(k) != proposal[k] for k in ('league_id', 'roster_id', 'season', 'week')):
            raise InvalidContract('Native observation belongs to another lineup scope')
        if (api['league']['league_id'] != proposal['league_id'] or api['roster']['roster_id'] != proposal['roster_id']
                or api['season'] != proposal['season'] or api['week'] != proposal['week']):
            raise InvalidContract('API observation belongs to another lineup scope')
        if api['roster']['starters'] != api['matchup']['starters'] or native['starters'] != api['matchup']['starters']:
            raise InvalidContract('Browser, roster and matchup starters disagree')
        if sorted(native['owned_player_ids']) != sorted(api['roster']['players']):
            raise InvalidContract('Browser and API ownership differ')
        if not isinstance(native.get('locked_player_ids'), list) or native.get('lock_controls_observed') is not True:
            raise InvalidContract('Explicit native lock observations are required')

    def prepare(self, execution_id, snapshot, api_path, native_path, review_path=None):
        # SQLite serializes action preparation. Historical proposal files stay hash-bound.
        with self.db() as db:
            row, execution = self.active(db, execution_id)
            if db.execute("SELECT 1 FROM actions WHERE execution_id=? AND state IN ('armed','outcome_unknown','not_applied')", (execution_id,)).fetchone():
                raise InvalidContract('Prior action needs reconciliation or explicit recovery')
            proposal, _ = self.read(execution['proposal']['path'])
            api, native, proofs = self.paired(api_path, native_path, proposal)
            manifest_proof = self.references.reference(str(Path(snapshot) / 'manifest.json'))
            inputs = load(self.root / snapshot)
            if state_key(api) != state_key(inputs['final_context']):
                raise InvalidContract('Fresh API state differs from validation inputs')
            history_path = self.root / 'data/weekly' / str(proposal['season']) / str(proposal['week']) / 'locks.json'
            history = json.loads(history_path.read_text()) if history_path.exists() else {}
            result = validate(proposal, inputs, datetime.fromtimestamp(self.clock(), timezone.utc), history)
            authority, _ = self.read(execution['authority']['path'])
            if authority['mode'] == 'delegated' and (result['status'] != 'PASS' or review_path):
                raise InvalidContract('Delegated changes require PASS without a review override')
            review, review_proof = self.read(review_path) if review_path else (None, None)
            resolution = resolve(result, review, native, self.clock(), self.read)
            locked = set(result['locked_player_ids']) | set(native['locked_player_ids'])
            before, target = native['starters'], execution['target']
            if any(sid in locked and before[i] != target[i] for i, sid in enumerate(before)):
                raise InvalidContract('A native or recorded locked starter would move')
            validation_path = self.folder / 'validations' / (uuid.uuid4().hex + '.json')
            save_new(validation_path, {'validation': result, 'resolution': resolution, 'native': proofs[1], 'api': proofs[0]})
            if before == target:
                execution['completion'] = {'at': utc(self.clock()), 'validation': validation_path.relative_to(self.root).as_posix(), 'evidence': proofs}
                db.execute("UPDATE executions SET state='completed',value=? WHERE id=?", (json.dumps(execution), execution_id))
                self.event(db, 'verified_no_change', {'execution_id': execution_id, 'evidence': proofs})
                return {'status': 'completed', 'no_change_needed': True, 'platform_changes': False}
            i = next(i for i in range(len(target)) if target[i] != before[i])
            incoming, outgoing = target[i], before[i]
            if incoming in locked or outgoing in locked:
                raise InvalidContract('A native or recorded locked player would move')
            after = list(before)
            if incoming in before:
                other = before.index(incoming)
                other_slot = next(a['slot'] for a in proposal['assignments'] if a['slot_index'] == other)
                p = inputs['sleeper_players']['data'][outgoing]
                if not set(p.get('fantasy_positions') or [p['position']]) & ELIGIBLE[other_slot]:
                    raise InvalidContract('Intermediate swap would be illegal. Prepare a different reviewed proposal.')
                after[other] = outgoing
            after[i] = incoming
            authority, _ = self.read(execution['authority']['path'])
            expires = min(self.clock() + 30, instant(result['expires_at']), instant(authority['expires_at']),
                          instant(native['observed_at']) + 60,
                          *[instant(m['fetched_at']) + (300 if name == 'user' else 60) for name, m in api['evidence'].items()])
            action = {'action_id': uuid.uuid4().hex, 'execution_id': execution_id, 'token': uuid.uuid4().hex,
                      'before': before, 'after': after, 'slot_index': i, 'incoming': incoming, 'outgoing': outgoing,
                      'expires_at': utc(expires), 'prepared_at': utc(self.clock()), 'api_state': api,
                      'sources': proofs + [manifest_proof] + ([review_proof] if review_proof else []),
                      'snapshot': snapshot, 'validation': validation_path.relative_to(self.root).as_posix()}
            if history_path.exists():
                action['sources'].append(self.references.reference(history_path.relative_to(self.root).as_posix()))
            if review:
                action['sources'].append(self.references.reference(review['owner_approval']))
                action['sources'] += [self.references.reference(e['official']['evidence']) for e in review['resolutions'] if e.get('official')]
            db.execute('INSERT INTO actions VALUES (?,?,?,?)', (action['action_id'], execution_id, 'armed', json.dumps(action)))
            self.event(db, 'armed', action)
            return action

    def dispatch(self, action_id, token):
        with self.db() as db:
            row = db.execute('SELECT * FROM actions WHERE id=?', (action_id,)).fetchone()
            if not row or row['state'] != 'armed':
                raise InvalidContract('Action is not armed. Never replay a consumed action.')
            value = json.loads(row['value'])
            _, execution = self.active(db, value['execution_id'])
            authority, _ = self.read(execution['authority']['path'])
            if authority['mode'] == 'delegated':
                from lineup_authority import verify
                proposal, _ = self.read(execution['proposal']['path'])
                grant = verify(self, db, proposal, authority)
                # Count all dispatched actions, including uncertain outcomes.
                count = 0
                prefix = ':'.join(execution['scope'].split(':')[:3]) + ':'
                for prior in db.execute('SELECT a.value FROM actions a JOIN executions e ON a.execution_id=e.id WHERE substr(e.scope,1,?)=?', (len(prefix), prefix)):
                    action = json.loads(prior[0])
                    count += bool(action.get('dispatched_at') and instant(action['dispatched_at']) > self.clock() - 86400)
                if count >= grant['max_actions_per_day']:
                    raise InvalidContract('Delegated daily action limit reached')
            if value['token'] != token or self.clock() >= instant(value['expires_at']):
                raise InvalidContract('Action token is wrong or expired')
            for proof in value['sources']:
                if self.references.reference(proof['path']) != proof:
                    raise InvalidContract('Prepared action evidence changed')
            load(self.root / value['snapshot'])
            value['dispatched_at'] = utc(self.clock())
            db.execute("UPDATE actions SET state='outcome_unknown',value=? WHERE id=?", (json.dumps(value), action_id))
            db.execute("UPDATE executions SET state='outcome_unknown' WHERE id=?", (value['execution_id'],))
            self.event(db, 'dispatch_consumed', {'action_id': action_id, 'at': value['dispatched_at']})
        return {'action_id': action_id, 'status': 'outcome_unknown', 'one_supervised_browser_action': True,
                'incoming': value['incoming'], 'outgoing': value['outgoing'], 'slot_index': value['slot_index'],
                'execute_before': value['expires_at'], 'retry': False}

    def reconcile(self, action_id, api_path, native_path):
        with self.db() as db:
            row = db.execute('SELECT * FROM actions WHERE id=?', (action_id,)).fetchone()
            if not row or row['state'] != 'outcome_unknown':
                raise InvalidContract('Only an uncertain dispatched action can be reconciled')
            action = json.loads(row['value'])
            execution = json.loads(db.execute('SELECT value FROM executions WHERE id=?', (action['execution_id'],)).fetchone()[0])
            proposal, proof = self.read(execution['proposal']['path'])
            if proof != execution['proposal']:
                raise InvalidContract('Execution proposal changed')
            api, native, proofs = self.paired(api_path, native_path, proposal, after=instant(action['dispatched_at']))
            expected = copy.deepcopy(action['api_state'])
            expected['roster']['starters'] = list(api['roster']['starters'])
            expected['matchup']['starters'] = list(api['matchup']['starters'])
            if state_key(expected) != state_key(api):
                raise InvalidContract('Ownership, rules or lineup scope changed during execution')
            observed = native['starters']
            outcome = 'confirmed' if observed == action['after'] else 'not_applied' if observed == action['before'] else 'outcome_unknown'
            db.execute('UPDATE actions SET state=? WHERE id=?', (outcome, action_id))
            state = 'completed' if outcome == 'confirmed' and observed == execution['target'] else 'planned' if outcome == 'confirmed' else 'outcome_unknown'
            if state == 'completed':
                execution['completion'] = {'at': utc(self.clock()), 'validation': action['validation'], 'evidence': proofs}
            db.execute('UPDATE executions SET state=?,value=? WHERE id=?', (state, json.dumps(execution), action['execution_id']))
            self.event(db, 'reconciled', {'action_id': action_id, 'outcome': outcome, 'evidence': proofs})
        return {'action_id': action_id, 'outcome': outcome, 'execution_state': state, 'blind_retry_allowed': False}

    def recover(self, action_id, evidence_path):
        evidence, proof = self.read(evidence_path)
        with self.db() as db:
            row = db.execute('SELECT * FROM actions WHERE id=?', (action_id,)).fetchone()
            if not row or row['state'] not in ('armed', 'not_applied'):
                raise InvalidContract('Unknown dispatched effects cannot be declared safe to retry')
            value = json.loads(row['value'])
            if row['state'] == 'armed' and self.clock() < instant(value['expires_at']):
                raise InvalidContract('Wait for the unused action token to expire')
            if evidence.get('action_id') != action_id or evidence.get('basis') != 'explicit_owner_recovery' or not evidence.get('reason'):
                raise InvalidContract('Exact owner recovery evidence is required')
            db.execute("UPDATE actions SET state='retired' WHERE id=?", (action_id,))
            db.execute("UPDATE executions SET state='planned' WHERE id=?", (value['execution_id'],))
            self.event(db, 'recovered', {'action_id': action_id, 'evidence': proof})
        return {'status': 'fresh_preparation_required', 'action_id': action_id}

    def status(self):
        with self.db() as db:
            from lineup_authority import policy
            current = policy(db)
            enabled = current['enabled']
            if enabled:
                try:
                    from lineup_authority import checked
                    grant, _ = self.read(current['grant']['path'])
                    checked(self, db, grant)
                except (ValueError, OSError, KeyError):
                    enabled = False
            return {'executions': [dict(r) for r in db.execute('SELECT id,scope,proposal_hash,state FROM executions')],
                    'actions': [dict(r) for r in db.execute('SELECT id,execution_id,state FROM actions')],
                    'standing_autonomy_enabled': enabled}

    def reauthorize(self, execution_id, authority_path):
        authority, proof = self.read(authority_path)
        owner, owner_proof = self.read(authority['owner_approval'])
        with self.db() as db:
            row = db.execute('SELECT * FROM executions WHERE id=?', (execution_id,)).fetchone()
            if not row or row['state'] != 'planned' or db.execute("SELECT 1 FROM actions WHERE execution_id=? AND state IN ('armed','outcome_unknown','not_applied')", (execution_id,)).fetchone():
                raise InvalidContract('Resolve all prior actions before renewing authority')
            value = json.loads(row['value'])
            proposal, proposal_proof = self.read(value['proposal']['path'])
            if proposal_proof != value['proposal'] or any(authority.get(k) != proposal[k] for k in ('league_id', 'roster_id', 'season', 'week')):
                raise InvalidContract('Renewed authority differs from the execution scope')
            if authority.get('mode') != 'supervised' or authority.get('proposal_hash') != value['proposal_hash'] or owner.get('basis') != 'explicit_owner_approval' or owner.get('proposal_hash') != value['proposal_hash']:
                raise InvalidContract('Renewal requires exact supervised owner approval')
            start, end = instant(authority['issued_at']), instant(authority['expires_at'])
            if not start <= self.clock() < end <= start + 600:
                raise InvalidContract('Renewed authority must expire within ten minutes')
            value.update(authority=proof, owner_approval=owner_proof)
            db.execute('UPDATE executions SET value=? WHERE id=?', (json.dumps(value), execution_id))
            self.event(db, 'reauthorized', {'execution_id': execution_id, 'authority': proof, 'owner_approval': owner_proof})
        return {'execution_id': execution_id, 'fresh_preparation_required': True}

    def record_window(self, execution_id, kickoff, evidence_path):
        evidence, proof = self.read(evidence_path)
        now = self.clock()
        if not 0 < instant(kickoff) - now <= 5400:
            raise InvalidContract('A real supervised game window must be within ninety minutes before kickoff')
        if evidence.get('basis') != 'actual_owner_supervised_window' or evidence.get('execution_id') != execution_id or evidence.get('kickoff') != kickoff:
            raise InvalidContract('Save explicit evidence of this actual supervised game window')
        with self.db() as db:
            row = db.execute('SELECT * FROM executions WHERE id=?', (execution_id,)).fetchone()
            if not row or row['state'] != 'completed':
                raise InvalidContract('Window requires a completed execution with no unresolved outcome')
            value = json.loads(row['value'])
            completion = value['completion']
            if not 0 <= now - instant(completion['at']) <= 300:
                raise InvalidContract('Execution completion is not current for this game window')
            record, validation_proof = self.read(completion['validation'])
            validation = record['validation']
            if now >= instant(validation['expires_at']) or not any(p['game'] and instant(p['game']['kickoff']) == instant(kickoff) for p in validation['players']):
                raise InvalidContract('Window lacks current validation for a relevant starter game')
            window = {'schema_version': 1, 'execution_id': execution_id, 'scope': row['scope'], 'kickoff': kickoff,
                      'recorded_at': utc(now), 'evidence': proof, 'completion': completion, 'validation': validation_proof}
            path = self.folder / 'windows' / (fingerprint([row['scope'], instant(kickoff)]) + '.json')
            save_new(path, window)
            self.event(db, 'supervised_window', window)
        return {'saved': str(path), 'standing_autonomy_enabled': False}

    def assess(self, proposal_path, snapshot, api_path, native_path):
        proposal, proof = self.read(proposal_path)
        api, native, evidence = self.paired(api_path, native_path, proposal)
        inputs = load(self.root / snapshot)
        if state_key(api) != state_key(inputs['final_context']):
            raise InvalidContract('Current API state differs from validation snapshot')
        history_path = self.root / 'data/weekly' / str(proposal['season']) / str(proposal['week']) / 'locks.json'
        history = json.loads(history_path.read_text()) if history_path.exists() else {}
        result = validate(proposal, inputs, datetime.fromtimestamp(self.clock(), timezone.utc), history)
        result['issues_hash'] = fingerprint([i for i in result['issues'] if i['level'] == 'review'])
        result['native_evidence'] = evidence[1]
        result['api_evidence'] = evidence[0]
        path = self.folder / 'assessments' / (uuid.uuid4().hex + '.json')
        save_new(path, result)
        return {'saved': str(path), 'status': result['status'], 'issues': result['issues'],
                'proposal_hash': result['proposal_hash'], 'input_hash': result['input_hash'], 'state_key': result['state_key'],
                'issues_hash': result['issues_hash'], 'expires_at': result['expires_at'], 'platform_changes': False}


def observe(root, season, week):
    root = Path(root).resolve()
    config = json.loads((root / 'config.json').read_text())
    value = context(config, season, week, require_agreement=False)
    value['starters_agree'] = value['roster']['starters'] == value['matchup']['starters']
    path = root / 'data/lineup_execution/observations' / (uuid.uuid4().hex + '.json')
    save_new(path, value)
    return {'saved': str(path), 'roster_id': value['roster']['roster_id'], 'starters_agree': value['starters_agree'],
            'roster_starters': value['roster']['starters'], 'matchup_starters': value['matchup']['starters'],
            'acquisition': {'network_attempts': sum(m.get('network_attempts', 0) for m in value['evidence'].values()),
                            'cache_hits': sum(bool(m.get('cache_hit')) for m in value['evidence'].values())},
            'platform_changes': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('observe', 'collect'):
        read = sub.add_parser(name)
        read.add_argument('--season', type=int, required=True)
        read.add_argument('--week', type=int, required=True)
    sub.add_parser('status')
    promote = sub.add_parser('promote')
    promote.add_argument('--delegation', required=True)
    promote.add_argument('--tests', required=True)
    revoke = sub.add_parser('revoke')
    revoke.add_argument('--reason', required=True)
    delegated = sub.add_parser('authorize-delegated')
    delegated.add_argument('--proposal', required=True)
    register = sub.add_parser('register')
    register.add_argument('--proposal', required=True)
    register.add_argument('--authority', required=True)
    for name in ('prepare', 'assess'):
        command = sub.add_parser(name)
        command.add_argument('--execution-id' if name == 'prepare' else '--proposal', required=True)
        command.add_argument('--snapshot', required=True)
        command.add_argument('--api', required=True)
        command.add_argument('--native', required=True)
        if name == 'prepare':
            command.add_argument('--review')
    dispatch = sub.add_parser('dispatch')
    dispatch.add_argument('--action-id', required=True)
    dispatch.add_argument('--token', required=True)
    reconcile = sub.add_parser('reconcile')
    reconcile.add_argument('--action-id', required=True)
    reconcile.add_argument('--api', required=True)
    reconcile.add_argument('--native', required=True)
    recovery = sub.add_parser('recover')
    recovery.add_argument('--action-id', required=True)
    recovery.add_argument('--evidence', required=True)
    renew = sub.add_parser('reauthorize')
    renew.add_argument('--execution-id', required=True)
    renew.add_argument('--authority', required=True)
    window = sub.add_parser('record-window')
    window.add_argument('--execution-id', required=True)
    window.add_argument('--kickoff', required=True)
    window.add_argument('--evidence', required=True)
    args = parser.parse_args(argv)
    try:
        execution = Execution(args.root)
        if args.command == 'observe':
            result = observe(args.root, args.season, args.week)
        elif args.command == 'collect':
            config, _ = execution.read('config.json')
            snapshot = collect(config, args.season, args.week, root=execution.root, validation_only=True)
            result = {'snapshot': snapshot.relative_to(execution.root).as_posix(),
                      'api': (snapshot / 'final_context.json').relative_to(execution.root).as_posix(),
                      'acquisition': acquisition_summary(load(snapshot)), 'platform_changes': False}
        elif args.command == 'status':
            result = execution.status()
        elif args.command == 'promote':
            from lineup_authority import promote
            result = promote(execution, args.delegation, args.tests)
        elif args.command == 'revoke':
            from lineup_authority import revoke
            result = revoke(execution, args.reason)
        elif args.command == 'authorize-delegated':
            from lineup_authority import authorize
            result = authorize(execution, args.proposal)
        elif args.command == 'register':
            result = execution.register(args.proposal, args.authority)
        elif args.command == 'prepare':
            result = execution.prepare(args.execution_id, args.snapshot, args.api, args.native, args.review)
        elif args.command == 'assess':
            result = execution.assess(args.proposal, args.snapshot, args.api, args.native)
        elif args.command == 'dispatch':
            result = execution.dispatch(args.action_id, args.token)
        elif args.command == 'reconcile':
            result = execution.reconcile(args.action_id, args.api, args.native)
        elif args.command == 'reauthorize':
            result = execution.reauthorize(args.execution_id, args.authority)
        elif args.command == 'record-window':
            result = execution.record_window(args.execution_id, args.kickoff, args.evidence)
        else:
            result = execution.recover(args.action_id, args.evidence)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, sqlite3.Error) as error:
        print(json.dumps({'status': 'blocked', 'error_type': type(error).__name__,
                          'message': str(error) if isinstance(error, InvalidContract) else 'Inspect provider evidence. No browser action was performed.'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
