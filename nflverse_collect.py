"""Reusable general nflverse collection and asset inspection CLI."""
import argparse
import json
from pathlib import Path
from nflverse import DATASETS, NFLVerseError, ROOT, get_nflverse, shared_client
from storage import save_atomic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['catalog', 'collect', 'inspect', 'usage'])
    parser.add_argument('--dataset', choices=[*DATASETS, 'schedules'])
    parser.add_argument('--file', type=Path)
    parser.add_argument('--season', type=int)
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--revalidate', action='store_true', help='Check publication metadata now; reuse unchanged assets')
    args = parser.parse_args()
    try:
        if args.command == 'usage':
            print(json.dumps(shared_client().usage(), indent=2))
        elif args.command == 'inspect':
            if not args.file:
                parser.error('inspect requires --file')
            result = json.loads(args.file.read_text())
            rows = result['data']
            latest = max((r.get('dt', '') for r in rows), default='')
            sample = [r for r in rows if not latest or r.get('dt') == latest][:3]
            print(json.dumps({'rows': len(rows), 'latest_dt': latest, 'sample': sample}, indent=2))
        elif not args.dataset:
            parser.error('catalog/collect requires --dataset')
        elif args.command == 'catalog':
            if args.dataset == 'schedules':
                raise ValueError('Schedules use a fixed nfldata file, not release assets; use collect --dataset schedules --season YEAR')
            result = shared_client().catalog(args.dataset, args.season)
            print(json.dumps([{'name': a['name'], 'bytes': a['size'], 'updated_at': a['updated_at']}
                              for a in result['assets'] if '.csv' in a['name'] and
                              (args.season is None or str(args.season) in a['name'])], indent=2))
        else:
            result = get_nflverse(args.dataset, args.season, refresh=args.refresh, revalidate=args.revalidate)
            folder = 'data/nflverse/local' if args.dataset == 'depth_charts' else 'data/nflverse/snapshots'
            path = ROOT / folder / f'{args.dataset}_{args.season or "all"}.json'
            save_atomic(path, result)
            print(json.dumps({'rows': len(result['data']), 'provenance': result['provenance'], 'saved': str(path)}, indent=2))
    except (NFLVerseError, ValueError) as error:
        parser.exit(1, str(error)+'\n')


if __name__ == '__main__':
    main()
