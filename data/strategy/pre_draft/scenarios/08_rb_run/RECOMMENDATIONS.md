# Draft strategy recommendations

Draft simulation-assigned-seat-08_rb_run; observed through pick 12; targeting 13 then 16.
1 scenarios; 6 evaluated candidates; 0.34s computation.

Scenario survival percentages are model-dependent fractions, not calibrated probabilities.

Planning: ab; phase: A; horizon: [13, 16, 41].

| Player | Pos | Immediate gain | Horizon gain | Downside | Survives if passed | Flags |
|---|---|---:|---:|---:|---:|---|
| De'Von Achane | RB | 127.6 | 258.4 | 256.3 | 43% |  |
| CeeDee Lamb | WR | 111.4 | 248.8 | 240.0 | 57% |  |
| Derrick Henry | RB | 107.0 | 245.7 | 231.2 | 100% |  |
| Trey McBride | TE | 102.5 | 241.9 | 231.2 | 100% |  |
| Drake London | WR | 98.6 | 237.9 | 227.3 | 57% |  |
| A.J. Brown | WR | 91.8 | 231.2 | 220.5 | 57% | team_changed_since_history |

Assumptions:

- A: maximin within bounded own choices and plausible short responses; discounted one-pick terminal approximation beyond B.
- B: long-gap scenarios followed by a constrained-maximin future A–B pair; mean blended with lower-tail average.
- Opponent plausibility uses near-best adjusted rank under at least one model, not optimal opponent season utility.
- Candidate/response widths bound search; this is not exhaustive minimax over every legal draft.
- A availability fractions count enumerated responses; B fractions count simulated paths. Neither is calibrated probability.
- Virtual starter references and bench values remain partial-projection proxies; injury/news flags require review.
- Before our turn, bounded prefix scenarios forecast preceding picks; recompute when actual picks arrive.
