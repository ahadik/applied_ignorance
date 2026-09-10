# Draft strategy recommendations

Draft simulation-assigned-seat-07_rb_run; observed through pick 12; targeting 13 then 16.
1 scenarios; 6 evaluated candidates; 0.31s computation.

Scenario survival percentages are model-dependent fractions, not calibrated probabilities.

Planning: ab; phase: A; horizon: [13, 16, 41].

| Player | Pos | Immediate gain | Horizon gain | Downside | Survives if passed | Flags |
|---|---|---:|---:|---:|---:|---|
| Jaxon Smith-Njigba | WR | 151.8 | 280.4 | 280.4 | 50% |  |
| Derrick Henry | RB | 107.0 | 255.8 | 231.2 | 100% |  |
| Trey McBride | TE | 102.5 | 253.6 | 231.2 | 100% |  |
| Rashee Rice | WR | 100.7 | 251.7 | 229.3 | 100% |  |
| Justin Jefferson | WR | 100.0 | 251.0 | 228.6 | 50% |  |
| A.J. Brown | WR | 91.8 | 242.9 | 220.5 | 50% | team_changed_since_history |

Assumptions:

- A: maximin within bounded own choices and plausible short responses; discounted one-pick terminal approximation beyond B.
- B: long-gap scenarios followed by a constrained-maximin future A–B pair; mean blended with lower-tail average.
- Opponent plausibility uses near-best adjusted rank under at least one model, not optimal opponent season utility.
- Candidate/response widths bound search; this is not exhaustive minimax over every legal draft.
- A availability fractions count enumerated responses; B fractions count simulated paths. Neither is calibrated probability.
- Virtual starter references and bench values remain partial-projection proxies; injury/news flags require review.
- Before our turn, bounded prefix scenarios forecast preceding picks; recompute when actual picks arrive.
