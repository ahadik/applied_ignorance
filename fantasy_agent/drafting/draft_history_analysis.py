"""Offline draft evidence from collected nflverse data; never makes network calls."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import hashlib
import math
from pathlib import Path
from fantasy_agent.providers.nflverse import ROOT
from fantasy_agent.core.storage import save_atomic

POSITIONS = {'QB', 'RB', 'WR', 'TE', 'K'}
METRICS = ('attempts', 'passing_yards', 'passing_tds', 'passing_interceptions',
           'carries', 'rushing_yards', 'rushing_tds', 'targets', 'receptions',
           'receiving_yards', 'receiving_tds', 'fantasy_points_ppr', 'fg_made', 'fg_att', 'pat_made')


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Source timestamp has no timezone')
    return result


def number(value):
    if value in (None, '', 'NA', 'NaN'):
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Nonfinite historical value')
    return result


def team(value):
    return {'LA': 'LAR', 'JAC': 'JAX', 'WSH': 'WAS'}.get(value, value)


def identity_maps(rows):
    identities = defaultdict(list)
    indices = {'pfr_id': defaultdict(set), 'espn_id': defaultdict(set)}
    for row in rows:
        gsis = row.get('gsis_id')
        if not gsis:
            continue
        identities[gsis].append(row)
        for field in indices:
            if row.get(field):
                indices[field][row[field]].add(gsis)
    unique = {key: values[0] for key, values in identities.items() if len(values) == 1}
    return unique, indices


def metric_summary(rows, fields):
    result = {}
    for field in fields:
        values = [number(row.get(field)) for row in rows]
        present = [v for v in values if v is not None]
        complete = bool(rows) and len(present) == len(rows)
        result[field] = {'total': sum(present) if complete else None,
                         'per_recorded_game': sum(present)/len(rows) if complete else None,
                         'missing_records': len(rows)-len(present)}
    return result


def regular_rows(rows, season, type_field, identity_field, quarantine=None):
    selected, seen = [], set()
    for row in rows:
        if int(row['season']) != season:
            raise ValueError('Historical season mismatch')
        if row[type_field] != 'REG':
            continue
        week = int(row['week'])
        if not 1 <= week <= (18 if season >= 2021 else 17):
            raise ValueError('Invalid regular-season week')
        key = (row[identity_field], row['game_id'])
        if not all(key) and quarantine is not None:
            quarantine.append({'season': season, 'game_id': row['game_id'], 'id_field': identity_field,
                               'name': row.get('player_display_name', row.get('player', '')),
                               'position': row.get('position'), 'reason': 'missing_player_or_game_id'})
            continue
        if not all(key) or key in seen:
            raise ValueError(f'Missing identity or duplicate player/game record: season={season}, field={identity_field}, key={key}')
        seen.add(key)
        selected.append(row)
    if not selected:
        raise ValueError('No regular-season historical records')
    return selected


def historical_features(stats_by_year, snaps_by_year, identities, indices):
    players, unmatched, coverage = {}, [], {}
    for season, raw in sorted(stats_by_year.items()):
        excluded = []
        stats = regular_rows(raw, season, 'season_type', 'player_id', excluded)
        snaps = regular_rows(snaps_by_year[season], season, 'game_type', 'pfr_player_id', excluded)
        max_week = max(int(r['week']) for r in stats)
        coverage[str(season)] = {'regular_games': len({r['game_id'] for r in stats}),
                                 'weeks': sorted({int(r['week']) for r in stats}),
                                 'teams': len({team(r['team']) for r in stats}),
                                 'stat_records': len(stats), 'snap_records': len(snaps),
                                 'excluded_records': excluded,
                                 'late_window_weeks': list(range(max_week-3, max_week+1))}
        grouped, snap_groups = defaultdict(list), defaultdict(list)
        for row in stats:
            if row['position'] in POSITIONS:
                grouped[row['player_id']].append(row)
        for row in snaps:
            if row['position'] not in POSITIONS:
                continue
            matches = indices['pfr_id'].get(row['pfr_player_id'], set())
            if len(matches) != 1 or next(iter(matches), None) not in identities:
                unmatched.append({'season': season, 'pfr_id': row['pfr_player_id'],
                                  'name': row['player'], 'reason': 'missing_or_ambiguous_pfr_crosswalk'})
                continue
            snap_groups[next(iter(matches))].append(row)
        for gsis in sorted(set(grouped) | set(snap_groups)):
            games, snap_games = grouped[gsis], snap_groups[gsis]
            identity = identities.get(gsis, {})
            name = identity.get('display_name') or (games[0].get('player_display_name') if games else '')
            player = players.setdefault(gsis, {'gsis_id': gsis, 'name': name, 'pfr_id': identity.get('pfr_id'),
                                               'espn_id': identity.get('espn_id'), 'seasons': {}})
            late = [r for r in games if int(r['week']) >= max_week-3]
            late_snaps = [r for r in snap_games if int(r['week']) >= max_week-3]
            def snap_summary(records):
                for row in records:
                    share = number(row['offense_pct'])
                    if share is not None and not 0 <= share <= 1:
                        raise ValueError('Snap share outside fraction range; schema review required')
                values = metric_summary(records, ('offense_snaps', 'offense_pct'))
                return {'recorded_games': len(records), 'offense_snaps': values['offense_snaps'],
                        'mean_game_offense_snap_share': values['offense_pct']['per_recorded_game'],
                        'missing_share_records': values['offense_pct']['missing_records']}
            player['seasons'][str(season)] = {
                'position': games[0]['position'] if games else snap_games[0]['position'],
                'teams': sorted({team(r['team']) for r in games+snap_games}),
                'stats_recorded_games': len(games), 'metrics': metric_summary(games, METRICS),
                'snaps': snap_summary(snap_games),
                'late_window_weeks': coverage[str(season)]['late_window_weeks'],
                'late_stats_recorded_games': len(late), 'late_metrics': metric_summary(late, METRICS),
                'late_snaps': snap_summary(late_snaps)}
    distinct = {json.dumps(r, sort_keys=True): r for r in unmatched}
    return players, list(distinct.values()), coverage


def current_depth(rows, identities, indices, as_of, max_age_hours=36):
    required = {'dt', 'team', 'gsis_id', 'espn_id', 'pos_abb', 'pos_rank', 'pos_slot', 'pos_grp'}
    if not rows or not required.issubset(rows[0]):
        raise ValueError('Unsupported current depth-chart schema')
    latest, parsed, future = {}, [], 0
    for row in rows:
        dt = timestamp(row['dt'])
        if dt > as_of:
            future += 1
            continue
        club = team(row['team'])
        latest[club] = max(latest.get(club, dt), dt)
        parsed.append((row, club, dt))
    if not latest:
        raise ValueError('No depth snapshot at or before analysis time')
    ages = {club: (as_of-dt).total_seconds()/3600 for club, dt in latest.items()}
    roles, unmatched, seen = [], [], set()
    for row, club, dt in parsed:
        position = {'PK': 'K', 'FB': 'RB'}.get(row['pos_abb'], row['pos_abb'])
        if dt != latest[club] or position not in POSITIONS:
            continue
        gsis = row['gsis_id']
        espn_matches = indices['espn_id'].get(row['espn_id'], set())
        if not gsis and len(espn_matches) == 1:
            gsis = next(iter(espn_matches))
        if not gsis or gsis not in identities or espn_matches and espn_matches != {gsis}:
            unmatched.append({'team': club, 'name': row['player_name'], 'gsis_id': gsis,
                              'espn_id': row['espn_id'], 'reason': 'missing_or_conflicting_depth_identity'})
            continue
        rank = int(row['pos_rank'])
        if rank < 1:
            raise ValueError('Invalid depth rank')
        key = (club, row['pos_grp'], row['pos_slot'], rank, gsis)
        if key in seen:
            continue
        seen.add(key)
        roles.append({'gsis_id': gsis, 'name': row['player_name'], 'team': club,
                      'position': position, 'source_position': row['pos_abb'],
                      'formation': row['pos_grp'], 'slot': row['pos_slot'], 'depth_rank': rank,
                      'observed_at': dt.isoformat(), 'age_hours': round(ages[club], 2),
                      'usable': ages[club] <= max_age_hours})
    for role in roles:
        role['listed_ahead_ids'] = sorted({other['gsis_id'] for other in roles
            if other['team'] == role['team'] and other['formation'] == role['formation']
            and other['slot'] == role['slot'] and other['depth_rank'] < role['depth_rank']})
    return roles, unmatched, {'team_count': len(latest), 'team_age_hours': ages,
                             'stale_teams': sorted(t for t in ages if ages[t] > max_age_hours),
                             'future_rows_excluded': future}


def build(folder, as_of, max_age_hours=36):
    manifest = json.loads((folder / 'collection.json').read_text())
    if not manifest.get('complete'):
        raise ValueError('Collection is incomplete; previous files are not a valid replacement')
    snapshots, provenance = {}, []
    for entry in manifest['datasets']:
        raw = Path(entry['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry.get('snapshot_sha256'):
            raise ValueError('Snapshot checksum missing or changed; rerun the cached collection command')
        saved = json.loads(raw)
        if saved['provenance'] != entry['provenance']:
            raise ValueError('Snapshot provenance differs from collection manifest')
        if timestamp(saved['provenance']['asset_updated_at']) > as_of:
            raise ValueError('Asset publication is later than the requested analysis time')
        snapshots[(entry['dataset'], entry['season'])] = saved['data']
        provenance.append(saved['provenance'])
    identities, indices = identity_maps(snapshots[('players', None)])
    seasons = manifest['history_seasons']
    players, unmatched_snaps, coverage = historical_features(
        {y: snapshots[('player_stats', y)] for y in seasons},
        {y: snapshots[('snap_counts', y)] for y in seasons}, identities, indices)
    roles, unmatched_depth, depth_quality = current_depth(
        snapshots[('depth_charts', manifest['draft_season'])], identities, indices, as_of, max_age_hours)
    for role in roles:
        identity = identities[role['gsis_id']]
        player = players.setdefault(role['gsis_id'], {'gsis_id': role['gsis_id'], 'name': role['name'],
                 'pfr_id': identity.get('pfr_id'), 'espn_id': identity.get('espn_id'), 'seasons': {}})
        player.setdefault('current_depth', []).append(role)
    for player in players.values():
        player['no_recorded_history'] = not player['seasons']
        latest = player['seasons'].get(str(max(seasons)))
        current = {r['team'] for r in player.get('current_depth', []) if r['usable']}
        player['current_team_not_in_latest_history'] = bool(current and latest and not current.intersection(latest['teams']))
    result = {'draft_season': manifest['draft_season'], 'as_of': as_of.isoformat(), 'history_seasons': seasons,
              'players': sorted(players.values(), key=lambda p: p['gsis_id']), 'historical_coverage': coverage,
              'depth_quality': depth_quality, 'unmatched_snap_ids': unmatched_snaps,
              'unmatched_depth': unmatched_depth, 'sources': provenance,
              'limitations': ['Historical production is not a current-season projection.',
                  'Per-game means use recorded rows, not assumed games played; absent/missing values are not zero.',
                  'Late usage uses the last four observed league regular-season weeks, not a player\'s last four appearances.',
                  'Snap percentages are unweighted means across recorded games, not season-wide snap shares.',
                  'Depth rank is within a listed formation/slot; it does not guarantee workload or injury replacement.',
                  'PPR points use the source scoring, not an exact recomputation of our league settings.',
                  'Current-team changes and missing history require review, especially rookies.',
                  'Player matching uses GSIS/PFR/ESPN IDs; Sleeper/FantasyPros integration remains separate.',
                  'Latest corrected historical files are not prediction-time snapshots suitable for leakage-free backtests.']}
    save_atomic(folder / 'draft_evidence.json', result)
    report = render(result)
    (folder / 'DRAFT_EVIDENCE.md').write_text(report)
    return result, report


def render(result):
    players = result['players']
    roles = [r for p in players for r in p.get('current_depth', [])]
    lines = ['# Historical evidence for tonight\'s draft', '', f"Analysis time: {result['as_of']}",
             f"Historical seasons: {', '.join(map(str, result['history_seasons']))}", '',
             f"Player records: {len(players)}; current depth roles: {len(roles)}; teams: {result['depth_quality']['team_count']}.",
             f"Unmatched historical snap identities: {len(result['unmatched_snap_ids'])}; unmatched current depth rows: {len(result['unmatched_depth'])}.",
             f"Stale depth teams: {result['depth_quality']['stale_teams'] or 'none'}.", '',
             '| Season | Regular-season games in stats | Teams | Weeks |', '|---|---:|---:|---|']
    for year, c in result['historical_coverage'].items():
        lines.append(f"| {year} | {c['regular_games']} | {c['teams']} | {min(c['weeks'])}–{max(c['weeks'])} |")
    lines += ['', f"Historical records excluded for missing identity/game ID: {sum(len(c['excluded_records']) for c in result['historical_coverage'].values())}."]
    lines += ['', '## Collected sources', '']
    for source in result['sources']:
        lines.append(f"- {source['dataset']} {source['season'] or ''}: asset published {source['asset_updated_at']}; {source['url']}")
    lines += ['', '## Interpretation limits', ''] + ['- '+x for x in result['limitations']]
    lines += ['', 'Detailed per-player totals, observed-game averages, late usage, depth roles and quarantined matches are in `draft_evidence.json`. This report is evidence, not a draft ranking.']
    return '\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--draft-season', required=True, type=int)
    parser.add_argument('--as-of', help='Timezone-aware ISO timestamp; defaults to now')
    parser.add_argument('--max-depth-age-hours', type=float, default=36)
    parser.add_argument('--player', help='Read an existing evidence record by GSIS ID or name fragment; no rebuild')
    parser.add_argument('--review-issues', action='store_true', help='Inspect quarantined records in the saved evidence')
    args = parser.parse_args()
    try:
        if not math.isfinite(args.max_depth_age_hours) or args.max_depth_age_hours <= 0:
            raise ValueError('Depth freshness limit must be positive and finite')
        folder = ROOT / 'data/nflverse/draft' / str(args.draft_season)
        if args.player or args.review_issues:
            evidence = json.loads((folder / 'draft_evidence.json').read_text())
            if args.review_issues:
                print(json.dumps({'unmatched_snaps': evidence['unmatched_snap_ids'],
                    'unmatched_depth': evidence['unmatched_depth'],
                    'excluded_records': {y: c['excluded_records'] for y, c in evidence['historical_coverage'].items()}}, indent=2))
            else:
                matches = [p for p in evidence['players'] if p['gsis_id'] == args.player or args.player.lower() in p['name'].lower()]
                print(json.dumps({'as_of': evidence['as_of'], 'matches': matches}, indent=2))
            return
        result, report = build(folder, timestamp(args.as_of) if args.as_of else datetime.now(timezone.utc), args.max_depth_age_hours)
        print(report)
        print(f'Saved: {folder / "draft_evidence.json"}')
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, str(error)+'\n')


if __name__ == '__main__':
    main()
