# Milestone 3: draft strategy and decision engine

The active strategy now distinguishes A and B turns; see [AB_STRATEGY.md](AB_STRATEGY.md).
The original two-pick method described below remains an explicit comparison option.

Later assigned-order update: seat 13 of 14, with 14 rounds and one FLEX.
See [PRE_DRAFT_PLAN.md](PRE_DRAFT_PLAN.md). The initial six-pair evaluation below
used the previous 15-round/two-FLEX configuration and remains historical evidence.

Implemented September 8, 2026. The reusable system now turns the milestone 2
board and an observed draft state into roster-specific recommendations, two-pick
scenario comparisons, and ordered fallback candidates. Evaluation is offline;
the third browser mock and operational source refresh remain separate checkpoints.

## Review checkpoint

Open `data/strategy/milestone3/MILESTONE_3.md`. It links worked examples and reports
six paired complete synthetic drafts against highest legal expert-consensus rank
(ECR), using seats 1, 7 and 14, external seed 31001, and ECR/QB-run opponents.
The QB-run rule is outside the planner's default scenario mix. All twelve rosters
filled the required slots. Both policies use the same eligibility rules.

The first evaluation improved the supported offensive starter subtotal in all six
pairs: mean +92.4, range +1.2 to +270.2. This is a favorable model-based comparison,
because evaluation uses the same partial season projections as the planner.
It is **not evidence of six league wins, a calibrated win probability, or a proven
advantage against other agents**. The report includes arbitrary projection/injury
stress draws, timing, original seed, complete rosters and limitations. Re-run with
additional seeds using the saved command; do not tune to these six results.

## Selected strategy

We do not begin with a fixed desired lineup or a fixed round-by-round position
list. Maximize the useful offensive value of the roster, account for what might
disappear before the next selection, and preserve room for every required slot.

1. Allocate owned players to QB/RB/WR/TE and FLEX without double counting. Use
   milestone 2 positional reference players as virtual replacements while the
   roster is incomplete. Calculate each candidate's change in this roster value.
2. Add a discounted value for reserves. This makes additional RB/WR depth useful
   while reducing the appeal of repeatedly buying players at a filled position.
3. Simulate opponents through our next two selections. Compare each shortlisted
   first choice followed by the best marginal-value second choice. Prefer value
   that holds up across several opponent assumptions.
4. Leave K/DEF until the last two rounds unless required-slot constraints force
   them sooner. Use consensus order for specialists; their incomplete projection
   subtotals cannot support fair comparisons with offense.
5. Preserve injury, news, depth, historical workload and bye evidence for strategic
   review. Do not translate one week's injury probability into a full-season
   haircut or fit a forecast from a few historical seasons. An adjustment must be
   an explicit, reasoned policy override. Missing rookie history is not zero talent.

The virtual replacements are fixed reference assumptions, not simulated waiver
availability. They can remain in planning utility even when an owned starter is
below that reference. Final evaluation removes virtual players and uses the best
actual offensive starting lineup. This model does not optimize weekly substitutions,
correlations, schedules, waiver replacement, playoff performance or championship
probability. Bye conflicts are displayed; they are not an automatic draft penalty.

## Explicit policy and opponent assumptions

`strategy_policy.json` is the active policy, including its deterministic seed.

| Setting | Default | Meaning |
|---|---:|---|
| Scenario families | ECR, ADP, needs, RB run | Several plausible selection rules; no claim to know the other agents |
| Samples per family | 2 | Eight scenarios; availability fractions are coarse and uncalibrated |
| Shortlist | Top 5 ECR plus top 5 marginal value | Up to ten distinct candidates get lookahead; others are marginal-value fallbacks |
| Robust blend | 75% overall mean + 25% worst family mean | Penalizes dependence on a favorable opponent assumption |
| Bench weight | 0.18 | Discount on reserve points above a deeper positional reference |
| Bench decay | 0.6 | Each further reserve at that position gets less weight |
| Deep reference | Index 2 × teams at QB/TE; 5 × teams at RB/WR | First player beyond that count in descending modeled points, or last available |
| Backup QB/TE | Round 10 onward | Earlier permitted when needed for required slots/FLEX |
| Position caps | QB 2, RB 8, WR 8, TE 2, K 1, DEF 1 | Guardrails, not a prescribed roster |

Opponents draw from their five best adjusted ranks with exponential weighting
(temperature 5). ADP scenarios use ordinal ADP rank, otherwise ECR. Needs scenarios
subtract 8 ranks for a player who fills a vacancy and add 30 otherwise. RB/QB run
scenarios additionally subtract 15/20 for that position. These constants are
inspectable hypotheses, not learned behavior. All opponents preserve mandatory
slot feasibility. The ECR baseline shares our caps, exclusions and late-specialist
rules; it is not deliberately handicapped with invalid roster construction.

The reported “survival if passed” fraction asks: **if we choose the best legal ECR
alternative now, how often does this player survive until our following pick?**
It is conditional on availability at our first pick. When planning before our
turn, a separate fraction records survival to that turn; a missing target uses a
greedy fallback in that scenario. At the final pick there is no following-pick
availability estimate. Expert rank dispersion is never treated as point variance.

For an override, use the verified Sleeper player ID under `overrides`, with a
nonempty `reason` and `exclude: true` or a `multiplier` between 0 and 1.5.
Unknown IDs, malformed policy and caps below required slots fail. The generated
`examples/injury_sensitivity/policy.json` is hypothetical and **not active**.

## Reusable commands and effects

All commands below except controller `sync`/`watch` read local files only. They
never fetch FantasyPros/nflverse data, open a browser, alter Sleeper's queue, or
submit a selection. Reports under ignored `data/strategy/` remain private.

```sh
# Offline examples, including two saved mock first-round replays with later data.
python3 draft_strategy_evaluate.py examples

# Offline paired drafts; original seed differs from the planner seed.
python3 draft_strategy_evaluate.py evaluate --seats 1 7 14 --modes ecr qb_run --seeds 31001

# Offline: verify saved board/policy provenance and assemble the review report.
python3 draft_strategy_evaluate.py report

# Offline single-state calculation; saved review data may be old, so no API claims.
python3 draft_strategy.py --state data/strategy/milestone3/examples/mid_draft/state.json --output data/strategy/review

# Offline tests with synthetic fixtures/temp directories; zero provider calls.
python3 -m unittest discover -q
```

`draft_strategy.py` supports `--board`, `--policy`, and `--export`. Review output
includes JSON, Markdown, original board hash, exact state fingerprint, seed,
policy, shortlist, fallback order, per-scenario-family means, coverage needs and
timing. Export additionally requires fresh inputs, fresh real state, matching
league/draft, and validated roster settings. Rebuilding old data never resets its
deadlines. Replay outputs are explicitly synthetic and cannot be operationally
exported by changing only a draft ID.

For a separately authorized live session, after refreshing/rebuilding milestone 2
inputs and verifying the room/seat:

```sh
python3 controller.py sync --draft VERIFIED_DRAFT_ID --strategy-board data/draft_board/2026/board.json
python3 controller.py watch --draft VERIFIED_DRAFT_ID --strategy-board data/draft_board/2026/board.json
```

These commands make up to three uncached Sleeper reads per refresh through
`draft_data.read_live_draft` → `sleeper.get_sleeper`, with live retries disabled.
Then they calculate locally and save `strategy_result.json` and `candidates.json`
in the per-draft directory. The watcher sleeps five seconds after each cycle;
network and computation add to that interval. Repeated unchanged draft state,
board hash, engine version and policy reuse the calculation. Every cycle still
checks source expiry and the 20-second real-state deadline.

Use `--allow-mock` only for an explicitly verified league-less mock whose roster
format matches, after confirming that the league board's scoring assumptions are
appropriate. It explicitly binds the exported candidate file to that mock ID.
It cannot override a different real league, stale data or a synthetic replay.
This option configures the controller; it does not create or start a mock.

## Timed operation and recovery

- Follow `DRAFT_RUNBOOK.md` and `CONTROLLER.md`; after compaction reload them and
  the per-draft checkpoint. The process can compute while chat pauses if the
  computer/process keeps running. The first evaluation's slowest calculation was
  2.1 seconds, excluding provider/browser latency; this is not a time guarantee.
- Every observed selection invalidates old strategy candidates. The watcher
  recomputes before reporting readiness. `rank` refuses a different state
  fingerprint rather than merely deleting selected names from an old ranking.
- The native queue still requires actual supervised browser maintenance. Apply
  acceptable alternatives between turns, verify the displayed order, and save an
  actual UI observation. Generated fallback candidates are never called applied.
- `prepare` still requires fresh API/UI agreement, ongoing auto-pick off, an
  acceptable queued candidate and no pending selection. Reconcile before retrying
  any uncertain click. A source or computation failure blocks preparation.
- Source refresh is not automatic in milestone 3. The earliest source deadline
  often comes from 15-minute alerts. Use the saved collection/alert refresh and
  board-build commands before expiry as described in milestone 2; the watcher
  must not bypass this failure or consume provider calls itself to repair it.
- Unknown selected IDs, unassigned seats, traded picks, reversal, unsupported
  additional roster slots or ownership disagreement stop the engine. Repair
  verified inputs through the existing pipeline; do not guess identity/ownership.

## Acceptance evidence

125 offline tests passed, including 24 new strategy/handoff tests: numeric
marginal value, FLEX/bench accounting, late mandatory slots, reproducibility,
conditional availability at the snake turn, legal full drafts, explicit overrides,
all-team roster ownership, changed-state invalidation, source expiry, policy cache
invalidation, mock binding, unsupported formats and completed-roster handling.
No provider calls or Sleeper actions were made for milestone 3.

The code and offline evaluation checkpoint are complete. The next operational
checkpoint is the separately authorized integrated mock, including native queue
maintenance, `prepare`/click/reconcile and compaction recovery with this engine.
Refresh sources and review flagged candidates before the real draft.
