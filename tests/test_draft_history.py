from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from draft_history import collect
from draft_history_analysis import build
from nflverse import NFLVerseError


class CollectionTests(unittest.TestCase):
    def test_partial_collection_marks_failure_and_preserves_old_file(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'data/nflverse/draft/2026'
            folder.mkdir(parents=True)
            old = folder / 'players_all.json'
            old.write_text('last-good')
            def fail(*args, **kwargs):
                raise NFLVerseError('Missing dataset')
            with patch('draft_history.ROOT', Path(directory)), redirect_stdout(StringIO()):
                result = collect(2026, [2025], fail)
            self.assertFalse(result['complete'])
            self.assertEqual(old.read_text(), 'last-good')
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                build(folder, None)

    def test_future_history_season_rejected_before_request(self):
        with self.assertRaises(ValueError):
            collect(2026, [2026], lambda *args: self.fail('Should not request'))
