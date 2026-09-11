# M0 capability report

September 11, 2026. This report supersedes the historical pending statuses in the probe checkpoints.

## Decision

M0 capability evaluation is complete with a limited operating mode.
Scheduled local execution and browser inspection are feasible on this Mac.
The tests do not establish the full dynamic deadline-scheduling design.
Natural one-time expiration remains unverified.

Use the design's fallback: manual activation and explicit owner-maintained schedules.
Keep deterministic desired schedules as proposals until their actual configuration is verified.
Do not enable automatic deadline-task reconciliation or rely on automatic one-time expiration.
No production schedule was activated by this review.
M1 durable contracts and M2 offline planning can proceed with these limits.

## Capability matrix

| Capability | Finding | Evidence and scope |
|---|---|---|
| Project and interpreter | Verified | Standalone receipt `5228e3404cba4654ad63ac9387476e94` used the saved checkout and Python 3.13.6 |
| Local writes without user approval | Verified in the tested setup | Occurrence 4 saved project evidence through scoped approval review. Owner confirmed no approval was needed |
| Central Sleeper reads | Verified | Occurrences 2–4 and standalone each made one attempt with no cache hit |
| Other providers in scheduled runs | Untested | No FantasyPros or nflverse request was part of these tests |
| In-app browser inspection | Verified | Correct account `ahadik`, league Free Agents and team Applied Ignorance. No Sleeper writes |
| Standalone task | Verified execution | Separate task completed in the local checkout. No tool reported an approval interruption |
| Closed conversation | Verified | Occurrence 3 and owner confirmation |
| App restart after scheduling | Verified | Occurrence 4 and owner confirmation of quit/reopen sequence |
| Notifications | Verified receipt | Owner confirmed occurrences 3 and 4. Delivery device was not specified |
| Local schedule inventory | Verified within scope | Complete direct local file enumeration before and after cleanup. Not a transactional snapshot |
| Cloud or all-account inventory | Untested | Outside the chosen local mode |
| Create, edit, pause and delete | Verified | Supported controls plus saved-record inspection. Prompt and time edits persisted |
| Natural one-time expiration | Unverified | Completed standalone task retained an ACTIVE schedule. No next-run time was exposed |
| Time zone and delay | Observed | Eastern requests matched recorded UTC events on this date. No daylight-saving or punctuality guarantee |

The owner did not separately confirm approval behavior or notification delivery for the standalone occurrence.
Do not extend the confirmed heartbeat findings into those missing standalone facts.

## Timing and permissions

Recorded heartbeat events followed their requested times by 12.489 to 28.905 seconds for occurrences 2–4.
These values measure individual scheduler events, not a service guarantee.
Probe start times also include agent preparation and must not replace scheduler event times.

Restricted execution failed to connect to Sleeper.
The same command succeeded through the supported scoped permission mode.
The client now distinguishes connection failures from actual HTTP responses and records safe failure metadata.
Provider caches, request ledgers and cooldown policies remained intact.

Screen Recording setup preceded the successful confirmed tests.
After restart, the session listed only temporary directories as writable, but scoped project writes succeeded without owner approval.
App version and app-account identifiers remain unknown. Sleeper identity and machine context are recorded in the evidence.
Repeat affected checks after app, account or permission changes, and on the second Mac at M7.

## Cleanup and evidence

The supported control deleted both disposable schedules:

- `fantasy-football-m0-standalone-probe`
- `fantasy-football-m0-disposable-probe`

The complete local inventory after cleanup contains zero entries.
No further M0 run or production automation is scheduled.
The completed standalone task remains available as evidence.

Evidence is under `data/automation/m0/`:

- `acceptance_review.json` records this decision and capability scope.
- `standalone_result.json` identifies the completed standalone task and receipt.
- `standalone_schedule_before_cleanup.toml` preserves the ACTIVE schedule after completion.
- `inventory_before_cleanup.json` and `inventory_after_cleanup.json` verify local cleanup.
- `occurrence_3_user_confirmation.json` and `occurrence_4_user_confirmation.json` preserve owner confirmations.
- `runs/` and `observations/` retain the original receipts and separate observations.

All 208 offline tests passed after the inventory implementation.
The documentation checker reported zero structural findings. Advisory findings are not a compliance certification.

## Remaining engineering boundary

Full dynamic scheduling needs verified one-time semantics or a separately tested recurring dispatcher with explicit timing limits.
Automatic reconciliation also needs a complete inventory contract appropriate to its exact local scope.
This evaluation does not validate a production dispatcher, deadline coverage, phone alerts, lineup execution or second-Mac operation.
Those belong to later milestones and their acceptance tests.
