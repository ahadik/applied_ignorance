# Draft strategy recommendations

Draft simulation-mid_draft; observed through pick 62; targeting 63 then 78.
8 scenarios; 8 evaluated candidates; 1.05s computation.

Scenario survival percentages are model-dependent fractions, not calibrated probabilities.

| Player | Pos | Immediate gain | Two-pick gain | Worst mode | Survives if passed | Flags |
|---|---|---:|---:|---:|---:|---|
| Rhamondre Stevenson | RB | 45.7 | 82.2 | 81.5 | 0% |  |
| Jaylen Warren | RB | 44.6 | 80.4 | 80.4 | 12% |  |
| Bhayshul Tuten | RB | 36.0 | 72.6 | 71.8 | 0% | injury_review |
| DK Metcalf | WR | 34.7 | 70.5 | 70.5 | 38% | injury_review |
| Alec Pierce | WR | 35.8 | 70.5 | 70.5 | 100% |  |
| Marvin Harrison | WR | 31.8 | 68.7 | 67.6 | 0% |  |
| TreVeyon Henderson | RB | 24.6 | 61.2 | 60.4 | 0% | injury_review |
| Carnell Tate | WR | 18.5 | 55.4 | 54.3 | 38% | injury_review, no_recorded_nfl_history |

Assumptions:

- Two-pick horizon; future own pick uses greedy marginal utility.
- Scenario fractions depend on uncalibrated opponent assumptions, not measured probabilities.
- Pass survival assumes selecting the best legal ECR alternative at this turn.
- Season scoring subtotals, virtual replacement starters and discounted bench utility are proxies.
- No opponent agent identity/strategy is inferred from mock bot behavior.
- News/injury/depth flags require review; no automatic weekly injury probability multiplier.
