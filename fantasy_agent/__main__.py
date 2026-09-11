"""Run a saved command: python3 -m fantasy_agent COMMAND [OPTIONS]."""
import runpy
import sys
from fantasy_agent.commands import COMMANDS

if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
    print('Usage: python3 -m fantasy_agent COMMAND [OPTIONS]')
    print('Commands: ' + ', '.join(sorted(COMMANDS)))
    raise SystemExit(0 if len(sys.argv) == 1 or sys.argv[1] in ('-h', '--help') else 2)
command = sys.argv.pop(1)
sys.argv[0] = command + '.py'
runpy.run_module(COMMANDS[command], run_name='__main__')
