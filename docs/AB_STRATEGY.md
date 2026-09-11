# A/B planning and bounded minimax

Implemented September 8, 2026. Active `strategy_policy.json` now sets
`planning_mode: "ab"`. Engine version 2 invalidates earlier controller calculations.
This is an offline application-layer change. It adds no API reads, relaxes no
source deadlines, and starts no mock or browser action.

For seat 13/14, A picks 13, 41, 69… precede B by two opponent selections. B picks
16, 44, 72… precede the next A by 24 opponent selections. The engine classifies
the phase from actual snake-order gaps rather than hardcoding a round or seat.
Seats with no distinct short pair retain the previous two-pick planner. The final
pick uses one-pick valuation, and terminal pairs omit unavailable future picks.

## A: select a pair across opponent scenarios

For each shortlisted first choice, enumerate the neighboring team's plausible
two-pick responses. After each response, choose the best remaining B choice.
Take the minimum of those best-response values and choose the first player with
the greatest minimum. The order is **our choice → opponent response → our reply**.
Our B choice is allowed to adapt after observing the opponent.

The score for one branch is:

`utility(roster + A + B) + 0.35 × estimated marginal gain at the next A`

The estimate simulates the long gap twice (ECR and needs with the current four-mode
policy) and uses a greedy next-A choice in each resulting pool. It is a terminal
approximation. It does not solve the entire remaining draft. At the final A–B pair,
the terminal term is omitted. A chooses the worst branch score. Ties use immediate
value, ECR and player ID. Response means remain descriptive, not the A objective.

## B: protect against depletion through the long gap

For each current B candidate, simulate the 24 selections until the next A using
the existing four opponent families, two seeded paths per family. At each future A,
solve a bounded maximin A–B pair with no additional terminal estimate.

The B score is `75% × mean path gain + 25% × mean of the lowest quarter of path gains`.
Each path gain already reflects its future pair's worst plausible short response.
The horizon is therefore 16 → 41 → 44, not just 16 → 41. This lower-quarter metric
replaces the old worst-family-average term for B. The old term remains in the
explicit two-pick planner. Neither is a calibrated probability model.

A and B use different truncations. A's projected B reply is an approximation of
the later B decision, not a commitment. Actual new picks trigger fresh calculation.

## Search limits and meaning of plausible

| Active setting | Value |
|---|---:|
| Current first-choice beam | 6 |
| Future A choices at B | 3 |
| B replies per short response | 3 |
| Opponent choices at each short step | At most 3 |
| Maximum raw two-step response paths | 9. Equivalent resulting rosters are deduplicated |
| Opponent rank slack | 8 adjusted ranking places |
| Before-turn prefix forecasts | 2 |
| A terminal long-gap samples | 2 |
| B long-gap samples | 8 |
| A terminal gain weight | 0.35 |
| B lower-tail fraction | 0.25 |

At each short step, merge near-best options under ECR, ADP, needs and RB-run
adjusted rankings. Keep options within eight adjusted places of the best under
at least one model, then cap to three by minimum rank regret/ECR/ID. Apply legal
slot coverage on every response. This is a constraint on plausible ranking-based
behavior, **not proof of optimal season utility for the opponent**. It does not
assume the opponent deliberately sacrifices its own roster to hurt ours.

Own candidate beams interleave marginal-value and consensus order from a bounded
pool of top projected-value and top-consensus players at each eligible position.
This can omit useful players. Maximin is exact only inside those finite beams
and response sets. It is not exhaustive game-theoretic optimization of the league.
All widths and weights are explicit, uncalibrated assumptions.

Before our turn, two simulated prefixes forecast the intervening picks and propose
surviving candidates. A takes the worst prefix/response score. B aggregates the
prefix/long-gap cases before computing its lower-tail blend. Missing first choices
use greedy fallbacks within those hypothetical prefixes. Fractions of survival
are provided for review, not as measured odds. A's pass fraction counts enumerated
responses after an ECR alternative.  B's counts simulated paths after that alternative.

## Runtime work

`Engine.opponent_options` pre-indexes rankings by position. Scenario and need adjustments are constant within a position. Thus, each position's leading eligible options suffice to reproduce the original global top-five ranking exactly.
Tests compare selected players against the original full-scan implementation with
the same random seeds. Availability sets make removals and membership checks cheap.

`ABPlanner` caches exact utility calculations and complete greedy rankings by our
owned roster for the lifetime of one recommendation. Different opponent paths
reuse the ranking but still filter against their own remaining player pool. No
cache survives into another board/policy/state calculation through this layer.

The bench formula has a known limitation: position-specific reserve references can
make utility non-monotonic when a player crosses a FLEX allocation boundary. A
proposed dominance-pruning shortcut was removed after a counterexample. Exhaustive
greedy continuations preserve the existing objective, including those discontinuities.
The deliberately bounded own-choice beams remain approximate.

## Commands and integration

```sh
# All local: fixed-state benchmarks and comparisons under matching opponent seeds.
python3 draft_ab_evaluate.py benchmark
python3 draft_ab_evaluate.py compare
python3 draft_ab_evaluate.py report

# Rebuild the static seat-13 opening plan with the active A/B policy; no API reads.
python3 draft_preplan.py build

# Offline tests.
python3 -m unittest discover -q
```

Open `data/strategy/ab/AB_REVIEW.md`, linked from the report command. Saved JSON
includes board hash, policy, engine version, exact draft states, decision timing,
full comparison rosters, and work counters. `comparison.json` uses ECR and QB-run
opponents with seeds 31001 and 31002 at seat 13 under the actual 14-round/one-FLEX
rules. Every resulting roster must satisfy required slots or evaluation fails.

The existing controller `--strategy-board` integration calls `Engine.recommend`,
which dispatches A/B automatically. Candidate identity, exact-state fingerprints,
engine-version/policy invalidation, expiration and actual browser queue checks are
unchanged. The displayed recommendation report now labels the phase and horizon.
New A/B rows use `horizon_mean_gain` and `downside_gain`, rather than falsely labeling
three-pick scores as two-pick outcomes. Full `worst_case` IDs and continuation counts
are available in the saved JSON.

To explicitly compare or revert the strategy, set `planning_mode` to `two_pick`
in a separate policy and pass `--policy` to analysis commands or `--strategy-policy`
to the controller. There is no silent runtime fallback on A/B computation failure.

## Measured checkpoint

Four complete paired comparisons with the previous planner: two improved, one tied,
one declined. Mean offensive starter subtotal difference was +1.3 points. Individual
differences were +10.5, -9.9, 0.0 and +4.8. All four exceeded the legal ECR baseline,
but these are synthetic outcomes scored with the same partial projections the
planner uses. This is weak evidence of quality gain, not proof of a winning edge.

The slowest of 56 A/B recommendations in those complete drafts was 0.415 seconds.
The optimized previous planner's maximum was 0.584 seconds. Same-state example A
calculations were about 0.34–0.37 seconds.  B examples about 0.19–0.21 seconds. Timings
exclude network/browser work and are observations, not deadlines or guarantees.

The benchmark additionally exercises planning before our turn and end-of-draft
truncation. The full suite passes 146 offline tests. Tests cover phase geometry, exact opponent-index equivalence, adaptive
replies/minimax aggregation, bounded legal responses, cached-greedy equivalence,
the FLEX/bench counterexample, tail use, B's future pair, invalid budgets,
reproducibility, state preservation and prior controller safeguards.
