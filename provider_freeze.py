"""Persistent session network prohibition, independent of provider cache TTLs."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCK = ROOT/'data/draft_session/network_lock.json'
DEFAULTS = {'fantasypros':ROOT/'data/fantasypros','nflverse':ROOT/'data/nflverse/cache'}


class FrozenNetwork(RuntimeError):
    pass


def check(provider,directory):
    # Custom directories isolate synthetic test clients. Operational clients
    # must use the project's shared defaults, as required in AGENTS.md.
    path = LOCK if Path(directory).resolve()==DEFAULTS[provider].resolve() else Path(directory)/'draft_network_lock.json'
    if path.exists():
        lock = json.loads(path.read_text())
        if lock['active'] and provider in lock['blocked_providers']:
            raise FrozenNetwork(f'{provider} network frozen until the draft is confirmed complete; no request sent')
