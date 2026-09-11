import copy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from fantasy_agent.drafting.draft_session import board_digest,verify_board,release
from fantasy_agent.providers.fantasypros import FantasyPros
from fantasy_agent.providers.nflverse import NFLVerse,API
from fantasy_agent.providers.provider_freeze import FrozenNetwork,check,DEFAULTS
from fantasy_agent.core.storage import save_atomic
from tests.test_draft_strategy import fixture


class SessionTests(unittest.TestCase):
    def test_fp_cache_hits_work_but_miss_and_force_refresh_are_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            send = Mock(return_value=(200,{}, {'players':[{'player_id':'1'}]}))
            client = FantasyPros(directory,key_loader=lambda:'test',send=send)
            original = client.get('nfl/players')
            save_atomic(Path(directory)/'draft_network_lock.json',{'active':True,'blocked_providers':['fantasypros','nflverse']})
            cached = client.get('nfl/players')
            self.assertEqual(cached['fetched_at'],original['fetched_at'])
            for endpoint,params in [('nfl/players',None),('nfl/news',{'limit':100})]:
                with self.assertRaises(FrozenNetwork):
                    client.get(endpoint,params,max_age=0)
            self.assertEqual(send.call_count,1)
            self.assertEqual(client.usage()['attempts_last_24h'],1)

    def test_nflverse_guard_blocks_before_attempt_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            send = Mock(side_effect=AssertionError('No network'))
            client = NFLVerse(directory,send=send)
            save_atomic(Path(directory)/'draft_network_lock.json',{'active':True,'blocked_providers':['fantasypros','nflverse']})
            with client.locked() as db:
                with self.assertRaises(FrozenNetwork):
                    client.request(db,API+'/repos/nflverse/nflverse-data/releases')
            self.assertEqual(client.usage()['attempts_last_hour'],0)
            send.assert_not_called()

    def test_default_provider_directories_share_one_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'lock.json'
            save_atomic(path,{'active':True,'blocked_providers':['fantasypros','nflverse']})
            with patch('fantasy_agent.providers.provider_freeze.LOCK',path):
                for provider in DEFAULTS:
                    with self.assertRaises(FrozenNetwork):
                        check(provider,DEFAULTS[provider])

    def test_session_preserves_times_accepts_age_and_rejects_tampering_expiry(self):
        board,_ = fixture()
        now = datetime.now(timezone.utc)
        session = {'draft_id':board['draft_id'],'league_id':board['league_id'],
                   'board_sha256':board_digest(board),'frozen_at':now.isoformat(),
                   'valid_until':(now+timedelta(hours=12)).isoformat()}
        board['draft_session'] = session
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory)/'lock.json'
            save_atomic(lock,{'active':True,'status':'ready','session':session})
            original = copy.deepcopy(board)
            self.assertEqual(verify_board(board,now+timedelta(hours=3),lock),session['valid_until'])
            self.assertEqual(board,original)
            with self.assertRaisesRegex(ValueError,'window'):
                verify_board(board,now+timedelta(hours=12),lock)
            board['players'][0]['name'] = 'Changed'
            with self.assertRaisesRegex(ValueError,'content'):
                verify_board(board,now,lock)

    def test_export_uses_session_deadline_without_extending_live_state(self):
        from fantasy_agent.drafting.draft_board import export_candidates
        from fantasy_agent.drafting.draft_strategy import Engine,candidate_export
        from fantasy_agent.drafting.draft_strategy_evaluate import state_from_ids
        board,policy = fixture()
        now = datetime.now(timezone.utc)
        session = {'draft_id':board['draft_id'],'league_id':board['league_id'],
                   'board_sha256':board_digest(board),'frozen_at':now.isoformat(),
                   'valid_until':(now+timedelta(hours=12)).isoformat()}
        board['draft_session'] = session
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'lock.json'
            save_atomic(path,{'active':True,'status':'ready','session':session})
            with patch('fantasy_agent.drafting.draft_session.LOCK',path):
                exported = export_candidates(board,now+timedelta(hours=3))
                self.assertEqual(exported['expires_at'],session['valid_until'])
                self.assertEqual(exported['observed_at'],board['sources'][0]['fetched_at'])
                state = state_from_ids(board,[],1,'freshness')
                state.update(simulation=False,draft_id=board['draft_id'])
                result = Engine(board,policy).recommend(state)
                with self.assertRaisesRegex(ValueError,'Fresh real'):
                    candidate_export(board,state,result,now+timedelta(hours=3))

    def test_release_requires_real_draft_complete_and_makes_no_fp_call(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'lock.json'
            lock = {'active':True,'status':'ready','session':{'draft_id':'123','league_id':'456'}}
            save_atomic(path,lock)
            with patch('fantasy_agent.drafting.draft_session.LOCK',path):
                with patch('fantasy_agent.drafting.draft_data.read_live_draft',return_value=({'status':'drafting','league_id':'456'},[])):
                    with self.assertRaises(ValueError):
                        release()
                self.assertEqual(json.loads(path.read_text()),lock)
                with patch('fantasy_agent.drafting.draft_data.read_live_draft',return_value=({'status':'complete','league_id':'456'},[])):
                    self.assertFalse(release()['active'])


if __name__=='__main__':
    unittest.main()
