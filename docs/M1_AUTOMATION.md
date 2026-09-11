# M1: Durable automation records

## Scope

`automation.py` manages local records in `data/automation/state.sqlite3`.
New installations start in `disabled` mode.
The M1 record commands do not call providers, control browsers, create schedules or change lineups.
[M2](M2_AUTOMATION.md) adds deadline collection and planning. Later milestones will connect these records to workflows and execution.

`automation_store.py` owns contract validation, transactions, claims and recovery.
The existing provider clients and their shared stores remain separate.
Only one Mac operates at a time.

## Initialize and inspect

Run these commands from the project root:

```sh
python3 automation.py init --policy config/automation_policy.example.json
python3 automation.py status
python3 automation.py export --output data/automation/m1/ledger.json
```

Initialization creates the database, disabled policy and first event.
Repeated initialization preserves existing policy and records.
Status reads local state. Export writes a complete JSON snapshot through `storage.save_atomic`.
Exports omit run tokens. Exports are reports, not restorable database backups.
Stop all workers before copying the database for a backup or machine transfer.

`--root PATH` selects another project root. Put this option before the subcommand.
Command input and output paths use the working directory.
Evidence and source references use the selected project root.

## Contracts and modes

The schemas describe policy, check and ledger records:

- `schemas/automation_policy.schema.json`
- `schemas/automation_check.schema.json`
- `schemas/automation_ledger.schema.json`

Runtime validation additionally checks time ordering, time zones and file references.
Unknown contract versions stop the operation.
Database version 1 supports initialization from an empty version 0 database only.
Unknown versions and nonempty unversioned databases require a separate migration. Initialization does not erase them.

The policy permits `disabled`, `observe` and `propose` modes.
Observe mode permits inspection, collection and validation records.
Propose mode additionally permits proposal records.
The operation must also appear in `allowed_operations`.
M1 rejects `authorized_apply` because platform execution is unavailable.

An enabled mode requires an existing setup evidence file:

```sh
python3 automation.py mode observe --evidence docs/M0_EXIT_REPORT.md
python3 automation.py mode disabled
```

These examples describe deliberate mode changes. Initialization does not run them.
The store records the evidence path and checksum. It cannot determine whether the evidence proves setup readiness.
Disabling prevents new claims and renewals. An active worker can still record its result before its lease expires.

## Register and claim a check

A check identifies one operation, season, week, conflict scope and permitted time window.
Use the same scope for operations that must not overlap, such as work on the same league roster.
Use a stable check ID for the same logical check across revisions.

1. Save the check contract as JSON.
2. Include relevant weekly record paths in `source_refs`.
3. Register the check with `register --check PATH`.
4. Read the returned revision.
5. Inspect the packet with `context --check-id ID --revision REVISION`.
6. Claim the check with `begin --check-id ID --revision REVISION`.

For a changed check, supply `register --check PATH --expected-revision PREVIOUS_REVISION`.
Registration hashes normalized UTC timestamps, the check contract and source file checksums.
Equivalent time zones produce the same revision.
Repeated registration of the current contract returns the existing revision without another event.
A check cannot change its conflict scope.

`begin` creates a run record and returns its run ID, token and lease deadline.
It does not execute the operation named in the check.
The claim requires `run_at <= now <= latest_start_at < expires_at`.
Changed source files, disabled modes and stale revisions block the claim.
A completed revision cannot run again.

The claim and its event commit in one SQLite transaction.
Concurrent claims in the same scope cannot both succeed.
The lease expires at the earlier of the policy duration or check expiry.

## Record work

Use the returned run ID and token with these commands:

```text
renew --run-id ID --token TOKEN
reference --run-id ID --token TOKEN --kind evidence --path PROJECT_PATH
finish --run-id ID --token TOKEN --outcome completed --summary DESCRIPTION --artifact PROJECT_PATH
```

Prefix each command with `python3 automation.py`.
Reference kinds are `proposal`, `action` and `evidence`.
An action reference records a file. It neither authorizes nor performs a platform action.
Finish outcomes are `completed`, `failed` and `outcome_unknown`.
Use `failed` only when the failure permits a safe retry.
Use `outcome_unknown` when the result requires inspection before another run.

Renewal and result recording require the active token, current revision and unexpired lease.
A replaced check revision stops its earlier worker from recording completion.
Expired or uncertain runs continue to block their scope.
An expired lease does not establish that an external operation stopped or failed.

## Recover an interrupted run

1. Read `status` and the check's context packet.
2. Inspect the saved evidence and any relevant external state through the authorized workflow.
3. Save the inspection evidence in a project file.
4. Choose `completed` only when the evidence confirms completion.
5. Choose `safe_to_retry` only when the evidence supports another attempt.
6. Record the resolution:

```text
python3 automation.py recover --run-id ID --resolution safe_to_retry --evidence PROJECT_PATH --reason DESCRIPTION
```

Recovery refuses a live lease.
`safe_to_retry` marks the old run `abandoned`. It does not start another run or extend a check's time window.
`completed` prevents another run of that revision.
Recovery appends the reason, evidence checksum and previous state to history.
It does not remove the earlier result or events.
The old token cannot renew or finish after recovery.

## Context and evidence limits

The context packet includes the policy, check, source checksums and relevant scope records.
It contains at most 20 unresolved runs, 20 references and 10 recent events.
An explicit flag reports truncated unresolved runs.
The packet does not copy source contents or conversation history.
File checksums establish saved identity, not current provider freshness.
Workers must inspect the referenced records and independently verify applicable freshness requirements.

References must identify existing non-hidden project files.
The store rejects absolute paths, parent traversal and links to files outside the project or hidden files.
Do not put credentials in summaries or evidence files.

Checks, references and events reject updates and deletions through database triggers.
Current check pointers and run states change transactionally with events.
These protections coordinate cooperative local workers. They do not prevent direct database tampering or unauthorized external operations.
Clock injection supports deterministic tests. The production clock uses the Mac's wall clock.
M1 does not prove recovery from hardware failure or arbitrary clock changes.

## Validation

`tests/test_automation_store.py` uses temporary storage and an injected clock.
Coverage includes concurrent duplicate claims, rollback, restart recovery, stale revisions, lease boundaries and unknown schemas.
Additional checks cover append-only history, mode gates, bounded context, reference isolation and failed export replacement.
Automatic tests do not call live providers or mutate Sleeper.
Local acceptance passed on September 11, 2026: 20 M1 tests and 228 tests across the full suite.
The document checker reported zero structural findings. Manual review retained three vocabulary advisories because the terms describe distinct technical concepts.
The local database started disabled with zero checks, zero runs and one initialization event.
The baseline export is `data/automation/m1/INITIAL_LEDGER.json`.
