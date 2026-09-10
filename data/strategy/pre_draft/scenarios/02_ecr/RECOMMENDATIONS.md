# Draft strategy recommendations

Draft simulation-assigned-seat-02_ecr; observed through pick 12; targeting 13 then 16.
1 scenarios; 6 evaluated candidates; 0.32s computation.

Scenario survival percentages are model-dependent fractions, not calibrated probabilities.

Planning: ab; phase: A; horizon: [13, 16, 41].

| Player | Pos | Immediate gain | Horizon gain | Downside | Survives if passed | Flags |
|---|---|---:|---:|---:|---:|---|
| De'Von Achane | RB | 127.6 | 260.7 | 256.3 | 50% |  |
| Chase Brown | RB | 113.0 | 253.4 | 241.7 | 50% |  |
| CeeDee Lamb | WR | 111.4 | 252.3 | 240.0 | 50% |  |
| Derrick Henry | RB | 107.0 | 251.1 | 240.0 | 100% |  |
| James Cook | RB | 100.4 | 242.0 | 233.3 | 50% |  |
| Chris Olave | WR | 87.2 | 228.9 | 220.2 | 50% |  |

Assumptions:

- A: maximin within bounded own choices and plausible short responses; discounted one-pick terminal approximation beyond B.
- B: long-gap scenarios followed by a constrained-maximin future A–B pair; mean blended with lower-tail average.
- Opponent plausibility uses near-best adjusted rank under at least one model, not optimal opponent season utility.
- Candidate/response widths bound search; this is not exhaustive minimax over every legal draft.
- A availability fractions count enumerated responses; B fractions count simulated paths. Neither is calibrated probability.
- Virtual starter references and bench values remain partial-projection proxies; injury/news flags require review.
- Before our turn, bounded prefix scenarios forecast preceding picks; recompute when actual picks arrive.
