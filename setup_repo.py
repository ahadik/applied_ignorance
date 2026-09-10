"""Restore repository data omitted from Git using the shared nflverse client."""
import argparse
from draft_history import collect


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', type=int, default=2026)
    args = parser.parse_args(argv)
    # Recollect a coherent manifest, retaining each provider's normal cache policy.
    # Current depth metadata is always checked; unchanged asset bytes may be reused.
    result = collect(args.season, [args.season - 2, args.season - 1])
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
