# Python code layout

Application code lives in `fantasy_agent/`. There are no Python scripts in the repository root.
Use the package command interface for all operations.

| Directory | Responsibility |
|---|---|
| `fantasy_agent/core/` | Configuration, shared storage, and scoring helpers |
| `fantasy_agent/providers/` | Central provider clients, caches, quotas, and diagnostics |
| `fantasy_agent/drafting/` | Draft collection, planning, simulation, and supervision |
| `fantasy_agent/weekly/` | Weekly data, lineup calculations, validation, and season analysis |
| `fantasy_agent/execution/` | Action permission, preparation, reconciliation, and recovery |
| `fantasy_agent/automation/` | Scheduled reviews, saved obligations, and workflow control |
| `fantasy_agent/notifications/` | Push notifications and game reminders |
| `fantasy_agent/maintenance/` | Repository setup, documentation checks, and acceptance tests |
| `tests/` | Simulated provider tests and temporary fixtures |

Use package imports for new implementation code.
`fantasy_agent.paths.ROOT` identifies the repository regardless of the command's working directory.
Data, configuration, schemas, and templates retain their existing locations.

## Commands

Run commands from the repository root:

```sh
python3 -m fantasy_agent league_manager status
python3 -m fantasy_agent team_notifications status
python3 -m unittest discover -v
```

Root script commands and unqualified Python imports are no longer supported.
Current task templates and documentation use the package command interface.
Historical receipts under `data/` preserve their original text and are not current operating instructions.
Acceptance fingerprints include the nested package code, tests, schemas, and templates.

## Work performed on scheduled wakeups

The five-minute wakeup checks saved work before starting a full football review.
Pending inference resumes its saved review. A waiting tick does not collect another weekly dataset.
Notification work remains active during waiting ticks.

Notification processing resumes after the last processed execution event.
It reads the player directory once for a batch of new changes, and does not reopen it for old events.
The database selects due, unfinished games before Python decodes their records.
Queued notices and saved event IDs prevent duplicate sends after restart.

A full review loads and verifies its snapshot once for lineup and roster analysis.
The calculations reuse those verified inputs within that review. They still evaluate source age and game locks.
The standalone roster analysis also avoids loading its first snapshot a second time.
These changes reduce file reads and JSON parsing. They do not extend provider cache ages.

## Further optimization

Every scheduled wakeup still invokes conversational inference, even when no football work is due.
A future local timer could run deterministic checks and request inference only for actionable work.
That requires a supported wakeup mechanism and failure recovery before replacing the current recurring task.

Live collection still repeats some state reads to detect changes during collection and before execution.
Remove these only after defining equivalent consistency checks and measuring provider latency.
Do not reuse old mutable Sleeper responses to make a run appear faster.
