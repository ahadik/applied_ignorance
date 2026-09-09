"""Print a fresh, advice-only draft recommendation. No browser required."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import monotonic

from controller import build, rank
from draft_data import read_live_draft
from draft_strategy import Engine, candidate_export, load_policy

ROOT = Path(__file__).resolve().parent
DRAFT_ID = '1400628785413394432'
USER_ID = '1403069775155884032'
BOARD = ROOT / 'data/draft_session' / DRAFT_ID / 'board.json'


def recommend_now(board_path=BOARD, draft_id=DRAFT_ID, user_id=USER_ID, *, mock=False):
    """Use fresh central Sleeper reads and the shared validated strategy pipeline.

    Intentionally do not overwrite controller state, reconcile pending submissions,
    or require a working browser. The human verifies the room before selecting.
    """
    started = monotonic()
    board = json.loads(Path(board_path).read_text())
    draft, picks = read_live_draft(draft_id)
    state = build(draft, picks, user_id)
    if mock and state['league_id'] is not None:
        raise ValueError('--mock requires a league-less mock draft, not a real league')
    if not mock and (state['draft_id'] != board['draft_id'] or state['league_id'] != board['league_id']):
        raise ValueError('Live draft does not match the saved board')
    if state['status'] == 'complete' or state['next_pick'] is None:
        return {'state': state, 'players': [], 'finished': True}
    if state['status'] not in ('pre_draft', 'drafting', 'paused'):
        raise ValueError('Unsupported draft status; check Sleeper before selecting')
    result = Engine(board, load_policy()).recommend(state)
    candidates = candidate_export(board, state, result, datetime.now(timezone.utc), allow_mock=mock)
    players = rank(state, candidates)[:3]
    # build() stamps the completed read. Also bound the ENTIRE collection and
    # calculation so a slow multi-request response cannot masquerade as fresh.
    if monotonic() - started > 20:
        raise ValueError('Live read/calculation took over 20 seconds; rerun for fresh advice')
    if not players:
        raise ValueError('No validated available candidates; inspect Sleeper manually')
    return {'state': state, 'players': players, 'finished': False}


def render(advice):
    state = advice['state']
    if advice['finished']:
        return 'No selection needed: the draft or your selections are complete.'
    best, *backups = advice['players']
    label = 'DRAFT NOW' if state['our_turn'] else 'PREVIEW ONLY — NOT YOUR TURN'
    lines = [f"{label}: {best['name']} ({best['position']})"]
    for i, player in enumerate(backups, 1):
        lines.append(f"Backup {i}: {player['name']} ({player['position']})")
    lines.append(f"Seat {state['seat']} | Through pick {state['last_pick']} | Your next pick {state['next_pick']} | Status: {state['status']}")
    lines.append(f"Sleeper observation: {state['observed_at']}")
    lines.append('Verify the player is still available and it is your turn in Sleeper. Rerun after any new pick.')
    lines.append('Backups are alternatives for this pick, not a plan for subsequent rounds.')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mock', metavar='DRAFT_ID',
                        help='Target this league-less mock with matching roster settings; default is tonight\'s real draft')
    parser.add_argument('--name-only', action='store_true',
                        help='Print only the name; refuse to output a name unless it is your turn')
    args = parser.parse_args(argv)
    if args.mock is not None and not args.mock.isdigit():
        parser.error('--mock must be a numeric Sleeper draft ID')
    draft_id = args.mock or DRAFT_ID
    print(f"Target: {'MOCK' if args.mock else 'REAL DRAFT'} https://sleeper.com/draft/nfl/{draft_id}", file=sys.stderr, flush=True)
    print('Reading live Sleeper picks; calculating with frozen player data...', file=sys.stderr, flush=True)
    try:
        advice = recommend_now(draft_id=draft_id, mock=args.mock is not None)
        if args.name_only:
            if advice['finished'] or not advice['state']['our_turn']:
                print('No name printed: it is not your turn or your selections are complete.', file=sys.stderr)
                return 2
            print(advice['players'][0]['name'])
        else:
            print(render(advice))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'NO RECOMMENDATION: {error}', file=sys.stderr)
        print('Check Sleeper and rerun. No saved recommendation was substituted.', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\nCancelled; no selection made.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    sys.exit(main())
