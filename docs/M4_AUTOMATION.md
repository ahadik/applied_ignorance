# M4 workflow implementation and acceptance

## Status

M4 local acceptance passed on September 11, 2026, in bounded recurring-dispatch mode.
Pushover delivered the setup alert to the owner's phone on September 11, 2026.
The owner explicitly confirmed receipt. The confirmation is in `data/automation/m4/phone-confirmation.json`.

The daily workflow collects deadline evidence and creates a desired plan.
It compares that plan with the local scheduler inventory.
The bounded dispatcher provides a recurring scheduling path with explicit timing assumptions.
Daily recipes with `dispatcher_check_recipe` register executable checks and the next daily planner before reporting coverage.
Without that field, the legacy M3 manual scheduling path remains active and reports missing coverage.
No successful collection or inspection alone proves coverage.

Two actual scheduler-injected heartbeats executed distinct harmless workflows and republished verified future configuration coverage.
The scheduled events occurred at 16:48:56.289 UTC and 16:50:26.217 UTC.
The saved result is `data/automation/m4/live/acceptance.json`.
The daily-planner integration separately verifies deadline registration, the next daily planner and its overlap horizon with simulated provider data.
A command argument that says `scheduled` does not prove a scheduler invoked the command.
The supported control deleted the test dispatcher. Fresh complete local inventory verified cleanup, and the test restored disabled mode.
All 299 offline tests passed. They include an actual child-process exit immediately after a durable claim.
The restarted dispatcher required explicit recovery, then completed the check once without replay.
This acceptance does not establish current football readiness, uninterrupted operation or a punctuality guarantee.

## Commands and authority

`automation_run.py` executes bounded workflows through existing application services.
`automation_health.py` summarizes saved evidence and the local scheduler inventory.
The versioned prompts are `templates/automation/daily-v1.txt` and `templates/automation/check-v1.txt`.

| Command | Effect |
|---|---|
| `automation.py workflow-register` | Saves the check revision and hashes its recipe and source files. |
| `automation.py context` | Reads the exact check revision, current mode and unresolved runs. |
| `automation.py workflow-run` | Claims the check, executes bounded work and saves a receipt. |
| `automation.py health --output PATH` | Reads local health and saves a report. It makes no provider requests. |
| `automation.py pause` | Disables new work and blocks active workers at their next checkpoint. |
| `automation.py resume --mode observe --evidence PATH` | Enables observations with saved setup evidence. |
| `automation.py resume --mode propose --evidence PATH` | Also permits saved lineup proposals. |
| `automation.py browser-observation --status STATUS --evidence PATH` | Saves an actual browser observation and attempts an alert for failure. |

Pause cannot cancel an external request already in progress.
Resume does not repair missed schedules or resolve uncertain runs.
The existing `begin`, `finish`, `recover` and scheduler commands remain available for controlled recovery.
Do not call `begin` before `workflow-run`. The workflow command acquires its own claim.

## Recipe contract

A recipe is a project-relative JSON file with `schema_version: 1`.
Required common fields are `kind`, `league_id`, `season`, `week`, `roster_id` and `notify_on_failure`.
The notification flag must be a Boolean value.

| Kind | Additional fields | Work |
|---|---|---|
| `inspection` | None | Reads local automation status without provider requests. |
| `daily` | `planning_policy`, `target_thread_id` | Collects deadline evidence and compares the desired plan with schedules. |
| `deadline` | `operation: validate_lineup`, `proposal` | Collects fresh validation inputs and validates the saved proposal. |
| `deadline` | `operation: propose_lineup` | Collects weekly inputs, computes a proposal and validates it. |

Daily recipes can supply `previous_plan`, `timing` and `proposal` paths.
The optional `dispatcher_check_recipe` identifies a matching executable deadline recipe.
Supply the previous plan when continuity must preserve earlier obligations and passed locks.
In propose mode, daily work also prepares a lineup proposal.
In observe mode, a daily recipe with a proposal validates that proposal.
Missing recipes, timing evidence, scheduler configuration or execution capacity retain a blocking finding.

## Bounded recurring dispatcher

`automation_dispatch.py` uses one supported app heartbeat with a 60-second interval.
It executes at most one registered workflow per invocation.
The contract expires within seven days. An expired contract returns a retirement instruction without executing work.
The agent deletes that exact task through supported controls. Natural one-time expiration is not required.

The `prepare` command saves the intended contract before the scheduler call.
Repeated preparation returns an existing-contract warning without another creation request.
After creation or interruption, `bind` requires exactly one matching active task in a complete local inventory.
Wrong targets, changed prompts, changed revisions, paused tasks, duplicates and unresolved M3 operations block execution.
Python never edits app-owned scheduler files or calls a private scheduling endpoint.

```sh
python3 automation_dispatch.py prepare --target TASK_ID --expires UTC_TIME
python3 automation_dispatch.py bind
python3 automation_dispatch.py coverage
python3 automation_dispatch.py tick --revision REVISION
```

Use the returned tool arguments with the supported scheduling control after preparation.
Do not manually repeat a scheduler-triggered `tick` command.
The live acceptance harness calls `tick` itself and must not receive a separate preliminary invocation.

Coverage describes the exact published workflow manifest through its recorded horizon.
The calculation reserves 60 seconds per wake interval, 120 seconds for dispatch delay and a full workflow lease per check.
It allocates checks sequentially by latest-start time and rejects windows that lack sufficient capacity.
The 120-second allowance is an explicit operating assumption, not a scheduler service guarantee.
Busy tasks, sleep, network failures or delayed delivery can exceed it. Missed windows remain visible and do not execute late.

Daily publication registers the next planner and preserves the M2 horizon, including its overlap interval.
It refuses a future week without a matching recipe and proposal.
Plan blockers remain blockers after configuration verification.
Current claims, uncertain prior work and superseded sources prevent execution through the existing M1 controls.

Harmless scheduled acceptance uses synthetic inspection obligations and the real dispatcher and workflow services.
It verifies saved future configuration, not current football data or a real lineup decision.
The daily-planner integration separately runs against simulated provider evidence in automatic tests.
See [M4_LIVE_ACCEPTANCE.md](M4_LIVE_ACCEPTANCE.md) for the two-cycle procedure and cleanup.

Register the recipe before execution:

```sh
python3 automation.py workflow-register --recipe PATH --check-id CHECK_ID --run-at UTC_TIME --latest-start UTC_TIME --expires UTC_TIME
python3 automation.py context --check-id CHECK_ID --revision REVISION
python3 automation.py workflow-run --recipe PATH --check-id CHECK_ID --revision REVISION
```

Replace each placeholder with the saved recipe, check identity, revision or approved UTC time.
Use the returned revision exactly. Register a new revision when a source file changes.

## Data access and saved results

Daily collection uses `automation_deadlines.collect` and the central Sleeper and nflverse clients.
Deadline collection uses `weekly_data.collect` and the central Sleeper and FantasyPros clients.
Normal cache, quota, cooldown and freshness policies apply.
The workflow does not bypass a provider failure or retry an uncertain run automatically.

Proposal work uses the existing weekly model, append-only proposal history and independent validator.
Observed game locks persist for later runs. A validation result can be PASS, REVIEW or FAIL.
Neither a proposal nor a PASS means the lineup was applied. These commands cannot change Sleeper lineups.

Receipts are under `data/automation/workflows/runs/RUN_ID/`.
The immutable `result.json` records the workflow result and available acquisition counts.
Separate notification and recovery files preserve subsequent outcomes.
The latest pointer is a convenience file. Health reads the receipt and its companion records.
For interrupted collection, inspect the provider ledgers and partial snapshots for actual attempt counts.
An incomplete count is not zero attempts.

Daily and deadline checks share the league, season and roster scope.
An active or uncertain claim blocks another workflow in that scope.
The weekly file lock also excludes concurrent standalone weekly commands.
Workers check mode, revision and lease before each major phase.
The supported Mac main-thread runtime enforces a wall-clock budget shorter than the claim lease.

The ledger distinguishes completed execution from the receipt's decision status.
A blocked decision can finish its execution without a valid lineup or future coverage.
A failed workflow records an uncertain outcome and requires explicit recovery.

## Recovery procedures

### Missing browser login

1. Save the actual browser failure evidence.
2. Run `automation.py browser-observation --status login_required --evidence PATH`.
3. Check the saved notification result.
4. Ask the owner to restore login when interaction is necessary.
5. Inspect the browser again before saving a ready observation.

The alert command does not require browser access. Browser readiness expires after five minutes in the health report.
Pushover cannot detect or report a powered-off Mac by itself.
An external offline monitor is not configured.

### Provider quota or cooldown

1. Read the central provider's saved attempt and cooldown records.
2. Preserve the provider's retry time and request budget.
3. Inspect partial snapshots and the workflow receipt.
4. Resolve an uncertain run only after its effects are known.
5. Register a fresh check within a valid deadline window before another collection.

Do not delete ledgers, change cache directories or force a refresh to avoid a limit.

### Missed planner or missing future checks

1. Run `python3 automation.py health`.
2. Compare the last receipt, desired obligations and fresh local scheduler inventory.
3. Inspect the dispatcher contract and published coverage, or follow the legacy M3 manual setup procedure.
4. Retain the missing-coverage finding until actual checks cover the required horizon.
5. Complete both scheduled acceptance cycles before declaring M4 complete.

### Changed ownership or source revision

1. Pause automation.
2. Compare current league and roster evidence with the saved recipe.
3. Correct the recipe and register a new check revision.
4. Review setup evidence before resuming observation mode.

A superseded prompt must stop before provider work or notifications.

### Interrupted execution or uncertain scheduling

1. Read the exact check context and saved run receipt.
2. Inspect proposals, provider attempts and pending scheduler operations.
3. Determine whether work completed or a retry is safe.
4. Save the evidence for that determination.
5. Use the M1 recovery command with that evidence and an explicit reason.
6. Use M3 scheduler recovery for an uncertain task creation.

Do not create another task to compensate for an unverified creation.
Do not replay a Pushover incident with an unknown send outcome.
See [M1_AUTOMATION.md](M1_AUTOMATION.md), [M3_AUTOMATION.md](M3_AUTOMATION.md) and [PUSHOVER.md](PUSHOVER.md).
