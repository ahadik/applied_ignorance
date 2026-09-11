# Weekly lineup pipeline

Implemented September 9, 2026. Public reads and local recommendations only.
The first Week 1 live run validated all 14 owned identities/projections and
produced a recommendation. No lineup was submitted and no scheduler is running.

The pipeline also exports a structured `proposed_lineup.json`. Run the
[independent validator](LINEUP_VALIDATION.md) against that exact file before
execution. It returns PASS, FAIL, REVIEW or UNAVAILABLE from fresh provider inputs.
This is separate from read-back verification and does not trust inferred health
or legality flags in the proposal.

## Run it

From the project root:

```sh
python3 weekly_lineup.py run --season 2026 --week 1
```

Run this before the first relevant game and again whenever injuries, ownership,
or lineup choices change. It works before, during, and after games within the
current regular-season week. Supply the new week when the NFL week advances.
An explicitly wrong season/week is rejected. This is not a historical replay CLI.

The command collects through the central Sleeper, FantasyPros and nflverse
clients, validates data, scores players, solves the legal lineup and saves:

- `data/weekly/2026/1/LINEUP.md`: readable starters, changes, backups and deadlines.
- `latest_report.json`: complete scoring, injuries/news, identities, source
  provenance, acquisition counts, objective, input hash and alternatives.
- `snapshots/<id>/`: immutable per-run input files and checksummed manifest.
- `reports/<id>.json` and `.md`: durable recommendation history.
- `locks.json`: persistent lock observations for this league/week.
- `last_failure.json`: last failed operation, if any. Its timestamp distinguishes
  an old failure from subsequent success. Old reports are never relabeled fresh.

The script serializes same-week runs using a filesystem lock. Provider requests
retain the shared cache/budget directories. A second host is not coordinated.

```sh
# Offline recomputation of the latest validated snapshot. Still checks freshness.
python3 weekly_lineup.py recommend --season 2026 --week 1

# After browser changes: read back current starters and compare with the report.
python3 weekly_lineup.py verify --season 2026 --week 1

# Deliberately shorten projection cache age after material news, if necessary.
python3 weekly_lineup.py run --season 2026 --week 1 --projection-max-age 900
```

`run` always rechecks mutable league state. `recommend` does not refresh inputs
and rejects expired snapshots. Use `run` when returning later in the week.
`verify` saves a timestamped comparison, not an assertion that the original
recommendation is still best. Neither an unchanged starter list nor an API read
establishes native unlock status. All commands leave Sleeper account state alone.

## Data and scoring

`weekly_data.context` reads league rules, NFL state, user identity, rosters and
the selected week's matchup through `sleeper.get_sleeper`. It verifies ownership
and agreement between roster and matchup starters. Collection repeats context
after the other reads to catch ownership/rule changes during collection.

`fantasypros.get_fantasypros` supplies explicit weekly QB/RB/WR/TE/K/DST
projections, identity crosswalk, injuries and recent news. Preseason/ROS/wrong-week
payloads are rejected. Same-ID team conflicts and unresolved joins are quarantined.
A missing eligible owned valuation blocks optimization instead of becoming zero.
News is retained as evidence, not executable instructions or an automatic bonus.
The global 100-item news window is not guaranteed comprehensive. Unrelated team
injury/news effects require human review. This version does not infer workload
changes or calibrated injury probabilities.

`player_scoring.py` contains the shared deterministic joins/scoring previously
inside `draft_board.py`. Draft imports remain compatible. It applies actual league
coefficients to supported projected statistics and lists omitted nonzero rules.
Full projected point totals are not available for every scoring category.
Kicker subtotals exclude made-field-goal points because distance bands are absent.
Defense subtotals omit points-allowed bands and several touchdown/special-teams
events. These numbers must not be described as complete expected fantasy totals.
There is only one K and one DEF on our current roster, so no choice between
specialists is currently affected. Acquisitions require separate evaluation.

No preseason forecasts, draft utility scores or historical season averages are
used as weekly projections. Weekly forecasts supply the baseline matchup context.
We do not add arbitrary injury/matchup multipliers or treat rank spread as point
variance. Richer usage features and model calibration remain future work.

## Exact assignment and remaining freedom

`weekly_model.optimize` uses deterministic dynamic programming to enumerate legal
slot assignments over the owned roster. It first fills as many legal slots as
possible, then maximizes supported projected points. Thus it does not intentionally
leave an eligible slot empty solely to avoid a negative projection. Ties prefer
later kickoffs in flexible slots, then fewer changes, then stable ID order.

It supports positional slots, FLEX, SUPER_FLEX, REC_FLEX and WRRB_FLEX. It prevents
duplicate starters, honors multiple eligible positions, excludes known out/IR/
inactive/suspended players and byes, and preserves already locked starters in
their exact slots. Started bench players cannot be inserted even if bench drops
would be permitted. Off-roster starters stay fixed when their game is locked.
Automatic substitution leagues fail explicitly pending dedicated AutoSubs support.

Locks use current scheduled kickoff in UTC, any reported game score, and prior
saved lock/kickoff observations. If a previously observed kickoff passes and a
later feed moves it, the player remains conservatively locked. Missing or ambiguous
kickoff data blocks the run. This may sacrifice flexibility for unusual postponed
games. Native Sleeper verification is required, and no guessed unlock is allowed.
The schedule is not an authoritative live game-status or Sleeper lock endpoint.

The numerical objective only counts adjustable slots. Already-started points are
fixed and cannot change the comparison. The report retains the observed fantasy
matchup score separately. It does not add full-game projections to live scores.

The engine computes a full alternative lineup excluding each recommended unlocked
starter and reports the affected players and earliest required decision deadline.
These alternatives are conditional plans, not promises a substitute will remain
available. Re-run before using them. Multiple simultaneous injuries require a
fresh run. Individually computed alternatives are not composable.

Questionable/doubtful players remain in the projection comparison but are flagged
for review. No probability discount is applied without established projection
semantics. The numerical recommendation is retained as `review_required` and
`applied=false`. There is no automatic execution or hidden agent override.

## Freshness and operational procedure

At analysis time: final Sleeper reads and schedule metadata checks must be at
most five minutes old. Player status, injuries/news 15 minutes. Weekly projection
retrieval six hours. Player crosswalk 24 hours. Known projection publication times
must be within 24 hours. Absent publication time remains unknown. These are
initial safety policies, not a guarantee that an upstream source incorporated
every late report. Rerun with justified shorter cache ages after material news.

Before applying any report:

1. Run live collection close to execution. Inspect flags and confirm official
   availability when it matters. Check the earliest owned-player/backup kickoff.
2. Verify native Sleeper game locks and starters. Stale or differing state means
   rerun, not proceeding from a prior screen.
3. Apply authorized changes sequentially in the browser, checking each result.
4. Run `verify` to reconcile the full starting lineup. Fix discrepancies only
   while legal. Recommendations never imply submission.

Run before each relevant game window and after significant news. Suggested checks
are about 90 and 30 minutes before kickoff, leaving time for browser changes.
There is no notification delivery, watcher, cloud service or mobile MCP dependency.
If retrieval fails, preserve the current lineup and inspect the explicit failure.
The prior report retains its original timestamps and must not be assumed current.

## Schedule provider extension

`get_nflverse('schedules', season)` reads the documented `nfldata/data/games.csv`.
GitHub Contents metadata establishes the current blob SHA and size. The download
must match both Git blob SHA-1 and saved SHA-256. Every call checks metadata and
unchanged file bytes are reused. Requests share existing nflverse quotas,
cooldowns, retries and process locking. Publication time is explicitly unknown.
The full file contains multiple seasons. The provider selects exactly the requested
season and the weekly adapter validates the modern 272-game/32-team/17-game season.
This adapter is intentionally limited to that regular-season format.

The supported general command is
`python3 nflverse_collect.py collect --dataset schedules --season 2026`.
Schedules have no release-asset catalog. `--revalidate` is already implicit.
`--refresh` forces a full download and should not be routine.

Primary references checked September 9, 2026:

- https://nflreadr.nflverse.com/reference/load_schedules.html
- https://github.com/nflverse/nfldata/tree/master/data
- https://raw.githubusercontent.com/nflverse/nflreadr/main/data-raw/dictionary_schedules.csv

The dictionary explicitly defines kickoff in Eastern time. Use America/New_York
to handle daylight saving rather than a fixed UTC offset. Schedule weather/odds
columns are not promoted into live weather/market signals by this implementation.

## Validation

September 9 checkpoint: all 182 project tests passed. The final live run at 04:44 UTC used 11 Sleeper network attempts. It used nine FantasyPros cache hits with zero new FP requests. It used one nflverse metadata request with cached schedule bytes. The
04:45 UTC read-back verification correctly reported `matches=false`. Mahomes remained the actual QB. Purdy remained the recommended QB. The observed league/roster state still matched the state at analysis time. No recommendation was submitted.

Run `python3 -m unittest discover -v`. Tests use simulated providers and temporary
storage. They cover:

- Original draft-scoring compatibility.
- Agreement with the brute-force optimizer.
- Multi-position/FLEX legality.
- Fixed/off-roster starters.
- Exclusion of bench players whose games started.
- Injuries.
- Byes.
- Stale/wrong-week data.
- Identities.
- Schedule completeness.
- Time zones.
- Conservative treatment of postponed kickoffs.
- Provenance/revision reuse.
- Tampering.

Live diagnostics are separate from test discovery. Predictions and tests do not
establish a measured winning edge or calibrated win probability.
