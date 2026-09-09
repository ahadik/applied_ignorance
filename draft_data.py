"""Draft-specific collection and scope validation using shared provider access.

No HTTP or persistence here. Callers save only after the complete collection and
their draft strategy checks pass. Separate requests are not a transactional API
snapshot; the controller must still reconcile the live board with the browser.
"""
from datetime import datetime, timezone

from sleeper import get_sleeper


def read_draft_context(config):
    """Collect league rules, our identity, draft metadata, picks and rosters."""
    league_id = config['league_id']
    league = get_sleeper(f'league/{league_id}')
    if not isinstance(league, dict) or league.get('league_id') != league_id or not league.get('draft_id'):
        raise ValueError('League response missing or invalid; preserving saved snapshot')
    draft_id = league['draft_id']
    draft = get_sleeper(f'draft/{draft_id}')
    if not isinstance(draft, dict) or draft.get('draft_id') != draft_id:
        raise ValueError('Draft response missing or mismatched; preserving saved snapshot')
    if draft.get('league_id') not in (None, league_id):
        raise ValueError('Draft belongs to another league; preserving saved snapshot')
    user = get_sleeper(f"user/{config['username']}")
    if not isinstance(user, dict) or not user.get('user_id'):
        raise ValueError('User unavailable; preserving saved snapshot')
    picks = get_sleeper(f'draft/{draft_id}/picks')
    rosters = get_sleeper(f'league/{league_id}/rosters')
    if not isinstance(picks, list) or not isinstance(rosters, list):
        raise ValueError('Picks/rosters unavailable; preserving saved snapshot')
    if any(not isinstance(p, dict) or p.get('draft_id') != draft_id for p in picks):
        raise ValueError('Pick belongs to another draft; preserving saved snapshot')
    return {'fetched_at': datetime.now(timezone.utc).isoformat(),
            'league': league, 'draft': draft, 'user_id': user['user_id'],
            'picks': picks, 'rosters': rosters}


def read_live_draft(draft_id):
    """Collect a live board for the controller, rejecting unsupported trades."""
    draft = get_sleeper(f'draft/{draft_id}', retries=0)
    if not isinstance(draft, dict) or draft.get('draft_id') != draft_id:
        raise ValueError('Wrong draft or missing draft response')
    trades = get_sleeper(f'draft/{draft_id}/traded_picks', retries=0)
    if not isinstance(trades, list):
        raise ValueError('Traded-pick response unavailable; cannot establish ownership')
    if trades:
        raise ValueError('Traded picks require ownership support; controller will not assume snake ownership')
    picks = get_sleeper(f'draft/{draft_id}/picks', retries=0)
    if not isinstance(picks, list):
        raise ValueError('Invalid picks response')
    return draft, picks


def read_pre_draft_context(config):
    """Seven logical central-client reads for a static, untraded draft plan."""
    context = read_draft_context(config)
    draft_id = context['draft']['draft_id']
    trades = get_sleeper(f'draft/{draft_id}/traded_picks', retries=0)
    if not isinstance(trades,list) or trades:
        raise ValueError('Static snake plan requires confirmed untraded picks')
    users = get_sleeper(f"league/{config['league_id']}/users")
    if not isinstance(users,list) or any(not isinstance(u,dict) or not u.get('user_id') for u in users):
        raise ValueError('League membership response invalid')
    context.update(traded_picks=trades,league_users=users,
                   fetched_at=datetime.now(timezone.utc).isoformat())
    return context
