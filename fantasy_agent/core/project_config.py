"""Load project settings with an explicitly configured Sleeper league."""
from fantasy_agent.paths import ROOT as PROJECT_ROOT
import json
import os
from pathlib import Path
import re

ROOT = PROJECT_ROOT


def load_config(root=ROOT, *, path=None):
    """Read the league from the environment or local .env, without a default."""
    path = Path(path) if path is not None else Path(root) / 'config.json'
    config = json.loads(path.read_text())
    names = {'SLEEPER_LEAGUE_ID': 'league_id', 'SLEEPER_USER_ID': 'user_id'}
    values = {name: os.environ.get(name) for name in names}
    env_path = path.parent / '.env'
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            match = re.fullmatch(r'\s*(?:export\s+)?(SLEEPER_LEAGUE_ID|SLEEPER_USER_ID)\s*=\s*(.*?)\s*', line)
            if match and os.environ.get(match[1]) is None:
                values[match[1]] = match[2]
    for name, field in names.items():
        value = (values[name] or '').strip().strip('\"\'')
        if not value:
            raise ValueError(f'Set {name} in .env before running league operations')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
            raise ValueError(f'{name} must be an identifier, not a URL')
        config[field] = value
    return config


def check_user(config, user):
    """Require the provider profile to match the configured account ID."""
    if not config.get('user_id') or not isinstance(user, dict) or user.get('user_id') != config['user_id']:
        raise ValueError('Sleeper profile differs from SLEEPER_USER_ID')
