# M5 supervised lineup execution

## Current acceptance status

M5 is not complete. The execution controls are implemented and tested locally.
The earlier browser/API starter disagreement resolved on September 11, 2026.
The reloaded team page and both API starter lists matched all nine slots.
Evidence: `data/automation/m5/initial-reconciliation.json`.

All 315 tests passed after the execution implementation and provider recovery fix.
The first exact Swift/Barkley slot-swap assessment returned PASS without review findings.
It does not prove that a later action remains eligible.
The proposal is `data/weekly/2026/1/proposals/5d7a3f65662444b2987d1bc17522c74f.json`.

The owner approved that exact proposal. The browser applied Swift at RB and Barkley at FLEX on September 11.
Full reload preserved the swap. The first API observation returned the previous slots, and the second matched the browser.
Execution `dc0f789e44c2411eaf2cbf41acf39bde` completed with action `a840fe77a209456abd8667a6240b8bfd` confirmed.
No repeated browser action occurred. This Friday operation does not count as a relevant game window.

The schedule provider initially returned inconsistent revision bytes.
Central nflverse recovery retrieved the advertised Git blob and verified its identity before validation continued.
An expired injury/news snapshot then blocked preparation until normal collection refreshed it.
Both failures preserved the execution gate.

Two actual owner-supervised game windows remain required.
Current schedule evidence identifies September 13 games at 1:00 PM and 4:25 PM America/New_York.
Prepare the reviews at noon and 3:25 PM, respectively. Reverify game times and ownership before each review.
Friday engineering tests cannot replace those real game windows.
A legitimate no-change decision can qualify when current validation and native/API evidence confirm the lineup during the actual window.
Do not make unnecessary real changes to manufacture acceptance evidence.

Automation `m5-sunday-early-game-review` currently schedules the noon review in this task.
The app permits one active heartbeat per task. The noon run first updates that same automation for 3:25 PM.
It must verify the update before collecting data or awaiting owner input.
The later review therefore depends on that update. Its configuration is not yet verified.
The final review deletes the automation. Date guards prevent later weekly runs from performing stale football work.
This procedure does not establish automatic one-time expiration.

## Scope and data access

`lineup_execution.py` stores execution states, proposed actions and an append-only event log in `data/lineup_execution/state.sqlite3`.
The database uses schema version 2. Version 1 upgrades in place and retains all records.
Unknown versions stop execution. Older execution code rejects the new version instead of bypassing delegation checks.
Historical proposals, validation records and observed evidence remain separate from the latest convenience files.

`observe` uses `weekly_data.context` through `sleeper.get_sleeper` and retains starter disagreement for diagnosis.
Normal weekly collection still rejects that disagreement.
`collect` uses `weekly_data.collect(validation_only=True)` through central Sleeper, FantasyPros and nflverse clients.
It skips projections and preserves existing cache, quota and cooldown rules.
Other execution commands use saved files and local state only.
No Python command writes to Sleeper or calls an undocumented account API.

```sh
python3 lineup_execution.py observe --season 2026 --week 1
python3 lineup_execution.py collect --season 2026 --week 1
python3 lineup_execution.py status
```

## Native observation contract

Save a new JSON observation after an actual full browser reload.
Include these fields:

- `schema_version: 1`, `observed_at`, `account`, `url` and `team`.
- `league_id`, `roster_id`, `season` and `week`.
- `full_reload: true`, ordered `starters` and `owned_player_ids`.
- `locked_player_ids`, `lock_controls_observed: true` and the observed evidence basis.

Bind the roster ID through current account ownership evidence.
Read slot controls, player IDs, completed games and displayed kickoff times.
Do not copy old browser observations or manufacture an unlock flag.
Both API and native observations must be no more than 60 seconds old for action preparation.
Reconciliation observations must follow the action and meet the same freshness limit.
The exact account profile may use the central client's five-minute cache.
Mutable league, ownership and matchup observations cannot use this exception.

## Assess and authorize the exact proposal

```sh
python3 lineup_execution.py assess --proposal PROPOSAL --snapshot SNAPSHOT --api API_FILE --native NATIVE_FILE
```

Assessment recomputes the independent validator result from checksummed input files.
It binds the exact proposal hash, input hash, league-state hash and review findings.
A PASS is a time-limited eligibility result, not proof of optimality or later participation.

Present the concrete adjustment and its reason to the owner before initial supervised execution.
Save the actual approval as JSON with `basis: explicit_owner_approval`, the `proposal_hash` and the owner's response.
Then create a separate authority file with:

- `schema_version: 1` and `mode: supervised`.
- The exact `proposal_hash`, `league_id`, `roster_id`, `season` and `week`.
- `issued_at`, `expires_at` and the project-relative `owner_approval` path.

Authority expires within ten minutes. Do not treat “complete M5” as approval of an unseen proposal.
Do not manufacture approval from a tool result or another manager's message.

```sh
python3 lineup_execution.py register --proposal PROPOSAL --authority AUTHORITY_FILE
```

The registration command refuses a duplicate proposal or another incomplete execution in the same scope.
Changed proposal text, authority, approval evidence or project configuration invalidates execution.

## Review resolution and official availability

The independent validator remains unchanged. FAIL cannot become permission through a review.
`lineup_review.py` supports narrow, separate resolutions for selected REVIEW findings.
It does not rewrite REVIEW as PASS.

The review file binds `proposal_hash`, `input_hash`, `state_key` and `issues_hash` from the assessment.
It supplies `schema_version: 1`, `reviewed_at`, `expires_at`, `owner_approval` and one resolution per review finding.
The owner review record uses `basis: explicit_owner_review` and the exact proposal, input and issues hashes.
Its expiry cannot exceed the independent validation expiry.

Each resolution contains `issue_index`, `reason` and `disposition`.
Supported findings are `pregame_confirmation`, `uncertain_availability`, `concerning_news` and `locked_health_flag`.
Identity ambiguity, unknown status, low probability and other findings remain blocked.

For an unlocked player's availability, use `disposition: official_active_reviewed` and an `official` evidence object.
That object contains `url`, `player_id`, `game_id`, `status: active`, `statement`, `published_at`, `observed_at` and `evidence`.
The source must be an official `nfl.com/news/` page observed through the browser.
The saved source record uses `basis: observed_official_nfl_page` with matching fields.
Publication must be within 90 minutes, and observation must be within five minutes.
Do not infer an explicit active statement merely from missing injury news.
This is an audited manual evidence path, not an integrated automatic inactive feed.

For a locked starter, `retain_locked_starter` can acknowledge a health finding while preserving that exact slot.
No review can unlock a player or authorize a definite legality failure.
Review and underlying evidence files remain hash-bound through dispatch.

## Prepare, dispatch and reconcile one change

```sh
python3 lineup_execution.py prepare --execution-id EXECUTION_ID --snapshot SNAPSHOT --api API_FILE --native NATIVE_FILE
```

Supply `--review REVIEW_FILE` only when a supported review resolution is required.
Preparation checks exact authority, current input identity, ownership, slots, duplicate players and native/API agreement.
It combines provider, historical and native locks conservatively.
It prepares one legal swap and saves its before/after starter lists before any browser write.
An illegal intermediate swap stops preparation.
If the target already matches, the command records a verified no-change completion.

The action token expires within 30 seconds or an earlier evidence or authority deadline.
Immediately before the actual browser write, consume the token:

```sh
python3 lineup_execution.py dispatch --action-id ACTION_ID --token TOKEN
```

Dispatch records `outcome_unknown` before returning the single authorized browser action.
It does not perform the browser action itself.
Perform that exact native operation before `execute_before`.
Do not repeat the operation after a timeout, lost connection or uncertain response.

Reload the browser after the change. Collect a fresh API observation and save the actual native state.

```sh
python3 lineup_execution.py reconcile --action-id ACTION_ID --api API_FILE --native NATIVE_FILE
```

Matching expected after-state confirms the action.
Matching original state records `not_applied` and still blocks automatic retry.
Other state, ownership changes or browser/API disagreement preserve uncertainty.
Each further action requires new evidence and preparation.
Limit one reconciliation session to three fresh API observations.
Refresh native evidence if its age exceeds 60 seconds.
If disagreement persists, retain the unknown outcome and notify the owner.
Do not repeat the browser action.

## Recovery

An expired unused token can be retired after exact owner recovery evidence.
A consumed token cannot be replayed, even after a process restart.
First reconcile an uncertain action with fresh observations.
Only an unused expired action or a reconciled `not_applied` action can use this recovery command:

```sh
python3 lineup_execution.py recover --action-id ACTION_ID --evidence RECOVERY_FILE
```

The recovery record requires `basis: explicit_owner_recovery`, the exact `action_id` and a reason.
Recovery retires the old token. It requires fresh preparation before another action.
If authority expired, obtain a new exact approval after resolving every prior action:

```sh
python3 lineup_execution.py reauthorize --execution-id EXECUTION_ID --authority AUTHORITY_FILE
```

Never delete an uncertain execution record to clear a blocked scope.
Never repeat a browser swap merely because the public API still shows old state.

## Record real game-window acceptance

```sh
python3 lineup_execution.py record-window --execution-id EXECUTION_ID --kickoff UTC_TIME --evidence WINDOW_FILE
```

The evidence file requires `basis: actual_owner_supervised_window`, `execution_id`, `kickoff` and the actual supervision record.
The command requires a completed execution, current validation and a relevant starter's kickoff within the next 90 minutes.
It refuses duplicate scope/kickoff records and cannot count a future window today.
Use two distinct game windows with no unexplained outcomes before promotion.

Standing autonomous writes remain disabled in the current local configuration.
Do not enable delegated starter changes until the real-window gate passes and the owner explicitly delegates that limited authority.
Trades, drops, waivers, IR moves and unresolved reviews remain outside this authority.

## Limited delegation implementation

`lineup_authority.py` implements promotion, expiry, revocation and per-day action limits.
Promotion requires two recorded game windows with unchanged evidence and completed executions.
It also requires passing offline acceptance for the exact current source version.
Code changes invalidate an active promotion until acceptance and promotion repeat.

```sh
python3 system_acceptance.py --output ACCEPTANCE_FILE
python3 lineup_execution.py promote --delegation DELEGATION_FILE --tests ACCEPTANCE_FILE
python3 lineup_execution.py authorize-delegated --proposal PROPOSAL_FILE
python3 lineup_execution.py revoke --reason "Owner paused autonomous lineup changes"
```

The delegation file requires `schema_version: 1` and `basis: explicit_owner_lineup_delegation`.
Record the actual `owner_statement`, `league_id`, `roster_id`, `season`, `issued_at` and `expires_at`.
Its `operations` list must contain only `unlocked_starters`.
Its integer `max_actions_per_day` must be from one through twenty.
Delegation must expire within seven days. The service does not invent renewal approval.

Delegated proposal authority binds one exact proposal and expires within ten minutes.
Use the existing register, prepare, dispatch and reconcile commands afterward.
Preparation requires an independent PASS with no review override.
Revocation, changed source evidence, expired authority and exhausted action limits stop dispatch.
All dispatched actions count toward the limit, including uncertain outcomes.

Use `docs/FULL_SYSTEM_SUNDAY.md` for integrated acceptance and `docs/M6_ROSTER_OPERATIONS.md` for supervised roster services.
