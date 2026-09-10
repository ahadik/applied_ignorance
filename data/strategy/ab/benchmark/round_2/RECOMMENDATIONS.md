# Draft strategy recommendations

Draft simulation-ab-benchmark-2; observed through pick 15; targeting 16 then 41.
8 scenarios; 6 evaluated candidates; 0.19s computation.

Scenario survival percentages are model-dependent fractions, not calibrated probabilities.

Planning: ab; phase: B; horizon: [16, 41, 44].

| Player | Pos | Immediate gain | Horizon gain | Downside | Survives if passed | Flags |
|---|---|---:|---:|---:|---:|---|
| De'Von Achane | RB | 127.6 | 250.2 | 239.0 | 0% |  |
| Chase Brown | RB | 113.0 | 235.6 | 224.4 | 0% |  |
| Derrick Henry | RB | 107.0 | 231.4 | 218.4 | 0% |  |
| Trey McBride | TE | 102.5 | 224.7 | 212.7 | 0% |  |
| Chris Olave | WR | 87.2 | 207.5 | 190.5 | 0% |  |
| George Pickens | WR | 78.8 | 199.0 | 182.1 | 0% |  |

Assumptions:

- A: maximin within bounded own choices and plausible short responses; discounted one-pick terminal approximation beyond B.
- B: long-gap scenarios followed by a constrained-maximin future A–B pair; mean blended with lower-tail average.
- Opponent plausibility uses near-best adjusted rank under at least one model, not optimal opponent season utility.
- Candidate/response widths bound search; this is not exhaustive minimax over every legal draft.
- A availability fractions count enumerated responses; B fractions count simulated paths. Neither is calibrated probability.
- Virtual starter references and bench values remain partial-projection proxies; injury/news flags require review.
- Before our turn, bounded prefix scenarios forecast preceding picks; recompute when actual picks arrive.
