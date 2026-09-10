"""Check a structured proposed lineup against fresh central-provider evidence.

python3 lineup_validate.py --lineup data/weekly/2026/1/proposed_lineup.json
Exit 0 PASS, 1 FAIL, 2 REVIEW, 3 validation unavailable/invalid document.
No account writes. Does not optimize or silently repair a supplied lineup.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import uuid

from lineup_validation import check_document, validate
from weekly_data import ROOT, collect, load, stamp
from storage import save_atomic
from fantasypros import APIError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lineup', required=True, type=Path)
    args = parser.parse_args()
    folder = None
    try:
        proposal = json.loads(args.lineup.read_text())
        check_document(proposal)
        config = json.loads((ROOT/'config.json').read_text())
        if proposal['league_id'] != config['league_id']:
            raise ValueError('Proposed lineup belongs to another configured league')
        folder = ROOT/'data/weekly'/str(proposal['season'])/str(proposal['week'])
        folder.mkdir(parents=True, exist_ok=True)
        with (folder/'operation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            history = json.loads((folder/'locks.json').read_text()) if (folder/'locks.json').exists() else {}
            run = collect(config, proposal['season'], proposal['week'], validation_only=True)
            inputs = load(run)
            result = validate(proposal, inputs, datetime.now(timezone.utc), history)
            result['snapshot'] = str(run)
            result['proposal_file'] = str(args.lineup.resolve())
            save_atomic(folder/'validation'/(uuid.uuid4().hex+'.json'), result)
            save_atomic(folder/'latest_validation.json', result)
            # Evidence-only locks; never save health/ownership facts supplied by a proposal.
            if result['status'] != 'FAIL':
                save_atomic(folder/'locks.json', {'league_id': proposal['league_id'],
                    'players': result['locked_player_ids'], 'kickoffs': history.get('kickoffs', {}) |
                    {p['player_id']: p['game']['kickoff'] for p in result['players'] if p['game']}})
            print(json.dumps({k: result[k] for k in ('status','checks_passed','checked_at','expires_at','issues','acquisition','meaning')}, indent=2))
            print('Saved '+str(folder/'latest_validation.json'))
            code = {'PASS':0,'FAIL':1,'REVIEW':2}[result['status']]
    except (APIError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        result = {'status': 'UNAVAILABLE', 'checks_passed': False, 'checked_at': stamp(), 'error': str(error),
                  'meaning': 'No current validation pass. Prior success is not reusable.'}
        if folder is not None:
            save_atomic(folder/'latest_validation.json', result)
            save_atomic(folder/'validation'/(uuid.uuid4().hex+'.json'), result)
        print(json.dumps(result, indent=2))
        code = 3
    raise SystemExit(code)


if __name__ == '__main__':
    main()
