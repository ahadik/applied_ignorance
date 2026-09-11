# Mock 3: partial advanced-strategy rehearsal

September 8, 2026. Mock ID **1403185547618349056**, title **Free Agents**.
The user stopped the rehearsal after four supervised selections. Do not resume
this mock without a new request or treat it as a completed draft.

## Setup and evidence

- Seat 13 of 14, snake, 14 rounds, one FLEX, five bench slots, 120-second timer.
- Valuation used the actual league's frozen board at
  `data/draft_session/1400628785413394432/board.json`, with `--allow-mock`.
- Active shared strategy: A/B planner, engine version 2. No fresh FantasyPros
  or nflverse data was fetched.
- `controller.py sync/watch` used the central Sleeper client. Restricted execution
  returned 503. The same sync succeeded with network permission. This is evidence
  of an execution-path difference, not a definitive diagnosis of the 503 origin.
- Initial rapid queue batch attempted six additions but only one visibly persisted.
  Sequential search → add → visible verification successfully populated six entries.
- A player name can match both list and queue. The list is virtualized. Searching
  explicitly and scoping the row resolved missing/ambiguous selectors.

## Verified selections

| Overall pick | Phase | Player | Sleeper ID |
|---|---|---|---|
| 13 | A | Chase Brown | 9224 |
| 16 | B | Derrick Henry | 3198 |
| 41 | A | Garrett Wilson | 8146 |
| 44 | B | Travis Etienne | 7543 |

Each selection used current computed recommendations, a real queue/autopick
observation, successful `controller.py prepare`, one player-list selection, and
subsequent reconciliation. Drafted names disappeared from the native queue.
Team 14 selected Justin Jefferson and A.J. Brown between our first two picks.
The B recommendation recalculated from those actual selections.

The last saved observation was through overall pick 68, with the four-player
roster above and our next pick 69. The final submission record matched Etienne
at 44. Files are under `data/drafts/1403185547618349056/`. These are mutable
checkpoints, not an immutable history of every decision. At stop time, the
watcher's UI observation was stale. Its EMPTY_QUEUE/AUTO_PICK blockers reflected
missing fresh verification, not proof that the browser queue was empty or
autopick was enabled. The last observed browser queue contained Stevenson and
Kittle. Later timeout behavior was not inspected.

The watcher was stopped with Ctrl-C at the user's request. Browser actions also
stopped. Neither action pauses the Sleeper clock. No pause was claimed or verified.

## Conclusions and limits

The public API supplied active mock picks and all opponent rosters. Four complete
supervised A/B selection cycles worked. API state sometimes trailed the browser.
Polling, request and provider delays have not been separately measured. Calculation
benchmarks exclude browser/network time. Operational overhead remained substantial
in UI inspection, queue handling and transferring observations into controller files.

Three RBs in four picks demonstrates the model's valuation preference and FLEX
allocation, not superior team quality. This rehearsal proves neither a winning
edge nor full-draft reliability. Late-round constraints, integrated compaction
recovery, manual takeover and unattended 1–2 hour operation were not tested here.

Apply the required procedures in `DRAFT_RUNBOOK.md` tonight. Further engineering
work remains: compact observation handoff, measured end-to-end latency, and an
append-only audit of state/board/policy hashes, recommendation, queue, preparation
and actual pick. These notes do not claim those improvements are implemented.
