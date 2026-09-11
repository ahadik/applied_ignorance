# M0 capability probe

## Final capability decision

M0 capability evaluation is complete with a limited operating mode.
See [M0_EXIT_REPORT.md](M0_EXIT_REPORT.md) for the capability matrix, fallback and remaining limits.
Standalone scheduled API and browser checks passed. Natural one-time expiration remains unverified.
Both disposable schedules were deleted. The fresh complete local inventory contains zero entries.
Full dynamic deadline scheduling is not accepted. Use manual activation and explicit schedule maintenance.
The sections below preserve historical checkpoints and the reusable test procedure.

## Standalone test and acceptance review scheduled

The standalone test ID is `fantasy-football-m0-standalone-probe`.
It requests September 11, 2026, at 00:28 America/New_York in the saved local project.
The saved record confirms project ID `f2956e4c-2b7a-4221-acff-9a6e34e07b63` and the existing checkout.
The test uses a separate task with GPT-6 Astra and medium reasoning.
It must save `data/automation/m0/standalone_result.json` and leave its schedule unchanged for inspection.
Repeated execution must not repeat provider or browser work.

The existing conversation schedule requests a supervisor check at 00:33 Eastern.
It must inspect the actual standalone result, preserve scheduler state, clean up both disposable schedules and produce the M0 capability report.
An active record with no known next-run timestamp does not prove natural one-occurrence expiration.
No recurrence beyond the next daily boundary has been observed.

The local inventory command is `python3 -m fantasy_agent automation_probe inventory --output OUTPUT.json`.
It reads all direct local automation directories from `CODEX_HOME`, or `~/.codex` when that variable is absent.
It makes no network requests and saves a new JSON file without prompt text.
Missing, malformed or unreadable schedule records make the inventory incomplete.
Its scope excludes cloud tasks and run history. It is not a transactional scheduler snapshot.
Setup evidence is in `data/automation/m0/inventory_standalone_scheduled.json`.
Both saved schedules were active in that complete local enumeration.
Earlier paused statuses below are historical.

## Scheduled occurrence 4 result

The scheduler resumed this conversation at 04:18:28.905 UTC on September 11, 2026.
The central Sleeper probe succeeded: one API attempt and no cache hit.
Receipt: `72cba698b93243808d83e6434e044606`.
The in-app browser displayed `ahadik`, Free Agents and Applied Ignorance without a login screen.
No tool reported an approval interruption. No Sleeper state changed.
This resumed session listed only temporary directories as writable.
The probe and project record updates used supported scoped approval review.
No persistent permission change was made.

The schedule is paused. Its saved record confirmed `PAUSED`.
Evidence is in `data/automation/m0/scheduled_occurrence_4_evidence.json`.
The owner confirmed the quit/reopen sequence, no required approval and notification receipt.
The confirmation is in `data/automation/m0/occurrence_4_user_confirmation.json`.
The controlled restart test passed for this Mac and account. No new occurrence is scheduled.
M0 acceptance also requires a final review of the chosen mode's capability matrix and scheduling limitations.
The current evidence verifies scheduled continuation in this conversation, including closed-conversation and restart cases.
It does not verify standalone tasks, complete app-wide inventory or automatic reconciliation across tasks.
Explicit pauses prevented further runs. Natural expiration of the one-occurrence schedule remains unverified.
Notification receipt is confirmed, but the delivery device remains unspecified.
These limits prevent a claim that the full dynamic scheduling design is verified.
The sections below preserve earlier checkpoints.

## Controlled restart test scheduled

Occurrence 4 requests a start at 00:18 America/New_York on September 11, 2026.
The existing disposable schedule is active. Its saved record confirmed the new prompt and time.
The snapshot is `data/automation/m0/disposable_schedule_occurrence_4.toml`.
The owner must fully quit and reopen the app after scheduling and before the run.
The app must then remain running, with the Mac awake.
Restart verification requires owner confirmation of this sequence.
The run must record approval requirements, pause the schedule and verify cleanup.
Earlier paused statuses below are historical.

## Scheduled occurrence 3 result

The scheduler resumed this conversation at 04:07:12.489 UTC on September 11, 2026.
The central Sleeper probe succeeded: one API attempt and no cache hit.
Receipt: `8dcf7f45486648c897b88fdd4df69962`.
The in-app browser displayed `ahadik`, Free Agents and Applied Ignorance without a login screen.
No tool reported an approval interruption. No user intervention message arrived during the checks.
No Sleeper state changed.

The schedule is paused. Its saved record confirmed `PAUSED`.
Evidence is in `data/automation/m0/scheduled_occurrence_3_evidence.json`.
The owner confirmed that the conversation stayed closed, no approval was needed and a notification arrived.
The confirmation is in `data/automation/m0/occurrence_3_user_confirmation.json`.
Closed-conversation execution and notification delivery passed for this occurrence.
This occurrence does not test a controlled app restart.
No new occurrence is scheduled. The following sections preserve earlier checkpoints.

## Closed-conversation test scheduled

Occurrence 3 requests a start at 00:07 America/New_York on September 11, 2026.
The existing disposable schedule is active. Its saved record confirmed the new prompt and time.
The snapshot is `data/automation/m0/disposable_schedule_occurrence_3.toml`.
The owner must open another conversation before the run and keep the app running and Mac awake.
The run must obtain owner confirmation before marking closed-conversation execution or notification delivery as verified.
It must record any approval requirement, pause the schedule afterward and verify cleanup.
The controlled app-restart test remains a separate occurrence. Earlier paused statuses below are historical.

## Scheduled occurrence 2 result

The scheduler resumed this conversation at 03:58:12.672 UTC on September 11, 2026.
This event was 12.672 seconds after the requested time.
The exact probe command succeeded with scoped network permission.
Its receipt ID is `9fa9ac0741994df28487351afb408796`.
The central client recorded one API attempt and no cache hit.
The browser displayed `ahadik`, Free Agents and Applied Ignorance without a login screen.
Week 1 showed Purdy among the starters and Mahomes on the bench.
No Sleeper state changed.

No tool reported an approval interruption. No user intervention message arrived during these checks.
The owner subsequently confirmed that no approval was needed during occurrence 2.
This verifies unattended completion for this occurrence after permission setup.
The confirmation is in `data/automation/m0/occurrence_2_user_confirmation.json`.
The owner reported Screen Recording approval and an app restart before this occurrence.
This establishes successful scheduled execution after that setup, but not a controlled restart test.
Closed-chat execution and notification delivery remain unverified.

The schedule is paused. Inspection of the saved record confirmed `PAUSED`.
Evidence is in `data/automation/m0/scheduled_occurrence_2_evidence.json`.
The saved schedule is `data/automation/m0/disposable_schedule_occurrence_2_paused.toml`.
No new occurrence is scheduled. M0 acceptance remains pending.
The sections below preserve earlier checkpoints.

## API diagnosis and second occurrence

The client now distinguishes connection failures from HTTP responses in safe diagnostic fields.
It records attempt counts for connection, HTTP and cooldown failures without raw transport messages.
The probe preserves those fields. All 207 offline tests passed.

The restricted read failed with a connection error, one attempt and no cache hit.
Its receipt ID is `2758a9819f5e42aca653b14a63e6d442`.
The same command succeeded with the supported network permission mode at 03:54:28 UTC on September 11.
Its receipt ID is `2e4e47e8e97d41ca8ef0533014f5985d`.
It made one API attempt with no cache hit. Source publication time remains unknown.
This comparison points to restricted execution as the cause. Screen Recording permission does not control API access.
The agent did not change persistent permissions, provider policies or cache locations.

The existing disposable schedule now requests occurrence 2 at 23:58 Eastern on September 10, 2026.
The saved record confirmed its active status, revised prompt and time.
Its snapshot is `data/automation/m0/disposable_schedule_occurrence_2.toml`.
This occurrence will test scoped network permission and browser access after the owner's permission setup.
Any required user approval prevents a claim of unattended success.
The run must pause the schedule and verify cleanup afterward.
Closed-chat execution and a controlled restart test remain separate requirements.

## Scheduled occurrence 1 result

The scheduler resumed this conversation on September 11, 2026, at 03:49:17.639 UTC with prompt revision B.
This event was 17.639 seconds after the requested time. One event does not establish general scheduler latency.
The local probe ran in the correct project.
Its receipt ID is `29fd98a2bf6e49828fd50ddfad881570`.
The central Sleeper read failed with `SleeperError`. The cause, cache result and attempt count remain unknown.
The in-app browser displayed `ahadik`, Free Agents and Applied Ignorance without a login screen.
Week 1 showed Purdy among the starters and Mahomes on the bench.

The owner reported granting macOS Screen Recording permission and restarting the app.
The timing of these actions relative to the browser observation remains unknown.
This was not a confirmed grant of API network permission.
The agent misinterpreted the initial permission report and repeated the API probe.
The repeat receipt is `df6df9d9f7a841a892ab9307e25bd178`. It also reports `SleeperError`.
No Sleeper state changed.

The disposable schedule is paused. Inspection of its saved record confirmed `PAUSED`.
Evidence is in `data/automation/m0/scheduled_occurrence_1_evidence.json`.
This result establishes a scheduled continuation and browser inspection with reported user intervention.
It does not establish unattended operation, a scheduled start after restart, closed-chat execution or notification delivery.
M0 remains incomplete. Resolve the API failure and test another scheduled occurrence after permission setup.

## Disposable schedule setup

The disposable schedule ID is `fantasy-football-m0-disposable-probe`.
It targets this conversation in the local project.
Creation and updates succeeded through the scheduling tool.
The saved record confirmed the prompt change from revision A to revision B.
It also confirmed the requested time change from 23:48 to 23:49.
The requested date is September 10, 2026, in America/New_York.
The schedule requests one occurrence.
The scheduler's computed due time remains unknown.
Computer Use blocked inspection of the app's scheduling screen.
No access restriction was bypassed.

Evidence is in `data/automation/m0/schedule_setup_evidence.json`.
The exact saved prompt is in `data/automation/m0/disposable_schedule_revision_b.toml`.
The prompt requires the resumed session to pause this schedule after the probe and verify cleanup.
At this setup checkpoint, scheduled execution and cleanup were pending. The result above supersedes that status.
This occurrence tests continuation in the same conversation.
Closed-chat and app-restart tests remain separate requirements.

## September 11 interactive browser result

The local probe succeeded in this session at this checkpoint.
Its receipt ID is `11d0a475c2634606b7d2f65d7154325b`.
The command made no provider requests.
The in-app browser displayed the Sleeper team page without a login screen.
The visible account was `ahadik`.
The league was Free Agents, 2026 14-Team PPR.
The team was Applied Ignorance.
Week 1 showed Purdy among the starters and Mahomes on the bench.
No Sleeper state changed.

The observation time was September 11, 2026, at 03:37 UTC.
The app version and app account were unknown.
Evidence is in `data/automation/m0/browser_evidence_11d0a475c2634606b7d2f65d7154325b.json`.
The owner identifies this session as ChatGPT.
The owner uses VS Code with the ChatGPT plugin for separate infrastructure development.
The browser tool reported its name as `Codex In-app Browser`.
The original evidence used that tool label to identify the app.
That label does not resolve the difference from the owner's app identification.
The interactive browser test passed in this session. It does not need repetition because of this naming difference.
Scheduled browser access remains untested.
Scheduled tests and M0 acceptance remain pending.

## Earlier checkpoint and procedure

The probe script exists. Scheduled execution and in-app browser access still need tests in the ChatGPT app.
Use the ChatGPT in-app browser for these tests.
Do not substitute Chrome or another browser.

The IDE session could run local tools.
It had no scheduling tool.
Computer Use blocked access to the ChatGPT app.
The browser tool reported no available browser.
Native Chrome access also failed before the owner selected the in-app browser.
These observations do not establish the capabilities of a scheduled ChatGPT run.

The local suite passed 205 tests.
The restricted Sleeper probe failed and saved its receipt.
The same command succeeded with network permission.
That successful read made one API attempt with no cache hit.
Its receipt ID is `d10b1de378084d7c912a1e989118ba9d`.
No task or Sleeper state changed.

## Commands

Run this command from the project root:

```sh
python3 -m fantasy_agent automation_probe run
```

It saves a new receipt under `data/automation/m0/runs/`.
It makes no provider requests by default.
The receipt records Python, host, project, commit and source checksum.
It also records whether the working directory matches the project.
It never reads `.env` or saves credentials.

Use this command for one public league read:

```sh
python3 -m fantasy_agent automation_probe run --sleeper-read
```

This command uses `sleeper.get_sleeper` with metadata and no retries.
It preserves the shared cache, quota ledger and cooldown.
It makes no FantasyPros or nflverse requests.
It does not check browser login or verify roster changes.
A failed read returns exit code 1 and saves the failure receipt.
The report omits raw error text to protect credentials.

## Test from the ChatGPT app

1. Open this project in the ChatGPT app.
2. Start a new chat.
3. Request the M0 test from this document.
4. Run the local probe.
5. Inspect Sleeper through the in-app browser.
6. Record the visible account and league evidence.
7. Record whether the page shows the team or a login screen.

Do not change the lineup, queue, waivers or account settings.
If browser access fails, record the failure.
Do not bypass an access restriction.

## Disposable scheduled task

Use the task title `Fantasy Football M0 disposable probe`.
Use this project as the local execution directory.
Use the prompt in [M0_TASK_PROMPT.md](M0_TASK_PROMPT.md).
Select a supported one-off time with enough time to save and inspect the task.

Record the exact task ID, time zone, due time and task prompt.
Read the task through the supported controls after creation.
Record all pages if the task inventory uses pagination.
Do not infer task absence from an incomplete inventory.

Change the disposable task time and prompt before it starts.
Read the task again to verify both changes.
Then allow the scheduler to start it.
Do not use Run now as proof of scheduled execution.
Use separate test occurrences for a closed chat and an app restart.
The app must run when the local task is due.

After the test, disable or cancel the disposable task.
Read the task inventory to verify cleanup.
Do not change unrelated tasks.
If the controls lack a required function, record that limitation.

## Evidence and limits

The `--trigger scheduled` option records a caller claim.
It cannot prove that ChatGPT started a scheduled run.
The `--expected-at` option also records a caller claim.
The resulting delay measures time against that supplied value.
Require scheduler evidence before interpreting the delay as measured scheduler latency.

Record UI or tool evidence with this command:

```sh
python3 -m fantasy_agent automation_probe observe --run-id RUN_ID --capability browser_inspection --status unavailable --evidence-file data/automation/m0/evidence.json
```

The evidence JSON requires these fields:

- `observed_at`: a timestamp with a time zone.
- `surface`: the tool or UI that supplied the result.
- `execution_mode`: `interactive` or `scheduled`.
- `result`: the observed result without credentials.
- `reference`: the task, tool-call or screenshot reference.

Include app version and account/workspace context when available.
Keep unknown values explicit.
The command stores evidence in a separate record.
It does not overwrite the original receipt or certify M0 acceptance.

The [receipt schema](../schemas/automation_probe.schema.json) documents the output.
The script checks basic record invariants without a third-party schema package.
The unit tests use simulated provider responses and temporary directories.

Use the current capability decision in [M0_EXIT_REPORT.md](M0_EXIT_REPORT.md).
Preserve its manual-activation fallback until further tests establish the missing scheduling capabilities.
