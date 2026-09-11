from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from automation_probe import probe, save_run, observe, validate_record, read_inventory
from sleeper import SleeperError


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'config.json').write_text(json.dumps({'league_id': '123'}))

    def test_offline_does_not_request_and_preserves_record(self):
        request = Mock(side_effect=AssertionError('No network'))
        record = probe(self.root, request=request)
        path = save_run(record, self.root)
        self.assertEqual(json.loads(path.read_text()), record)
        with self.assertRaises(FileExistsError):
            save_run(record, self.root)
        request.assert_not_called()

    def test_scheduled_flag_does_not_prove_scheduling(self):
        record = probe(self.root, trigger='scheduled', task_id='test',
                       expected_at='2026-09-10T12:00:00Z',
                       now=datetime(2026, 9, 10, 12, 0, 5, tzinfo=timezone.utc))
        self.assertEqual(record['start_delay_seconds'], 5)
        self.assertEqual(record['capabilities']['scheduled_start']['status'], 'untested')
        record['capabilities']['scheduled_start']['status'] = 'verified'
        with self.assertRaises(ValueError):
            validate_record(record)

    def test_invalid_schedule_metadata(self):
        with self.assertRaises(ValueError):
            probe(self.root, trigger='scheduled')
        with self.assertRaises(ValueError):
            probe(self.root, expected_at='2026-09-10T12:00:00')

    def test_central_client_metadata_and_no_retries(self):
        request = Mock(return_value={'data': {'league_id': '123', 'sport': 'nfl'},
                                    'cache_hit': False, 'network_attempts': 1})
        record = probe(self.root, live=True, request=request)
        request.assert_called_once_with('league/123', with_metadata=True, retries=0)
        self.assertEqual(record['capabilities']['sleeper_read']['acquisition']['network_attempts'], 1)

    def test_wrong_league_and_error_do_not_pass_or_expose_text(self):
        for request in (Mock(return_value={'data': {'league_id': 'other'}}),
                        Mock(side_effect=OSError('secret-token'))):
            record = probe(self.root, live=True, request=request)
            self.assertEqual(record['capabilities']['sleeper_read']['status'], 'unavailable')
            self.assertNotIn('secret-token', json.dumps(record))

    def test_observation_is_separate_and_mode_bound(self):
        record = probe(self.root)
        path = save_run(record, self.root)
        original = path.read_bytes()
        evidence = self.root / 'evidence.json'
        evidence.write_text(json.dumps({
            'observed_at': '2026-09-10T12:00:00Z', 'surface': 'test tool',
            'execution_mode': 'interactive', 'result': 'No access', 'reference': 'test case',
        }))
        observe(self.root, record['run_id'], 'browser_inspection', 'unavailable', evidence)
        self.assertEqual(path.read_bytes(), original)
        with self.assertRaises(ValueError):
            observe(self.root, record['run_id'], 'scheduled_start', 'verified', evidence)
        with self.assertRaises(ValueError):
            observe(self.root, '../escape', 'task_create', 'verified', evidence)

    def test_safe_failure_diagnostics_preserve_attempt_evidence(self):
        request = Mock(side_effect=SleeperError('secret-token', category='http',
                                              http_status=503, network_attempts=1))
        record = probe(self.root, live=True, request=request)
        evidence = record['capabilities']['sleeper_read']['acquisition']
        self.assertEqual(evidence['network_attempts'], 1)
        self.assertEqual(evidence['http_status'], 503)
        self.assertNotIn('secret-token', json.dumps(record))

    def test_inventory_fails_closed_and_does_not_save_prompt_text(self):
        schedules = self.root / 'automations'
        self.assertFalse(read_inventory(schedules)['complete'])
        folder = schedules / 'test'
        folder.mkdir(parents=True)
        (folder / 'automation.toml').write_text(
            'id="test"\nkind="cron"\nstatus="PAUSED"\nrrule="RRULE:FREQ=DAILY"\nprompt="secret-token"\n'
            'target={type="project",project_id="project1"}\ncwds=["/test/project"]\n')
        record = read_inventory(schedules)
        self.assertTrue(record['complete'])
        self.assertEqual(record['entries'][0]['id'], 'test')
        self.assertEqual(record['entries'][0]['project_id'], 'project1')
        self.assertEqual(record['entries'][0]['cwds'], ['/test/project'])
        self.assertNotIn('secret-token', json.dumps(record))
        (schedules / 'broken').mkdir()
        self.assertFalse(read_inventory(schedules)['complete'])
