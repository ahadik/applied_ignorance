# nflreadr / nflverse research and operating context

Reviewed **2026-09-08** against official documentation, loader source, GitHub
delivery guidance, and this project's previously collected files. Read alongside
[NFLVERSE.md](NFLVERSE.md), which defines the implemented commands and policies.
This is a maintained reference for future agents, not a promise that every
documented feed is already integrated or currently publishing.

## Decisions to preserve

1. Keep acquisition in `nflverse.py`; invoke saved collectors. No direct agent
   requests, alternate cache directories to escape limits, or hidden package
   downloads. Researching documentation does not require collecting every dataset.
2. Use explicit seasons, data grain, IDs and timestamps. Keep unknowns unknown.
   Recent retrieval does not establish recent underlying information.
3. For tonight, use the four wired datasets for workload, production and depth
   evidence. Historical records supplement current projections; they do not replace
   them. Do not install R or another loader during the draft.
4. Prioritize a verified fantasy ID crosswalk when integrating these results with
   our draft board. Its existence is documented; its current coverage is untested.
5. Treat additional sources and models below as candidates requiring central-client
   support, validation and evaluation before production use.

## What the ecosystem provides

nflreadr is an R acquisition package; nflverse-data publishes automated release
files organized around its loader functions. Reading those published files directly
is a supported access route. Our Python implementation uses that route, not an R
wrapper. [nflverse-data README](https://raw.githubusercontent.com/nflverse/nflverse-data/master/README.md)

The reference index covers these families. The final column is our assessment of
use, not a provider recommendation. Only the four entries marked **wired** are
supported by our general client today.

| Family / loaders | Data grain or purpose | Project use |
|---|---|---|
| `load_players` | Player directory and identifiers | **Wired:** identity joins |
| `load_player_stats` | Player production | **Wired:** weekly historical evidence |
| `load_snap_counts` | Player/game participation | **Wired:** workload |
| `load_depth_charts` | Team role snapshots | **Wired:** current role context |
| `load_pbp`, `load_team_stats` | Plays and team production | Later: opportunity/team environment |
| `load_participation`, `load_ftn_charting` | Personnel and charted plays | Later: historical role features |
| `load_nextgen_stats`, `load_pfr_advstats`, `load_espn_qbr` | Specialist performance measures | Later: test incremental predictive value |
| `load_rosters`, `load_rosters_weekly`, `load_injuries` | Membership and availability records | Verify coverage before use |
| `load_schedules`, `load_officials`, `load_teams` | Games, officials, team metadata | Later: fixtures, joins and display |
| `load_draft_picks`, `load_combine`, `load_trades`, `load_contracts` | Career and organizational context | Later: rookie priors and role changes |
| `load_ff_playerids`, `load_ff_rankings`, `load_ff_opportunity` | Fantasy IDs, consensus and modeled opportunity | Evaluate separately below |
| Bulk download, release listing, name/team cleaning, season/week helpers | Acquisition and normalization utilities | Reimplement only needed behavior centrally |

Source: [nflreadr function index](https://nflreadr.nflverse.com/reference/index.html).
An indexed function does not establish current availability or consistent fields
across every year. Example output on a documentation page is not a live probe.

## Publication schedules and availability

These are documented schedules, not service guarantees. Upstream publication and
our refresh schedule are separate. [Official update schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html)

| Feed | Documented cadence / limitation |
|---|---|
| Play-by-play, player/team stats | Nightly after game days, plus selected game-day runs; refresh Thursday for corrections |
| PFR snaps, FTN charting | 00:00, 06:00, 12:00, 18:00 UTC; upstream dependent |
| Rosters, depth charts | Daily 07:00 UTC |
| NGS | Overnight, 03:00–05:00 Eastern; upstream dependent |
| PFR advanced | Daily 07:00 UTC; upstream dependent |
| Schedules | Every five minutes during the season |
| Injuries | Documentation says source ended after 2024; no 2025 data or restoration ETA |

The injury warning specifically names 2025. It is not independent confirmation of
2026 availability: verify restoration before designing current injury decisions
around it. Our prior collection observed depth rows at 11:56:57 UTC, illustrating
why actual timestamps matter more than assumed cron times. Do not poll daily feeds
per pick. Planned future refreshes should follow useful publication windows and
validate completeness before promoting a snapshot.

## Schemas, seasons and joins

### Version changes are operationally important

The reviewed nflreadr site identifies itself as development version 1.5.1.9002;
the changelog lists stable 1.5.1 on April 13, 2026. Version 1.5.0 changed player
statistics, the player directory and depth-chart sourcing. The 2026 season helper
also changed its transition day. Pin explicit seasons and record file columns;
do not infer schema or season from a remembered package example.
[nflreadr changelog](https://nflreadr.nflverse.com/news/index.html)

The modern weekly stats release is `stats_player_week_YEAR.csv`, with separate
season-summary variants. nflreadr supports week, regular-season, postseason and
combined summaries. Our adapter selects weekly files and explicitly filters `REG`.
[Stats loader source](https://raw.githubusercontent.com/nflverse/nflreadr/main/R/load_stats.R)

Modern stat names include `team`, `passing_interceptions`, `sacks_suffered` and
`sack_yards_lost`; old examples may use different names. Never interpret an absent
old column as zero. [nflfastR schema changes](https://nflfastr.com/articles/stats_variables.html)

`calculate_stats()` has different season-filter behavior for weekly versus
seasonal aggregation. Custom play subsets also need explicit scope. Our weekly
filtering and completeness checks must remain in application code rather than
assuming a loader argument removed postseason rows.
[Stats calculation reference](https://nflfastr.com/reference/calculate_stats.html)

### Preserve identity namespaces and row grain

Our current analysis treats GSIS as its football-player identity, maps PFR snap IDs
through the player directory, and checks ESPN IDs on depth rows. All IDs remain
strings. Normalize documented missing tokens to null; quarantine conflicting or
missing links. Names support display and manual review, never silent fuzzy joins.

The snap dictionary distinguishes nflverse game IDs, PFR game IDs and PFR player
IDs. It supplies offensive, defensive and special-team counts/shares. Validate the
numeric scale from the actual file; our observed offensive shares are fractions
between zero and one. Never join solely on week number across seasons or treat
different game-ID namespaces as interchangeable.
[Snap dictionary](https://nflreadr.nflverse.com/articles/dictionary_snap_counts.html)

For modern depth data, `dt` records when the row was loaded; `pos_grp`, `pos_slot`
and `pos_rank` describe formation, slot and within-slot order. A rank of one is
not a forecast of touches. Our analysis selects a team's latest complete timestamp
at or before analysis time. Selecting each player's latest row would retain people
removed from the current chart.
[Depth dictionary](https://nflreadr.nflverse.com/articles/dictionary_depth_charts.html)

Season-level rosters expose several platform IDs, including Sleeper in the
documented example, but are not game-level participation records. Their default
season selection differs from ordinary football-season helpers. Request seasons
explicitly and distinguish roster membership from playing time.
[Roster reference](https://nflreadr.nflverse.com/reference/load_rosters.html)

The online player/stats dictionary tables did not fully render through text
retrieval during this audit. We inspected loader source and the columns recorded
in our saved provenance instead. Before introducing an unfamiliar metric, obtain
its specific definition; this audit does not assert that every dictionary field
has been individually verified.
[Stats dictionary](https://nflreadr.nflverse.com/articles/dictionary_player_stats.html),
[Player dictionary](https://nflreadr.nflverse.com/articles/dictionary_players.html)

### Fantasy platform crosswalk: first integration candidate

`load_ff_playerids()` exposes DynastyProcess's cross-platform ID database. The
reference includes `gsis_id`, `sleeper_id` and `fantasypros_id`, so it may supply the
missing join between our historical evidence and draft-board data.
[Fantasy ID loader](https://nflreadr.nflverse.com/reference/load_ff_playerids.html)

Its dictionary identifies MFL as the complete unique primary ID; that does not
make every other column complete or one-to-one. Team, position and age have their
own provenance and build timing. Validate namespace uniqueness, ambiguous links,
rookies and unmapped draft candidates before adopting a crosswalk.
[Fantasy ID dictionary](https://nflreadr.nflverse.com/articles/dictionary_ff_playerids.html)

The actual R loader points to `dynastyprocess/data`, not the existing
`nflverse/nflverse-data` release allowlist. Do not invent an asset name in our
current repository. Add a specific validated source adapter, establish its cache
revision mechanism and available format, then collect through that adapter.
[Fantasy loader source](https://raw.githubusercontent.com/nflverse/nflreadr/main/R/load_ffverse.R)

## Analytical value and limits

**Implemented evidence:** two completed seasons of production, recorded-row
averages, last four league weeks, offensive snap means and current depth. These
can identify sustained workload, late-season changes and role uncertainty. The
same observed evidence can support different strategies; downstream models should
make assumptions visible and test them against outcomes.

Missing stat rows are not automatically zero games. Snap means are unweighted
game averages, not season-weighted participation. A new team or rookie needs a
separate prior; absent NFL history does not establish low ability. Historical PPR
columns are not guaranteed to match the league's full scoring rules. Recompute
league scoring from supported components and report any uncovered rules.

**Next Gen Stats:** passing, rushing and receiving aggregates start in 2016, but
minimum opportunity thresholds exclude some players. `week == 0` denotes a
regular-season aggregate; combining it with weekly rows would double count.
Potential added signal must be evaluated without treating excluded players as
zeros. [NGS reference](https://nflreadr.nflverse.com/reference/load_nextgen_stats.html)

**Participation:** pre-2023 data originates with NGS; 2023 onward is FTN and arrives
after the postseason. That makes it a historical feature candidate, not a live
weekly personnel feed. Provider changes are a potential modeling discontinuity.
Its documented license is CC-BY-SA 4.0, with attribution to the applicable source
via nflverse. [Participation reference](https://nflreadr.nflverse.com/reference/load_participation.html)

**FTN charting:** a public subset of manually charted plays, available from 2022,
with stated charting within 48 hours after games. It includes context such as
motion, play action and catchable/contested balls. It does not imply access to the
entire premium product. The reference specifies CC-BY-SA 4.0 and FTN attribution.
[FTN charting reference](https://nflreadr.nflverse.com/reference/load_ftn_charting.html)

**Expected opportunity:** `load_ff_opportunity()` supplies precomputed modeled
expected fantasy points with weekly/pass-play/rush-play modes and version options.
This is a candidate for comparing outcomes with opportunity, not automatically a
forward player projection or calibrated uncertainty distribution. Pin model
version, inputs and season; verify actual coverage before using it.
[Opportunity reference](https://nflreadr.nflverse.com/reference/load_ff_opportunity.html)

**Consensus rankings:** `load_ff_rankings()` accesses DynastyProcess's republished
FantasyPros consensus, documented as weekly. It is correlated with the FantasyPros
feed we already use. Do not count it as a second independent expert ensemble, or
use it to bypass an entitlement or quota. Prefer our licensed central FantasyPros
client for current supported rankings.
[Rankings reference](https://nflreadr.nflverse.com/reference/load_ff_rankings.html)

**Backtesting policy:** today's corrected historical download was not necessarily
available on the historical decision date. Save acquisition/publication/observation
times separately. Do not use later depth charts, retrospective identities, future
model versions or final-season summaries as if known earlier. Our `--as-of` check
rejects assets published after its cutoff; it cannot reconstruct old publication
versions that were never saved. Train and evaluate in chronological splits, retain
sample sizes and compare deterministic baselines before claiming an edge.

## Caching and polite delivery

There are four separate freshness layers: upstream observation, release
publication, HTTP/cache validation and our saved analytical snapshot. A successful
metadata check proves only the release state seen at that time.

nflreadr's source configures memoized download functions with an 86,400-second
timeout and memory/filesystem/off cache choices. Adding it underneath our client
could introduce an additional stale layer. Our Python client does not use this
cache. [nflreadr cache initialization](https://raw.githubusercontent.com/nflverse/nflreadr/main/R/zzz.R)

nflreadpy is an official Python alternative using Polars and its own caching. It
is not a dependency here. If adopted later, route its retrieval through the same
central policy or explicitly replace that layer; do not operate two uncoordinated
downloaders. Its MIT code license is distinct from dataset licensing, and its
general licensing summary has a stated July 2025 scope.
[nflreadpy overview](https://nflreadpy.nflverse.com/)

GitHub documents unauthenticated REST access at 60 requests/hour per originating
IP. Other applications on that IP can consume the same quota. Observe returned
remaining/reset headers; do not spend calls repeatedly checking the rate-limit
endpoint. Rate limits can return 403 or 429; secondary limits can require waiting
even when primary quota remains.
[GitHub rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)

GitHub recommends serial access, conditional requests, respecting polling headers
and increasing delays after repeated limits. Its exemption for conditional 304
responses is explicitly for authenticated requests. Our unauthenticated client
conservatively counts 304s as attempts.
[GitHub request practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)

Release metadata exposes asset identity, size, update time, browser download URL
and optional digest. Downloads can redirect to asset infrastructure. Our client
validates fixed source URLs, permits only expected HTTPS delivery hosts, hashes
revisions and validates bytes. It never persists temporary signed redirect URLs.
[GitHub release assets](https://docs.github.com/en/rest/releases/assets)

Our local budgets are deliberately below the unauthenticated REST allowance:
45 routine / 50 hard REST attempts per rolling hour, plus 120 routine / 150 hard
total attempts including downloads. Reserve headroom is only for retries already
underway. These are project policies, not published asset-download limits. They
cannot guarantee unused IP-wide quota. Counters and cooldowns persist in SQLite;
all operational callers share one directory. See [NFLVERSE.md](NFLVERSE.md) for
the full implemented cache, retry, header and command contract.

## Future collection checklist

Before enabling another dataset, record the official loader/source, exact
repository and asset format, explicit season range, expected grain, ID namespaces,
required columns, source license/attribution, source cadence and absence behavior.
Add mocked tests for schema changes, mixed seasons, missing IDs, duplicate keys,
delayed publication, cache invalidation and rate limits. Then run one bounded
collection and save its provenance and coverage report.

For a future remote collector, use a shared ledger or single acquisition service;
the current file lock coordinates one filesystem, not multiple cloud hosts. MCP
should expose collection/status/analysis services that reuse these policies. Save
only compact calculated evidence for the agent; do not send annual raw archives
into its context. No cloud scheduler or MCP endpoint was added in this audit.

## Research boundaries and maintenance

This review covered the function index, source update schedule, schema changes,
relevant loader implementations/dictionaries, fantasy feeds, package caching and
GitHub delivery rules. Linked sources are primary documentation. All were reviewed
on September 8, 2026; live data observations come from the separate earlier
collection recorded in `NFLVERSE.md`, not from documentation examples.

Open items: current injury restoration; availability/coverage of unwired feeds;
cross-platform ID coverage; exact definitions for any new metric; licenses of each
new feed before redistribution; and whether additional features improve forecasts.
Do not silently promote these unknowns into facts. Revisit schedule/changelog and
asset schemas at season transitions, upstream failures and new integrations.
