"""Stage 1 access probes. All provider requests use the shared API clients.

Usage: python3 -m fantasy_agent fantasypros_diagnostic --season 2026
Reports are private, cache-first, and contain metadata rather than player feeds.
"""
import argparse
from datetime import datetime, timezone
import json

from fantasy_agent.providers.sleeper import get_sleeper
from fantasy_agent.core.storage import save_atomic
from fantasy_agent.providers.fantasypros import APIError, InvalidData, FantasyPros, ROOT, get_fantasypros


def summarize(result, collection):
    data = result['data']
    rows = data[collection]
    evidence = {}
    # Only scope/count/date fields, never arbitrary response content or headers.
    for key in ('sport', 'season', 'year', 'week', 'scoring', 'position_id',
                'positions', 'ranking_type_name', 'count', 'total_experts',
                'last_updated', 'last_updated_ts'):
        value = data.get(key)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            evidence[key] = value
    records = rows if isinstance(rows, list) else list(rows.values())
    dates = sorted({str(row[key]) for row in records if isinstance(row, dict)
                    for key in ('created', 'updated', 'injury_update_date')
                    if row.get(key) is not None})
    return {'status': 'passed_basic_checks', 'records': len(rows),
            'scope_and_source_metadata': evidence,
            'source_date_examples': dates[-3:],
            'fetched_at': result['fetched_at'], 'cache_hit': result['cache_hit'],
            'quota_headers_at_fetch': result.get('quota_headers_at_fetch', {}),
            'freshness': 'Source dates require review; retrieval time is not source freshness.'}


def diagnose(season, request=get_fantasypros, usage=None, state_reader=get_sleeper):
    usage = usage or FantasyPros().usage
    before = usage()
    report = {'generated_at': datetime.now(timezone.utc).isoformat(),
              'requested_season': season, 'stage': 1, 'probes': [],
              'production_entitlement': 'Not evaluated by access probes; user-supplied account approval is recorded in docs/FANTASYPROS.md.',
              'provider_quota': 'Account approval states 1 request/second and 500/day; reset time and remaining provider balance are unknown. No documented account quota endpoint; numeric headers, if present, are observations at fetch time.',
              'limitations': ['Access diagnostics only; no scoring, identity mapping, or draft recommendations.',
                             'RB is the projection access probe; see docs/MILESTONE_2.md for the separate full collection/coverage checkpoint.',
                             'Broad rankings, expert metadata, and comparison endpoints are not probed; historical points remain disabled.',
                             'An empty news/injury response does not prove absence of news/injuries.']}
    probes = [
        ('player_directory', 'nfl/players', {}, 'players'),
        ('draft_ppr_consensus', f'nfl/{season}/consensus-rankings',
         {'position': 'ALL', 'type': 'DRAFT', 'scoring': 'PPR', 'week': 0}, 'players'),
        ('ppr_adp', f'nfl/{season}/consensus-rankings',
         {'position': 'ALL', 'type': 'ADP', 'scoring': 'PPR', 'week': 0}, 'players'),
        ('rb_season_projections', f'nfl/{season}/projections', {'position': 'RB', 'week': 0}, 'players'),
        ('recent_news', 'nfl/news', {'limit': 3, 'order_by': 'updated'}, 'items'),
        ('current_injuries', 'nfl/injuries', None, 'injuries'),
    ]
    stop = False
    for name, path, params, collection in probes:
        entry = {'name': name, 'path': path, 'parameters': params}
        if stop:
            entry.update(status='not_run', reason='Stopped after an access/budget/connection failure to conserve calls.')
        else:
            if params is None:
                try:
                    state = state_reader('state/nfl')
                    week = int(state['week'])
                    if str(state['season']) != str(season) or not 1 <= week <= 18 or state.get('season_type') != 'regular':
                        raise ValueError('No matching regular-season week')
                    params = {'year': season, 'week': week, 'include_probabilities': True}
                    entry['parameters'] = params
                    report['injury_week_basis'] = {'source': 'Sleeper state/nfl', 'season': season, 'week': week}
                except Exception:
                    # External error text can contain request information; never print it.
                    entry.update(status='not_run', reason='Could not establish a matching current regular-season NFL week.')
                    report['probes'].append(entry)
                    continue
            try:
                # No forced refresh and no automatic diagnostic retries: one attempt
                # per cache miss, at most six FantasyPros calls for this command.
                entry.update(summarize(request(path, params, retries=0), collection))
            except InvalidData as error:
                entry.update(status='invalid_data', reason=str(error))
            except APIError as error:
                entry.update(status='access_failed', reason=str(error))
                stop = True
        report['probes'].append(entry)
    after = usage()
    report['local_budget_before'] = before
    report['local_budget_after'] = after
    report['local_attempt_delta'] = after['attempts_last_24h'] - before['attempts_last_24h']
    report['access_checks_passed'] = all(p['status'] == 'passed_basic_checks' for p in report['probes'])
    report['ready_for_draft_use'] = False
    report['next_checkpoint'] = 'Account approval is recorded in docs/FANTASYPROS.md; integrated data/scoring coverage is recorded in docs/MILESTONE_2.md. This diagnostic does not start strategy work or a mock.'
    return report


def render(report):
    lines = ['# Stage 1 — FantasyPros access report', '',
             f"Generated: {report['generated_at']}", '',
             f"Requested season: {report['requested_season']}",
             f"All access probes passed: {report['access_checks_passed']}",
             f"Production entitlement: {report['production_entitlement']}", '',
             '| Probe | Result | Records | Cached |', '|---|---|---:|---|']
    for probe in report['probes']:
        lines.append(f"| {probe['name']} | {probe['status']} | {probe.get('records', '—')} | {probe.get('cache_hit', '—')} |")
    for probe in report['probes']:
        lines.extend(['', f"## {probe['name']}", '',
                      f"Request: `{probe['path']}`; parameters: `{json.dumps(probe['parameters'], sort_keys=True)}`"])
        if 'reason' in probe:
            lines.append(probe['reason'])
        else:
            lines.extend([f"Retrieved: {probe['fetched_at']}",
                          f"Source metadata: `{json.dumps(probe['scope_and_source_metadata'], sort_keys=True)}`",
                          f"Source date examples: `{json.dumps(probe['source_date_examples'])}`",
                          f"Quota headers at fetch: `{json.dumps(probe['quota_headers_at_fetch'])}`"])
    lines.extend(['', '## Budget and checkpoint', '',
                  f"Local attempts added during run: {report['local_attempt_delta']} (includes concurrent client activity, if any).",
                  f"Local ledger after run: `{json.dumps(report['local_budget_after'])}`", '',
                  report['provider_quota'], '', *['- ' + x for x in report['limitations']], '',
                  report['next_checkpoint'], '',
                  'No draft-ready data or production entitlement is asserted by this report.'])
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', type=int, required=True)
    args = parser.parse_args()
    if not 2000 <= args.season <= 2100:
        parser.error('season must be a four-digit NFL year')
    report = diagnose(args.season)
    destination = ROOT / 'data' / 'fantasypros' / 'diagnostic.json'
    save_atomic(destination, report)
    destination.with_suffix('.md').write_text(render(report))
    print(render(report))
    print(f'Saved report: {destination.with_suffix(".md")}')
    return 0 if report['access_checks_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
