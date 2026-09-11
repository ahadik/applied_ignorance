# From supervised tools to an autonomous team manager

## Implementation update

`league_manager.py` now supplies startup, live phase discovery, recurring scheduling checks, saved inference decisions, and retained follow-up obligations.
`manager_authority.py` adds standing management permission with source, account, scheduling, daily-limit, and live acceptance checks.
The owner excluded external outage monitoring from scope.
The sections below retain the original gap analysis. Use `docs/LEAGUE_MANAGER.md` for implemented operation and `docs/PROGRESS.md` for acceptance evidence.
Live game windows, supervised transaction acceptance, and broader football judgment remain separate from code completion.

## Product goal

The agent should run the fantasy team throughout the season without routine human approval.
The owner should observe its work through conversation and intervene when necessary.
Human involvement should address failures, unresolved confusion, and serious decision errors.
Routine uncertainty about future football performance should not trigger an approval request by itself.

This goal updates the product direction on September 11, 2026.
It does not activate existing permissions or remove the current execution checks.
Earlier supervised procedures remain the operating instructions until implementation and live evidence support their replacement.

## 1. Give the agent authority for routine work

**Current:** automatic changes are disabled.
The implemented promotion path permits only unlocked starter changes after two supervised game windows and explicit delegation.
That permission expires within seven days and includes a daily action limit.
Roster transactions require approval for each exact plan.

**Gap:** the owner remains part of ordinary execution.
Short permission periods also require repeated owner involvement.

**Required work:** define standing operating rules for lineups, additions, drops, ordered waiver requests, and eligible injury-reserve moves.
Include transaction limits, protected players, pause controls, and conditions that suspend permission.
Define trade authority separately, including whether offers or messages may be sent.
Current instructions do not authorize unsolicited offers or messages.

**Completion evidence:** routine authorized work completes without an owner response.
Out-of-scope actions stop, and revocation blocks new actions immediately.
The system checks the actual result of every change.

## 2. Keep the season running without manual scheduling

**Current:** bounded scheduled workflows, deadline planning, and schedule verification exist.
Harmless scheduled tests passed. Continuing daily coverage is not configured.
Sunday's noon review must schedule the later review.

**Gap:** a scheduled test is not a continuing season service.

**Required work:** configure and verify ongoing reviews, deadline checks, week changes, and pending-transaction follow-ups.
Handle expired schedules, delayed runs, changed game times, and restarts without losing obligations.

**Completion evidence:** operation continues across multiple planning cycles and a week change without manual schedule repair.
Records distinguish a future scheduled check from a check that actually completed.

## 3. Finish live roster execution

**Current:** saved plans support additions, drops, waiver requests, cancellation, and injury-reserve operations.
Tests cover ownership changes, conflicting actions, and requests that depend on the same dropped player.
The integrated review compares five available offensive candidates against unlocked bench players.
Actual roster transaction testing remains pending. This league has no injury-reserve slots.

**Gap:** these services do not yet prove independent roster management through the browser and actual league processing.

**Required work:** test legitimate transactions, private pending requests, claim order, and final results.
Connect those steps to standing permission and scheduled follow-ups.
Expand candidate coverage where evidence supports it.

**Completion evidence:** an appropriate real transaction completes with matching browser and provider records.
A submitted waiver request remains pending until its actual outcome is known.
Test unsupported league features in simulation without manufacturing unnecessary real moves.

## 4. Recover first, ask for help when necessary

**Current:** saved execution states prevent blind duplicate actions.
Unknown outcomes block conflicting work. Some recovery paths require explicit owner instructions.
Pushover delivery to the owner's phone passed a live test.

**Gap:** the system lacks a complete policy for deciding which failures it can resolve independently.
It also lacks an external monitor for a silent or disconnected Mac.

**Required work:** define bounded recovery for temporary provider failures, stale observations, browser interruptions, and missed reviews.
Preserve uncertain results until fresh evidence resolves them.
Add an independent check for missed operation when the Mac cannot send its own alert.
Escalate unresolved cases with the cause, attempted recovery, deadline, and exact help needed.

**Completion evidence:** recoverable interruptions resolve without human involvement or duplicate changes.
Unrecoverable and silent failures produce a useful alert through a functioning route.

## 5. Improve judgment and detect serious errors

**Current:** the system checks legality, identities, locks, source age, and supported scoring.
Current forecasts support weekly comparisons. Future forecasts remain incomplete.
Bench value uses an uncalibrated assumption, and waiver-priority cost remains a separate strategic judgment.
An evaluation tool exists, but there is no evidence of a winning advantage.

**Gap:** a legal action can still be a poor football decision.
The existing checks do not establish reliable detection of deeply incorrect calls.

**Required work:** define decision checks for major losses in expected team value, contradictory evidence, and departures from established strategy.
Improve future-week coverage, specialist scoring, and the cost of using waiver priority.
Compare decisions with alternatives using information available at the time.
Record owner corrections and investigate whether they expose a repeatable defect.

**Completion evidence:** recorded cases show serious errors stopped before execution and ordinary uncertainty handled without unnecessary escalation.
Evaluate actual outcomes over time. A disappointing score alone does not prove the original decision was wrong.
No detector can guarantee that it will identify every bad call.

## 6. Make observation easy

**Current:** conversation can explain saved proposals, approvals, actions, and outcomes.
Those records span several commands and files.

**Gap:** the owner lacks one consistent view of what the agent is doing and whether it needs help.

**Required work:** provide a concise status summary from saved records.
Show current activity, last completed review, next verified check, recent changes, pending claims, and unresolved exceptions.
Support questions about reasons and alternatives without changing strategy merely because the owner asked.
Keep routine success quiet unless the owner requests updates.

**Completion evidence:** the owner can understand current operation and trace a decision without reading internal files or approving routine work.

## 7. Prove the complete operating cycle

**Current:** 346 offline tests, a live integrated review, an approved lineup swap, and individual scheduler and notification checks passed.
Two supervised game windows remain pending.

**Gap:** component checks do not prove season-long unattended operation.

**Required work:** complete Sunday's reviews, then test legitimate waiver processing, week changes, and recovery during continuing operation.
Record missed or incomplete work as failures rather than successful reminders.
Repeat machine-specific checks before moving to the second Mac.

**Completion evidence:** the complete cycle collects data, decides, acts, checks results, schedules future work, and recovers without routine owner input.
Retain separate evidence for simulated failures and actual platform behavior.

## What Sunday establishes

The September 13 reviews can test current data, browser state, supervised decisions, and saved outcomes near actual game deadlines.
Two qualifying reviews can satisfy the live gate for limited lineup permission.
They cannot establish Wednesday waiver processing, complete roster autonomy, or continuing daily coverage.
The [Sunday procedure](FULL_SYSTEM_SUNDAY.md) remains the test plan.

The next delivery stages should address continuing operation and exception handling, then expand authority with verified roster execution.
Observer reporting and decision evaluation can improve alongside that work.
Cloud hosting and mobile access are separate access options. They are not prerequisites for autonomy on a reliable local Mac.
