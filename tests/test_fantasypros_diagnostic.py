import unittest

from fantasy_agent.providers.fantasypros import APIError, InvalidData
from fantasy_agent.providers.fantasypros_diagnostic import diagnose


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.fail = None

    def request(self, path, params, **options):
        self.calls.append((path, params, options))
        if self.fail:
            raise self.fail
        field = 'items' if path.endswith('news') else 'injuries' if path.endswith('injuries') else 'players'
        return {'data': {field: [], 'season': 2026}, 'cache_hit': True,
                'fetched_at': '2026-09-08T20:00:00+00:00'}

    def run_diagnostic(self, state=None):
        return diagnose(2026, self.request,
                        lambda: {'attempts_last_24h': 0},
                        lambda _: state or {'season': '2026', 'season_type': 'regular', 'week': 1})

    def test_access_failure_stops_remaining_calls(self):
        self.fail = APIError('Missing credential')
        result = self.run_diagnostic()
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(result['access_checks_passed'])
        self.assertEqual(result['probes'][-1]['status'], 'not_run')

    def test_success_does_not_assert_entitlement_or_draft_readiness(self):
        result = self.run_diagnostic()
        self.assertEqual(len(self.calls), 6)
        self.assertTrue(result['access_checks_passed'])
        self.assertFalse(result['ready_for_draft_use'])
        self.assertIn('Not evaluated by access probes', result['production_entitlement'])
        self.assertIn('docs/FANTASYPROS.md', result['production_entitlement'])
        self.assertTrue(all(call[2] == {'retries': 0} for call in self.calls))
        self.assertEqual(result['local_attempt_delta'], 0)

    def test_invalid_payload_not_hidden_and_other_scopes_still_probed(self):
        self.fail = InvalidData('Wrong season')
        result = self.run_diagnostic()
        self.assertEqual(len(self.calls), 6)
        self.assertFalse(result['access_checks_passed'])
        self.assertTrue(all(p['status'] == 'invalid_data' for p in result['probes']))

    def test_wrong_season_state_does_not_query_injuries(self):
        result = self.run_diagnostic({'season': '2025', 'season_type': 'regular', 'week': 1})
        self.assertEqual(len(self.calls), 5)
        self.assertEqual(result['probes'][-1]['status'], 'not_run')


if __name__ == '__main__':
    unittest.main()
