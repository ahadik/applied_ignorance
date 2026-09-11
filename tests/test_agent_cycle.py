from datetime import datetime, timezone
import json
import unittest
from unittest.mock import patch

from agent_cycle import review
from tests import test_lineup_execution as base
from tests import test_roster_operations as roster_base


class CycleTests(unittest.TestCase):
    setUp = base.ExecutionTests.setUp
    write = base.ExecutionTests.write
    snapshot = base.ExecutionTests.snapshot

    def test_integrated_review_saves_proposal_validation_roster_and_calendar(self):
        current = datetime.fromtimestamp(self.now, timezone.utc)
        self.inputs['final_context']['roster']['owner_id'] = 'owner'
        self.snapshot()
        observation = {'context': self.inputs['final_context'], 'rosters': {'data': [self.inputs['final_context']['roster']]}}
        self.write('observation.json', observation)
        with patch('agent_cycle.collect', return_value=self.root / 'snapshot') as provider, \
             patch('agent_cycle.collect_rosters', return_value={'saved': str(self.root / 'observation.json'), 'network_attempts': 0}), \
             patch('weekly_model.schedule_games', return_value=(self.games, {'BUF', 'NYJ'})), \
             patch('lineup_validation.schedule_games', return_value=(self.games, {'BUF', 'NYJ'})), \
             patch('agent_cycle.season_calendar', return_value={'weeks': [], 'assumption': 'Simulated schedule'}), \
             patch('agent_cycle.datetime') as clock:
            clock.now.return_value = current
            result = review(self.root, 2026, 1)
        self.assertEqual(result['status'], 'owner_review_required', result)
        self.assertFalse(result['platform_changes'])
        self.assertTrue(result['native_review_required'])
        self.assertTrue((self.root / result['proposal']).exists())
        provider.assert_called_once()

    def test_provider_failure_saves_blocked_result_and_no_authority(self):
        with patch('agent_cycle.collect', side_effect=OSError('Simulated provider failure')):
            result = review(self.root, 2026, 1)
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['lineup_state']['standing_autonomy_enabled'])
        self.assertTrue(__import__('pathlib').Path(result['saved']).exists())

    def test_unresolved_action_blocks_collection(self):
        eid = self.engine.register('proposal.json', 'authority.json')['id']
        with patch('agent_cycle.collect') as collect:
            result = review(self.root, 2026, 1)
        self.assertEqual(result['status'], 'blocked')
        collect.assert_not_called()
