import importlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from fantasy_agent.commands import COMMANDS
from fantasy_agent.paths import ROOT
from fantasy_agent.maintenance.system_acceptance import source_digest


class PackageTests(unittest.TestCase):
    def test_commands_resolve_inside_package(self):
        for name, target in COMMANDS.items():
            with self.subTest(module=name):
                module = importlib.import_module(target)
                self.assertTrue(Path(module.__file__).is_relative_to(ROOT / 'fantasy_agent'))
        self.assertEqual(list(ROOT.glob('*.py')), [])

    def test_package_commands_have_working_cli(self):
        for command in ('league_manager', 'notify', 'weekly_lineup', 'controller'):
            new = subprocess.run([sys.executable, '-m', 'fantasy_agent', command, '--help'], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(new.returncode, 0, new.stderr)
            self.assertIn('usage:', new.stdout)

    def test_acceptance_covers_nested_implementation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            file = root / 'fantasy_agent/core/example.py'
            file.parent.mkdir(parents=True)
            file.write_text('x = 1\n')
            before = source_digest(root)
            file.write_text('x = 2\n')
            self.assertNotEqual(source_digest(root), before)

    def test_roots_still_refer_to_repository(self):
        from fantasy_agent.providers import sleeper, fantasypros, nflverse
        from fantasy_agent.automation import league_manager
        for module in (sleeper, fantasypros, nflverse, league_manager):
            self.assertEqual(module.ROOT, ROOT)
