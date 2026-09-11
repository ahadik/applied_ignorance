"""Durable owner pushes and game reminders. All sends use the central Pushover client."""
from fantasy_agent.paths import ROOT as PROJECT_ROOT
import argparse
from contextlib import contextmanager, closing
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import time
from zoneinfo import ZoneInfo

from fantasy_agent.automation.automation_store import instant, utc
from fantasy_agent.core.project_config import load_config
from fantasy_agent.core.player_scoring import team
from fantasy_agent.providers.pushover import get_pushover
from fantasy_agent.providers.sleeper import get_sleeper
from fantasy_agent.core.storage import save_atomic

ROOT = PROJECT_ROOT


class Notices:
    def __init__(self, root=ROOT, *, clock=time.time):
        self.root, self.clock = Path(root), clock
        self.folder = self.root / 'data/team_notifications'

    @contextmanager
    def db(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.folder / 'state.sqlite3', timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE IF NOT EXISTS notices(id TEXT PRIMARY KEY, message TEXT, state TEXT, result TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS games(id TEXT PRIMARY KEY, value TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS progress(key TEXT PRIMARY KEY, value INTEGER)')
        try:
            with db:
                yield db
        finally:
            db.close()

    def enable(self):
        path = self.folder / 'policy.json'
        self.folder.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            cfg = load_config(self.root)
            save_atomic(path, {'enabled_at': self.clock(), 'league_id': cfg['league_id'],
                              'user_id': cfg['user_id'], 'before_minutes': 30, 'scope': 'roster_games'})
        return self.policy()

    def policy(self):
        path = self.folder / 'policy.json'
        if not path.exists():
            return None
        value = json.loads(path.read_text())
        cfg = load_config(self.root)
        if any(value[k] != cfg[k] for k in ('league_id', 'user_id')):
            raise ValueError('Notification policy belongs to another league or account')
        return value

    def enqueue(self, key, message):
        if not message or len(message) > 1024:
            raise ValueError('Notification must contain 1 to 1024 characters')
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO notices VALUES (?,?,?,?)', (key, message, 'pending', '{}'))

    def flush(self):
        results = []
        with self.db() as db:
            rows = db.execute("SELECT * FROM notices WHERE state='pending' ORDER BY rowid").fetchall()
        for row in rows:
            if row['id'].startswith('before-'):
                with self.db() as db:
                    game = db.execute('SELECT value FROM games WHERE id=?', (row['id'][7:],)).fetchone()
                    if not game or self.clock() >= json.loads(game[0])['kickoff']:
                        db.execute("UPDATE notices SET state='missed' WHERE id=?", (row['id'],))
                        continue
            try:
                result = get_pushover(self.root).send('team-' + row['id'], row['message'])
            except (ValueError, OSError) as error:
                # Cooldown and missing credentials remain pending for the next wakeup.
                results.append({'id': row['id'], 'state': 'pending', 'error': str(error)})
                break
            with self.db() as db:
                db.execute('UPDATE notices SET state=?,result=? WHERE id=?',
                           (result['state'], json.dumps(result), row['id']))
            results.append({'id': row['id'], **result})
        return results

    def plan(self, snapshot):
        from fantasy_agent.weekly.weekly_data import load
        raw = load(snapshot)
        ctx = raw['final_context']
        policy = self.policy()
        if not policy or ctx['league']['league_id'] != policy['league_id'] or ctx['user']['user_id'] != policy['user_id']:
            raise ValueError('Snapshot belongs to another notification scope')
        directory = raw['sleeper_players']['data']
        owned = ctx['roster']['players']
        with self.db() as db:
            for game in raw['schedule']['data']:
                if game.get('game_type') != 'REG' or int(game['week']) < ctx['week']:
                    continue
                clubs = {team(game['home_team']), team(game['away_team'])}
                ids = [sid for sid in owned if team(directory.get(sid, {}).get('team') or sid) in clubs]
                if not ids:
                    db.execute('DELETE FROM games WHERE id=? AND json_extract(value,\'$.kickoff\')>?', (game['game_id'], self.clock()))
                    continue
                kickoff = datetime.fromisoformat(game['gameday'] + 'T' + game['gametime']).replace(tzinfo=ZoneInfo('America/New_York')).timestamp()
                if kickoff < policy['enabled_at']:
                    continue
                record = {'id': game['game_id'], 'kickoff': kickoff, 'week': int(game['week']),
                          'away': game['away_team'], 'home': game['home_team'], 'season': ctx['season'],
                          'roster_id': ctx['roster']['roster_id'], 'players': {sid: directory.get(sid, {}).get('full_name') or sid for sid in ids},
                          'snapshot': str(Path(snapshot).relative_to(self.root))}
                # Preserve the kickoff roster once the pregame notice has been prepared.
                old = db.execute('SELECT value FROM games WHERE id=?', (record['id'],)).fetchone()
                if old:
                    previous = json.loads(old[0])
                    for key in ('pregame_roster', 'final'):
                        if key in previous:
                            record[key] = previous[key]
                    if self.clock() >= previous['kickoff']:
                        record['players'] = previous['players']
                db.execute('INSERT OR REPLACE INTO games VALUES (?,?)', (record['id'], json.dumps(record)))
        return self.status()

    def capture_changes(self):
        policy = self.policy()
        path = self.root / 'data/lineup_execution/state.sqlite3'
        if not policy or not path.exists():
            return
        with self.db() as db:
            cursor = db.execute("SELECT value FROM progress WHERE key='execution_events'").fetchone()
            cursor = cursor[0] if cursor else 0
        players = None
        with closing(sqlite3.connect(path)) as db:
            rows = db.execute("SELECT id,kind,value FROM events WHERE id>? AND at>=? AND kind IN ('reconciled','roster_reconciled') ORDER BY id",
                              (cursor, utc(policy['enabled_at']))).fetchall()
            for event_id, kind, raw in rows:
                event = json.loads(raw)
                outcome = event['outcome']
                if outcome not in ('confirmed', 'pending', 'won', 'lost', 'cancelled', 'applied'):
                    continue
                table = 'actions' if kind == 'reconciled' else 'roster_actions'
                row = db.execute('SELECT value FROM ' + table + ' WHERE id=?', (event['action_id'],)).fetchone()
                if not row:
                    continue
                action = json.loads(row[0])
                if kind == 'reconciled':
                    message = 'Lineup changed: ' + action['outgoing'] + ' → ' + action['incoming'] + '.'
                else:
                    step = action['step']
                    message = step['kind'].replace('_', ' ') + ': ' + outcome
                    message += ''.join(' | ' + key + ' ' + str(step[key]) for key in ('add', 'drop', 'player_id') if step.get(key)) + '.'
                # Resolve IDs from the last verified player directory without another API call.
                if players is None:
                    snapshots = list((self.root / 'data/weekly').glob('*/*/snapshots/*/sleeper_players.json'))
                    players = json.loads(max(snapshots, key=lambda p: p.stat().st_mtime).read_text())['data'] if snapshots else {}
                if players:
                    import re
                    message = re.sub(r'\b\d+\b', lambda m: players.get(m[0], {}).get('full_name') or m[0], message)
                self.enqueue(event['action_id'] + '-' + outcome, message)
        if rows:
            # All enqueues commit before advancing. Restart can replay IDs without duplicate sends.
            with self.db() as db:
                db.execute("INSERT OR REPLACE INTO progress VALUES ('execution_events',?)", (rows[-1][0],))

    def live_roster(self, game, *, before=True):
        cfg = load_config(self.root)
        rosters = get_sleeper('league/' + cfg['league_id'] + '/rosters', retries=0)
        owned = [r for r in rosters if r.get('owner_id') == cfg['user_id'] and r.get('roster_id') == game['roster_id']]
        if len(owned) != 1:
            raise ValueError('Expected account roster is missing')
        matches = get_sleeper('league/' + cfg['league_id'] + '/matchups/' + str(game['week']), retries=0)
        match = [m for m in matches if m.get('roster_id') == game['roster_id']]
        if len(match) != 1 or (before and match[0]['starters'] != owned[0]['starters']):
            raise ValueError('Live roster and matchup disagree')
        return owned[0], match[0]

    def tick(self):
        if not self.policy():
            return {'enabled': False}
        self.capture_changes()
        final_checks = []
        with self.db() as db:
            games = [json.loads(r[0]) for r in db.execute(
                "SELECT value FROM games WHERE json_extract(value,'$.kickoff')<=? AND json_extract(value,'$.final') IS NULL",
                (self.clock() + 1800,))]
        for game in games:
            now = self.clock()
            if game['kickoff'] - 1800 <= now < game['kickoff'] and 'pregame_roster' not in game:
                roster, match = self.live_roster(game)
                directory = get_sleeper('players/nfl', retries=0)
                game['players'] = {sid: directory.get(sid, {}).get('full_name') or sid for sid in roster['players']
                                   if team(directory.get(sid, {}).get('team') or sid) in (team(game['home']), team(game['away']))}
                game['pregame_roster'] = roster
                starters = [name for sid, name in game['players'].items() if sid in roster['starters']]
                bench = [name for sid, name in game['players'].items() if sid in roster['players'] and sid not in roster['starters']]
                message = game['away'] + ' at ' + game['home'] + ' in ' + str(max(1, round((game['kickoff'] - now) / 60))) + 'm. '
                message += 'Starting: ' + (', '.join(starters) or 'none') + '. Bench: ' + (', '.join(bench) or 'none') + '.'
                self.enqueue('before-' + game['id'], message)
                with self.db() as db:
                    db.execute('UPDATE games SET value=? WHERE id=?', (json.dumps(game), game['id']))
            if now >= game['kickoff'] + 7200 and not game.get('final'):
                final_checks.append({'game_id': game['id'], 'game': game['away'] + ' at ' + game['home'],
                                     'instruction': 'Inspect a current game page. Record final only when explicitly marked Final. Retain this check otherwise.'})
        return {'delivery': self.flush(), 'final_checks': final_checks, **self.status()}

    def final(self, path):
        proof = json.loads(Path(path).read_text())
        if proof.get('status') != 'Final' or not proof.get('source_url') or not 0 <= self.clock() - instant(proof['observed_at']) <= 300:
            raise ValueError('A fresh observed Final result and source URL are required')
        with self.db() as db:
            row = db.execute('SELECT value FROM games WHERE id=?', (proof['game_id'],)).fetchone()
        if not row:
            raise ValueError('Unknown roster game')
        game = json.loads(row[0])
        if self.clock() < game['kickoff'] or any(proof[k] != game[k] for k in ('home', 'away')):
            raise ValueError('Final result does not match the scheduled game')
        scores = [proof[k] for k in ('away_score', 'home_score')]
        if any(type(s) is not int or s < 0 for s in scores):
            raise ValueError('Final scores must be nonnegative integers')
        roster, match = self.live_roster(game, before=False)
        ids = [sid for sid in game['players'] if sid in match['starters']]
        points = match.get('players_points') or {}
        total = sum(points[sid] for sid in ids) if all(isinstance(points.get(sid), (int, float)) for sid in ids) else None
        message = f"Final: {game['away']} {scores[0]}–{scores[1]} {game['home']}. "
        message += ('Your starters: ' + f'{total:.1f} pts (provisional).' if total is not None else 'Your points pending.')
        self.enqueue('after-' + game['id'], message)
        game['final'] = proof
        with self.db() as db:
            db.execute('UPDATE games SET value=? WHERE id=?', (json.dumps(game), game['id']))
        return self.flush()

    def status(self):
        with self.db() as db:
            return {'notice_counts': dict(db.execute('SELECT state,COUNT(*) FROM notices GROUP BY state')),
                    'tracked_games': db.execute('SELECT COUNT(*) FROM games').fetchone()[0],
                    'delivery_attention': [dict(r) for r in db.execute("SELECT id,state FROM notices WHERE state NOT IN ('queued','confirmed')")]}


def after_change(root):
    """Committed execution evidence survives notification failures for the next wakeup."""
    try:
        notices = Notices(root)
        if notices.policy():
            notices.capture_changes()
            return notices.flush()
    except Exception as error:
        return {'notification_error': type(error).__name__, 'retry_on_next_wakeup': True}
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['enable', 'status', 'tick', 'plan', 'final'])
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    notices = Notices()
    result = notices.plan(args.snapshot.resolve()) if args.command == 'plan' else notices.final(args.evidence) if args.command == 'final' else getattr(notices, args.command)()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
