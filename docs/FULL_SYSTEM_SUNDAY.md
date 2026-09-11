# Sunday local acceptance

## Purpose and boundaries

The permanent league manager supersedes this document's historical one-off scheduling steps.
Both Sunday windows are saved manager obligations. Keep the recurring manager task before and after these reviews.
Do not replace its schedule with a single later review or delete it after acceptance.
Use `docs/LEAGUE_MANAGER.md` to finish each review and resolve its actual obligation.

Test the integrated local system on September 13, 2026.
The early review starts at noon Eastern. The later review starts at 3:25 PM Eastern.
Recheck the actual game times before each review.
Keep this Mac awake, connected and signed in to Sleeper.

The local services support collection, proposals, validation, notifications, supervised lineup execution, roster transactions and season coverage.
Live autonomous lineup changes still require two qualifying windows and explicit delegation.
Roster transactions remain supervised. The league currently has zero IR slots.
Do not manufacture claims, drops or IR moves for testing.
Sunday cannot establish Wednesday waiver-processing success or second-Mac acceptance.

## Early review

1. Read `docs/PROGRESS.md` and `docs/M5_EXECUTION.md`.
2. Check the date and current execution status.
3. Update this task's existing heartbeat to Sunday at 3:25 PM Eastern.
4. Preserve the full-system instructions in that update.
5. Run `python3 -m fantasy_agent automation schedule-import`.
6. Confirm one active task with the intended later schedule and prompt.
7. Run the integrated review command below.
8. Open the actual Sleeper team page in the in-app browser.
9. Reload the page and record the account, owned players, starter slots and locks.
10. Compare the native state with fresh central API evidence.
11. Present the exact lineup proposal and any availability findings to the owner.
12. Follow the supervised execution procedure for necessary changes.
13. Confirm the final lineup through a full reload and fresh API observations.
14. Record the actual qualifying game window.

```sh
python3 -m fantasy_agent lineup_execution status
python3 -m fantasy_agent roster_operations status
python3 -m fantasy_agent agent_cycle --season 2026 --week 1 --notify
```

The review uses the central Sleeper, FantasyPros and nflverse clients.
It saves the proposal, independent validation, roster observations, candidate comparisons and season calendar.
The notification uses the central Pushover client. Confirm receipt through actual evidence.
The command performs no browser write and grants no execution authority.

If collection fails, inspect its saved result and provider evidence.
Do not call an unexplained connection failure a provider outage.
Do not repeatedly refresh a rate-limited source.
If an execution outcome is unknown, reconcile it before preparing conflicting work.

## Roster and season review

1. Read the integrated package's season calendar and candidate comparisons.
2. Keep modeled gains separate from priority cost, uncertainty and strategic judgment.
3. Check actual Add/Claim controls and candidate deadlines in Sleeper.
4. Inspect the private pending-claims page and claim order.
5. Record the league's acquisition restrictions and displayed waiver type.
6. Confirm that zero IR slots prevent IR placement in this league.
7. Present a concrete transaction plan only if a legitimate beneficial move exists.
8. Obtain exact owner approval before submitting a transaction.
9. Follow `docs/M6_ROSTER_OPERATIONS.md` for preparation and reconciliation.

Do not count a submitted claim as a won claim.
Reconcile its actual result after the platform processes it.
Schedule that follow-up for the candidate's verified processing window if a claim exists.
Do not send trade offers or messages to other managers.

## Later review and promotion

Repeat the integrated and native checks for the later games.
Preserve players whose games already started.
Record a second distinct qualifying window only after actual owner supervision and successful reconciliation.
A confirmed no-change decision can qualify. An absent owner or fired reminder cannot qualify.

After the later review, delete this exact heartbeat through the supported control.
Verify its removal with `automation.py schedule-import`.
Retain any unresolved owner work in the task.

After both windows pass, present the limited delegation terms to the owner.
The terms must identify the league, roster, season, expiry and daily action limit.
Only unlocked starter changes are eligible. Reviews, roster transactions and trades remain outside delegated authority.
Use the tested promotion commands in `docs/M5_EXECUTION.md` after explicit delegation.
Do not claim promotion merely because the test suite passed.

For continuing daily operation, use M4's bounded dispatcher and an `integrated_review` recipe in propose mode.
After verified scheduler removal, use `automation_dispatch.py archive-expired` to retain an expired contract before preparing its replacement.
Verify its fresh configuration and coverage before claiming ongoing daily monitoring.
The Sunday review schedule alone does not provide that continuing coverage.

## Evidence to retain

- Actual scheduler-trigger and Pushover receipt evidence.
- Fresh provider counts, source times and checksummed snapshots.
- Exact proposals, approvals and independent validation results.
- Native observations, consumed action tokens and reconciled outcomes.
- Two distinct game-window records, or explicit incomplete/missed records.
- Transaction results when a legitimate transaction exists.
- Current offline acceptance for the exact source version.

Record implementation, simulated results and live acceptance separately.
Keep `.env` and credentials excluded from Git.
