"""Shared deterministic identity joins and explicitly partial league scoring."""
from collections import defaultdict
import math

POSITIONS = ('QB', 'RB', 'WR', 'TE', 'K', 'DEF')
OFFENSE = ('QB', 'RB', 'WR', 'TE')
STAT_MAP = {'pass_yd': 'pass_yds', 'pass_td': 'pass_tds', 'pass_int': 'pass_ints',
            'rush_yd': 'rush_yds', 'rush_td': 'rush_tds', 'rec': 'rec_rec',
            'rec_yd': 'rec_yds', 'rec_td': 'rec_tds'}
OFFENSE_EXTRA = {'pass_2pt', 'rush_2pt', 'rec_2pt', 'fum_lost', 'fum', 'fum_rec_td', 'st_td', 'st_ff', 'st_fum_rec'}
DEFENSE_STATS = {'sack','int','fum_rec','ff','safe','blk_kick','def_td','def_st_td','def_st_ff','def_st_fum_rec'}
KICK_STATS = {'fgm_0_19','fgm_20_29','fgm_30_39','fgm_40_49','fgm_50_59','fgm_60p','fgmiss','xpm','xpmiss'}
DEF_MAP = {'sack':'def_sack','int':'def_int','fum_rec':'def_fr','ff':'def_ff','safe':'def_safety'}


def ident(value):
    if value is None or isinstance(value, bool) or str(value).strip() in ('','0','NA','None','null'):
        return None
    return str(value).strip()


def number(value):
    if value in (None, '', 'NA'):
        return None
    if isinstance(value, bool):
        raise ValueError('Boolean is not a statistic')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Nonfinite numeric input')
    return value


def positive(value):
    value = number(value)
    return value if value is not None and value > 0 else None


def position(value):
    return {'DST':'DEF', 'PK':'K', 'FB':'RB'}.get(value, value)


def team(value):
    return {'JAC':'JAX','WSH':'WAS','LA':'LAR'}.get(value, value)


def rows(data, key):
    value = data[key]
    if isinstance(value, dict):
        value = list(value.values())
    if not isinstance(value, list) or any(not isinstance(r, dict) for r in value):
        raise ValueError('Expected collection of objects: '+key)
    if 'count' in data and int(data['count']) != len(value):
        raise ValueError('Advertised count differs from actual rows: '+key)
    return value


def unique(records, key):
    result = {}
    for row in records:
        value = ident(row.get(key))
        if not value or value in result:
            raise ValueError('Missing/duplicate '+key)
        result[value] = row
    return result


def index(records, field, id_field):
    result = defaultdict(set)
    for row in records:
        if ident(row.get(field)) and ident(row.get(id_field)):
            result[ident(row[field])].add(ident(row[id_field]))
    return result


def match_player(records, pos, club, sleeper, indices):
    """Require agreement among explicit IDs; never infer identity from names."""
    if pos == 'DEF':
        candidates = {sid for sid, row in sleeper.items() if row.get('position') == 'DEF' and team(row.get('team') or sid) == club}
        return (next(iter(candidates)), ['team_defense']) if len(candidates) == 1 else (None, ['missing_or_ambiguous_team_defense'])
    evidence, candidates = [], set()
    for source, target in (('sportsdata_player_id','sportradar_id'), ('sportsdata_id','sportradar_id'),
                           ('espn_id','espn_id'), ('player_yahoo_id','yahoo_id')):
        for row in records:
            value = ident(row.get(source))
            matches = indices[target].get(value, set()) if value else set()
            if matches:
                candidates |= matches
                evidence.append(target)
    if len(candidates) != 1:
        return None, ['conflicting_ids' if candidates else 'no_shared_id']
    sid = next(iter(candidates))
    eligible = sleeper[sid].get('fantasy_positions') or [sleeper[sid].get('position')]
    if pos not in eligible:
        return None, ['position_mismatch']
    return sid, sorted(set(evidence))


def scoring(stats, pos, settings):
    """Calculate only verified mapped components; never silently fill omitted stats."""
    known = set(STAT_MAP) | OFFENSE_EXTRA | DEFENSE_STATS | KICK_STATS | {f'pts_allow_{x}' for x in ('0','1_6','7_13','14_20','21_27','28_34','35p')}
    unknown = sorted(k for k,v in settings.items() if v and k not in known)
    if unknown:
        raise ValueError('Unsupported league scoring rules: '+', '.join(unknown))
    contributions, missing = {}, []
    mapping = STAT_MAP if pos in OFFENSE else DEF_MAP if pos == 'DEF' else {'xpm':'xpt'}
    relevant = (set(STAT_MAP)|OFFENSE_EXTRA if pos in OFFENSE else
                DEFENSE_STATS | {k for k in settings if k.startswith('pts_allow_')} if pos == 'DEF' else KICK_STATS)
    for stat in sorted(relevant):
        weight = settings.get(stat, 0)
        if not weight:
            continue
        field = mapping.get(stat)
        value = number(stats.get(field)) if field else None
        if value is None:
            missing.append(stat)
        else:
            contributions[stat] = {'source_field': field, 'quantity': value, 'coefficient': weight, 'points': value*weight}
    if pos == 'K' and settings.get('fgmiss'):
        attempts, makes = number(stats.get('fga')), number(stats.get('fg'))
        if attempts is not None and makes is not None:
            if attempts < makes:
                raise ValueError('Projected field goals exceed attempts')
            contributions['fgmiss'] = {'source_field': 'fga-fg', 'quantity': attempts-makes,
                                       'coefficient': settings['fgmiss'], 'points': (attempts-makes)*settings['fgmiss']}
            missing.remove('fgmiss')
    required = {'QB': ('pass_yds','pass_tds','pass_ints','rush_yds','rush_tds'),
                'RB': ('rush_yds','rush_tds','rec_rec','rec_yds','rec_tds'),
                'WR': ('rec_rec','rec_yds','rec_tds'), 'TE': ('rec_rec','rec_yds','rec_tds'),
                'K': ('fg','fga','xpt'), 'DEF': tuple(DEF_MAP.values())}[pos]
    complete_core = all(number(stats.get(k)) is not None for k in required)
    subtotal = sum(r['points'] for r in contributions.values())
    ppr, standard = number(stats.get('points_ppr')), number(stats.get('points'))
    receptions = number(stats.get('rec_rec'))
    ppr_difference = None if None in (ppr, standard, receptions) else ppr-standard-receptions
    return {'supported_points': subtotal, 'contributions': contributions, 'uncovered_rules': missing,
            'exact_league_total': not missing, 'core_fields_complete': complete_core,
            'provider_points': standard, 'provider_points_ppr': ppr,
            'ppr_reception_check_error': ppr_difference,
            'basis': 'Sum of mapped projected components only; omitted events remain unknown, not zero.'}


