# Queue rehearsal — September 8, 2026

Draft: https://sleeper.com/draft/nfl/1403090401178435584

Separate second mock.  Sleeper inherited the title “Applied Ignorance — Mock 1” and settings: 14 teams, PPR, 15 rounds, 2-minute timer. Claimed seat 7. All 15 roster slots verified. Actual league untouched.

## Verified queue behavior

- Added eight first-round alternatives before starting. Other managers' selections automatically removed players from the queue.
- Removed Puka Nacua and re-added him. This moved him behind Amon-Ra St. Brown and James Cook. St. Brown was visibly marked Next Pick even though Puka had a higher Sleeper ranking.
- With auto-pick initially OFF, deliberately allowed the first-round timer to expire. Sleeper selected St. Brown, proving it honored the queue order in this mock.
- The timeout also enabled ongoing AUTO-PICK. Before the next observation, opponents had exhausted the remaining queue and Sleeper selected Kenneth Walker at pick 22. Disabled auto-pick through the banner immediately after observing this.
- Prepared queues for subsequent turns, selected queued targets manually through the player-row plus control, and checked roster counts. Queue alternatives sometimes disappeared before our next turn, requiring replenishment.
- Removed obsolete position targets when roster needs changed. Most normal turns observed had well over a minute remaining at selection. Timing was not systematically instrumented.

This does not test browser disconnection, server-side persistence while offline, or behavior in the actual league. Drag-and-drop queue ordering and drafting via the queue panel's own action were not tested. Removing and re-adding works to move a player to the end.

## Live draft procedure

1. Queue acceptable alternatives before the turn. Include sufficient depth for intervening selections. A small queue is not protection against a long absence.
2. Verify the first surviving queue entry remains appropriate for current roster needs.
3. Select promptly and verify the recorded pick. Refresh the queue between turns.
4. After any timeout or interruption, check for the auto-pick banner immediately, disable ongoing auto-pick to regain manual control, and reconcile any intervening selections before proceeding.
5. Keep queue state and draft recommendations in an external checkpoint so conversation compaction does not require reconstruction.

## Verified roster, in draft order

1. Amon-Ra St. Brown — WR — queued timeout pick
2. Kenneth Walker — RB — automatic pick after timeout enabled ongoing auto-pick
3. DeVonta Smith — WR
4. D'Andre Swift — RB
5. Terry McLaurin — WR
6. George Kittle — TE
7. Trevor Lawrence — QB
8. Jayden Reed — WR
9. Aaron Jones — RB
10. Jalen Coker — WR
11. Denzel Boston — WR
12. Dalton Schultz — TE
13. Keaton Mitchell — RB
14. Eddy Pineiro — K
15. Green Bay Packers — DEF

Execution rehearsal only. Choices used displayed Sleeper rankings/projections, not an independently validated optimization model. Several injury flags and shared bye weeks require evaluation before any live recommendations. Do not reuse this roster as a fixed draft plan.
