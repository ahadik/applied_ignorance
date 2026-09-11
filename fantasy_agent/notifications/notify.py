"""Send owner notifications through the central Pushover client. Status is offline."""
import argparse
import json
import sqlite3
from pathlib import Path

from fantasy_agent.providers.pushover import get_pushover, PushoverError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    send = sub.add_parser('send')
    send.add_argument('--incident', required=True)
    send.add_argument('--message', required=True)
    send.add_argument('--title', default='Fantasy Football agent')
    confirm = sub.add_parser('confirm')
    confirm.add_argument('--incident', required=True)
    confirm.add_argument('--evidence', required=True)
    args = parser.parse_args(argv)
    try:
        client = get_pushover(args.root)
        if args.command == 'status':
            result = client.status()
        elif args.command == 'send':
            result = client.send(args.incident, args.message, args.title)
        else:
            result = client.confirm(args.incident, args.evidence)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, sqlite3.Error) as error:
        print(json.dumps({'error': str(error) if isinstance(error, PushoverError) else type(error).__name__,
                          'delivery_status': 'unverified', 'retry_automatically': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
