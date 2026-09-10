# A/B planner checkpoint

Seat 13; generated 2026-09-08T22:23:35.714136+00:00.
Offline tests and synthetic drafts only. Source freshness and live-state checks are unchanged.

## Planning

- A enumerates bounded plausible short-gap responses and chooses the strongest worst-case pair. A discounted greedy terminal pick approximates the long gap.
- B samples the long gap and solves a constrained-maximin future A–B pair in every path. Its score blends mean utility with the lower-quarter average.
- Last picks truncate the horizon. Other seats without a short pair retain the two-pick planner.
- Opponent rankings are pre-indexed by position; eligibility/position adjustments are applied before merging the best few options. Greedy marginal evaluation remains exhaustive.

## Same-state timing and choices

| Phase | Pick | Horizon | A/B choice | Previous choice | A/B seconds | Previous seconds |
|---|---:|---|---|---|---:|---:|
| A | 13 | [13, 16, 41] | De'Von Achane | De'Von Achane | 0.338 | 0.426 |
| B | 16 | [16, 41, 44] | De'Von Achane | De'Von Achane | 0.192 | 0.395 |
| A | 69 | [69, 72, 97] | Sam LaPorta | Sam LaPorta | 0.374 | 0.435 |
| B | 72 | [72, 97, 100] | Sam LaPorta | Sam LaPorta | 0.213 | 0.441 |
| A | 181 | [181, 184] | Kansas City Chiefs | Kansas City Chiefs | 0.009 | 0.029 |
| FINAL | 184 | [184] | Tyler Loop | Tyler Loop | 0.004 | 0.003 |

Before-turn prefix forecast: 0.607s. Timings are observations on this machine, not guarantees.
The previous planner here also uses the new, equivalent opponent-ranking index; comparing against old 2-second timings would mix algorithm and implementation changes.

## Paired complete drafts

| Opponents | Seed | Difference vs two-pick | Difference vs ECR |
|---|---:|---:|---:|
| ecr | 31001 | +10.5 | +64.3 |
| ecr | 31002 | -9.9 | +96.2 |
| qb_run | 31001 | +0.0 | +218.3 |
| qb_run | 31002 | +4.8 | +224.3 |

Mean differences: +1.3 vs two-pick; +150.8 vs ECR.
All 12 final rosters satisfy required slots. Slowest A/B calculation: 0.415s; previous planner: 0.584s.
The score is the supported offensive starter season subtotal. It uses the same inputs as the planner and is not a win rate or calibrated forecast. K/DEF, weekly lineup changes and real agents are not evaluated.

## Limits

- Search is exact only within the capped choices/responses. Plausibility uses adjusted-rank slack, not a proven optimal opponent objective.
- A and B use different truncated approximations; an A forecast does not commit the later B action.
- Bench references can make utility non-monotonic at FLEX transitions. No unsafe dominance pruning is used in exhaustive greedy continuations; A/B beams can still omit useful candidates.
- Terminal weight, candidate widths and downside blend are explicit assumptions, not fitted parameters.
- Saved player data may be expired. No live export or browser action was performed.
