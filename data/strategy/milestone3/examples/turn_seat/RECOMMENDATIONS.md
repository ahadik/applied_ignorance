# Draft strategy recommendations

Draft simulation-turn_seat; observed through pick 13; targeting 14 then 15.
8 scenarios; 7 evaluated candidates; 0.35s computation.

Scenario survival percentages are model-dependent fractions, not calibrated probabilities.

| Player | Pos | Immediate gain | Two-pick gain | Worst mode | Survives if passed | Flags |
|---|---|---:|---:|---:|---:|---|
| Derrick Henry | RB | 125.2 | 243.7 | 243.7 | 100% |  |
| James Cook | RB | 118.5 | 243.7 | 243.7 | 100% |  |
| Rashee Rice | WR | 115.5 | 240.7 | 240.7 | 100% |  |
| Justin Jefferson | WR | 114.8 | 240.0 | 240.0 | 100% |  |
| Drake London | WR | 113.5 | 238.7 | 238.7 | 100% |  |
| A.J. Brown | WR | 106.7 | 231.9 | 231.9 | 100% | team_changed_since_history |
| Nico Collins | WR | 91.9 | 217.1 | 217.1 | 100% |  |

Assumptions:

- Two-pick horizon; future own pick uses greedy marginal utility.
- Scenario fractions depend on uncalibrated opponent assumptions, not measured probabilities.
- Pass survival assumes selecting the best legal ECR alternative at this turn.
- Season scoring subtotals, virtual replacement starters and discounted bench utility are proxies.
- No opponent agent identity/strategy is inferred from mock bot behavior.
- News/injury/depth flags require review; no automatic weekly injury probability multiplier.
