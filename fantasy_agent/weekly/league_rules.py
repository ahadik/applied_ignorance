"""Read current league rules through central Sleeper access; no account writes.

Usage: python3 -m fantasy_agent league_rules
Saves data/league_rules/latest.json only after validation. Numeric setting codes
remain raw observations until their meanings are independently verified.
"""
from fantasy_agent.paths import ROOT as PROJECT_ROOT
from fantasy_agent.core.project_config import load_config, check_user
import argparse
import json
from pathlib import Path

from fantasy_agent.providers.sleeper import get_sleeper
from fantasy_agent.core.storage import save_atomic

ROOT = PROJECT_ROOT


def collect(config):
    league_id = config['league_id']
    evidence = {}

    def read(name, path):
        result = get_sleeper(path, with_metadata=True, retries=0)
        evidence[name] = {k: v for k, v in result.items() if k != 'data'}
        return result['data']

    league = read('league', f'league/{league_id}')
    if (not isinstance(league, dict) or league.get('league_id') != league_id
            or league.get('sport') != 'nfl'
            or not isinstance(league.get('settings'), dict)
            or not isinstance(league.get('scoring_settings'), dict)
            or not isinstance(league.get('roster_positions'), list)):
        raise ValueError('Missing or mismatched league rules')
    user = read('user', f"user/{config['username']}")
    check_user(config, user)
    if not isinstance(user, dict) or not user.get('user_id'):
        raise ValueError('Missing user identity')
    rosters = read('rosters', f'league/{league_id}/rosters')
    if (not isinstance(rosters, list) or len(rosters) != league.get('total_rosters')
            or any(not isinstance(r, dict) or not r.get('roster_id') for r in rosters)
            or len({r['roster_id'] for r in rosters}) != len(rosters)):
        raise ValueError('Incomplete or invalid league rosters')
    owned = [r for r in rosters if r.get('owner_id') == user['user_id']]
    if len(owned) != 1:
        raise ValueError('Our roster ownership is not unique')
    return {'schema_version': 1, 'league_id': league_id,
            'season': league.get('season'), 'status': league.get('status'),
            'settings': league['settings'], 'scoring_settings': league['scoring_settings'],
            'roster_positions': league['roster_positions'],
            'roster_count': len(rosters), 'our_roster_id': owned[0]['roster_id'],
            'our_roster_settings': owned[0].get('settings', {}),
            'evidence': evidence,
            'interpretation': 'Raw API settings; undocumented enum meanings are unverified.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = collect(load_config(ROOT))
        save_atomic(ROOT / 'data/league_rules/latest.json', result)
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f'Rules collection failed: {error}\nPrevious report retained.\n')


if __name__ == '__main__':
    main()
