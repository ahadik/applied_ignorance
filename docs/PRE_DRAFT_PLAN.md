# Static assigned-order preparation

The active policy now uses distinct A/B planning; see [AB_STRATEGY.md](AB_STRATEGY.md).
`draft_preplan.py build` uses that policy automatically when regenerating the opening branches.

Latest verified observation: September 8, 2026, 22:02:44 UTC. League
1400628784381612032; draft 1400628785413394432; ahadik is **seat 13 of 14**.
The current rules are **14 rounds and one FLEX**, with five bench slots, a
120-second timer and PPR scoring. These supersede the earlier 15-round/two-FLEX
mock configuration. Sleeper lists 9:05 p.m. America/New_York; prepare by the user's
9 p.m. target. These are saved observations, not immutable league settings.

Our picks: **13, 16, 41, 44, 69, 72, 97, 100, 125, 128, 153, 156, 181, 184**.
Waiting intervals alternate between two and 24 other selections. Team 14 takes
both intervening selections at the short turn, making its roster needs relevant
to whether an alternative can wait. The long gap warrants stronger attention to
positional scarcity. There is no fixed desired roster or guaranteed player choice.

Open `data/strategy/pre_draft/PRE_DRAFT_PLAN.md` for the full member order, pick
schedule and eight illustrative opening branches. `plan.json` records context and
board content hashes, the policy, original observation times, expired input names
and each hypothetical prefix. `mock_profile.json` saves seat/format/roster/scoring
settings for the next mock; it does not apply settings to Sleeper.

The member-to-seat order contains 13 owners. The complete slot-to-roster mapping
establishes all 14 seats; seat 11 maps to unclaimed roster 14. This is represented
explicitly, not filled with an invented owner or removed from the draft. The code
cross-checks known member seats against roster owners and rejects conflicts,
duplicate/missing slots, unknown members and unsupported traded/reversed drafts.
No member's username is used to infer their agent strategy.

## Reusable workflow

```sh
# Seven logical reads through draft_data -> sleeper.get_sleeper.
# Only the user profile can be cached; provider retry/cooldown policies apply.
python3 draft_preplan.py sync

# Offline inspection of the last returned observation if validation failed.
python3 draft_preplan.py inspect

# Offline revalidation after a supported schema-handling fix; original time kept.
python3 draft_preplan.py accept

# Offline import of newer same-league context. Other source files/times stay intact.
python3 draft_inputs.py adopt-context --season 2026 --context data/strategy/pre_draft/context.json

# Offline league-specific scoring/reference rebuild, then seat-specific planning.
python3 draft_board.py build --season 2026
python3 draft_preplan.py build
python3 draft_preplan.py summary

# Optional offline complete draft checks for the verified seat and current board.
python3 draft_strategy_evaluate.py evaluate --seats 13 --seeds 31001 --modes ecr qb_run --output data/strategy/pre_draft/evaluation
```

`sync` saves `last_observation.json` for diagnostics, but replaces accepted
`context.json` only after the order passes validation. `accept` is not a bypass:
it repeats those same checks without a new provider read. Provider acquisition
failure leaves prior accepted context intact. The shared client owns network
attempts, caching, rate limits and cooldowns; seven logical reads does not imply
seven network attempts when profiles are cached or retries occur.

`adopt-context` validates league/draft/season and observation chronology, writes an
immutable context file, then atomically updates the input manifest. A change to
reception scoring requires corresponding new ECR/ADP feeds and is rejected by
this shortcut. Other scoring and roster changes are applied by the normal board
builder. It also updates `data/snapshot.json` and `DRAFT_CONTEXT.md`.

No FantasyPros or nflverse API calls were needed for this order update. Player
data retain their original timestamps; news/injuries were expired at this static
review. All artifacts are for review. Refresh inputs before live/mock operational
exports, verify assigned order and rules again, and maintain the actual native
queue through the supervised browser workflow. No browser mock was started.

The earlier milestone 3 six-pair performance checkpoint used the former roster
format. It is historical evidence, not performance validation of the new format.
New seat-13 checks are saved separately under `data/strategy/pre_draft/evaluation`.
Their synthetic scores are still not calibrated win probabilities.
