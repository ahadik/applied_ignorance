# Milestone 3 review checkpoint

Offline strategy implementation and evaluation. No live or browser mock was started.
Board collected/built earlier: 2026-09-08T20:41:36.527888+00:00. Evaluation: 2026-09-08T21:09:55.595440+00:00.
Board content SHA-256: `16020bb1bb71804cf5e8f1c590e28c5035fd902066bae292a7e2c7bbb109974c`.

## What is implemented

- Roster-specific starter/FLEX value and discounted bench value.
- Two-pick lookahead across consensus, ADP, roster needs and running-back runs.
- Ranked alternatives, conditional availability fractions and explicit policy overrides.
- Controller integration with all-team rosters, exact-state invalidation, computation reuse and source expiry.
- Offline examples, two recorded mock first-round replays, paired full drafts and projection stress checks.

## Paired full-draft evaluation

Each pair uses the same opponent scenario/seed for the planner and highest legal ECR baseline. QB-run opponents are outside the default planner scenario mix. All 12 resulting rosters filled all required slots.
The metric is the sum of supported offensive season projections for the best starting lineup. It excludes kicker/defense and is not a league win probability.

| Seat | Opponents | Seed | Planner subtotal | ECR subtotal | Difference | Positive stress draws |
|---:|---|---:|---:|---:|---:|---:|
| 1 | ecr | 31001 | 2004.9 | 1913.5 | +91.4 | 70% |
| 1 | qb_run | 31001 | 2018.7 | 1748.5 | +270.2 | 92% |
| 7 | ecr | 31001 | 1962.6 | 1850.0 | +112.6 | 65% |
| 7 | qb_run | 31001 | 2002.3 | 2001.1 | +1.2 | 32% |
| 14 | ecr | 31001 | 1898.4 | 1893.4 | +5.0 | 55% |
| 14 | qb_run | 31001 | 1888.0 | 1814.2 | +73.9 | 60% |

Mean difference: +92.4; positive pairs: 6/6. Slowest of 90 recommendations: 2.02s.
Mean difference across arbitrary projection stress draws: +76.9. These fractions depend on the chosen perturbations, not measured real-world accuracy.

## Worked examples

| Scenario | Planner choice | ECR choice | Runtime |
|---|---|---|---:|
| [early_seat](examples/early_seat/RECOMMENDATIONS.md) | Jahmyr Gibbs | Ja'Marr Chase | 1.25s |
| [middle_seat](examples/middle_seat/RECOMMENDATIONS.md) | Puka Nacua | Puka Nacua | 0.92s |
| [turn_seat](examples/turn_seat/RECOMMENDATIONS.md) | Derrick Henry | Justin Jefferson | 0.35s |
| [mid_draft](examples/mid_draft/RECOMMENDATIONS.md) | Rhamondre Stevenson | Bhayshul Tuten | 1.05s |
| [quarterback_run](examples/quarterback_run/RECOMMENDATIONS.md) | David Montgomery | Christian Watson | 0.97s |
| [bench](examples/bench/RECOMMENDATIONS.md) | Josh Jacobs | Chris Rodriguez | 1.26s |
| [final_slots](examples/final_slots/RECOMMENDATIONS.md) | Green Bay Packers | Green Bay Packers | 0.30s |
| [injury_sensitivity](examples/injury_sensitivity/RECOMMENDATIONS.md) | Jahmyr Gibbs | — | 1.22s |
| [replay_1403085664475467776](examples/replay_1403085664475467776/RECOMMENDATIONS.md) | Amon-Ra St. Brown | — | 0.93s |
| [replay_1403090401178435584](examples/replay_1403090401178435584/RECOMMENDATIONS.md) | Puka Nacua | — | 0.95s |

`injury_sensitivity` applies a hypothetical 20% season-value reduction to the highest-ranked injury-flagged offensive player. It writes a separate policy; the active policy is unchanged. Mock replays use later player data and only the recorded first-round prefixes; they are not historical performance tests.

## Assumptions to review

- Synthetic drafts, not actual season outcomes or proof of a winning edge.
- Primary evaluation uses the same partial projection inputs as the planner, creating a favorable model-based yardstick.
- Both policies share eligibility constraints; baseline is highest legal ECR, not an intentionally broken drafter.
- Stress draws use arbitrary 20% lognormal dispersion, plus a 20% injury-flag discount in half the draws. No calibration or win probabilities.
- Offensive starters only are scored; K/DEF scoring gaps, weekly matchups, trades, waivers and real opponent agents are not evaluated.
- Policy coefficients and opponent selection rules are explicit but uncalibrated. This run evaluated 6 paired drafts and 1 external seed(s).
- History, current depth, news and injury flags remain evidence for strategic review. They do not automatically change season projections. No independent forecast has been fitted.
- Saved data can expire during review. Operational export rechecks source deadlines and a real controller observation no older than 20 seconds.
- Browser queue maintenance and selection remain supervised. The third integrated mock and pre-draft source refresh are separate operational checkpoints.
