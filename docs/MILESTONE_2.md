# Milestone 2: integrated draft evidence

Implemented September 8, 2026. This milestone collects complete positional feeds,
joins provider identities, validates scope/coverage, calculates supported scoring
and starter value, and produces a reviewable draft board. It does not start the
third mock or implement a fully optimized live draft strategy.

Subsequent milestone 3 adds roster-specific two-pick scenario planning and
controller integration. See [MILESTONE_3.md](MILESTONE_3.md). Descriptions below
of the ECR baseline and next strategy checkpoint describe milestone 2's scope.

## Review checkpoint

Open `data/draft_board/2026/MILESTONE_2.md` for the current readable board.
`board.json` contains all players, source timestamps, ID evidence, original
projection statistics, individual scoring contributions, gaps, injury/news records,
historical workloads and depth roles. Both remain private and ignored by Git.

Initial validated coverage:

| Measure | Result |
|---|---:|
| Joined candidates | 808 |
| Consensus top 210 matched to Sleeper | 210 / 210 |
| Consensus top 210 with projections | 210 / 210 |
| Non-defense top 210 with nflverse history or depth | 198 / 198 |
| Projection records returned | 621 |
| Projection records matched safely | 618 |
| Quarantined identities in the entire pool | 12 |
| Quarantined identities within ECR/ADP top 210 | 0 |

The three unmatched projected players and other unresolved identities remain in
the report; none enters recommendations through a guessed name match. Fifteen
top-range players have no recorded prior NFL production, but do have matched
identity/depth evidence. That is an explicit missing-history condition, not zero
ability. Injury and roster-status flags require strategic review.

## Reusable commands

Run from the project root:

```sh
# Network through central clients: league, Sleeper identities/state, FP feeds.
# Reuses valid FantasyPros cache; resets the collection manifest to incomplete
# until every required read succeeds. Also publishes the fresh league context.
python3 draft_inputs.py collect --season 2026

# Explicit pre-draft refresh of FantasyPros, still under its shared budget.
python3 draft_inputs.py collect --season 2026 --refresh

# Targeted alert refresh: one Sleeper state read plus two cache-first FP reads.
python3 draft_inputs.py refresh-alerts --season 2026

# Offline: checksums, joins, scoring, history rebuild, coverage and report.
python3 draft_board.py build --season 2026
python3 draft_board.py summary --season 2026
python3 draft_board.py player --season 2026 --player 'Jahmyr Gibbs'
python3 draft_board.py issues --season 2026

# Offline review artifact only; no browser, queue, pick or watcher action.
python3 draft_board.py export --season 2026 --output data/draft_board/2026/candidates.review.json
```

Use `--as-of TIMEZONE_AWARE_ISO` on `build` for repeatable analytical time. It must
be at or after the inputs' fetch/publication times. The board records hashes of
both collection manifests; snapshot hashes are checked before calculations.
Rebuilding does not make old inputs fresh. `summary` reports readiness **at build
time**; export independently checks ages at the moment it is invoked.

`draft_inputs.py inspect --season 2026` prints limited samples and metadata for
schema review; no network calls. `enrich-ids` refreshes only the documented ESPN/MFL
directory request, principally for upgrading an older collection. Normal `collect`
now includes it. `publish-context` publishes a complete saved collection's league
context to `data/snapshot.json` and `DRAFT_CONTEXT.md` without re-fetching it.

## Data and identity contract

Sleeper is authoritative for league rules, roster eligibility and draft identity.
The collector performs five league/context reads, one full player-directory read
and one NFL-state read through `sleeper.get_sleeper`. FantasyPros collection uses
`fantasypros.get_fantasypros` for the player directory including external IDs,
draft consensus, ADP, QB/RB/WR/TE/K/DST preseason projections, latest 100 requested
news items and the verified current injury week. Eleven distinct FP requests are
possible on an uncached baseline, with bounded retries managed centrally.
The initial collection kept the earlier plain-directory snapshot as additional
provenance; subsequent collection requests only the enriched directory, avoiding
a redundant lookup.

The initial run used seven new FP calls and four cached responses; one subsequent
external-ID request made eight new FP calls in total. The first sandboxed attempt
failed before collecting context; rerunning the saved collector with network
permission succeeded. No fallback data was substituted after the failure.

Player IDs remain strings. Match FantasyPros Sportradar UUIDs to Sleeper's
`sportradar_id`, cross-check available ESPN/Yahoo IDs, and require agreement and
position eligibility. Team defenses use explicit team codes and Sleeper DEF
records. Multiple matching candidates or conflicting IDs are quarantined.
Projection MFL IDs are checked against the external-ID directory when both exist.
Match nflverse through GSIS/ESPN; conflicting historical IDs leave history detached.
Names are for display and review only.

The documented DynastyProcess fantasy crosswalk was not needed: FantasyPros'
documented `external_ids=espn:mfl` supplied the additional bridge. We did not add
another downloader or spend GitHub calls for this integration. The account approval
and observed `tier=premium` are preserved separately from the ambiguous
`public_api_limited=true` metadata; that flag's meaning is not documented here.
Record counts and top-range coverage are measured, not inferred from that flag.

Official contracts: [FantasyPros OpenAPI](https://api.fantasypros.com/public/v2/docs/fantasypros_v2_public.yml),
[Sleeper reference](https://docs.sleeper.com/). nflverse field and schedule references
are in [NFLVERSE_RESEARCH.md](NFLVERSE_RESEARCH.md).

## Scoring: what the numbers mean

`scoring.supported_points` is the sum of projected components with reviewed
field mappings and the league's coefficients. It is deliberately **not an exact
total** when `uncovered_rules` is nonempty. The original STD/PPR totals remain
alongside it. No unknown event is silently filled with zero.

- Offense: passing/rushing/receiving yards, touchdowns, interceptions and receptions
  are mapped when present. Our league's passing interception penalty is -1, and
  that actual coefficient is used. The PPR-minus-STD difference is checked against
  receptions within a 0.1-point rounding tolerance.
- Fumbles: the API field `fumbles` does not establish fumbles lost. It is retained
  but not assigned to `fum_lost`. Two-point and return/special-team events likewise
  remain uncovered where their mapping is not established. Position feeds omit
  some atypical activities, such as quarterback receptions and tight-end rushing.
- Kicker: extra points and misses derived from attempts minus makes can be shown.
  Field-goal distance bands and missed extra points are not provided adequately for
  the league's full scoring. No distance distribution is invented.
- Defense: supported sacks, interceptions, recoveries, forced fumbles and safeties
  can be shown. The returned points-allowed buckets are all zero in this collection;
  they are not interpreted as a forecast of no points allowed. Other touchdown,
  blocked-kick and special-team components remain uncovered.

`exact_league_total` and `core_fields_complete` are distinct. A complete set of
ordinary positional fields is sufficient for a **partial** starter-value comparison,
not proof that all scoring rules are covered. K/DEF do not participate in that
cross-position value calculation. Unsupported nonzero league scoring settings
outside the reviewed rule set stop the builder for a mapping review.

## Starter value and ranking

The league has 14 teams, one QB, two RBs, two WRs, one TE and two FLEX starters per
team. The model first allocates required positions across the league. It then fills
the 28 FLEX slots from the remaining RB/WR/TE supported subtotals, without reusing
a player. The next player at each offensive position establishes its reference.
Value is the player's subtotal minus that reference subtotal.

This is a deterministic positional-scarcity comparison. It omits bench demand,
streaming, bye-week substitution, weekly covariance and opponent strategy. It does
not estimate a player's probability of being available at the next pick. ADP
ordinal/average ranks and expert rank dispersion remain evidence, not calibrated
probabilities. Injury probabilities are displayed without mechanically multiplying
them into season projections.

The review board and initial candidate export use **ECR order**. Calculated value,
ADP, depth and historical workload remain separate inputs for the next strategy
decision. We have not hidden arbitrary blend weights inside an “optimal” score.
The controller still filters drafted/excluded players and protects required slots;
it does not yet recompute a roster-specific value model after each selection.

## Freshness and controller handoff

Maximum age since retrieval: league context 1 hour; news/injuries 15 minutes;
projections/ECR/ADP/NFL state 6 hours; identity directories 24 hours. These are
application review deadlines, not caching extensions or assertions about provider
publication frequency. Publication timestamps remain unknown when absent. The
nflverse builder rechecks current role age against a 36-hour threshold.

The candidate file carries its original ECR observation timestamp and an
`expires_at` equal to the earliest input deadline. Both export and controller
ranking enforce expiry. New code cannot turn an old board into fresh candidates
merely by writing a new file. A stale board remains readable for review, but must
be refreshed before exporting operational candidates.

An exported file is **not applied** to the controller or native Sleeper queue.
Actual operation still requires the separate runbook, fresh live draft state,
browser agreement, seat assignment and queue verification. No third mock has run.

## Validation and next checkpoint

101 offline project tests passed after implementation, including numeric
scoring examples, missing stats, invalid numbers, explicit ID conflicts, position
checks, MFL conflicts, bad injury probabilities, season/week/ROS validation,
duplicate/count mismatches, partial collections, checksum failures, FLEX allocation,
stale exports, controller expiry and drafted-player removal. Tests use synthetic
responses and temporary files; they consume no provider calls.

The final review refresh made two additional FantasyPros alert calls after their
15-minute freshness deadline, plus one Sleeper NFL-state check. Milestone 2's total
FantasyPros acquisition was ten new calls, including that final refresh. Older
projection and identity snapshots retained their original timestamps.

Milestone 2's data integration and scoring-coverage checkpoint is complete. Exact
full-league projections remain unavailable from these fields; this is a documented
source limitation rather than an unimplemented silent assumption. Next review:
choose a draft strategy and the treatment of flagged players, then test it in the
separately authorized integrated mock. Refresh the inputs near the actual draft.
