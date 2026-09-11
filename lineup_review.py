"""Evidence-bound review dispositions. Never changes the independent validator's result."""
from urllib.parse import urlparse

from automation_store import InvalidContract, instant
from weekly_data import fingerprint

REVIEWABLE = {'pregame_confirmation', 'uncertain_availability', 'concerning_news', 'locked_health_flag'}


def resolve(validation, review, native, now, read):
    if validation['status'] == 'PASS':
        return {'eligible': True, 'basis': 'independent_validator_pass', 'resolved': []}
    if validation['status'] != 'REVIEW' or any(i['level'] == 'error' for i in validation['issues']):
        raise InvalidContract('A failed validation cannot be resolved by a review')
    issues = [i for i in validation['issues'] if i['level'] == 'review']
    if not review or review.get('schema_version') != 1:
        raise InvalidContract('An evidence-bound review disposition is required')
    if any(review.get(k) != validation[k] for k in ('proposal_hash', 'input_hash', 'state_key')):
        raise InvalidContract('Review does not bind the exact proposal and current evidence')
    if review.get('issues_hash') != fingerprint(issues):
        raise InvalidContract('Review does not cover the exact findings')
    if not instant(review['reviewed_at']) <= now < instant(review['expires_at']) <= instant(validation['expires_at']):
        raise InvalidContract('Review disposition expired or has invalid times')
    owner, _ = read(review['owner_approval'])
    if owner.get('basis') != 'explicit_owner_review' or any(owner.get(k) != review[k] for k in ('proposal_hash', 'input_hash', 'issues_hash')):
        raise InvalidContract('Save owner review of these exact findings and inputs')
    entries = review.get('resolutions', [])
    if len(entries) != len(issues):
        raise InvalidContract('Every review finding requires one resolution')
    covered = set()
    for entry in entries:
        index = entry.get('issue_index')
        if type(index) is not int or index in covered or not 0 <= index < len(issues):
            raise InvalidContract('Duplicate or unknown review finding')
        covered.add(index)
        finding = issues[index]
        if finding['code'] not in REVIEWABLE or not isinstance(entry.get('reason'), str) or not entry['reason'].strip():
            raise InvalidContract('Finding has no supported reasoned resolution')
        if finding['code'] == 'locked_health_flag':
            if finding['player_id'] not in native['locked_player_ids'] or entry.get('disposition') != 'retain_locked_starter':
                raise InvalidContract('Locked health resolution can only retain the locked starter')
            continue
        # Operator-transcribed primary evidence. No unsupported automatic news extraction.
        official = entry.get('official', {})
        url = urlparse(official.get('url', ''))
        if url.scheme != 'https' or url.hostname not in ('www.nfl.com', 'nfl.com') or not url.path.startswith('/news/'):
            raise InvalidContract('Availability evidence requires an official NFL news page')
        if official.get('player_id') != finding['player_id'] or official.get('status') != 'active':
            raise InvalidContract('Official evidence must explicitly establish this player as active')
        player = next((p for p in validation['players'] if p['player_id'] == finding['player_id']), None)
        if not player or not player.get('game') or official.get('game_id') != player['game']['game_id']:
            raise InvalidContract('Official availability evidence belongs to another game')
        if not instant(official['published_at']) <= instant(official['observed_at']) <= now:
            raise InvalidContract('Official publication or observation time is invalid')
        if now - instant(official['observed_at']) > 300 or now - instant(official['published_at']) > 5400:
            raise InvalidContract('Official availability evidence is too old')
        if not isinstance(official.get('statement'), str) or not official['statement'].strip():
            raise InvalidContract('Save the observed official availability statement')
        observed, _ = read(official['evidence'])
        if observed.get('basis') != 'observed_official_nfl_page' or any(observed.get(k) != official[k] for k in ('url', 'player_id', 'game_id', 'status', 'statement', 'published_at', 'observed_at')):
            raise InvalidContract('Official evidence must match the saved page observation')
        if entry.get('disposition') != 'official_active_reviewed':
            raise InvalidContract('Unsupported availability disposition')
        if finding['player_id'] in native['locked_player_ids']:
            raise InvalidContract('Review cannot unlock a player')
    return {'eligible': True, 'basis': 'supervised_review_resolution', 'independent_status': 'REVIEW',
            'resolved': entries, 'review_hash': fingerprint(review)}
