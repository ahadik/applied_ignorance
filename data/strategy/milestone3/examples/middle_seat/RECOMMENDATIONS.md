# Draft strategy recommendations

Draft simulation-middle_seat; observed through pick 6; targeting 7 then 22.
8 scenarios; 7 evaluated candidates; 0.92s computation.

Scenario survival percentages are model-dependent fractions, not calibrated probabilities.

| Player | Pos | Immediate gain | Two-pick gain | Worst mode | Survives if passed | Flags |
|---|---|---:|---:|---:|---:|---|
| Puka Nacua | WR | 180.5 | 302.9 | 296.1 | 0% | injury_review |
| Amon-Ra St. Brown | WR | 174.6 | 296.9 | 290.1 | 0% |  |
| De'Von Achane | RB | 145.8 | 267.4 | 261.3 | 0% |  |
| Chase Brown | RB | 131.2 | 252.8 | 246.7 | 12% |  |
| CeeDee Lamb | WR | 126.2 | 248.5 | 241.7 | 0% |  |
| Justin Jefferson | WR | 114.8 | 237.2 | 230.4 | 0% |  |
| Drake London | WR | 113.5 | 235.8 | 229.0 | 12% |  |

Assumptions:

- Two-pick horizon; future own pick uses greedy marginal utility.
- Scenario fractions depend on uncalibrated opponent assumptions, not measured probabilities.
- Pass survival assumes selecting the best legal ECR alternative at this turn.
- Season scoring subtotals, virtual replacement starters and discounted bench utility are proxies.
- No opponent agent identity/strategy is inferred from mock bot behavior.
- News/injury/depth flags require review; no automatic weekly injury probability multiplier.
