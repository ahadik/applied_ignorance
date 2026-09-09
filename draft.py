"""Dependency-free, read-only Sleeper draft snapshots and exact scoring.

Usage: python3 draft.py sync | summary | score stats.json
The score input is a JSON object keyed by Sleeper scoring stat names.
Only supplied stats are scored; this is not a prediction model.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from draft_data import read_draft_context
from storage import save_atomic

ROOT = Path(__file__).resolve().parent
SNAPSHOT = ROOT / "data" / "snapshot.json"


def sync(config):
    data = read_draft_context(config)
    # Publish only after every required read and scope check succeeds.
    save_atomic(SNAPSHOT, data)
    return data


def snake_picks(slot, teams, rounds):
    if not 1 <= slot <= teams:
        raise ValueError("Draft slot must be between 1 and team count")
    return [(r - 1) * teams + (slot if r % 2 else teams + 1 - slot)
            for r in range(1, rounds + 1)]


def score(stats, settings):
    unknown = set(stats) - set(settings)
    if unknown:
        raise ValueError("Unrecognized scoring stats: " + ", ".join(sorted(unknown)))
    contributions = {}
    for stat, count in stats.items():
        if isinstance(count, bool) or not isinstance(count, (int, float)):
            raise ValueError(f"{stat} must be numeric")
        import math
        if not math.isfinite(count):
            raise ValueError(f"{stat} must be finite")
        contributions[stat] = count * settings[stat]
    return {"points": sum(contributions.values()), "contributions": contributions,
            "scope": "Only supplied stats; omitted stats are not estimated"}


def summary(data, config):
    league, draft = data["league"], data["draft"]
    settings = draft["settings"]
    start = draft.get("start_time")
    start_text = (datetime.fromtimestamp(start / 1000, ZoneInfo(config["timezone"])).isoformat()
                  if start else "Unscheduled")
    slot = (draft.get("draft_order") or {}).get(data["user_id"])
    positions = league["roster_positions"]
    lines = ["# Draft context", "", f"Snapshot: {data['fetched_at']}",
             "This is saved data. Run sync to refresh; no background monitoring is active.", "",
             f"League: {league['name']} ({league['season']})",
             f"Status: {draft['status']}; format: {draft['type']}",
             f"Scheduled start: {start_text}",
             f"Teams: {settings['teams']}; rounds: {settings['rounds']}; seconds/pick: {settings['pick_timer']}",
             f"Draft slot: {slot or 'Not assigned'}",
             f"Roster: {', '.join(positions)}",
             f"Points per reception: {league['scoring_settings'].get('rec', 0)}",
             f"Completed pick records: {len(data['picks'])}",
             f"AutoSubs allowed: {league['settings'].get('max_subs', 0)}", ""]
    if slot and draft["type"] == "snake" and not settings.get("reversal_round"):
        numbers = snake_picks(slot, settings["teams"], settings["rounds"])
        # Traded slots can change ownership, so do not claim these as guaranteed.
        lines += ["Base snake-order picks (before any traded picks): " + ", ".join(map(str, numbers)), ""]
    lines += ["## Observed picks", ""]
    for pick in sorted(data["picks"], key=lambda p: p["pick_no"]):
        info = pick.get("metadata") or {}
        name = " ".join(filter(None, [info.get("first_name"), info.get("last_name")]))
        lines.append(f"- {pick['pick_no']}: {name or pick['player_id']} ({info.get('position', '?')}) — {pick.get('picked_by', '?')}")
    lines += ["", "This context report does not calculate projections or recommend players. Use draft_board.py for the integrated draft board."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["sync", "summary", "score"])
    parser.add_argument("stats", nargs="?")
    args = parser.parse_args()
    config = json.loads((ROOT / "config.json").read_text())
    try:
        data = sync(config) if args.command == "sync" else json.loads(SNAPSHOT.read_text())
        if args.command == "score":
            if not args.stats:
                parser.error("score requires a stats JSON file")
            print(json.dumps(score(json.loads(Path(args.stats).read_text()), data["league"]["scoring_settings"]), indent=2))
        else:
            report = summary(data, config)
            (ROOT / "DRAFT_CONTEXT.md").write_text(report)
            print(report)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Unable to complete: {error}\nSaved snapshot is retained.\n")


if __name__ == "__main__":
    main()
