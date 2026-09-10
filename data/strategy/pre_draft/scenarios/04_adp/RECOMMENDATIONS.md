# Draft strategy recommendations

Draft simulation-assigned-seat-04_adp; observed through pick 12; targeting 13 then 16.
1 scenarios; 6 evaluated candidates; 0.35s computation.

Scenario survival percentages are model-dependent fractions, not calibrated probabilities.

Planning: ab; phase: A; horizon: [13, 16, 41].

| Player | Pos | Immediate gain | Horizon gain | Downside | Survives if passed | Flags |
|---|---|---:|---:|---:|---:|---|
| CeeDee Lamb | WR | 111.4 | 240.0 | 240.0 | 57% |  |
| Derrick Henry | RB | 107.0 | 236.2 | 231.2 | 100% |  |
| Trey McBride | TE | 102.5 | 233.7 | 231.2 | 100% |  |
| Rashee Rice | WR | 100.7 | 231.8 | 229.3 | 100% |  |
| Drake London | WR | 98.6 | 229.7 | 227.3 | 57% |  |
| A.J. Brown | WR | 91.8 | 223.0 | 220.5 | 57% | team_changed_since_history |

Assumptions:

- A: maximin within bounded own choices and plausible short responses; discounted one-pick terminal approximation beyond B.
- B: long-gap scenarios followed by a constrained-maximin future A–B pair; mean blended with lower-tail average.
- Opponent plausibility uses near-best adjusted rank under at least one model, not optimal opponent season utility.
- Candidate/response widths bound search; this is not exhaustive minimax over every legal draft.
- A availability fractions count enumerated responses; B fractions count simulated paths. Neither is calibrated probability.
- Virtual starter references and bench values remain partial-projection proxies; injury/news flags require review.
- Before our turn, bounded prefix scenarios forecast preceding picks; recompute when actual picks arrive.
