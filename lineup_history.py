"""Append-only lineup records. Latest JSON is a convenience copy, not history.

python3 lineup_history.py list --season 2026 --week 1
python3 lineup_history.py record --lineup FILE --rationale-file TEXT_FILE
No provider calls; record saves a new version and never edits historical records.
"""
import argparse
import copy
import fcntl
import json
from pathlib import Path
import uuid

from storage import save_new, save_atomic
from weekly_data import ROOT, stamp, fingerprint
from lineup_validation import check_document


def append_proposal(folder, proposal):
    """Caller holds operation.lock. Archive old convenience copy before replacement.

    Existing v1 records are retained verbatim; no retrospective rationale invented.
    Each new proposal gets a new record ID even if assignments are unchanged.
    """
    check_document(proposal)
    if proposal['schema_version'] != 2:
        raise ValueError('New history records require schema v2 and a rationale')
    folder = Path(folder)
    latest = folder/'proposed_lineup.json'
    previous_id = None
    if latest.exists():
        previous = json.loads(latest.read_text())
        existing_id = previous.get('lineup_id')
        existing = folder/'proposals'/(str(existing_id)+'.json') if isinstance(existing_id, str) and len(existing_id) == 32 and all(c in '0123456789abcdef' for c in existing_id) else None
        legacy_path = folder/'proposals'/('preserved-'+fingerprint(previous)+'.json')
        if existing and existing.exists() and json.loads(existing.read_text()) == previous:
            previous_id = existing_id
        else:
            try:
                save_new(legacy_path, previous)
            except FileExistsError:
                if json.loads(legacy_path.read_text()) != previous:
                    raise ValueError('Preserved proposal integrity mismatch')
            previous_id = legacy_path.stem
    record = copy.deepcopy(proposal)
    record.update(lineup_id=uuid.uuid4().hex, recorded_at=stamp(), previous_lineup_id=previous_id)
    path = folder/'proposals'/(record['lineup_id']+'.json')
    save_new(path, record)
    save_atomic(latest, record)
    return path


def history(folder):
    records = []
    for path in (Path(folder)/'proposals').glob('*.json'):
        value = json.loads(path.read_text())
        records.append({'file': str(path), 'lineup_id': value.get('lineup_id', path.stem),
            'recorded_at': value.get('recorded_at', value.get('created_at')),
            'rationale': value.get('rationale', 'Legacy record: no rationale was recorded.'),
            'assignments': value.get('assignments'), 'preserved_copy': path.name.startswith('preserved-')})
    return sorted(records, key=lambda r: (r['recorded_at'] or '', r['file']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('list','record'))
    parser.add_argument('--season', type=int)
    parser.add_argument('--week', type=int)
    parser.add_argument('--lineup', type=Path)
    parser.add_argument('--rationale-file', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'list':
            if args.season is None or args.week is None:
                raise ValueError('list requires --season and --week')
            print(json.dumps(history(ROOT/'data/weekly'/str(args.season)/str(args.week)), indent=2))
            return
        if not args.lineup or not args.rationale_file:
            raise ValueError('record requires --lineup and --rationale-file')
        proposal = json.loads(args.lineup.read_text())
        proposal.update(schema_version=2, rationale=args.rationale_file.read_text().strip(),
                        rationale_source='supplied_free_text')
        check_document(proposal)
        config = json.loads((ROOT/'config.json').read_text())
        if proposal['league_id'] != config['league_id']:
            raise ValueError('Proposal belongs to another configured league')
        folder = ROOT/'data/weekly'/str(proposal['season'])/str(proposal['week'])
        folder.mkdir(parents=True, exist_ok=True)
        with (folder/'operation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = append_proposal(folder, proposal)
        print('Appended '+str(path)+'; new version requires validation, no lineup applied.')
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, str(error)+'\n')


if __name__ == '__main__':
    main()
