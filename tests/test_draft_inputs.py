import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from draft_inputs import collect, load_inputs
from tests.test_draft_board import fixtures


class InputCollectionTests(unittest.TestCase):
    def run_collection(self, fail=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root/'config.json').write_text(json.dumps({'league_id':'123','username':'test','timezone':'UTC'}))
        inputs, _, _ = fixtures()
        context = inputs['context']
        context['user_id'] = 'user'
        context['picks'] = []
        context['league'].update(name='Test',settings={})
        context['draft'].update(status='pre_draft',type='snake',draft_order={})
        context['draft']['settings']['pick_timer'] = 120
        calls = []
        def fp(path, params, **options):
            calls.append((path,params))
            if fail:
                raise ValueError('Synthetic provider failure')
            if path.endswith('/players'):
                name = 'fp_external'
            elif path.endswith('/projections'):
                name = 'projections_'+params['position']
            elif path.endswith('/consensus-rankings'):
                name = 'ecr' if params['type']=='DRAFT' else 'adp'
            else:
                name = path.split('/')[-1]
            return inputs[name]
        with patch('draft_inputs.ROOT',root), patch('draft_inputs.read_draft_context',return_value=context), \
             patch('draft_inputs.get_sleeper',side_effect=lambda path,**kw:inputs['sleeper_players' if path=='players/nfl' else 'nfl_state']), \
             patch('draft_inputs.get_fantasypros',side_effect=fp), patch('draft_inputs.FantasyPros') as client, patch('builtins.print'):
            client.return_value.usage.return_value = {'attempts_last_24h':0}
            if fail:
                with self.assertRaises(ValueError):
                    collect(2026)
            else:
                collect(2026)
        return root,calls

    def test_failed_collection_cannot_be_loaded_or_publish_context(self):
        root,calls = self.run_collection(fail=True)
        with self.assertRaises(ValueError):
            load_inputs(root/'data/draft_inputs/2026')
        self.assertEqual(len(calls),1)
        self.assertFalse((root/'data/snapshot.json').exists())

    def test_complete_collection_uses_six_positions_and_verified_ids(self):
        root,calls = self.run_collection()
        manifest, inputs = load_inputs(root/'data/draft_inputs/2026')
        self.assertTrue(manifest['complete'])
        self.assertEqual(len(calls),11)
        self.assertEqual({params['position'] for path,params in calls if path.endswith('/projections')}, {'QB','RB','WR','TE','K','DST'})
        self.assertIn('fp_external',inputs)
        self.assertTrue((root/'data/snapshot.json').exists())


if __name__ == '__main__':
    unittest.main()
