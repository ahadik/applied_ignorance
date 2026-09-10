# Draft strategy recommendations

Draft simulation-bench; observed through pick 146; targeting 147 then 162.
8 scenarios; 9 evaluated candidates; 1.26s computation.

Scenario survival percentages are model-dependent fractions, not calibrated probabilities.

| Player | Pos | Immediate gain | Two-pick gain | Worst mode | Survives if passed | Flags |
|---|---|---:|---:|---:|---:|---|
| Josh Jacobs | RB | 10.1 | 17.2 | 15.6 | 0% | injury_review |
| Brenton Strange | TE | 7.9 | 14.8 | 14.4 | 62% |  |
| Alvin Kamara | RB | 7.5 | 14.5 | 13.0 | 50% | injury_review |
| Zach Charbonnet | RB | 7.4 | 14.5 | 12.9 | 0% | injury_review |
| Dylan Sampson | RB | 6.7 | 13.7 | 12.2 | 25% |  |
| Chris Rodriguez | RB | 4.4 | 11.4 | 10.0 | 0% | team_changed_since_history |
| Mike Washington | RB | 4.1 | 11.1 | 9.8 | 0% | no_recorded_nfl_history |
| Keaton Mitchell | RB | 3.4 | 10.6 | 9.2 | 25% | injury_review, team_changed_since_history |
| Jonah Coleman | RB | 0.0 | 7.6 | 7.0 | 0% | no_recorded_nfl_history |

Assumptions:

- Two-pick horizon; future own pick uses greedy marginal utility.
- Scenario fractions depend on uncalibrated opponent assumptions, not measured probabilities.
- Pass survival assumes selecting the best legal ECR alternative at this turn.
- Season scoring subtotals, virtual replacement starters and discounted bench utility are proxies.
- No opponent agent identity/strategy is inferred from mock bot behavior.
- News/injury/depth flags require review; no automatic weekly injury probability multiplier.
