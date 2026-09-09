"""Milestone 2 collection and offline inspection through shared provider clients."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from draft_data import read_draft_context
from fantasypros import FantasyPros, get_fantasypros
from sleeper import get_sleeper
from storage import save_atomic

ROOT = Path(__file__).resolve().parent


def stamp():
    return datetime.now(timezone.utc).isoformat()


def load_inputs(folder):
    manifest = json.loads((folder / 'collection.json').read_text())
    if not manifest.get('complete'):
        raise ValueError('Input collection incomplete; inspect collection.json')
    result = {}
    for entry in manifest['datasets']:
        path = folder / entry['file']
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ValueError('Input snapshot checksum mismatch: '+entry['name'])
        result[entry['name']] = json.loads(raw)
    return manifest, result


def collect(season, refresh=False):
    from provider_freeze import check
    check('fantasypros',ROOT/'data/fantasypros')
    folder = ROOT / 'data/draft_inputs' / str(season)
    manifest = {'season': season, 'started_at': stamp(), 'complete': False, 'datasets': []}
    save_atomic(folder / 'collection.json', manifest)
    config = json.loads((ROOT / 'config.json').read_text())
    def save(name, result):
        path = folder / (name+'.json')
        save_atomic(path, result)
        entry = {'name': name, 'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        manifest['datasets'].append(entry)
        save_atomic(folder / 'collection.json', manifest)
        print(json.dumps({'saved': name, 'cache_hit': result.get('cache_hit'),
                          'fetched_at': result.get('fetched_at')}), flush=True)
    context = read_draft_context(config)
    if str(context['league']['season']) != str(season) or str(context['draft']['season']) != str(season):
        raise ValueError('Requested season does not match league/draft')
    save('context', context)
    players = get_sleeper('players/nfl', with_metadata=True)
    if not isinstance(players['data'], dict) or not players['data']:
        raise ValueError('Sleeper player directory missing')
    save('sleeper_players', players)
    state = get_sleeper('state/nfl', with_metadata=True)
    save('nfl_state', state)
    value = state['data']
    if str(value['season']) != str(season) or value['season_type'] != 'regular' or not 1 <= int(value['week']) <= 18:
        raise ValueError('Cannot establish matching regular-season injury week')
    rec = context['league']['scoring_settings'].get('rec', 0)
    if rec not in (0, .5, 1):
        raise ValueError('Consensus scoring baseline requires STD/HALF/PPR')
    scoring = {0: 'STD', .5: 'HALF', 1: 'PPR'}[rec]
    tasks = [('fp_external', 'nfl/players', {'external_ids': 'espn:mfl'}),
             ('ecr', f'nfl/{season}/consensus-rankings', {'position': 'ALL', 'type': 'DRAFT', 'scoring': scoring, 'week': 0}),
             ('adp', f'nfl/{season}/consensus-rankings', {'position': 'ALL', 'type': 'ADP', 'scoring': scoring, 'week': 0})]
    tasks += [('projections_'+p, f'nfl/{season}/projections', {'position': p, 'week': 0}) for p in ('QB','RB','WR','TE','K','DST')]
    tasks += [('news', 'nfl/news', {'limit': 100, 'order_by': 'updated'}),
              ('injuries', 'nfl/injuries', {'year': season, 'week': int(value['week']), 'include_probabilities': True})]
    usage = FantasyPros().usage
    manifest['fp_usage_before'] = usage()
    for name, endpoint, params in tasks:
        options = {'max_age': 0} if refresh else {}
        before_call = usage()['attempts_last_24h']
        result = get_fantasypros(endpoint, params, **options)
        result['request'] = {'endpoint': endpoint, 'params': params}
        save(name, result)
        print(json.dumps({'dataset':name,'fp_attempts':usage()['attempts_last_24h']-before_call}), flush=True)
    manifest.update(complete=True, completed_at=stamp(), fp_usage_after=usage())
    save_atomic(folder / 'collection.json', manifest)
    publish_context(context, config)
    print(json.dumps({'complete': True, 'folder': str(folder),
                      'fp_attempts': manifest['fp_usage_after']['attempts_last_24h']-manifest['fp_usage_before']['attempts_last_24h']}))


def publish_context(context, config):
    from draft import summary
    save_atomic(ROOT / 'data/snapshot.json', context)
    (ROOT / 'DRAFT_CONTEXT.md').write_text(summary(context, config))


def adopt_context(folder,context):
    """Offline replacement of league context; preserve every player-data timestamp."""
    manifest,inputs = load_inputs(folder)
    old = inputs['context']
    if (context['league']['league_id']!=old['league']['league_id']
            or context['draft']['draft_id']!=old['draft']['draft_id']
            or str(context['league']['season'])!=str(manifest['season'])
            or str(context['draft']['season'])!=str(manifest['season'])):
        raise ValueError('Context scope differs from saved collection')
    fetched = datetime.fromisoformat(context['fetched_at'])
    if not datetime.fromisoformat(old['fetched_at'])<=fetched<=datetime.now(timezone.utc):
        raise ValueError('Context must be newer, with a valid observation time')
    if context['league']['scoring_settings'].get('rec',0)!=old['league']['scoring_settings'].get('rec',0):
        raise ValueError('Reception scoring changed; collect matching ECR/ADP feeds')
    # New immutable file first, then atomically point the manifest to it. Existing
    # inputs and manifest remain usable if the replacement write is interrupted.
    suffix = hashlib.sha256(json.dumps(context,sort_keys=True).encode()).hexdigest()[:16]
    path = folder/('context.'+suffix+'.json')
    save_atomic(path,context)
    manifest['datasets'] = [e for e in manifest['datasets'] if e['name']!='context']
    manifest['datasets'].append({'name':'context','file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest['context_adopted_at'] = stamp()
    save_atomic(folder/'collection.json',manifest)


def inspect(folder):
    manifest, inputs = load_inputs(folder)
    print(json.dumps({'season': manifest['season'], 'league_scoring': inputs['context']['league']['scoring_settings'],
                      'roster_positions': inputs['context']['league']['roster_positions']}, indent=2))
    for name, entry in inputs.items():
        if name in ('context', 'nfl_state'):
            continue
        data = entry['data']
        field = 'items' if name == 'news' else 'injuries' if name == 'injuries' else 'players'
        rows = data if name == 'sleeper_players' else data[field]
        rows = list(rows.values()) if isinstance(rows, dict) else rows
        selected = [r for r in rows if r.get('position') in ('QB','RB','WR','TE','K','DEF') and r.get('team')] if name == 'sleeper_players' else rows
        print(json.dumps({'dataset': name, 'rows': len(rows), 'metadata': {k:v for k,v in data.items() if not isinstance(v,(dict,list))} if name != 'sleeper_players' else {},
                          'sample': selected[:2]}, indent=2))


def enrich_ids(season):
    from provider_freeze import check
    check('fantasypros',ROOT/'data/fantasypros')
    folder = ROOT / 'data/draft_inputs' / str(season)
    manifest, _ = load_inputs(folder)
    result = get_fantasypros('nfl/players', {'external_ids': 'espn:mfl'})
    result['request'] = {'endpoint': 'nfl/players', 'params': {'external_ids': 'espn:mfl'}}
    path = folder / 'fp_external.json'
    save_atomic(path, result)
    manifest['datasets'] = [e for e in manifest['datasets'] if e['name'] != 'fp_external']
    manifest['datasets'].append({'name': 'fp_external', 'file': path.name,
                                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    save_atomic(folder / 'collection.json', manifest)
    print(json.dumps({'saved': str(path), 'cache_hit': result['cache_hit'],
                      'sample': result['data']['players'][:1]}, indent=2))


def refresh_alerts(season):
    """Refresh only near-deadline news/injuries; retain other checksummed inputs."""
    from provider_freeze import check
    check('fantasypros',ROOT/'data/fantasypros')
    folder = ROOT / 'data/draft_inputs' / str(season)
    manifest, inputs = load_inputs(folder)
    state = get_sleeper('state/nfl', with_metadata=True)
    value = state['data']
    if str(value['season']) != str(season) or value['season_type'] != 'regular' or not 1 <= int(value['week']) <= 18:
        raise ValueError('Cannot establish injury week')
    tasks = [('nfl_state', state), ('news', None), ('injuries', None)]
    # Any interrupted refresh makes the manifest incomplete instead of mixing old
    # and new alert files into a seemingly successful collection.
    manifest['complete'] = False
    save_atomic(folder / 'collection.json', manifest)
    for name, result in tasks:
        if result is None:
            endpoint = 'nfl/'+name
            params = {'limit':100,'order_by':'updated'} if name=='news' else {'year':season,'week':int(value['week']),'include_probabilities':True}
            result = get_fantasypros(endpoint, params)
            result['request'] = {'endpoint':endpoint,'params':params}
        path = folder / (name+'.json')
        save_atomic(path, result)
        manifest['datasets'] = [e for e in manifest['datasets'] if e['name'] != name]
        manifest['datasets'].append({'name':name,'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        save_atomic(folder / 'collection.json', manifest)
        print(json.dumps({'saved':name,'cache_hit':result.get('cache_hit'),'fetched_at':result['fetched_at']}),flush=True)
    manifest['complete'] = True
    manifest['alerts_checked_at'] = stamp()
    save_atomic(folder / 'collection.json', manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('collect','inspect','enrich-ids','refresh-alerts','publish-context','adopt-context'))
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--refresh', action='store_true', help='Explicitly refresh FantasyPros responses')
    parser.add_argument('--context',type=Path,help='Saved provider context for offline adopt-context')
    args = parser.parse_args()
    try:
        if args.command == 'adopt-context':
            if not args.context:
                raise ValueError('--context is required')
            context = json.loads(args.context.read_text())
            adopt_context(ROOT/'data/draft_inputs'/str(args.season),context)
            publish_context(context,json.loads((ROOT/'config.json').read_text()))
            print('Adopted observed league context; player data/timestamps retained; zero API calls. Rebuild the board.')
        elif args.command == 'collect':
            collect(args.season, args.refresh)
        elif args.command == 'enrich-ids':
            enrich_ids(args.season)
        elif args.command == 'refresh-alerts':
            refresh_alerts(args.season)
        elif args.command == 'publish-context':
            _, inputs = load_inputs(ROOT / 'data/draft_inputs' / str(args.season))
            publish_context(inputs['context'], json.loads((ROOT / 'config.json').read_text()))
            print('Published saved context; no network requests.')
        else:
            inspect(ROOT / 'data/draft_inputs' / str(args.season))
    except Exception as error:
        parser.exit(1, f'Collection/inspection failed: {error}\n')


if __name__ == '__main__':
    main()
