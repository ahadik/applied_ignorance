"""Draft-focused nflverse collection. Offline historical analysis is kept separate."""
import argparse
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
from nflverse import NFLVerseError, ROOT, get_nflverse
from storage import save_atomic


def collect(draft_season, seasons, request=get_nflverse, refresh=False, revalidate=False):
    if not seasons or len(set(seasons)) != len(seasons) or any(y >= draft_season or y < 2012 for y in seasons):
        raise ValueError('Choose distinct completed seasons before the draft season (2012 onward)')
    folder = ROOT / 'data/nflverse/draft' / str(draft_season)
    tasks = [('players', None), ('depth_charts', draft_season)]
    tasks += [(dataset, year) for year in sorted(seasons) for dataset in ('player_stats', 'snap_counts')]
    manifest = {'draft_season': draft_season, 'history_seasons': sorted(seasons),
                'collected_at': datetime.now(timezone.utc).isoformat(), 'datasets': [],
                'scope': 'Historical evidence and current depth charts, not projections'}
    for dataset, year in tasks:
        entry = {'dataset': dataset, 'season': year}
        try:
            result = request(dataset, year, refresh=refresh, revalidate=revalidate)
            path = folder / f'{dataset}_{year or "all"}.json'
            save_atomic(path, result)
            entry.update(status='ok', path=str(path), rows=len(result['data']), provenance=result['provenance'],
                         snapshot_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        except (NFLVerseError, ValueError) as error:
            entry.update(status='failed', error=str(error))
        manifest['datasets'].append(entry)
        print(json.dumps({k: v for k, v in entry.items() if k not in ('provenance', 'snapshot_sha256')} |
              ({k: entry['provenance'][k] for k in ('cache_hit', 'network_attempts', 'asset_updated_at')}
               if 'provenance' in entry else {})), flush=True)
        # Save progress after each dataset, including failures; never pretend an old
        # file belongs to a successful current collection.
        save_atomic(folder / 'collection.json', manifest)
    manifest['complete'] = all(d['status'] == 'ok' for d in manifest['datasets'])
    save_atomic(folder / 'collection.json', manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['collect'])
    parser.add_argument('--draft-season', required=True, type=int)
    parser.add_argument('--seasons', nargs='+', type=int)
    parser.add_argument('--refresh', action='store_true', help='Explicitly revalidate metadata and redownload assets')
    parser.add_argument('--revalidate', action='store_true', help='Check publication metadata now; reuse unchanged assets')
    args = parser.parse_args()
    try:
        result = collect(args.draft_season, args.seasons or [args.draft_season-2, args.draft_season-1], refresh=args.refresh, revalidate=args.revalidate)
        return 0 if result['complete'] else 1
    except (OSError, ValueError) as error:
        parser.exit(1, str(error)+'\n')


if __name__ == '__main__':
    raise SystemExit(main())
