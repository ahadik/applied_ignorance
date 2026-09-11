# Start and continue league management

## Owner push notifications

The owner receives pushes for team changes and games involving players on the roster.
Pregame notices list the game, starters, and bench players about 30 minutes before kickoff.
Postgame notices give the final score and the starters' fantasy points in one short message.
Fantasy points remain provisional because later scoring corrections are possible.

1. Run `python3 -m fantasy_agent team_notifications enable` once to save the owner's notification policy.
2. Run `python3 -m fantasy_agent team_notifications plan --snapshot PATH` with a verified weekly snapshot.
3. Read `notifications` from every manager tick, including waiting ticks.
4. Inspect current browser evidence for each `final_checks` game.
5. Save the observed result only when the page explicitly says Final.
6. Run `python3 -m fantasy_agent team_notifications final --evidence PATH` to send the recap.

The evidence JSON requires `game_id`, `home`, `away`, integer scores, `status`, `observed_at`, and `source_url`.
The score fields are `home_score` and `away_score`. The status must be `Final`.
The observation must be no older than five minutes. Do not infer completion from elapsed time.
Keep unfinished games for the next wakeup, including overtime and delayed games.

Manager reviews update the saved game plan. Each wakeup checks notification work independently of the next football review.
Lineup and roster reconciliation send pushes after verified changes. Pending claims and claim outcomes also produce notices.
Saved execution events recover notifications if the process exits after a team change.
For draft picks or management policy changes, use `notify.py send` with a unique incident ID and a short explanation.
Routine cache updates and log writes do not require owner pushes.

Use network permission from the outset for sends and live roster reads.
All sends use the central Pushover client. Unknown delivery requires investigation, not a blind resend.
Queued means Pushover accepted the message. It does not establish delivery to the phone.
Game notification timing still requires live acceptance. The Mac and scheduled task must remain available.

## Start from conversation

When the owner says “start managing my league,” start the manager in this task.
Use the configured league and user IDs. Never select a default league.
Keep normal repetitive work in saved scripts. Use inference for interaction and final decisions.

1. Read `docs/PROGRESS.md` and inspect existing manager state.
2. Run `python3 -m fantasy_agent league_manager start --target TASK_ID` with this actual task ID.
3. Inspect the returned scheduler status.
4. Apply the returned scheduler arguments through the supported automation tool.
5. If another heartbeat occupies this task, preserve its unfinished obligations before updating that heartbeat.
6. Run `python3 -m fantasy_agent league_manager status` to verify the actual recurring configuration.
7. Run `python3 -m fantasy_agent league_manager tick` after the recurring configuration passes.
8. Read the saved result and follow the appropriate phase procedure.

The start command saves local state. It does not contact providers or change Sleeper.
Scheduler tools create or update the actual wakeup. Python only reads their configuration.
The manager uses a permanent five-minute wakeup without a calendar expiry.
The owner can stop management explicitly. A failed review must not delete the wakeup.

## Transfer to another task

Use this procedure when the owner explicitly selects another conversation for management.

1. Run `python3 -m fantasy_agent league_manager transfer --target TASK_ID` with the selected task ID.
2. Apply the returned scheduler arguments through the supported automation tool.
3. Preserve the existing notification policy when updating the schedule.
4. Run `python3 -m fantasy_agent league_manager status` to verify the destination and recurring schedule.
5. Send the owner a schedule-change push through `notify.py send`.

The transfer preserves pending reviews, deadlines, installation identity, and prior decisions.
The transfer does not stop management or create a second schedule.
Collection remains blocked until the actual schedule matches the destination task.

## Setup requirements

Use Python 3.13 and an always-on Mac with Codex open and Sleeper signed in.
The `.env` file must contain `SLEEPER_LEAGUE_ID` and `SLEEPER_USER_ID`.
Set the matching Sleeper username and time zone in `config.json`.
Supply `FANTASYPROS_API_KEY`, `PUSHOVER_APP_TOKEN`, and `PUSHOVER_USER_KEY` for their respective providers.
Never print `.env` or include credentials in saved evidence.

Ask the owner only for missing credentials, account access, or permissions that the agent cannot establish.
Keep the recurring task while setup is incomplete. Record the blocker and schedule a bounded retry.
Do not repeatedly notify the owner about an unchanged blocker.

Provider clients create their stores when needed and preserve normal caching and request budgets.
Weekly collection obtains missing data through those clients.
Do not require a previous conversation or existing data snapshots to establish the league phase.
Do not copy another league's saved approvals or infer account identity from the league URL.

## Handle the discovered phase

The tick command reads Sleeper through `sleeper.get_sleeper` with zero automatic retries.
Run provider-reading commands with network permission from the outset in this desktop environment.
Do not first repeat a restricted execution that this environment already established cannot reach the provider.
File access, browser login, and script network permission are separate capabilities.
It checks league identity, expected user, owned roster, NFL state, and the league's actual draft.
The saved phase is an observation. Rediscover it after a transition or before relying on old evidence.

| Phase | Required work |
|---|---|
| `pre_draft` | Read the draft runbook. Collect missing draft inputs and prepare the actual room using existing draft commands. |
| `live_draft` | Read the draft runbook and resume the controller. Keep live inference active during draft turns. |
| `paused_draft` | Inspect the actual room and pending controller actions. Retain the recurring wakeup. |
| `regular_season` | The tick runs `agent_cycle.review`, including source collection, lineup analysis, and roster comparisons. |
| `post_draft_waiting` | Inspect roster needs and upcoming events. Do not manufacture an unsupported weekly forecast. |
| `season_complete` | Retain observation coverage until the owner stops management or explicitly selects another league. |
| `unresolved_phase` | Inspect current platform evidence and resolve the ambiguity before team changes. |

For draft preparation, use `draft_inputs.py collect --season SEASON` and the documented board/history commands.
Read `docs/FANTASYPROS.md`, `docs/NFLVERSE.md`, and `docs/DRAFT_RUNBOOK.md` before their respective collection or execution work.
Honor an active draft data freeze. Do not restart a completed draft or create another mock.
A missing or unsupported data feed is an explicit exception, not permission to invent projections.

## Standing management permission

Record the owner's actual management request once under `data/manager/`.
Use `basis: explicit_owner_management_request` with the exact `owner_statement`, league ID, user ID, roster ID, and season.
Specify `operations`, `lineup_actions_per_day`, and `roster_actions_per_day` in that record.
Supported operations are `unlocked_starters`, `free_agent`, `waiver`, `cancel_claim`, `ir_place`, and `ir_activate`.
Additions can include a checked bench drop. Standalone drops and trades require separate permission.
Use at most twenty lineup actions and five roster actions per rolling day.

Run `python3 -m fantasy_agent manager_authority install --request PATH` to record that standing permission.
Permission installation does not establish live acceptance.
Automatic actions require two supervised game windows and passing offline tests for the exact source version.
Automatic roster actions also require a successful supervised roster transaction.
These are acceptance gates, not recurring approval requests after acceptance.

Run `system_acceptance.py --output PATH` to save the full offline result.
Register it with `manager_authority.py accept-tests --evidence PATH`.
Code changes require a new passing result. Missing credentials or evidence do not count as acceptance.

Save each final decision with `subject_hash`, `reason`, `unresolved_concerns`, and source paths in `evidence`.
The hash must identify the exact proposal or transaction plan. Unresolved concerns block automatic action.
For roster decisions, include `season_impact` and `alternatives_considered` rather than relying only on current-week points.
Run `manager_authority.py authorize --subject PATH --decision PATH --operation OPERATION`.
Use its saved authority with the existing lineup register command or roster approval argument.
The short action permission expires after ten minutes. A fresh decision can obtain another permission under the same standing request.
Both execution services check standing permission again before dispatch and enforce rolling daily limits.
Automatic lineup changes require an independent PASS without a review override.
Automatic acquisitions require positive computed value after priority cost and all existing ownership and scoring checks.

Run `python3 -m fantasy_agent manager_authority revoke` to disable standing management permission.
Stopping the manager or losing verified scheduling also blocks automatic actions.

## Finish an inference turn

The tick saves a pending record before collection.
A repeated tick returns that record instead of collecting again or repeating a browser action.
Read the returned files. Decide whether to keep the lineup, act, retry, or request help.
Inspect the actual signed-in account through Sleeper's account menu before preparing a team change.

Use the lineup and roster execution services for all changes.
Preserve their validation, permission, lock, and outcome checks.
An autonomous product goal does not establish a passing live acceptance record.
Until the relevant permission exists, retain the exact proposal and request the required decision.

Save a decision JSON under `data/manager/` with these fields:

| Field | Meaning |
|---|---|
| `run_id` | The exact pending run ID. |
| `outcome` | `no_change`, `completed`, `retry`, or `exception`. |
| `reason` | The agent's explanation, including uncertainty when relevant. |
| `evidence` | Project-relative paths to actual source, execution, or observation records. |
| `next_review_at` | UTC Unix seconds, after now and no more than one hour away. |
| `followups` | Optional records with `id`, `at` in UTC Unix seconds, and `reason`. |
| `resolved_obligations` | Optional IDs of saved obligations whose resolution the evidence establishes. |

Run `python3 -m fantasy_agent league_manager finish --decision PATH` with that saved file.
Finish verifies the recurring schedule again before accepting the decision.
It retains prior obligations unless the decision explicitly resolves them.
It prevents unresolved prepared or uncertain actions from counting as completed reviews.

Plan earlier reviews for player availability, claim deadlines, and game locks.
Use `league_manager.py obligation --file PATH` to retain an independent future check.
The five-minute wakeup is a fallback. Remain actively engaged when a deadline needs closer attention.
Do not assume five-minute wakeups can operate a draft with a shorter pick clock.

## Recover without losing continuity

After an interrupted collection, inspect the pending record and provider evidence.
An interrupted collection can finish only as `retry` or `exception`.
For a temporary read failure, retain evidence and set a later retry that respects the provider cooldown.
Never erase provider attempt records or repeatedly force a refresh.
The manager retires expired unused tokens automatically from their saved undispatched state.
It does not retire uncertain dispatched actions through this path.
Use fresh authority and preparation after an unused token retires.

After an uncertain browser action, reconcile the actual state before another write.
Do not treat a submitted waiver request as an acquired player.
Retain an obligation to inspect its real processing result.

If scheduler inventory differs, repair it through the supported control before more football work.
If the Python command fails, the scheduled prompt still tells the agent to diagnose the problem and retain the wakeup.
A process restart releases the local operation lock. Saved pending work survives that restart.

The status command reports overdue wakeups and detected gaps after the agent returns.
External outage monitoring is outside scope at the owner's request.
Power loss, a disconnected Mac, app failure, and exhausted model access can interrupt execution.
The system cannot promise uninterrupted inference or report while all of its execution routes are unavailable.
Official scheduling behavior is documented in [OpenAI scheduled tasks](https://learn.chatgpt.com/docs/automations?surface=app).

## Stop or observe

Answer observer questions from `league_manager.py status`, the latest decision, and its evidence.
Do not alter strategy merely because the owner asks about a decision.
Keep unchanged routine results quiet. Notify for meaningful exceptions or required action.

When the owner stops management, run `python3 -m fantasy_agent league_manager stop`.
Delete the returned task through the supported automation tool and verify its removal.
The stop command preserves pending records for inspection or a later explicit restart.
