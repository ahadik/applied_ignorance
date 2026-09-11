# M2: Deterministic deadline planning

## Scope

`automation_deadlines.py` collects deadline evidence through the shared Sleeper and nflverse clients.
`automation_plan.py` converts saved observations into an immutable desired plan.
The planner does not call providers or change the scheduler, automation mode or lineup.
M3 will compare desired checks with verified scheduler observations.

The planner includes all owned players as conservative alternatives, including bench players with earlier games.
It does not rank those alternatives or recommend substitutions.
It validates regular-season fixture coverage before treating an absent game as a bye.
Unknown teams, unknown kickoffs, changed ownership and incomplete inputs produce blockers.
The collector supports the explicitly selected current regular-season week, from 1 through 18.
Plans can include later weeks within the horizon.

## Collect deadline observations

Run from the project root:

```sh
python3 automation.py collect-deadlines --season 2026 --week 1
```

Use the actual current season and week.
The command reads `config.json` unless `--config PATH` selects another file.
The configuration requires `league_id` and `username`.

Collection performs these operations:

1. Read the league, NFL state, user, rosters and player directory through `sleeper.get_sleeper`.
2. Read season fixtures through `nflverse.get_nflverse('schedules', season)`.
3. Read the league and rosters again to detect changes during collection.
4. Save raw inputs and normalized observations under `data/automation/observations/`.

Normal success requires seven logical Sleeper reads and one nflverse call.
Sleeper uses `retries=0`. Only the exact user profile can use its normal short cache.
nflverse verifies schedule metadata and reuses unchanged assets under its existing cache and quota policies.
Its logical call can perform multiple network attempts.
The command does not request FantasyPros projections, injury reports or news.

The output records actual cache hits and network attempts per operation when available.
An unavailable attempt count stays null.
Collection stops after a provider failure and saves partial evidence with a controlled error category.
Failed or incomplete collection is evidence, not verified coverage.
No command clears provider budgets or cooldowns.

Each successful input is immutable. The normalized observation records source paths and checksums.
It preserves retrieval times, metadata-check times and available publication times separately.
An unknown publication time remains null.
The plan command rejects changed or missing source files.

## Supply verified waiver and review timing

The owner already confirmed rolling waivers, Wednesday 3 AM EDT clearing and a two-day dropped-player wait on September 9.
`data/automation/rules/1400628784381612032.json` preserves that evidence and its original date.
Collection automatically incorporates this record when its confirmed settings match the league response.
Plans expose it as `known_waiver_rules`, separately from unresolved exceptions and agent reviews.
The agent must not request this basic confirmation again merely because complete coverage remains unavailable.

Use this offline command to attach confirmed rules to a previously saved observation:

```text
python3 automation.py incorporate-rules --observations PROJECT_RELATIVE_OBSERVATIONS --rules PROJECT_RELATIVE_RULES
```

The command verifies source checksums and saves a new immutable observation.
It preserves the original observation timestamps. It does not call providers or rewrite earlier evidence.
The record establishes the displayed weekly schedule, not every candidate's deadline or processing completion time.
Custom daily waivers, acquisition restrictions and unresolved agent reviews remain separate checks.

Raw league settings without confirmed labels do not establish exact processing times by themselves.
The collector does not interpret undocumented waiver bit masks or assume a processing weekday.
It requires explicit saved timing evidence for waiver and unresolved-review coverage.

1. Inspect the applicable league settings and deadline evidence through the authorized workflow.
2. Save that evidence in a project file.
3. Create a timing record using `schemas/automation_timing.schema.json`.
4. Copy `settings_hash` from the matching normalized collection.
5. List all waiver and review deadlines within the declared coverage interval.
6. Run collection with `--timing PROJECT_RELATIVE_PATH`.

The timing record binds the league, season, current week, settings hash and observation time.
It includes `coverage_start`, `coverage_end`, `evidence_refs`, `complete` and `events`.
Each event identifies its kind, stable event ID, week, UTC deadline and relevant owned player IDs.
An empty event list asserts verified absence throughout the interval. Inspect the interval before recording an empty list.
The collector checks file references and scope. It cannot independently certify the truth of manually recorded evidence.

Missing timing evidence blocks desired checks and creates a bounded recollection obligation.
It does not erase game observations or previous obligations.
Saved timing evidence must cover the full planning horizon and satisfy the policy's age limit.

## Produce a plan

```text
python3 automation.py plan --observations OBSERVATIONS_PATH --policy config/automation_plan_policy.example.json --as-of UTC_TIMESTAMP
```

1. Use an explicit timestamp with a time zone for `--as-of`.
2. Supply `--previous PREVIOUS_PLAN_PATH` whenever a prior plan exists for this roster and season.
3. Read `issues`, `capacity` and `coverage` before interpreting `desired_checks`.
4. Preserve the returned plan path for the next planning run.

The default output directory is `data/automation/plans/`.
Use `--output-dir PATH` to select another output directory.
The filename contains the plan's canonical hash. Repeating identical inputs, policy and clock preserves the same file and bytes.
The command rejects a conflicting existing file.
Observation, policy and source files must be inside the selected project root.

`--previous` preserves missing obligations and conservative lock history.
The planner rejects a previous plan with a wrong scope, future clock or invalid checksum.
Without a previous plan, the planner cannot recover lock evidence from an earlier planning run.
Future orchestration must supply that predecessor. It must not omit the predecessor to bypass a blocker.

## Timing rules

The example policy is a starting configuration, not a measured operating guarantee.
It requests game checks 90 and 30 minutes before kickoff.
Waiver offsets are 1,440 and 60 minutes before an explicitly verified deadline.
Review checks use a 30-minute offset.
The policy reserves a 15-minute execution buffer and permits up to 10 minutes of start lateness.
Measure runtime and recovery latency before enabling unattended execution.

For each event and offset:

```text
nominal_run_at = deadline - offset
expires_at = deadline - execution_buffer
latest_start_at = min(nominal_run_at + lateness, expires_at - 1 second)
```

An overdue check can start now only while its latest-start bound still permits useful work.
Otherwise, its disposition is `missed`. The planner does not move missed work into the future.
Checks have separate obligations. The planner does not merge nearby deadlines.

The horizon ends at the later of the configured horizon or the next daily run plus the recovery overlap.
The example horizon is 48 hours, with a daily time of 09:00 Eastern and a 24-hour overlap.
`next_daily_at` describes a desired anchor. M2 does not install that anchor.
At least two task slots remain reserved for the anchor and recovery.

Deadline arithmetic uses UTC. Display times use the configured time zone.
A nonexistent daily time advances to the first real minute after the daylight-saving gap.
A repeated daily time uses its first occurrence, once per local date.
Ambiguous or nonexistent fixture times remain unknown and block planning.

A kickoff change preserves logical check identity but changes its payload revision.
Identity includes league, season, event week, event ID, kind and policy offset.
The planner includes next-week and overnight checks when their due times enter the horizon.
An observed score or previously passed kickoff remains a conservative lock across predecessor plans.
A later schedule edit cannot establish that the player became available again.

## Plans, capacity and scheduler coverage

Desired checks contain M1-compatible check contracts and revisions.
Their prompts contain fixed instructions, an opaque check ID and a revision.
Provider text never becomes executable command text.
M2 prompts permit context inspection only. Later workflow milestones must supply bounded execution instructions.
Before any future delivery, orchestration must register the exact contract and verify its revision through M1.
Planning itself does not register checks or enable a mode.

Capacity selection preserves the earliest latest-start deadlines first.
The example cap is a local policy value, not a verified account limit.
All excess obligations remain visible as coverage gaps.
The report does not assume that unrelated tasks leave the configured capacity available.
M3 must reconcile capacity against a complete scheduler inventory.

Coverage intervals describe desired start windows, not continuous monitoring or completed work.
Every plan sets `scheduler_verified` to false and `deletion_authorized` to false.
Missing inputs preserve prior obligations and identify an unknown coverage interval.
A retry obligation permits at most one recollection attempt within a bounded window.
The retry remains unscheduled and is not an automatic loop.

## Files and validation

The planning policy is separate from M1's execution-mode policy.
The schemas describe planning policy, timing evidence, observations and plan output.
Runtime checks additionally enforce relationships between fields, source hashes and timestamps.
The policy limits provider retrieval age to five minutes. Timing evidence has a separate configurable limit of at most 24 hours.
These limits constrain retrieval age. They do not prove that a provider published every change promptly.

`tests/test_automation_plan.py` uses synthetic seasons, simulated providers and temporary files.
Tests cover exact times, daylight saving, prior locks, postponements, late work, source failures, capacity and immutable persistence.
Existing draft and weekly behavior remains subject to the full project test suite.

Local acceptance passed on September 11, 2026: all 251 tests passed, including 23 M2 tests.
The document checker reported zero structural findings. Manual review retained the technical vocabulary distinctions.
The real collection used seven Sleeper attempts and two nflverse attempts, with no cache hits or platform changes.
Its ownership and fixture validation passed. The initial replay reported missing timing evidence.
Subsequent incorporation preserves the owner's existing waiver confirmation and narrows the gaps to exceptions and agent reviews.
All 253 tests pass after this correction, including 25 planner tests.
See [the current handoff](PROGRESS.md) for observation and plan paths.
This completes M2 implementation acceptance. It does not establish operational waiver coverage or activate the scheduler.
