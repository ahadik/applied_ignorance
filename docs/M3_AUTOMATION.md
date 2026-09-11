# M3: Scheduler reconciliation and verified read-back

## Operating boundary

`automation_reconcile.py` compares desired tasks with observed local scheduler records.
It saves inventories, comparisons, operations, results, verification and recovery history.
The Python commands do not call a scheduler API or edit app-owned scheduler files.
The agent applies rendered operations through the supported `automation_update` control.

M3 retains the [M0 operating limits](M0_EXIT_REPORT.md).
Production deadline setup remains manual because exact one-time execution and expiration remain unverified.
The M3 comparator does not substitute a recurring dispatcher or local OS timer.
M4 adds a separate bounded dispatcher with its own configuration, coverage checks and acceptance procedure.
See [M4_AUTOMATION.md](M4_AUTOMATION.md). That path does not establish natural one-time expiration.
It renders manual instructions from M2 plans and verifies supported local configuration changes.
It does not claim complete deadline coverage or enable production automation.

Official documentation describes supported task creation and updates from a chat.
It also distinguishes existing-chat tasks from standalone runs.
See [scheduled tasks](https://learn.chatgpt.com/docs/automations?surface=app).
The local tool schema and saved records establish the controls used in this test.
No private scheduling endpoint is part of this implementation.

## Local records and ownership

The scheduler ledger is `data/automation/scheduler/state.sqlite3`.
It uses a separate version 1 schema and preserves M1's existing database.
Initialization assigns an installation ID and binds it to the checkout and local inventory directory.
Unknown database versions stop execution.

Managed prompts contain one ownership line with the installation, logical key, role and revision.
Roles are `check`, `anchor` and `probe`.
An ownership marker does not authorize changing a different target task.
The comparator preserves unrelated tasks and rejects ambiguous ownership or target conflicts.
The daily anchor requires separate manual setup. Ordinary reconciliation cannot update, delete or disable it.

## Initialize and import inventory

```sh
python3 -m fantasy_agent automation schedule-init
python3 -m fantasy_agent automation schedule-import
```

Initialization writes local scheduler state only.
The default inventory directory is `$CODEX_HOME/automations`, or `~/.codex/automations` when that variable is absent.
`schedule-init --inventory-directory PATH` selects the directory for a new installation.
Repeated initialization preserves the existing installation and directory.

The reader enumerates all direct local task directories twice and compares their file bytes.
Missing files, malformed records, symlinks and detected changes make the inventory incomplete.
The result excludes cloud schedules and historical runs. It is not an atomic account-wide snapshot.
Prompt hashes support comparison without copying unrelated prompt text into the ledger.

`schedule-import --file PATH` stores externally supplied evidence with an untrusted provenance label.
That evidence cannot certify state or authorize scheduling operations in M3.
The implementation trusts only its own local read for this scoped workflow.

Inventories must be complete, correctly scoped and no more than 60 seconds old.
Malformed, future or stale timestamps block reconciliation.
The comparator does not interpret incomplete inventory as an empty scheduler.

## Compare an M2 plan

```text
python3 -m fantasy_agent automation schedule-spec --plan PLAN_PATH --target-thread TASK_ID --output DESIRED_PATH
python3 -m fantasy_agent automation schedule-import
python3 -m fantasy_agent automation schedule-diff --desired DESIRED_PATH --inventory-id INVENTORY_ID
```

1. Supply the actual target task ID.
2. Use a current M2 plan with unchanged source references.
3. Read all findings and manual instructions.
4. Register the exact M1 contract before any future scheduled delivery.
5. Verify the control's timing semantics before configuring the requested date.

M3 does not register M1 checks or enable M1 execution modes.
M2 input blockers remain visible in the desired specification and comparison.
The manual instructions preserve exact due and latest-start times.
Expired checks do not become future tasks.
Missing desired checks never authorize broad cleanup.

Task capacity counts all local entries, including unrelated and paused tasks.
The comparison reserves two slots for the daily anchor and recovery.
The configured cap is a conservative local policy, not a verified account limit.
Capacity failures remain visible as uncovered requirements.

## Apply one supported operation

```text
python3 -m fantasy_agent automation schedule-begin --diff-id DIFF_ID --index 0
```

This command creates a durable pending operation before the external tool call.
It checks the comparison's expiry and rereads local inventory hashes.
Any inventory change requires another import and comparison.
Use the returned `automation_update` arguments before `apply_before`.
Do not repeat a tool call after an uncertain result.

The tool-call interval cannot be atomic with app changes by another actor.
If the operation window passes before dispatch, inspect and resolve the pending record before starting again.
All supported operations require the existing authorized scope.
Rendered arguments preserve the current notification preference during updates.

The software permits only one unresolved scheduler operation per installation.
It retains that block after interruption, restart or elapsed time.
It does not assume that a timed-out external call had no effect.

For duplicate tasks, the comparator first requires an exact matching keeper.
It can then propose pausing an active duplicate with matching ownership and target.
Without a verified keeper, it reports ambiguity instead.
Deletion requires explicit retirement keys and preserves protected anchors.

## Record and verify the result

1. Save the actual tool result in a project evidence file.
2. Record the result with the returned operation ID and token.
3. Import a fresh inventory after the tool call and result record.
4. Verify the operation against that new inventory.

```text
python3 -m fantasy_agent automation schedule-record --operation-id OP_ID --token TOKEN --outcome success --task-id RETURNED_ID --evidence EVIDENCE_PATH
python3 -m fantasy_agent automation schedule-import
python3 -m fantasy_agent automation schedule-verify --operation-id OP_ID --inventory-id NEW_INVENTORY_ID
```

Use `unknown` for an uncertain tool outcome. `failed` also requires read-back before another operation.
A successful create response requires its returned scheduler ID.
The response alone never establishes success.
Verification compares the saved name, status, schedule, prompt hash and target.
Create and update verification require exactly one owned task for the logical key.
Delete verification requires absence in a complete later inventory.

Configuration verification is separate from active status, completed execution and deadline coverage.
A paused matching task proves its saved configuration only.
M3 always reports `deadline_coverage_verified` as false under the retained M0 timing limits.
After a verified operation, another comparison of matching desired state produces no changes.

## Recover an uncertain operation

If creation succeeded but its response was lost, import a fresh inventory.
An exact unique match can verify the pending create and recover its scheduler ID.
A missing task alone does not prove that a delayed request cannot still complete.

If the operator confirms that the control request ended without a possible late completion:

1. Save that confirmation as evidence.
2. Import another complete inventory.
3. Confirm that affected task state equals the pre-operation state.
4. Record the explicit recovery decision:

```text
python3 -m fantasy_agent automation schedule-resolve --operation-id OP_ID --inventory-id INVENTORY_ID --evidence EVIDENCE_PATH --reason DESCRIPTION
```

The command requires unchanged affected state and saves the reason and evidence checksum.
It does not independently prove external request completion. The operator's confirmation remains a separate evidence obligation.
Recovery preserves prior records and invalidates the earlier operation token.
After recovery, start with another import and comparison.

## Validation and live evidence

Tests use simulated scheduler files under temporary directories.
They cover missing, matching, changed, duplicate and unrelated tasks, protected anchors, capacity and timestamp failures.
They also cover serialized operations, lost responses, source changes, explicit recovery and M2 integration.
Database triggers reject updates and deletions of history records.
Exports omit operation tokens and use immutable `storage.save_new` persistence.

The September 11 live cycle created one paused probe, verified it, updated the same scheduler ID, verified it and deleted it.
A final complete local inventory contained zero entries.
The probe never ran. No provider call or Sleeper change occurred during the cycle.
Evidence: `data/automation/m3/live-cycle.json` and the three saved tool results beside it.
The scheduler ID was `fantasy-football-m3-disposable-probe-v1`.
The generated probe files preserve both versions and the explicit retirement request.

Use `schedule-export --output NEW_PATH` to save an immutable ledger report.
The report is evidence, not a restorable database backup.
Repeat machine-specific verification after transfer. Only one Mac operates at a time.

Local acceptance passed on September 11, 2026: all 274 tests passed, including 21 M3 tests.
The document checker reported zero structural findings. Manual review retained the technical vocabulary distinctions.
This completes M3 in the documented manual operating mode. It does not establish automatic exact one-time deadline scheduling.
