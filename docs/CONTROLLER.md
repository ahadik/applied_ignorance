# Draft controller and third-mock procedure

**September 8 update:** mock 3 ran four successful supervised A/B selections,
then the user stopped it. Read [MOCK_3_ADVANCED.md](MOCK_3_ADVANCED.md) and the
required operating changes in [DRAFT_RUNBOOK.md](DRAFT_RUNBOOK.md) before tonight.
This was a partial rehearsal, not completion of the checklist below.

For the active user-requested frozen-data session, use the pinned board described
in [DRAFT_SESSION.md](DRAFT_SESSION.md). Player-source refresh instructions below
are superseded until the real draft completes. Live Sleeper/UI checks still apply.

The controller implements deterministic state reconciliation, availability filtering, required-slot protection, freshness checks, queue checks and durable checkpoints. It does not submit Sleeper selections or automatically manipulate its queue. Browser actions remain supervised through Computer Use. Milestone 3's optional strategy integration now calculates priorities from the saved board and all teams' rosters. See [MILESTONE_3.md](MILESTONE_3.md) for assumptions and evaluation.

## Commands

Run from the workspace, substituting the verified draft ID:

```sh
python3 -m fantasy_agent controller sync --draft DRAFT_ID
python3 -m fantasy_agent controller watch --draft DRAFT_ID
python3 -m fantasy_agent controller watch --draft DRAFT_ID --strategy-board data/draft_board/2026/board.json
python3 -m fantasy_agent controller observe --draft DRAFT_ID --file observed-ui.json
python3 -m fantasy_agent controller status --draft DRAFT_ID
python3 -m fantasy_agent controller prepare --draft DRAFT_ID --player PLAYER_ID
```

`watch` sleeps five seconds after each refresh. Network calls and calculations add time. It saves checkpoints to disk. If a fetch fails, it retains the previous state and records unhealthy status. It exits when the draft is complete. Run it in a retained terminal session during a mock/live draft. It can continue through conversation compaction while its process and computer remain running. It is not a cloud service. Stop it with Ctrl-C. No watcher is automatically started by these instructions.

With `--strategy-board`, each successful sync/watch cycle computes or reuses local
strategy and installs its source-expiring `candidates.json`. Reuse requires the
same state fingerprint, board hash, engine version and policy. Full opponent
rosters are in `state.json`. Reasoning is in `strategy_result.json`. Any new pick
invalidates the old strategy, even if its leading candidates remain available.
Freshness is checked on every cycle. `--strategy-policy` selects an explicit
policy file. `--allow-mock` permits using the league valuation board in an
explicitly verified league-less mock with matching roster format. It never
permits binding to another real league or using synthetic state. No queue is
changed by these flags, and no source refresh is performed automatically.

The active policy dispatches to the A/B planner for distinct short/long-gap turns.
`strategy_result.json` records `phase`, `horizon_picks`, work counts and scenario
details. Engine version 2 invalidates the older two-pick calculation cache. See
`AB_STRATEGY.md` for the bounded search and measured limits. An explicit
`planning_mode: two_pick` policy remains available. Failures never silently switch modes.

State files are isolated by draft in `data/drafts/DRAFT_ID/`: `state.json`, `health.json`, `ui.json`, `candidates.json`, `checkpoint.json`, `pending.json`, and `last_submission.json` when applicable. Mock files cannot overwrite a live draft's state. `checkpoint.json` is the durable recovery record. Re-run status after recovery. Never rely on a previously saved ready=true result because freshness expires.

API/UI observations older than 20 seconds block preparation. Public API polls are sequential observations, not an atomic server snapshot. Browser/API agreement and immediate UI rechecking remain required. Unsupported formats, reversal and traded picks fail rather than silently assume ownership.

## Inputs

Write a fresh UI observation based on an actual browser inspection, then import it with `observe`. Do not infer auto-pick=false merely because no banner appeared. Inspect the control. Preserve the actual observation time, not the later file-writing time.

```json
{
  "draft_id": "VERIFIED_DRAFT_ID",
  "observed_at": "ACTUAL_ISO_TIMESTAMP_WITH_TIMEZONE",
  "last_pick": 0,
  "auto_pick": false,
  "queue": ["PLAYER_ID_1", "PLAYER_ID_2"]
}
```

Create `data/drafts/DRAFT_ID/candidates.json` from current sourced data and analysis. Lower priority numbers rank first. Ties use player ID. No fabricated IDs or projection numbers. The source timestamp must describe the source observation, not a fresh timestamp applied to old rankings. More than 24 hours old is rejected.

Milestone 2's `draft_board.py export` generates a reviewable candidate file in this
format. Its additional `expires_at` field is enforced by `rank`, including after
export. Current alert deadlines can expire earlier than 24 hours. See
`MILESTONE_2.md`. Export does not install the file or apply the native queue.

```json
{
  "draft_id": "VERIFIED_DRAFT_ID",
  "observed_at": "ACTUAL_SOURCE_TIMESTAMP_WITH_TIMEZONE",
  "source": "Source and scoring basis; disclose provisional Sleeper-only baseline if used",
  "players": [
    {"player_id": "PLAYER_ID", "name": "Name", "position": "RB", "priority": 1,
     "rationale": "Reason based on current analysis", "exclude": false}
  ]
}
```

The controller removes drafted/excluded candidates, protects required positions when remaining slots force them, reports up to eight next options, and flags thin queues. Strategy additionally models roster marginal value and two-pick scenarios, displays bye conflicts and injury flags, and supports explicit reasoned overrides. It does not infer injury probabilities or optimize weekly bye substitutions.

## Every pick

1. Keep the watcher running. Read its compact checkpoint instead of reconstructing the entire board.
2. With `--strategy-board`, read the newly computed priorities between turns and review flags. Refresh expired provider inputs through the saved collection commands and rebuild the board when needed. Apply the proposed queue through the browser, then inspect and record the actual queue. A proposed queue is never counted as applied.
3. Refresh UI observations and call `prepare` for a recommended, queued player when our turn begins. It writes a pending submission before any click and blocks another preparation until reconciled.
4. Immediately recheck the row and active turn in the browser, then make one selection. Preparation is not a lock on Sleeper and does not prevent another team picking meanwhile.
5. The next refresh verifies the expected pick. A match clears pending automatically. A mismatch remains blocked and is recorded in `last_submission.json`. Inspect it and refresh before explicitly acknowledging with `resolve`.
6. If preparation occurred but no click was made, do not clear pending blindly. Reconcile the live room. The conservative implementation requires that pick to resolve before `resolve` will clear it.

## Third mock acceptance checklist

- Create a separate mock, confirm settings and seat, record its unique ID, and load a sourced candidate shortlist before starting its clock.
- Start the watcher in a retained terminal and populate/verify the native queue.
- Verify status blocks until both current candidates and a real UI observation exist.
- Use prepare → immediate browser selection → API reconciliation for selections.
- Between turns simulate resuming with only files: reload checkpoint, observe the browser, and regenerate status. Confirm that stale UI cannot authorize a pick.
- Verify a drafted candidate disappears from recommendations and the actual queue.
- Verify at least one required-slot constraint as the roster fills.
- Do not intentionally expire another live clock just to repeat the proven timeout behavior. Unit tests cover the auto-pick flag and prior mock evidence remains recorded.
- Complete all 14 picks under tonight's verified settings and compare the API roster against the browser roster. Record any discrepancy. Do not claim proven strategy superiority or full unattended operation.

## Validation completed

The initial controller checkpoint passed 13 tests. Milestone 3's full suite now
passes 125 offline tests, including strategy integration and invalidation. See
`MILESTONE_3.md`. The earlier public API replay of mock 2 reconciled 210 picks and
the correct 15-player roster, including Kenneth Walker's automatic pick. Mock 1
also synced with 210 picks. The third integrated browser mock subsequently ran
four selections. See the update above. Full-draft acceptance remains unfinished.
