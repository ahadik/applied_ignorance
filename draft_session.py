"""Prefetch once, prohibit non-Sleeper network reads, and pin a draft board."""
import argparse
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import shutil
import time

from provider_freeze import ROOT,LOCK
from storage import save_atomic


def board_digest(board):
    return hashlib.sha256(json.dumps({k:v for k,v in board.items() if k!='draft_session'},sort_keys=True).encode()).hexdigest()


def verify_board(board,current,lock_path=None):
    lock = json.loads(Path(lock_path or LOCK).read_text())
    session = board['draft_session']
    if not lock['active'] or lock.get('status')!='ready' or lock.get('session')!=session:
        raise ValueError('Frozen board has no matching active approved session')
    if (session['board_sha256']!=board_digest(board) or session['draft_id']!=board['draft_id']
            or session['league_id']!=board['league_id']):
        raise ValueError('Frozen board content or scope changed; do not bypass the network freeze')
    if not datetime.fromisoformat(session['frozen_at'])<=current<datetime.fromisoformat(session['valid_until']):
        raise ValueError('Frozen board is outside its approved session window; network remains blocked')
    return session['valid_until']


def prefetch(season):
    from draft_inputs import collect,load_inputs
    from draft_board import make_board,export_candidates,render
    from draft_history_analysis import build
    from fantasypros import FantasyPros
    if LOCK.exists() and json.loads(LOCK.read_text())['active']:
        raise ValueError('A network freeze is already active; prefetch will not override it')
    started = time.monotonic()
    prior_usage = FantasyPros().usage()['attempts_last_24h']
    # Freeze even after an incomplete attempt. No later caller can silently retry
    # behind the user's back; a failure must be reported and explicitly resolved.
    try:
        collect(season,refresh=True)
    finally:
        save_atomic(LOCK,{'active':True,'status':'pending_validation',
                         'blocked_providers':['fantasypros','nflverse'],
                         'locked_at':datetime.now(timezone.utc).isoformat()})
    fetched_seconds = time.monotonic()-started
    folder = ROOT/'data/draft_inputs'/str(season)
    manifest,inputs = load_inputs(folder)
    current = datetime.now(timezone.utc)
    history,_ = build(ROOT/'data/nflverse/draft'/str(season),current)
    board = make_board(inputs,history,season,current)
    board['input_manifest_sha256'] = hashlib.sha256((folder/'collection.json').read_bytes()).hexdigest()
    board['history_manifest_sha256'] = hashlib.sha256((ROOT/'data/nflverse/draft'/str(season)/'collection.json').read_bytes()).hexdigest()
    export_candidates(board,current)  # Original source deadlines must pass NOW.
    session = {'draft_id':board['draft_id'],'league_id':board['league_id'],
               'frozen_at':current.isoformat(),'valid_until':(current+timedelta(hours=12)).isoformat(),
               'board_sha256':board_digest(board),'policy':'User-approved static draft snapshot; original source times preserved'}
    board['draft_session'] = session
    destination = ROOT/'data/draft_session'/board['draft_id']
    shutil.copytree(folder,destination/'inputs',dirs_exist_ok=True)
    save_atomic(destination/'board.json',board)
    board_folder = ROOT/'data/draft_board'/str(season)
    save_atomic(board_folder/'board.json',board)
    (board_folder/'MILESTONE_2.md').write_text(render(board))
    calls = FantasyPros().usage()['attempts_last_24h']-prior_usage
    lock = {'active':True,'status':'ready','blocked_providers':['fantasypros','nflverse'],'session':session,
            'fp_attempts':calls,'fetch_seconds':fetched_seconds,'total_seconds':time.monotonic()-started,
            'board_file':str(destination/'board.json'),'source_times':board['sources']}
    save_atomic(LOCK,lock)
    verify_board(board,current)
    return lock


def release():
    from draft_data import read_live_draft
    lock = json.loads(LOCK.read_text())
    if lock.get('status')!='ready':
        raise ValueError('Incomplete snapshot requires explicit review; no automatic release')
    draft,_ = read_live_draft(lock['session']['draft_id'])
    if draft.get('status')!='complete' or draft.get('league_id')!=lock['session']['league_id']:
        raise ValueError('The actual league draft is not confirmed complete; freeze retained')
    lock.update(active=False,released_at=datetime.now(timezone.utc).isoformat(),status='released_after_draft')
    save_atomic(LOCK,lock)
    return lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prefetch','status','verify','release'))
    parser.add_argument('--season',type=int,default=2026)
    args = parser.parse_args()
    try:
        if args.command=='prefetch':
            result = prefetch(args.season)
        elif args.command=='release':
            result = release()
        else:
            result = json.loads(LOCK.read_text())
            if args.command=='verify':
                from draft_board import export_candidates
                board = json.loads(Path(result['board_file']).read_text())
                current = datetime.now(timezone.utc)
                export_candidates(board,current)
                export_candidates(board,current+timedelta(hours=3))
                # Exercise the actual client with forced-refresh semantics. The
                # guard must stop before any reservation or transport.
                from fantasypros import FantasyPros
                from provider_freeze import FrozenNetwork
                def forbidden_transport(*args,**kwargs):
                    raise AssertionError('Verification transport must never run')
                client = FantasyPros(send=forbidden_transport)
                before = client.usage()['attempts_last_24h']
                try:
                    client.get('nfl/news',{'limit':100,'order_by':'updated'},max_age=0)
                except FrozenNetwork:
                    pass
                else:
                    raise ValueError('Network freeze was not enforced')
                if client.usage()['attempts_last_24h']!=before:
                    raise ValueError('Verification unexpectedly consumed an attempt')
                result = dict(result,verification='Current/+3h frozen exports passed; forced FP refresh blocked with zero attempts')
        print(json.dumps({k:v for k,v in result.items() if k!='source_times'},indent=2))
    except Exception as error:
        parser.exit(1,str(error)+'\n')


if __name__=='__main__':
    main()
