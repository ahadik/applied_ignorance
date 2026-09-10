# Draft strategy recommendations

Draft simulation-ab-benchmark-5; observed through pick 68; targeting 69 then 72.
1 scenarios; 6 evaluated candidates; 0.37s computation.

Scenario survival percentages are model-dependent fractions, not calibrated probabilities.

Planning: ab; phase: A; horizon: [69, 72, 97].

| Player | Pos | Immediate gain | Horizon gain | Downside | Survives if passed | Flags |
|---|---|---:|---:|---:|---:|---|
| Sam LaPorta | TE | 34.7 | 64.9 | 64.9 | 100% | injury_review |
| TreVeyon Henderson | RB | 23.8 | 64.5 | 64.5 | 43% | injury_review |
| George Kittle | TE | 34.2 | 64.4 | 64.4 | 100% | injury_review |
| Rome Odunze | WR | 19.2 | 62.0 | 62.0 | 50% | injury_review |
| Harold Fannin | TE | 31.5 | 61.7 | 61.7 | 71% |  |
| Carnell Tate | WR | 3.7 | 47.6 | 47.6 | 57% | injury_review, no_recorded_nfl_history |

Assumptions:

- A: maximin within bounded own choices and plausible short responses; discounted one-pick terminal approximation beyond B.
- B: long-gap scenarios followed by a constrained-maximin future A–B pair; mean blended with lower-tail average.
- Opponent plausibility uses near-best adjusted rank under at least one model, not optimal opponent season utility.
- Candidate/response widths bound search; this is not exhaustive minimax over every legal draft.
- A availability fractions count enumerated responses; B fractions count simulated paths. Neither is calibrated probability.
- Virtual starter references and bench values remain partial-projection proxies; injury/news flags require review.
- Before our turn, bounded prefix scenarios forecast preceding picks; recompute when actual picks arrive.
