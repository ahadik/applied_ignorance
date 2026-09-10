# Draft strategy recommendations

Draft simulation-replay_1403085664475467776; observed through pick 6; targeting 7 then 22.
8 scenarios; 7 evaluated candidates; 0.93s computation.

Scenario survival percentages are model-dependent fractions, not calibrated probabilities.

| Player | Pos | Immediate gain | Two-pick gain | Worst mode | Survives if passed | Flags |
|---|---|---:|---:|---:|---:|---|
| Amon-Ra St. Brown | WR | 174.6 | 296.9 | 290.1 | 0% |  |
| Jonathan Taylor | RB | 156.0 | 278.4 | 271.6 | 0% |  |
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
