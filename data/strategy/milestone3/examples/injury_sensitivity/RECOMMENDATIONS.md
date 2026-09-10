# Draft strategy recommendations

Draft simulation-injury_sensitivity; observed through pick 0; targeting 1 then 28.
8 scenarios; 6 evaluated candidates; 1.22s computation.

Scenario survival percentages are model-dependent fractions, not calibrated probabilities.

| Player | Pos | Immediate gain | Two-pick gain | Worst mode | Survives if passed | Flags |
|---|---|---:|---:|---:|---:|---|
| Jahmyr Gibbs | RB | 216.0 | 336.4 | 331.6 | 0% |  |
| Bijan Robinson | RB | 200.0 | 320.4 | 315.5 | 0% |  |
| Puka Nacua | WR | 180.5 | 300.9 | 296.1 | 0% | injury_review |
| Christian McCaffrey | RB | 176.6 | 297.0 | 292.2 | 0% | injury_review |
| Amon-Ra St. Brown | WR | 174.6 | 294.9 | 290.1 | 0% |  |
| Ja'Marr Chase | WR | 112.5 | 232.9 | 228.1 | 0% | injury_review |

Assumptions:

- Two-pick horizon; future own pick uses greedy marginal utility.
- Scenario fractions depend on uncalibrated opponent assumptions, not measured probabilities.
- Pass survival assumes selecting the best legal ECR alternative at this turn.
- Season scoring subtotals, virtual replacement starters and discounted bench utility are proxies.
- No opponent agent identity/strategy is inferred from mock bot behavior.
- News/injury/depth flags require review; no automatic weekly injury probability multiplier.
