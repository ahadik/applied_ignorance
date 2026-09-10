# Draft strategy recommendations

Draft simulation-ab-benchmark-6; observed through pick 71; targeting 72 then 97.
8 scenarios; 6 evaluated candidates; 0.21s computation.

Scenario survival percentages are model-dependent fractions, not calibrated probabilities.

Planning: ab; phase: B; horizon: [72, 97, 100].

| Player | Pos | Immediate gain | Horizon gain | Downside | Survives if passed | Flags |
|---|---|---:|---:|---:|---:|---|
| Sam LaPorta | TE | 34.7 | 73.5 | 71.9 | 0% | injury_review |
| George Kittle | TE | 34.2 | 73.1 | 71.5 | 0% | injury_review |
| Harold Fannin | TE | 31.5 | 70.4 | 68.7 | 0% |  |
| Travis Kelce | TE | 27.8 | 66.7 | 65.0 | 25% |  |
| Carnell Tate | WR | 12.3 | 57.3 | 48.5 | 0% | injury_review, no_recorded_nfl_history |
| Justin Herbert | QB | 5.9 | 53.2 | 45.2 | 0% |  |

Assumptions:

- A: maximin within bounded own choices and plausible short responses; discounted one-pick terminal approximation beyond B.
- B: long-gap scenarios followed by a constrained-maximin future A–B pair; mean blended with lower-tail average.
- Opponent plausibility uses near-best adjusted rank under at least one model, not optimal opponent season utility.
- Candidate/response widths bound search; this is not exhaustive minimax over every legal draft.
- A availability fractions count enumerated responses; B fractions count simulated paths. Neither is calibrated probability.
- Virtual starter references and bench values remain partial-projection proxies; injury/news flags require review.
- Before our turn, bounded prefix scenarios forecast preceding picks; recompute when actual picks arrive.
