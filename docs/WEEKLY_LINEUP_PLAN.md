# Weekly lineup infrastructure plan

Implementation update: [WEEKLY_LINEUP.md](WEEKLY_LINEUP.md) documents the delivered
`weekly_lineup.py run/recommend/verify` pipeline. The interfaces and phases below
are the original plan. The implemented CLI supersedes its proposed filenames.
Phase 2, unattended reminders and browser submission remain separate work.

Prepared September 9, 2026. Planning only: no fresh player collection, lineup
submission, or automation was performed. Target: an initial lineup tomorrow,
September 10 Eastern, subject to verifying actual game and lineup-lock deadlines.

Subsequent rules-only API verification: see [LEAGUE_RULES_VERIFICATION.md](LEAGUE_RULES_VERIFICATION.md).
Roster/scoring and waiver priority were refreshed. A user screenshot confirms
rolling waivers, Wednesday 3 AM EDT clearing and a two-day waiver period.
Bench-drop and transaction-lock UI labels remain unverified. `league_rules.py` is implemented. The
weekly command surface below remains proposed.

## Objective and baseline

Select the legal starting lineup with the highest supported weekly expected
points, then protect it against late scratches and missed deadlines. Winning the
fantasy matchup is the ultimate objective. Maximizing expected points is our
initial decision rule, not a claim that we have calibrated win probabilities.

The saved league snapshot at 2026-09-09T03:41:54Z has full PPR and four-point passing touchdowns. Its starting slots are QB / RB / RB / WR / WR / TE / FLEX / K / DEF. It has five bench slots.
Refresh rules and ownership before using them. Draft completion and freeze release
are confirmed in PROGRESS.md. Frozen projections remain historical evidence.

## Signals and how to use them

| Signal | Decision use | Priority and limitations |
|---|---|---|
| Exact league rules and eligibility | Convert projected statistics into our scoring and enumerate legal lineups | Required. Standard PPR totals may omit custom rules |
| Explicit weekly projections | Baseline expected production for this week's game | Required. Reject preseason, ROS, wrong-week or stale substitutes |
| Availability and expected workload | Separate likely inactive, active but limited, and normal-role scenarios | Required. Practice status alone is not final availability |
| Offensive role | Carries, targets, reception opportunity, snaps, goal-line work, and teammate competition | High. Routes and red-zone features require additional validated feeds |
| NFL opponent and game environment | Defensive strength, pressure, likely pace and passing/rushing opportunities | High context. Weekly projections may already include these effects |
| Injuries to teammates and opponents | Identify changes to blocking, quarterback play, target competition and defensive strength | High when material. Do not restrict news review to our 14 players |
| Recent performance | Track opportunity and role changes alongside efficiency and points | High once games exist. Show sample size and regress small samples toward a prior |
| Game time, bye, postponement and lock rules | Exclude unavailable games and preserve legal replacement options | Required. Verify actual platform rules and kickoff times |
| Weather, venue and roof status | Review material wind or other conditions affecting the game | Useful if available. Central source integration needed for automated weather |
| Expected team scoring / betting totals and spreads | Summarize offensive environment and likely game script | Later enrichment. Verify source and timestamps, avoid duplicate adjustments |
| Coaching, scheme and personnel changes | Explain why historical usage may no longer apply | Contextual review. Record evidence rather than unsupported numerical bonuses |
| Rest, travel and home/away | Potential incremental matchup context | Later. Do not assume predictive value without evaluation |
| Projection disagreement and freshness | Flag close choices and outdated assumptions | Useful. Rank disagreement is not a fantasy-point outcome distribution |
| Our fantasy opponent | Explore matchup risk, correlations and late-game decisions | Optional for baseline points optimization. Requires distributions for credible win modeling |
| Other fantasy rosters | Identify available replacements and waiver competition | Needed for waiver expansion, not scoring the players already on our team |

Week 1 has no completed current-season regular-season sample before its games.
Use explicitly labeled historical evidence and current role reports. Never label
2025 production as recent 2026 performance. Preseason usage, if added, stays
separate. Avoid chasing last week's touchdowns once games begin: inspect whether
underlying opportunity changed. Simple historical fantasy-points-allowed rankings
also reflect prior opponents and personnel. They are context, not an automatic
matchup multiplier.

Preserve the provider forecast as the baseline. Any adjustment must state the new
evidence, whether the baseline already reflects it, the numerical assumption and
its sensitivity. Never multiply by an injury probability until the forecast's
conditional-on-playing semantics are understood.

## Existing foundation and missing work

| Component | Existing | Proposed work |
|---|---|---|
| Provider access | Central Sleeper, FantasyPros and nflverse clients with shared policies | Reuse unchanged access boundaries and ledgers |
| League data | Draft-oriented context collector | Weekly domain collector for league, ownership, starters, NFL state and optional fantasy matchups |
| Projections | Six-position preseason collection | Explicit season/week collection and weekly payload validation |
| Identity and scoring | Verified joins, quarantine, mapped scoring subtotals | Extract reusable functions from draft modules. Retain scoring-gap warnings |
| History | Stats, snaps, identities and depth wired | Weekly features with as-of cutoffs, sample sizes and current-team context |
| Games and deadlines | No schedule dataset wired in nflverse client | Add documented schedule support and test time zones, changed games and missing fixtures |
| Decision engine | Draft marginal value and A/B search | Separate exact roster/slot optimizer. Draft value is not weekly expected points |
| Execution | Draft-specific browser/controller procedures | Weekly review/apply/verify workflow with lock checks |
| Operations | Local durable snapshots | Weekly report, conditional backups, decision log and deadline checklist |

Follow DATA_ACCESS.md, FANTASYPROS.md and NFLVERSE.md. Research and validate
documentation/schema before wiring any new feed. Current source availability has
not been rechecked for this plan. An official inactive-report evidence record
may be entered manually with URL, published time and observed time. Automated
retrieval needs an approved central provider path. Sleeper injury fields and
secondary news do not by themselves prove official inactive status.

## Phase 1: required for tomorrow

1. **Collect and validate a weekly snapshot.** Implement `weekly_data.py` and
   `weekly_inputs.py`, independent of draft controllers. Retrieve league rules,
   roster/starters, season/week and necessary player identity/status through
   `sleeper.get_sleeper`. Retrieve six weekly positional projection sets and
   relevant injuries/news through `fantasypros.get_fantasypros`. Use verified
   joins and preserve separate provider publication and retrieval times. Collect
   once per coherent snapshot, not once per player comparison. Missing owned
   projections must be reported, not silently valued at zero.
2. **Establish games and locks.** Extend `nflverse.get_nflverse` with validated
   schedule support. Save each owned player's opponent, kickoff, game status and
   applicable lock. Verify platform lock behavior in Sleeper. If schedule
   integration cannot be completed in time, record manually verified fixtures
   with provenance and require a manual lock check before every change.
3. **Build a deterministic optimizer.** Implement `weekly_lineup.py`. Maximize
   the sum of weekly projected points over legal assignments. Enforce ownership,
   eligibility, uniqueness, slots, known inactive status and existing locks.
   Exhaustive enumeration is practical for this roster. Preserve later-playing
   eligible starters in FLEX when this keeps more backup options without
   sacrificing the selected lineup's points. Account for locked bench players
   according to actual rules. Do not assume a swap is possible.
4. **Make uncertainty actionable.** Output alternative legal lineups and their
   projected differences. For questionable players, record if-active/if-out
   contingencies and when replacement options lock. A later questionable player
   may require choosing a healthy earlier alternative before news arrives.
   Scenario values without calibrated probabilities are sensitivity analyses,
   not expected-value estimates. No arbitrary universal injury discount.
5. **Produce a review report and decision record.** Show starter, slot, opponent and kickoff. Show projected points and the scoring basis. Include injury/role evidence and the best bench alternative. Include the projected difference, source ages and remaining blockers. Save
   the numerical leader separately from any agent override, including reason,
   evidence, input hash, model version and final applied lineup.
6. **Apply and verify separately when requested.** Re-read ownership/starters and
   verify locks immediately before browser changes. Apply changes sequentially,
   inspect each visible update, then reconcile the full starting lineup through
   central Sleeper reads. The public API is read-only. A report is never evidence
   that the lineup was submitted. Recompute after a material state change.

Our main comparison groups are Purdy/Mahomes, Fannin/Johnson, and the combined
RB/WR/TE choices for positional slots and FLEX. Henry, Barkley, Swift and Jones
compete for RB/FLEX usage.  Flowers, Washington, Johnston and Shaheed compete for
WR/FLEX usage. Evaluate all legal combinations rather than fixing draft-order
starters. Loop and Pittsburgh are our only drafted K and DEF. Alternatives there
require a separately scoped free-agent/waiver analysis.

### Scoring gaps must remain visible

The current mapper omits some nonzero offensive categories and lacks full kicker
distance and defense scoring coverage. Extract it with regression tests, then
validate weekly schemas. Prefer exact stat-based conversion where supported.
Otherwise label the result a supported subtotal or explicitly labeled provider
estimate. Never mix the two as if they were exact comparable totals. Cross-position
FLEX comparisons need a consistent basis. If omitted categories or missing data
could change a close decision, mark that comparison for review and disclose the
limitation. Do not block choosing between fully covered alternatives solely
because an unrelated feed is absent.

### Proposed command surface — not implemented yet

```text
python3 weekly_inputs.py collect --season 2026 --week 1
python3 weekly_lineup.py recommend --season 2026 --week 1
python3 weekly_inputs.py refresh-alerts --season 2026 --week 1
python3 weekly_lineup.py verify --season 2026 --week 1
```

Collection/refresh/verification use central provider clients. Recommendation is
offline against a validated snapshot. Verification reads platform state and
compares it with the saved decision. It does not submit changes.

Store private snapshots and reports under `data/weekly/2026/1/`, with immutable
snapshot IDs/checksums, a latest-valid pointer, and append-only decision events.
Use `storage.save_atomic` for JSON persistence and a serialized durable event
writer. Partial collection must not promote a mixed or incomplete snapshot.

## Deadline workflow and failure handling

- Prepare an initial legal lineup before the earliest relevant verified lock.
  Do not assume all Week 1 games start after tomorrow's planning session.
- On each relevant game day, recheck current availability and material news.
  Proposed operational checkpoints: roughly 90 minutes and 30 minutes before
  each relevant kickoff, plus a final check with enough time to apply changes.
  These are our check times, not a promise of when providers publish inactives.
- Refresh projections at the initial decision and when material news makes the
  prior assumptions obsolete. Use cache-first calls and documented shorter ages
  when justified near a deadline. Never poll full feeds continuously.
- Proposed starting freshness gates: league/locks reverified for application,
  projections retrieved within six hours, injury/news checks within 15 minutes
  near lock, with publication age and unknown source timestamps separately
  exposed. Recent retrieval alone cannot clear an unresolved availability issue.
- Respect shared FantasyPros and nflverse quotas/cooldowns. A baseline budget is
  six projection requests plus injury/news requests, identity/schedule reads and
  any justified weekly-ranking validation. Print actual attempts and cache hits.
- If a required feed fails, preserve the last valid snapshot with its original
  age, show the blocker and retain the already verified lineup. Use saved legal
  contingencies only after checking current status and locks. Do not present old
  projections as a fresh recommendation.
- No reminder service currently exists. Initially use a visible manual checklist.
  Scheduled alerts require a persistent process, delivery destination, health
  checks and a tested failure notification path before we rely on them.

## Phase 2: after a working Week 1 lineup

Add waiver candidates ranked by marginal improvement to the optimized lineup,
accounting for ownership, acquisition rules, drop cost and future coverage.
Add routes, red-zone opportunity, richer matchup statistics, weather and game
totals only after central access and validation exist. Measure whether these
features improve on unadjusted weekly projections before assigning tuned weights.

Persist prediction-time snapshots and reconcile actual league-scored results.
Evaluate forecast error and bias by position against the baseline. Report sample
sizes and use chronological holdouts. One week's outcome does not establish that
an override or feature works. Latest corrected historical data cannot substitute
for historical prediction-time inputs in a backtest.

Opponent-aware win optimization comes later: it needs outcome distributions,
within-game correlations, opponent lineup uncertainty and remaining locked scores.
Avoid blanket rules such as always choosing upside when projected behind or
benching a quarterback because the opponent owns his receiver. Opponent ownership
does not change the player's expected production.

Cloud scheduling and authenticated MCP follow docs/MCP_DESIGN.md once local
services work. They are not dependencies for tomorrow's lineup.

## Acceptance checks before relying on the system

Tests and simulated fixtures belong under `tests/`. Run
`python3 -m unittest discover -v` from the project root after implementation.
Required meaningful cases:

- Wrong season/week, ambiguous IDs, partial feeds, stale data and missing owned
  projections cannot silently generate a complete confident recommendation.
- Hand-calculated scoring examples match. Unsupported categories remain exposed.
- A small exhaustive reference confirms the optimizer chooses the highest-value
  legal assignment, including multi-position/FLEX and deterministic ties.
- Inactive players, duplicate assignments, changing ownership and locked players
  cannot produce an executable illegal recommendation.
- Deadline tests cover time zones, delayed/postponed games, late questionable
  players and backups whose games start earlier.
- Identical inputs reproduce recommendations. Overrides preserve model advice.
  Failed collection preserves previous valid artifacts without relabeling them.
- Live verification reports the actual starting lineup and discrepancies. A
  successful calculation or browser click alone never marks application complete.

Tomorrow's deliverable is a verified legal lineup, a concise comparison of the
close choices, timestamped supporting evidence and usable late-injury backups.
This document proposes that work. It does not claim those capabilities exist yet.
