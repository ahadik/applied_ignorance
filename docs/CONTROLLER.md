# Draft controller and third-mock procedure

The controller implements deterministic state reconciliation, availability filtering, required-slot protection, freshness checks, queue checks and durable checkpoints. It does not submit Sleeper selections or automatically manipulate its queue. Browser actions remain supervised through Computer Use. Priorities are supplied explicitly by analysis; this is not yet an independent projection/value model.

## Commands

Run from the workspace, substituting the verified draft ID:

```sh
python3 controller.py sync --draft DRAFT_ID
python3 controller.py watch --draft DRAFT_ID
python3 controller.py observe --draft DRAFT_ID --file observed-ui.json
python3 controller.py status --draft DRAFT_ID
python3 controller.py prepare --draft DRAFT_ID --player PLAYER_ID
```

`watch` polls the public API every five seconds, checkpoints to disk, retains previous state on fetch failure, records unhealthy status, and exits when the draft is complete. Run it in a retained terminal session during a mock/live draft. It can continue through conversation compaction while its process and computer remain running; it is not a cloud service. Stop it with Ctrl-C. No watcher is automatically started by these instructions.

State files are isolated by draft in `data/drafts/DRAFT_ID/`: `state.json`, `health.json`, `ui.json`, `candidates.json`, `checkpoint.json`, `pending.json`, and `last_submission.json` when applicable. Mock files cannot overwrite a live draft's state. `checkpoint.json` is the durable recovery record. Re-run status after recovery; never rely on a previously saved ready=true result because freshness expires.

API/UI observations older than 20 seconds block preparation. Public API polls are sequential observations, not an atomic server snapshot; browser/API agreement and immediate UI rechecking remain required. Unsupported formats, reversal and traded picks fail rather than silently assume ownership.

## Inputs

Write a fresh UI observation based on an actual browser inspection, then import it with `observe`. Do not infer auto-pick=false merely because no banner appeared; inspect the control. Preserve the actual observation time, not the later file-writing time.

```json
{
  "draft_id": "VERIFIED_DRAFT_ID",
  "observed_at": "ACTUAL_ISO_TIMESTAMP_WITH_TIMEZONE",
  "last_pick": 0,
  "auto_pick": false,
  "queue": ["PLAYER_ID_1", "PLAYER_ID_2"]
}
```

Create `data/drafts/DRAFT_ID/candidates.json` from current sourced data and analysis. Lower priority numbers rank first; ties use player ID. No fabricated IDs or projection numbers. The source timestamp must describe the source observation, not a fresh timestamp applied to old rankings. More than 24 hours old is rejected.

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

The controller removes drafted/excluded candidates, protects required positions when remaining slots force them, reports up to eight next options, and flags thin queues. It does not model bye coverage or injury probabilities. Keep those in strategic analysis and exclusions until a valuation model is implemented.

## Every pick

1. Keep the watcher running. Read its compact checkpoint instead of reconstructing the entire board.
2. Compute/revise candidate priorities between turns. Apply the proposed queue through the browser, then inspect and record the actual queue. A proposed queue is never counted as applied.
3. Refresh UI observations and call `prepare` for a recommended, queued player when our turn begins. It writes a pending submission before any click and blocks another preparation until reconciled.
4. Immediately recheck the row and active turn in the browser, then make one selection. Preparation is not a lock on Sleeper and does not prevent another team picking meanwhile.
5. The next refresh verifies the expected pick. A match clears pending automatically. A mismatch remains blocked and is recorded in `last_submission.json`; inspect it and refresh before explicitly acknowledging with `resolve`.
6. If preparation occurred but no click was made, do not clear pending blindly. Reconcile the live room; the conservative implementation requires that pick to resolve before `resolve` will clear it.

## Third mock acceptance checklist

- Create a separate mock, confirm settings and seat, record its unique ID, and load a sourced candidate shortlist before starting its clock.
- Start the watcher in a retained terminal and populate/verify the native queue.
- Verify status blocks until both current candidates and a real UI observation exist.
- Use prepare → immediate browser selection → API reconciliation for selections.
- Between turns simulate resuming with only files: reload checkpoint, observe the browser, and regenerate status. Confirm that stale UI cannot authorize a pick.
- Verify a drafted candidate disappears from recommendations and the actual queue.
- Verify at least one required-slot constraint as the roster fills.
- Do not intentionally expire another live clock just to repeat the proven timeout behavior; unit tests cover the auto-pick flag and prior mock evidence remains recorded.
- Complete all 15 picks and compare the API roster against the browser roster. Record any discrepancy. Do not claim independent optimization or full unattended operation.

## Validation completed

13 unit tests pass (9 controller tests plus 4 existing tests), including submission match/mismatch reconciliation and preservation of the last good state after invalid responses. Public API replay of mock 2 reconciled 210 total picks and the correct 15-player roster, including Kenneth Walker's automatic pick. All required starting slots were filled. Mock 1 also synced successfully with 210 picks. The third integrated mock has not yet run.
