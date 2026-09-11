"""Supervised roster transaction plans and durable native/API reconciliation."""
import argparse
import copy
import json
from pathlib import Path
import uuid

from automation_store import InvalidContract, instant, utc
from lineup_execution import Execution
from sleeper import get_sleeper
from storage import save_new
from weekly_data import context, fingerprint

KINDS = {'waiver', 'free_agent', 'drop', 'ir_place', 'ir_activate', 'cancel_claim'}
TERMINAL = {'won', 'lost', 'cancelled', 'applied', 'invalidated'}


def draft_plan(observation, steps, protected, now):
    ctx = observation['context']
    return {'schema_version': 1, 'mode': 'supervised', 'league_id': ctx['league']['league_id'],
            'roster_id': ctx['roster']['roster_id'], 'season': ctx['season'], 'week': ctx['week'],
            'created_at': utc(now), 'expires_at': utc(now + 86400), 'rules_hash': rules_key(ctx),
            'waiver_position': ctx['roster'].get('settings', {}).get('waiver_position'),
            'protected_player_ids': protected, 'steps': steps, 'observation_hash': fingerprint(observation)}


def collect(root, season, week):
    root = Path(root)
    config = json.loads((root / 'config.json').read_text())
    current = context(config, season, week)
    rosters = get_sleeper(f"league/{config['league_id']}/rosters", with_metadata=True, retries=0)
    transactions = get_sleeper(f"league/{config['league_id']}/transactions/{week}", with_metadata=True, retries=0)
    if (not isinstance(rosters['data'], list) or len(rosters['data']) != current['league']['total_rosters']
            or len({r['roster_id'] for r in rosters['data']}) != len(rosters['data'])):
        raise InvalidContract('League ownership collection is incomplete or duplicated')
    ours = [r for r in rosters['data'] if r['roster_id'] == current['roster']['roster_id']]
    if len(ours) != 1 or ours[0] != current['roster']:
        raise InvalidContract('Roster changed during transaction collection')
    owners = [sid for r in rosters['data'] for sid in (r.get('players') or [])]
    if len(owners) != len(set(owners)):
        raise InvalidContract('A player has ambiguous league ownership')
    value = {'schema_version': 1, 'context': current, 'rosters': rosters, 'transactions': transactions}
    path = root / 'data/roster_operations/observations' / (uuid.uuid4().hex + '.json')
    save_new(path, value)
    meta = [*current['evidence'].values(), rosters, transactions]
    return {'saved': str(path), 'network_attempts': sum(m.get('network_attempts', 0) for m in meta),
            'cache_hits': sum(bool(m.get('cache_hit')) for m in meta), 'platform_changes': False}


def tables(db):
    db.execute('CREATE TABLE IF NOT EXISTS roster_plans(id TEXT PRIMARY KEY, scope TEXT NOT NULL, hash TEXT UNIQUE NOT NULL, value TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS roster_actions(id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, ordinal INTEGER NOT NULL, state TEXT NOT NULL, value TEXT NOT NULL, UNIQUE(plan_id,ordinal))')


def rules_key(ctx):
    league = ctx['league']
    return fingerprint({k: league[k] for k in ('league_id', 'settings', 'scoring_settings', 'roster_positions')} |
                       {'roster_id': ctx['roster']['roster_id'], 'owner_id': ctx['roster']['owner_id'], 'season': ctx['season'], 'week': ctx['week']})


class RosterOperations(Execution):
    def observations(self, api_path, native_path, plan, *, after=None):
        api, ap = self.read(api_path)
        native, np = self.read(native_path)
        ctx = api['context']
        self.check_pair(ctx, native, plan, after=after)
        for name in ('rosters', 'transactions'):
            fetched = instant(api[name]['fetched_at'])
            if not 0 <= self.clock() - fetched <= 60 or (after is not None and fetched < after):
                raise InvalidContract('Transaction API evidence is stale or predates the action')
        if sorted(native['reserve']) != sorted(ctx['roster'].get('reserve') or []):
            raise InvalidContract('Native and API reserve slots disagree')
        if native.get('transactions_observed') is not True or not isinstance(native.get('pending_claims'), list):
            raise InvalidContract('Observe the private pending-claims page explicitly')
        return api, native, [ap, np]

    def register_plan(self, plan_path, approval_path):
        plan, pp = self.read(plan_path)
        approval, op = self.read(approval_path)
        phash = fingerprint(plan)
        if (plan.get('schema_version') != 1 or plan.get('mode') != 'supervised'
                or approval.get('basis') != 'explicit_owner_transaction_approval'
                or approval.get('plan_hash') != phash or not approval.get('owner_statement')):
            raise InvalidContract('An exact owner-approved supervised transaction plan is required')
        steps = plan.get('steps', [])
        if not 1 <= len(steps) <= 10 or any(s.get('kind') not in KINDS for s in steps):
            raise InvalidContract('Use one through ten supported transaction steps')
        if len({s.get('claim_key') for s in steps}) != len(steps) or any(not s.get('claim_key') for s in steps):
            raise InvalidContract('Transaction steps require unique claim keys')
        if any(s.get('depends_on') is not None and (type(s['depends_on']) is not int or not 0 <= s['depends_on'] < i) for i, s in enumerate(steps)):
            raise InvalidContract('Claim dependencies must refer to an earlier step')
        if not instant(plan['created_at']) <= self.clock() < instant(plan['expires_at']) <= instant(plan['created_at']) + 7 * 86400:
            raise InvalidContract('Transaction plan expired or exceeds seven days')
        config, cp = self.read('config.json')
        if plan['league_id'] != config['league_id']:
            raise InvalidContract('Transaction plan is for another league')
        scope = ':'.join(str(plan[k]) for k in ('league_id', 'roster_id', 'season', 'week'))
        value = {'id': uuid.uuid4().hex, 'scope': scope, 'plan': pp, 'approval': op, 'config': cp, 'hash': phash}
        with self.db() as db:
            tables(db)
            if db.execute('SELECT 1 FROM roster_plans WHERE hash=?', (phash,)).fetchone():
                raise InvalidContract('This exact transaction plan already exists')
            db.execute('INSERT INTO roster_plans VALUES (?,?,?,?)', (value['id'], scope, phash, json.dumps(value)))
            self.event(db, 'roster_plan_registered', value)
        return value

    def plan(self, db, plan_id):
        tables(db)
        row = db.execute('SELECT * FROM roster_plans WHERE id=?', (plan_id,)).fetchone()
        if not row:
            raise InvalidContract('Unknown transaction plan')
        value = json.loads(row['value'])
        for key in ('plan', 'approval', 'config'):
            if self.references.reference(value[key]['path']) != value[key]:
                raise InvalidContract('Approved transaction source changed')
        plan, _ = self.read(value['plan']['path'])
        return value, plan

    def prepare_step(self, plan_id, ordinal, api_path, native_path, valuation_path=None):
        with self.db() as db:
            record, plan = self.plan(db, plan_id)
            if not self.clock() < instant(plan['expires_at']):
                raise InvalidContract('Transaction plan expired')
            if type(ordinal) is not int or not 0 <= ordinal < len(plan['steps']):
                raise InvalidContract('Unknown transaction step')
            if db.execute("SELECT 1 FROM executions WHERE scope=? AND state!='completed'", (record['scope'],)).fetchone():
                raise InvalidContract('A lineup execution requires completion first')
            if db.execute("SELECT 1 FROM roster_actions a JOIN roster_plans p ON a.plan_id=p.id WHERE p.scope=? AND a.state IN ('armed','outcome_unknown')", (record['scope'],)).fetchone():
                raise InvalidContract('Another roster action needs reconciliation')
            if db.execute('SELECT 1 FROM roster_actions WHERE plan_id=? AND ordinal=?', (plan_id, ordinal)).fetchone():
                raise InvalidContract('This transaction step already has an action; never replay it')
            step = plan['steps'][ordinal]
            for i in range(ordinal):
                prior = db.execute('SELECT state,value FROM roster_actions WHERE plan_id=? AND ordinal=?', (plan_id, i)).fetchone()
                if not prior or prior[0] not in TERMINAL | {'pending'}:
                    raise InvalidContract('Submit and reconcile earlier claims in order')
                earlier = plan['steps'][i]
                if prior[0] in ('won', 'applied') and step.get('drop') and earlier.get('drop') == step['drop']:
                    raise InvalidContract('Earlier success consumed this shared drop; create a fresh plan')
                if step.get('depends_on') == i and prior[0] not in ('lost', 'cancelled', 'invalidated'):
                    raise InvalidContract('Conditional claim waits for its earlier result')
            api, native, proofs = self.observations(api_path, native_path, plan)
            ctx = api['context']
            if rules_key(ctx) != plan['rules_hash']:
                raise InvalidContract('League rules or ownership identity changed')
            if native.get('acquisitions_unlocked') is not True or native.get('rules_confirmed') is not True:
                raise InvalidContract('Native acquisition restrictions require verification')
            owned = set(ctx['roster']['players'])
            reserve = set(ctx['roster'].get('reserve') or [])
            add, drop, kind = step.get('add'), step.get('drop'), step['kind']
            if kind in ('waiver', 'free_agent') and ctx['league']['settings'].get('disable_adds', 0) != 0:
                raise InvalidContract('The league API disables acquisitions')
            if drop and (drop not in owned or drop in native['locked_player_ids']):
                raise InvalidContract('Drop is no longer owned or is locked')
            if drop in ctx['matchup']['starters'] or (kind == 'ir_place' and add in ctx['matchup']['starters']):
                raise InvalidContract('Move the unlocked starter to the bench through a separate approved lineup plan first')
            if kind not in ('waiver', 'cancel_claim') and any(c.get('drop') == (drop or add) for c in native['pending_claims']):
                raise InvalidContract('Resolve pending claims that depend on this player before changing the roster')
            if drop in plan.get('protected_player_ids', []):
                approval, _ = self.read(record['approval']['path'])
                if drop not in approval.get('explicit_protected_drops', []):
                    raise InvalidContract('Protected drop requires explicit approval of that player')
            owner_ids = {sid for r in api['rosters']['data'] for sid in (r.get('players') or [])}
            if kind in ('waiver', 'free_agent'):
                if not add or add in owner_ids or add == drop:
                    raise InvalidContract('Acquisition target is owned or invalid')
                candidates = native.get('candidates', {})
                candidate = candidates.get(add, {})
                if candidate.get('action') != ('Claim' if kind == 'waiver' else 'Add'):
                    raise InvalidContract('Native candidate action differs from the plan')
                if kind == 'waiver':
                    if native.get('waiver_type') != 'Rolling Waivers':
                        raise InvalidContract('This planner supports verified rolling waivers only')
                    if (candidate.get('deadline') != step.get('deadline') or not self.clock() < instant(candidate['deadline'])
                            or ctx['roster'].get('settings', {}).get('waiver_position') != plan['waiver_position']):
                        raise InvalidContract('Claim deadline or rolling priority changed')
                if not valuation_path:
                    raise InvalidContract('A complete roster comparison is required')
                valuation, vp = self.read(valuation_path)
                if (valuation.get('kind') != 'roster_comparison' or valuation.get('status') != 'review_required'
                        or not instant(valuation['created_at']) <= self.clock() < instant(valuation['expires_at'])
                        or valuation.get('owned_before') != sorted(owned)
                        or valuation.get('add') != [add] or valuation.get('drop') != ([drop] if drop else [])
                        or valuation.get('specialist_streaming_eligible') is not True):
                    raise InvalidContract('Roster valuation is incomplete or differs from this action')
                from season_strategy import compare
                pool, pool_proof = self.read(valuation['pool_path'])
                if pool.get('rules_hash') != plan['rules_hash'] or pool.get('league_id') != plan['league_id'] or pool.get('season') != plan['season']:
                    raise InvalidContract('Forecast pool belongs to different rules or season')
                computed = compare(pool, sorted(owned), [add], [drop] if drop else [],
                                   priority_cost=valuation['rolling_priority_cost'], bench_weight=valuation['before']['bench_weight'])
                if any(valuation.get(k) != v for k, v in computed.items()):
                    raise InvalidContract('Roster comparison differs from its source forecasts')
                proofs.append(pool_proof)
                proofs.append(vp)
            elif kind == 'cancel_claim':
                if add or drop or len([c for c in native['pending_claims'] if c.get('claim_id') == step.get('platform_claim_id')]) != 1:
                    raise InvalidContract('Cancellation requires the exact visible pending claim')
            elif kind == 'drop':
                if not drop or add:
                    raise InvalidContract('A drop step requires exactly one drop')
            elif kind in ('ir_place', 'ir_activate'):
                if drop or add not in owned or add in native['locked_player_ids']:
                    raise InvalidContract('IR step cannot add ownership, drop a player or move a lock')
                capacity = ctx['league']['settings']['reserve_slots']
                if kind == 'ir_place':
                    if capacity <= len(reserve) or add in reserve or add not in native.get('ir_eligible_player_ids', []):
                        raise InvalidContract('No verified eligible IR slot is available')
                elif add not in reserve:
                    raise InvalidContract('Activation target is not in IR')
            if native.get('ir_roster_legal') is not True and kind not in ('ir_activate', 'drop', 'cancel_claim'):
                raise InvalidContract('Resolve the native IR roster restriction first')
            after = owned - ({drop} if drop else set())
            after_reserve = reserve - ({drop} if drop else set())
            if kind in ('waiver', 'free_agent'):
                after.add(add)
            elif kind == 'ir_place':
                after_reserve.add(add)
            elif kind == 'ir_activate':
                after_reserve.remove(add)
            main_capacity = len([s for s in ctx['league']['roster_positions'] if s not in ('IR', 'TAXI')])
            if len(after - after_reserve) > main_capacity:
                raise InvalidContract('IR activation or acquisition exceeds the main roster capacity')
            if any(c.get('add') == add for c in native['pending_claims']) and kind == 'waiver':
                raise InvalidContract('An existing private claim already targets this player')
            if kind == 'waiver':
                expected_pending = []
                for prior in db.execute("SELECT value FROM roster_actions WHERE plan_id=? AND state='pending' ORDER BY ordinal", (plan_id,)):
                    prior = json.loads(prior[0])
                    expected_pending.append(prior.get('platform_claim_id'))
                if [c.get('claim_id') for c in native['pending_claims']] != expected_pending:
                    raise InvalidContract('Unmanaged or reordered pending claims require a new reviewed plan')
            action = {'id': uuid.uuid4().hex, 'plan_id': plan_id, 'ordinal': ordinal, 'step': step,
                      'token': uuid.uuid4().hex, 'prepared_at': utc(self.clock()),
                      'expires_at': utc(min(self.clock() + 30, instant(plan['expires_at']), instant(native['observed_at']) + 60,
                                           instant(api['rosters']['fetched_at']) + 60, instant(api['transactions']['fetched_at']) + 60,
                                           *[instant(m['fetched_at']) + (300 if name == 'user' else 60) for name,m in ctx['evidence'].items()])),
                      'sources': proofs, 'rules_hash': rules_key(ctx), 'before': sorted(owned), 'after': sorted(after),
                      'before_reserve': sorted(reserve), 'after_reserve': sorted(after_reserve),
                      'before_claims': native['pending_claims']}
            db.execute('INSERT INTO roster_actions VALUES (?,?,?,?,?)', (action['id'], plan_id, ordinal, 'armed', json.dumps(action)))
            self.event(db, 'roster_action_armed', action)
        return action

    def dispatch_step(self, action_id, token):
        with self.db() as db:
            tables(db)
            row = db.execute('SELECT * FROM roster_actions WHERE id=?', (action_id,)).fetchone()
            if not row or row['state'] != 'armed':
                raise InvalidContract('Roster action is not armed; never replay it')
            action = json.loads(row['value'])
            record, plan = self.plan(db, action['plan_id'])
            if token != action['token'] or self.clock() >= instant(action['expires_at']):
                raise InvalidContract('Roster action token is wrong or expired')
            if db.execute("SELECT 1 FROM executions WHERE scope=? AND state!='completed'", (record['scope'],)).fetchone():
                raise InvalidContract('A conflicting lineup execution appeared')
            for proof in action['sources']:
                if self.references.reference(proof['path']) != proof:
                    raise InvalidContract('Prepared roster evidence changed')
            action['dispatched_at'] = utc(self.clock())
            db.execute("UPDATE roster_actions SET state='outcome_unknown',value=? WHERE id=?", (json.dumps(action), action_id))
            self.event(db, 'roster_dispatch_consumed', {'action_id': action_id})
        return {'action_id': action_id, 'step': action['step'], 'execute_before': action['expires_at'],
                'status': 'outcome_unknown', 'browser_action_required': True, 'retry': False}

    def reconcile_step(self, action_id, api_path, native_path):
        with self.db() as db:
            tables(db)
            row = db.execute('SELECT * FROM roster_actions WHERE id=?', (action_id,)).fetchone()
            if not row or row['state'] not in ('outcome_unknown', 'pending'):
                raise InvalidContract('Only dispatched or pending transactions need reconciliation')
            action = json.loads(row['value'])
            record, plan = self.plan(db, action['plan_id'])
            api, native, proofs = self.observations(api_path, native_path, plan, after=instant(action['dispatched_at']))
            if rules_key(api['context']) != action['rules_hash']:
                raise InvalidContract('Transaction rules or owner identity changed')
            observed = sorted(api['context']['roster']['players'])
            reserve = sorted(api['context']['roster'].get('reserve') or [])
            step = action['step']
            outcome = 'outcome_unknown'
            if step['kind'] == 'waiver':
                matches = [c for c in native['pending_claims'] if c.get('add') == step['add'] and c.get('drop') == step.get('drop')]
                results = [r for r in native.get('claim_results', []) if r.get('claim_key') == step['claim_key']
                           and r.get('add') == step['add'] and r.get('drop') == step.get('drop')]
                if len(matches) == 1 and observed == action['before'] and reserve == action['before_reserve']:
                    other_claims = [c for c in native['pending_claims'] if c is not matches[0]]
                    if other_claims != action['before_claims'] or matches[0].get('priority') != len(action['before_claims']) + 1:
                        raise InvalidContract('Native pending-claim order differs from the approved plan')
                    action['platform_claim_id'] = matches[0]['claim_id']
                    outcome = 'pending'
                elif len(results) == 1 and results[0].get('status') in ('won', 'lost', 'cancelled'):
                    result = results[0]
                    if action.get('platform_claim_id') and result.get('claim_id') != action['platform_claim_id']:
                        raise InvalidContract('Claim result identity differs from the pending claim')
                    if result['status'] == 'won':
                        tx = [t for t in api['transactions']['data'] if str(t.get('transaction_id')) == str(result.get('transaction_id'))
                              and t.get('status') == 'complete' and t.get('adds', {}).get(step['add']) == plan['roster_id']
                              and (not step.get('drop') or t.get('drops', {}).get(step['drop']) == plan['roster_id'])]
                        if len(tx) == 1 and observed == action['after'] and reserve == action['after_reserve']:
                            outcome = 'won'
                    elif not matches:
                        explained = [(action['before'], action['before_reserve'])]
                        for earlier in db.execute("SELECT value FROM roster_actions WHERE plan_id=? AND state IN ('won','applied')", (action['plan_id'],)):
                            earlier = json.loads(earlier[0])
                            explained.append((earlier['after'], earlier['after_reserve']))
                        if (observed, reserve) in explained:
                            outcome = result['status']
            elif step['kind'] == 'cancel_claim':
                results = [r for r in native.get('claim_results', []) if r.get('claim_id') == step['platform_claim_id'] and r.get('status') == 'cancelled']
                if (len(results) == 1 and not any(c.get('claim_id') == step['platform_claim_id'] for c in native['pending_claims'])
                        and observed == action['before'] and reserve == action['before_reserve']):
                    outcome = 'cancelled'
            elif observed == action['after'] and reserve == action['after_reserve']:
                outcome = 'applied'
            action['last_observation'] = proofs
            db.execute('UPDATE roster_actions SET state=?,value=? WHERE id=?', (outcome, json.dumps(action), action_id))
            self.event(db, 'roster_reconciled', {'action_id': action_id, 'outcome': outcome, 'evidence': proofs})
        return {'action_id': action_id, 'outcome': outcome, 'blind_retry_allowed': False}

    def roster_status(self):
        with self.db() as db:
            tables(db)
            return {'plans': [dict(r) for r in db.execute('SELECT id,scope,hash FROM roster_plans')],
                    'actions': [dict(r) for r in db.execute('SELECT id,plan_id,ordinal,state FROM roster_actions')],
                    'autonomous_transactions_enabled': False}

    def retire_unused(self, action_id, evidence_path):
        evidence, proof = self.read(evidence_path)
        with self.db() as db:
            tables(db)
            row = db.execute('SELECT state,value FROM roster_actions WHERE id=?', (action_id,)).fetchone()
            if not row or row[0] != 'armed' or self.clock() < instant(json.loads(row[1])['expires_at']):
                raise InvalidContract('Only an expired undispatched roster action can be retired')
            if evidence.get('basis') != 'explicit_owner_recovery' or evidence.get('action_id') != action_id or not evidence.get('reason'):
                raise InvalidContract('Exact owner recovery evidence is required')
            db.execute("UPDATE roster_actions SET state='invalidated' WHERE id=?", (action_id,))
            self.event(db, 'roster_unused_retired', {'action_id': action_id, 'evidence': proof})
        return {'status': 'new_plan_required', 'platform_changes': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    sub = p.add_subparsers(dest='command', required=True)
    read = sub.add_parser('collect')
    read.add_argument('--season', type=int, required=True)
    read.add_argument('--week', type=int, required=True)
    sub.add_parser('status')
    plan = sub.add_parser('plan')
    plan.add_argument('--api', required=True)
    plan.add_argument('--steps', required=True)
    plan.add_argument('--protected', nargs='*', default=[])
    plan.add_argument('--output', required=True)
    register = sub.add_parser('register')
    register.add_argument('--plan', required=True)
    register.add_argument('--approval', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--plan-id', required=True)
    prepare.add_argument('--ordinal', type=int, required=True)
    prepare.add_argument('--api', required=True)
    prepare.add_argument('--native', required=True)
    prepare.add_argument('--valuation')
    dispatch = sub.add_parser('dispatch')
    dispatch.add_argument('--action-id', required=True)
    dispatch.add_argument('--token', required=True)
    reconcile = sub.add_parser('reconcile')
    reconcile.add_argument('--action-id', required=True)
    reconcile.add_argument('--api', required=True)
    reconcile.add_argument('--native', required=True)
    retire = sub.add_parser('retire-unused')
    retire.add_argument('--action-id', required=True)
    retire.add_argument('--evidence', required=True)
    a = p.parse_args()
    engine = RosterOperations(a.root)
    if a.command == 'collect': result = collect(a.root, a.season, a.week)
    elif a.command == 'plan':
        import time
        result = draft_plan(json.loads(Path(a.api).read_text()), json.loads(Path(a.steps).read_text()), a.protected, time.time())
        save_new(Path(a.output), result)
    elif a.command == 'status': result = engine.roster_status()
    elif a.command == 'register': result = engine.register_plan(a.plan, a.approval)
    elif a.command == 'prepare': result = engine.prepare_step(a.plan_id, a.ordinal, a.api, a.native, a.valuation)
    elif a.command == 'dispatch': result = engine.dispatch_step(a.action_id, a.token)
    elif a.command == 'retire-unused': result = engine.retire_unused(a.action_id, a.evidence)
    else: result = engine.reconcile_step(a.action_id, a.api, a.native)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
