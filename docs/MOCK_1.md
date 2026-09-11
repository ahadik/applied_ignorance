# Mock draft 1 — September 8, 2026

Completed and verified all 15 roster selections through Sleeper's browser UI.

Draft: https://sleeper.com/draft/nfl/1403085664475467776

Settings: 14 teams, PPR, snake, seat 7, 15 rounds, 2 minutes per pick. Seat 7 was a rehearsal assumption, not a confirmed real draft assignment. The actual league was not drafted or modified.

| Round | Overall | Player | Position |
|---|---|---|---|
| 1 | 7 | Amon-Ra St. Brown | WR |
| 2 | 22 | Brock Bowers | TE |
| 3 | 35 | Ladd McConkey | WR |
| 4 | 50 | Quinshon Judkins | RB |
| 5 | 63 | Jadarian Price | RB |
| 6 | 78 | Brian Thomas | WR |
| 7 | 91 | Justin Herbert | QB |
| 8 | 106 | Jayden Reed | WR |
| 9 | 119 | Aaron Jones | RB |
| 10 | 134 | MarShawn Lloyd | RB |
| 11 | 147 | Jalen Coker | WR |
| 12 | 162 | Denzel Boston | WR |
| 13 | 175 | Dalton Schultz | TE |
| 14 | 190 | Eddy Pineiro | K |
| 15 | 203 | Green Bay Packers | DEF |

## Evidence and limitations

The completed Sleeper roster showed 1 QB, 4 RB, 6 WR, 2 TE, 1 K and 1 DEF. It covered all required starting slots and five bench slots. Final opponent picks also completed.

This was an execution rehearsal using displayed Sleeper PPR rankings and projections as a provisional baseline. Independent projections, deterministic candidate valuation and simulations were not used. No claim of optimal drafting or competitive advantage follows from this run. Mock bots are not evidence of real opponent strategies.

## Execution findings

- Direct browser draft selections worked for all 15 picks. No observed user autopicks.
- Searching a player and clicking the row's left plus control submits the selection immediately. Clicking a player name opens player details instead.
- Availability can change while bots are selecting. Recheck the current turn and rendered player row before submitting, then verify the recorded pick.
- Reopening the saved mock recovered its state after a stale tab.
- A native fallback queue was not tested and should be established before relying on this workflow for the live draft.
- The roster has concentrated week-11 byes, including both starting RBs and one backup RB. The valuation workflow must account for roster coverage and uncertainty. This mock should not be copied as a fixed target lineup.

## Before the live draft

Load current independent projections and player status with source timestamps. Compute league-specific values and replacement levels. Confirm the real draft position. Produce an ordered fallback queue. Maintain a live board that recomputes after each pick, with explicit roster constraints and candidate alternatives.
