"""Weekly domain collection; public provider reads only, no draft dependencies."""
from fantasy_agent.paths import ROOT as PROJECT_ROOT
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

from fantasy_agent.providers.sleeper import get_sleeper
from fantasy_agent.core.project_config import check_user
from fantasy_agent.providers.fantasypros import get_fantasypros, FantasyPros
from fantasy_agent.providers.nflverse import get_nflverse
from fantasy_agent.core.storage import save_atomic

ROOT = PROJECT_ROOT


def stamp():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def context(config, season, week, *, require_agreement=True):
    evidence = {}
    def read(name, path):
        result = get_sleeper(path, with_metadata=True, retries=0)
        evidence[name] = {k: v for k, v in result.items() if k != 'data'}
        return result['data']
    league_id = config['league_id']
    league = read('league', f'league/{league_id}')
    if (not isinstance(league, dict) or league.get('league_id') != league_id
            or str(league.get('season')) != str(season) or league.get('sport') != 'nfl'):
        raise ValueError('League scope mismatch')
    state = read('nfl_state', 'state/nfl')
    if (str(state.get('season')) != str(season) or state.get('season_type') != 'regular'
            or int(state.get('week', 0)) != week):
        raise ValueError('Live run requires the current regular-season NFL week')
    user = read('user', f"user/{config['username']}")
    check_user(config, user)
    rosters = read('rosters', f'league/{league_id}/rosters')
    if (not isinstance(rosters, list) or len(rosters) != league.get('total_rosters')
            or any(not isinstance(r, dict) for r in rosters)):
        raise ValueError('Incomplete rosters')
    ours = [r for r in rosters if r.get('owner_id') == user.get('user_id')]
    if not user.get('user_id') or len(ours) != 1:
        raise ValueError('Ambiguous roster ownership')
    matches = read('matchups', f'league/{league_id}/matchups/{week}')
    ours_match = [m for m in matches if m.get('roster_id') == ours[0]['roster_id']]
    if len(ours_match) != 1:
        raise ValueError('Our weekly matchup is missing or ambiguous')
    roster, matchup = ours[0], ours_match[0]
    if require_agreement and roster.get('starters') != matchup.get('starters'):
        raise ValueError('Roster and weekly starters disagree; rerun after platform settles')
    if not isinstance(roster.get('players'), list) or not isinstance(matchup.get('starters'), list):
        raise ValueError('Missing ownership or starters')
    if any(not isinstance(x, str) for x in roster['players']):
        raise ValueError('Invalid owned player IDs')
    if int(league['settings'].get('max_subs', 0)) != 0:
        raise ValueError('AutoSubs enabled: explicit substitution-state support required')
    return {'league': league, 'roster': roster, 'matchup': matchup, 'user': user,
            'season': season, 'week': week, 'evidence': evidence, 'fetched_at': stamp()}


def state_key(ctx):
    return fingerprint({k: ctx[k] for k in ('season', 'week')} | {
        'league_id': ctx['league']['league_id'], 'settings': ctx['league']['settings'],
        'scoring': ctx['league']['scoring_settings'], 'slots': ctx['league']['roster_positions'],
        'owned': sorted(ctx['roster']['players']), 'starters': ctx['matchup']['starters'],
        'roster_id': ctx['roster']['roster_id']})


def collect(config, season, week, *, projection_max_age=21600, root=ROOT, validation_only=False):
    if not 1 <= week <= 18:
        raise ValueError('Week must be 1–18')
    folder = root / 'data/weekly' / str(season) / str(week)
    run = folder / 'snapshots' / uuid.uuid4().hex
    run.mkdir(parents=True)
    manifest = {'complete': False, 'season': season, 'week': week, 'started_at': stamp(),
                'purpose': 'validation' if validation_only else 'recommendation', 'datasets': []}
    def save(name, value):
        save_atomic(run / (name+'.json'), value)
        manifest['datasets'].append({'name': name, 'file': name+'.json',
            'sha256': hashlib.sha256((run/(name+'.json')).read_bytes()).hexdigest()})
        save_atomic(run/'manifest.json', manifest)
        meta = value.get('provenance', value)
        print(json.dumps({'saved': name, 'cache_hit': meta.get('cache_hit'),
                          'network_attempts': meta.get('network_attempts'),
                          'fetched_at': meta.get('fetched_at')}), flush=True)
    try:
        ctx = context(config, season, week)
        save('context', ctx)
        save('sleeper_players', get_sleeper('players/nfl', with_metadata=True, retries=0))
        save('schedule', get_nflverse('schedules', season))
        tasks = [('fp_external', 'nfl/players', {'external_ids': 'espn:mfl'}, 86400)]
        if not validation_only:
            tasks += [('projections_'+p, f'nfl/{season}/projections', {'position': p, 'week': week}, projection_max_age)
                      for p in ('QB','RB','WR','TE','K','DST')]
        tasks += [('injuries', 'nfl/injuries', {'year': season, 'week': week, 'include_probabilities': True}, 900),
                  ('news', 'nfl/news', {'limit': 100, 'order_by': 'updated'}, 900)]
        for name, endpoint, params, age in tasks:
            before = FantasyPros().usage()['attempts_last_24h']
            value = get_fantasypros(endpoint, params, max_age=age)
            value['request'] = {'endpoint': endpoint, 'params': params}
            value['network_attempts'] = FantasyPros().usage()['attempts_last_24h']-before
            save(name, value)
        # Collection can take time. Re-read mutable state before promoting it.
        final = context(config, season, week)
        if state_key(ctx) != state_key(final):
            raise ValueError('Ownership/settings/starters changed during collection; rerun')
        save('final_context', final)
        manifest.update(complete=True, completed_at=stamp())
        save_atomic(run/'manifest.json', manifest)
        return run
    except Exception as error:
        manifest['error'] = str(error)
        save_atomic(run/'manifest.json', manifest)
        raise


def load(run):
    run = Path(run)
    manifest = json.loads((run/'manifest.json').read_text())
    if not manifest['complete']:
        raise ValueError('Incomplete weekly snapshot')
    values = {}
    for item in manifest['datasets']:
        if Path(item['file']).name != item['file'] or item['name'] in values:
            raise ValueError('Invalid snapshot manifest')
        raw = (run/item['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('Weekly snapshot checksum mismatch')
        values[item['name']] = json.loads(raw)
    return values


def acquisition_summary(inputs):
    totals = {name: {'network_attempts': 0, 'cache_hits': 0} for name in ('sleeper','fantasypros','nflverse')}
    for name, value in inputs.items():
        if name in ('context','final_context'):
            metas, provider = value['evidence'].values(), 'sleeper'
        elif name == 'schedule':
            metas, provider = [value['provenance']], 'nflverse'
        else:
            metas, provider = [value], 'sleeper' if name == 'sleeper_players' else 'fantasypros'
        for meta in metas:
            totals[provider]['network_attempts'] += meta.get('network_attempts', 0)
            totals[provider]['cache_hits'] += int(bool(meta.get('cache_hit')))
    return totals
