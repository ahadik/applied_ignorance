# Assigned-seat pre-draft plan

Our seat: **13 of 14**. Draft: 1400628785413394432.
Order observed: 2026-09-08T22:02:44.838696+00:00. Player board built: 2026-09-08T22:35:08.145592+00:00.
Stale board sources at review: none.
Static review only; no mock, watcher, native queue or live candidate export has been started.

## Assigned first-round order

| Seat | Member | Our team |
|---:|---|---|
| 1 | Tianbo |  |
| 2 | edenruro1 |  |
| 3 | jprince47 |  |
| 4 | SlaveAgent |  |
| 5 | hrishi91 |  |
| 6 | mihir14 |  |
| 7 | rickganz |  |
| 8 | Oehtly |  |
| 9 | moltomolto |  |
| 10 | trevorkeith |  |
| 11 | Unclaimed team (roster 14) |  |
| 12 | defnotabot1 |  |
| 13 | ahadik | Yes |
| 14 | pattyfayfay |  |

## Our picks and waiting intervals

| Round | Overall pick | Other selections before our following pick |
|---:|---:|---:|
| 1 | 13 | 2 |
| 2 | 16 | 24 |
| 3 | 41 | 2 |
| 4 | 44 | 24 |
| 5 | 69 | 2 |
| 6 | 72 | 24 |
| 7 | 97 | 2 |
| 8 | 100 | 24 |
| 9 | 125 | 2 |
| 10 | 128 | 24 |
| 11 | 153 | 2 |
| 12 | 156 | 24 |
| 13 | 181 | 2 |
| 14 | 184 | Finished |

There are 12 picks ahead of our opening selection. Our later waits are 2, 24 other selections.
Longer gaps increase the importance of comparing a scarce position now with the options likely to remain later. Shorter gaps allow planning the two choices together. Live selections still determine the actual choice.

## Opening branches

| Scenario | First choice | Likely next choices after taking them | Alternatives now |
|---|---|---|---|
| [01_ecr](scenarios/01_ecr/RECOMMENDATIONS.md) | De'Von Achane (RB) | Chase Brown, Derrick Henry | Chase Brown, Derrick Henry, Trey McBride, James Cook |
| [02_ecr](scenarios/02_ecr/RECOMMENDATIONS.md) | De'Von Achane (RB) | Chase Brown, CeeDee Lamb, Derrick Henry | Chase Brown, CeeDee Lamb, Derrick Henry, James Cook |
| [03_adp](scenarios/03_adp/RECOMMENDATIONS.md) | De'Von Achane (RB) | Derrick Henry, Chase Brown | Chase Brown, Derrick Henry, Drake London, A.J. Brown |
| [04_adp](scenarios/04_adp/RECOMMENDATIONS.md) | CeeDee Lamb (WR) | Derrick Henry | Derrick Henry, Trey McBride, Rashee Rice, Drake London |
| [05_needs](scenarios/05_needs/RECOMMENDATIONS.md) | De'Von Achane (RB) | Chase Brown, Derrick Henry | Chase Brown, Derrick Henry, Trey McBride, Drake London |
| [06_needs](scenarios/06_needs/RECOMMENDATIONS.md) | De'Von Achane (RB) | Chase Brown, Derrick Henry | Chase Brown, Derrick Henry, Trey McBride, James Cook |
| [07_rb_run](scenarios/07_rb_run/RECOMMENDATIONS.md) | Jaxon Smith-Njigba (WR) | Derrick Henry | Derrick Henry, Trey McBride, Rashee Rice, Justin Jefferson |
| [08_rb_run](scenarios/08_rb_run/RECOMMENDATIONS.md) | De'Von Achane (RB) | Derrick Henry, CeeDee Lamb | CeeDee Lamb, Derrick Henry, Trey McBride, Drake London |

First-choice counts in these illustrative branches: De'Von Achane: 6, CeeDee Lamb: 1, Jaxon Smith-Njigba: 1.
These are conditional examples, not a fixed queue or measured likelihoods. See each branch for the hypothetical preceding picks, flags and lookahead calculations.

## Next mock setup

Use seat 13, 14 teams, 14 rounds, snake order, and a 120-second timer.
Match the saved roster/scoring settings in `mock_profile.json`. Verify the new mock ID and its actual assigned seat before starting. The profile is an input for setup, not an applied Sleeper configuration. Use the approved frozen board and verify its session window; do not refresh non-Sleeper sources until the real draft completes.

## Limits

- Static order must be verified again before live use.
- Scenario counts are uncalibrated examples, not probabilities or guaranteed availability.
- Member identities do not imply known opponent strategies; all use the same scenario rules.
- Original player-data timestamps are preserved. This does not refresh or export live candidates.
