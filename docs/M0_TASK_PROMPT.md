# M0 task prompt

Run the M0 capability probe in this Fantasy Football project.
Read `docs/M0_PROBE.md` first.
Use the existing Python interpreter.

1. Run `python3 automation_probe.py run --sleeper-read`.
2. Retain the returned run ID and receipt path.
3. Inspect the Sleeper league through the ChatGPT in-app browser.
4. Use the league ID from `config.json`.
5. Record whether the page shows the team or a login screen.
6. Save the browser observation through `automation_probe.py observe`.
7. Report the result and any access failure.

Do not change Sleeper state.
Do not use another browser.
Do not install software or expand permissions.
Do not bypass a failed capability check.
Do not create further tasks from this test task.

Record the scheduler task ID and due time if the scheduler exposes them.
Label this execution as scheduled only when scheduler evidence establishes that fact.
The script's default trigger label is an unverified caller claim.
The supervising session will verify the task evidence and cancel the disposable task.
