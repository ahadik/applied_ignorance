"""Child-process crash fixture for durable automation claims. No provider access."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fantasy_agent.automation.automation_store import AutomationStore

if __name__ == '__main__':
    root, check_id, revision, now = sys.argv[1:]
    AutomationStore(root, clock=lambda: float(now)).claim(check_id, revision)
    os._exit(17)
