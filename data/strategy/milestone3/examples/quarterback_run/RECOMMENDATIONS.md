# Draft strategy recommendations

Draft simulation-quarterback_run; observed through pick 62; targeting 63 then 78.
8 scenarios; 7 evaluated candidates; 0.97s computation.

Scenario survival percentages are model-dependent fractions, not calibrated probabilities.

| Player | Pos | Immediate gain | Two-pick gain | Worst mode | Survives if passed | Flags |
|---|---|---:|---:|---:|---:|---|
| David Montgomery | RB | 46.5 | 83.1 | 82.3 | 0% | team_changed_since_history |
| Rhamondre Stevenson | RB | 42.8 | 79.3 | 78.6 | 0% |  |
| Jaylen Warren | RB | 41.7 | 77.5 | 77.5 | 12% |  |
| Mike Evans | WR | 40.6 | 77.1 | 76.4 | 0% | injury_review, team_changed_since_history |
| Christian Watson | WR | 37.9 | 74.4 | 73.7 | 0% |  |
| Bhayshul Tuten | RB | 33.1 | 69.6 | 68.9 | 0% | injury_review |
| Jadarian Price | RB | 7.7 | 44.3 | 43.5 | 0% | no_recorded_nfl_history |

Assumptions:

- Two-pick horizon; future own pick uses greedy marginal utility.
- Scenario fractions depend on uncalibrated opponent assumptions, not measured probabilities.
- Pass survival assumes selecting the best legal ECR alternative at this turn.
- Season scoring subtotals, virtual replacement starters and discounted bench utility are proxies.
- No opponent agent identity/strategy is inferred from mock bot behavior.
- News/injury/depth flags require review; no automatic weekly injury probability multiplier.
