import json
from pathlib import Path
import tempfile
import unittest

from lineup_history import append_proposal, history
from lineup_validation import check_document, proposal_from_report
from storage import save_new


class LineupHistoryTests(unittest.TestCase):
    def proposal(self, rationale='Start the higher projected QB, pending injury review.'):
        return {'schema_version':2, 'league_id':'test', 'roster_id':1, 'season':2026,
            'week':1, 'created_at':'2026-09-09T12:00:00Z', 'rationale':rationale,
            'assignments':[{'slot_index':0,'slot':'QB','player_id':'a'}]}

    def test_versions_preserved_and_linked(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            first = append_proposal(folder, self.proposal())
            original = first.read_bytes()
            second = append_proposal(folder, self.proposal('New injury evidence changes my reasoning.'))
            self.assertEqual(first.read_bytes(), original)
            self.assertNotEqual(first, second)
            self.assertEqual(json.loads(second.read_text())['previous_lineup_id'], first.stem)
            self.assertEqual(len(history(folder)), 2)
            self.assertEqual(json.loads((folder/'proposed_lineup.json').read_text()), json.loads(second.read_text()))

    def test_legacy_and_manual_edits_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            legacy = self.proposal()
            legacy['schema_version'] = 1
            del legacy['rationale']
            latest = folder/'proposed_lineup.json'
            latest.write_text(json.dumps(legacy))
            first = append_proposal(folder, self.proposal())
            preserved = list((folder/'proposals').glob('preserved-*.json'))
            self.assertEqual(json.loads(preserved[0].read_text()), legacy)
            edited = json.loads(latest.read_text())
            edited['rationale'] = 'Manual text that must not disappear'
            latest.write_text(json.dumps(edited))
            append_proposal(folder, self.proposal('Another version'))
            self.assertTrue(any(json.loads(p.read_text()) == edited for p in (folder/'proposals').glob('*.json')))
            self.assertNotEqual(json.loads(first.read_text())['rationale'], edited['rationale'])

    def test_new_records_require_rationale_and_refuse_overwrites(self):
        for text in ('', '   ', None):
            with self.assertRaises(ValueError):
                check_document(self.proposal(text))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'entry.json'
            save_new(path, {'a':1})
            with self.assertRaises(FileExistsError):
                save_new(path, {'a':2})
            self.assertEqual(json.loads(path.read_text()), {'a':1})

    def test_generated_rationale_and_custom_text(self):
        report = {'blockers':[], 'league_id':'test','season':2026,'week':1,
            'generated_at':'2026-09-09T12:00:00Z','input_hash':'x','engine_version':1,
            'slots':['QB'], 'recommendation':{'starters':['a']},
            'players':{'a':{'name':'Player A','availability_review':True}}, 'changes':[]}
        p = proposal_from_report(report, 1)
        self.assertIn('Player A', p['rationale'])
        self.assertIn('not been applied', p['rationale'])
        self.assertEqual(proposal_from_report(report,1,'My full reasoning.')['rationale'],'My full reasoning.')
