"""Limited lineup delegation. All policy mutations use the execution transaction."""
import json
import uuid

from automation_store import InvalidContract, instant, utc
from storage import save_new
from weekly_data import fingerprint
from system_acceptance import source_digest


def policy(db):
    db.execute('CREATE TABLE IF NOT EXISTS lineup_authority(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)')
    row = db.execute('SELECT value FROM lineup_authority WHERE id=1').fetchone()
    return json.loads(row[0]) if row else {'enabled': False}


def checked(engine, db, proposal):
    current = policy(db)
    if not current['enabled']:
        raise InvalidContract('Standing lineup authority is disabled')
    for proof in current['sources']:
        if engine.references.reference(proof['path']) != proof:
            raise InvalidContract('Promotion evidence or delegation changed')
    if current['source_digest'] != source_digest(engine.root):
        raise InvalidContract('Code changed after promotion; repeat offline acceptance and promotion')
    grant, _ = engine.read(current['grant']['path'])
    if any(grant[k] != proposal[k] for k in ('league_id', 'roster_id', 'season')):
        raise InvalidContract('Delegation scope differs from the proposal')
    if not instant(grant['issued_at']) <= engine.clock() < instant(grant['expires_at']):
        raise InvalidContract('Standing lineup delegation expired')
    return current, grant


def promote(engine, grant_path, tests_path):
    grant, grant_proof = engine.read(grant_path)
    tests, tests_proof = engine.read(tests_path)
    if (grant.get('schema_version') != 1 or grant.get('basis') != 'explicit_owner_lineup_delegation'
            or grant.get('operations') != ['unlocked_starters'] or not grant.get('owner_statement')):
        raise InvalidContract('Explicit, limited owner lineup delegation is required')
    start, end = instant(grant['issued_at']), instant(grant['expires_at'])
    if not start <= engine.clock() < end <= start + 7 * 86400:
        raise InvalidContract('Delegation must be current and expire within seven days')
    if type(grant.get('max_actions_per_day')) is not int or not 1 <= grant['max_actions_per_day'] <= 20:
        raise InvalidContract('An action limit from one through twenty is required')
    if (tests.get('basis') != 'verified_failure_exercises' or tests.get('failed') != 0
            or not tests.get('passed') or tests.get('command') != 'python3 -m unittest discover -v'
            or tests.get('source_digest') != source_digest(engine.root)):
        raise InvalidContract('Save the passing full-suite failure-exercise evidence')
    sources = [grant_proof, tests_proof, engine.references.reference('config.json')]
    with engine.db() as db:
        policy(db)
        config, _ = engine.read('config.json')
        if grant['league_id'] != config['league_id']:
            raise InvalidContract('Delegation is for another configured league')
        prefix = ':'.join(str(grant[k]) for k in ('league_id', 'roster_id', 'season')) + ':'
        if any(r['scope'].startswith(prefix) for r in db.execute("SELECT scope FROM executions WHERE state!='completed'")):
            raise InvalidContract('Resolve every incomplete execution before promotion')
        windows = {}
        for row in db.execute("SELECT value FROM events WHERE kind='supervised_window'"):
            window = json.loads(row[0])
            if not window['scope'].startswith(prefix):
                continue
            path = engine.folder / 'windows' / (fingerprint([window['scope'], instant(window['kickoff'])]) + '.json')
            saved, proof = engine.read(path.relative_to(engine.root).as_posix())
            if saved != window:
                raise InvalidContract('Saved game-window evidence changed')
            for evidence in [window['evidence'], window['validation'], *window['completion']['evidence']]:
                if engine.references.reference(evidence['path']) != evidence:
                    raise InvalidContract('Game-window source evidence changed')
                sources.append(evidence)
            execution = db.execute('SELECT state FROM executions WHERE id=?', (window['execution_id'],)).fetchone()
            if not execution or execution[0] != 'completed':
                raise InvalidContract('A game-window execution is unresolved')
            windows[instant(window['kickoff'])] = proof
        if len(windows) < 2:
            raise InvalidContract('Two distinct supervised game windows are required')
        sources.extend(windows.values())
        value = {'enabled': True, 'generation': uuid.uuid4().hex, 'promoted_at': utc(engine.clock()),
                 'grant': grant_proof, 'sources': sources, 'game_windows': len(windows), 'source_digest': tests['source_digest']}
        db.execute('INSERT OR REPLACE INTO lineup_authority VALUES (1,?)', (json.dumps(value),))
        engine.event(db, 'lineup_authority_promoted', value)
    return value


def revoke(engine, reason):
    if not reason.strip():
        raise InvalidContract('A revocation reason is required')
    with engine.db() as db:
        value = policy(db)
        value.update(enabled=False, revoked_at=utc(engine.clock()), reason=reason)
        db.execute('INSERT OR REPLACE INTO lineup_authority VALUES (1,?)', (json.dumps(value),))
        engine.event(db, 'lineup_authority_revoked', value)
    return {'standing_autonomy_enabled': False}


def authorize(engine, proposal_path):
    proposal, _ = engine.read(proposal_path)
    with engine.db() as db:
        current, grant = checked(engine, db, proposal)
        value = {k: proposal[k] for k in ('league_id', 'roster_id', 'season', 'week')}
        value.update(schema_version=1, mode='delegated', proposal_hash=fingerprint(proposal),
                     generation=current['generation'], issued_at=utc(engine.clock()),
                     expires_at=utc(min(engine.clock() + 600, instant(grant['expires_at']))),
                     owner_approval=current['grant']['path'])
        path = engine.folder / 'authority' / (uuid.uuid4().hex + '.json')
        save_new(path, value)
        engine.event(db, 'delegated_proposal_authority', value)
    return {'saved': path.relative_to(engine.root).as_posix(), 'platform_changes': False}


def verify(engine, db, proposal, authority):
    current, grant = checked(engine, db, proposal)
    if authority.get('generation') != current['generation'] or authority.get('owner_approval') != current['grant']['path']:
        raise InvalidContract('Proposal authority belongs to an obsolete delegation')
    return grant
