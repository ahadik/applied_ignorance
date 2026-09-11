# M4 scheduled acceptance procedure

This procedure uses the real app scheduler and harmless local inspection workflows.
The synthetic roster scope does not represent a real team. No provider request or Sleeper change occurs.
The owner authorized this test with “Finish m4”.

The dispatcher prompt must invoke this procedure during acceptance instead of calling `tick` separately.
The `cycle` command invokes `tick` exactly once.

1. Confirm that the current message is an actual scheduler-injected heartbeat for the bound dispatcher.
2. Save that observation as a new JSON file under `data/automation/m4/live/triggers/`.
3. Include `automation_id`, `basis: observed_scheduler_injected_message`, the observed UTC time and the actual message context.
4. Run the following command with that evidence:

```sh
python3 tests/live_m4.py cycle --automation-id AUTOMATION_ID --trigger-evidence PROJECT_RELATIVE_PATH
```

Do not create trigger evidence from an interactive user request, a manual invocation or a predicted future event.
Do not call the workflow twice for the same heartbeat.
The first cycle preserves the next cycle and a future sentinel in the published coverage horizon.
The second cycle republishes the remaining future obligation and verifies a fresh local inventory.
Each invocation uses a new process and existing durable claims.

If the command returns `retire: false`, retain the schedule for the next actual wakeup.
Keep routine progress quiet during heartbeat turns.
If it returns `retire: true`, delete this exact automation through the supported control.
Then run:

```sh
python3 tests/live_m4.py finish
```

Finish requires two distinct scheduled workflow receipts, verified coverage in both cycles and complete cleanup evidence.
Finish restores disabled automation mode. The future sentinel must never execute.
If a cycle fails, preserve the evidence and inspect the failure before another attempt.

After successful finish, update M4's acceptance record and project status.
Run the complete offline suite and the document checker after implementation changes.
Report M4 complete only after the scheduled acceptance record says `passed`.
Keep real football data readiness, current browser login and unattended uptime limits separate from this harmless acceptance result.
