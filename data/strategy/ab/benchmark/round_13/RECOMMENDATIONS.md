# Draft strategy recommendations

Draft simulation-ab-benchmark-13; observed through pick 180; targeting 181 then 184.
1 scenarios; 6 evaluated candidates; 0.01s computation.

Scenario survival percentages are model-dependent fractions, not calibrated probabilities.

Planning: ab; phase: A; horizon: [181, 184].

| Player | Pos | Immediate gain | Horizon gain | Downside | Survives if passed | Flags |
|---|---|---:|---:|---:|---:|---|
| Kansas City Chiefs | DEF | 0.0 | 0.0 | 0.0 | 100% |  |
| Eddy Pineiro | K | 0.0 | 0.0 | 0.0 | 57% |  |
| Tyler Loop | K | 0.0 | 0.0 | 0.0 | 71% |  |
| Green Bay Packers | DEF | 0.0 | 0.0 | 0.0 | 100% |  |
| Jake Bates | K | 0.0 | 0.0 | 0.0 | 57% |  |
| Evan McPherson | K | 0.0 | 0.0 | 0.0 | 100% |  |

Assumptions:

- A: maximin within bounded own choices and plausible short responses; discounted one-pick terminal approximation beyond B.
- B: long-gap scenarios followed by a constrained-maximin future A–B pair; mean blended with lower-tail average.
- Opponent plausibility uses near-best adjusted rank under at least one model, not optimal opponent season utility.
- Candidate/response widths bound search; this is not exhaustive minimax over every legal draft.
- A availability fractions count enumerated responses; B fractions count simulated paths. Neither is calibrated probability.
- Virtual starter references and bench values remain partial-projection proxies; injury/news flags require review.
- Before our turn, bounded prefix scenarios forecast preceding picks; recompute when actual picks arrive.
