# nflverse pipeline

Large depth-chart JSON outputs are now stored under ignored `data/nflverse/local/`.
Run `python3 -m fantasy_agent setup_repo --season 2026` after cloning to collect depth and its
companion datasets through the central client and write a matching manifest.
This checks current publication metadata and respects existing cache/budgets.
It does not recreate the exact historical draft snapshot if upstream changed.

September 9 extension: `get_nflverse('schedules', season)` now supports nfldata's
multi-season `games.csv` through the same central ledger/cache. It checks GitHub
Contents metadata every read, verifies Git blob identity and SHA-256, reuses
unchanged bytes and selects the requested season. Publication time remains
unknown. See [weekly guide](WEEKLY_LINEUP.md) for sources, schema, time zone and
lock limitations. Use `nflverse_collect.py collect --dataset schedules --season 2026`.
This feed uses a fixed repository file, not a release catalog.

September 11 recovery: if raw schedule bytes differ from Contents metadata, the client retrieves the exact advertised Git blob once.
It uses the shared budget and cooldown, verifies size and Git identity, and saves only verified bytes.
An incorrect replacement still stops collection. Provenance records `exact_blob_recovery` and actual request counts.
See GitHub's [blob endpoint](https://docs.github.com/en/rest/git/blobs#get-a-blob).

Implemented September 8, 2026. This is a third, general provider alongside Sleeper
and FantasyPros. Python reads the published files used by nflreadr.  R and the
nflreadr package are not runtime dependencies. No API key is required for the
public GitHub release assets used here.

The deeper, cited reference is [NFLVERSE_RESEARCH.md](NFLVERSE_RESEARCH.md), reviewed
September 8, 2026. Read it before adding feeds or interpreting unfamiliar metrics.
It covers publication schedules, schema changes, identity crosswalks, model/data
limitations, licensing and future integration decisions.

## Separation of responsibilities

- `nflverse.get_nflverse(dataset, season, ...)`: provider discovery, HTTP,
  persistent caching, publication metadata, checksums, validation and retries.
- `nflverse_collect.py`: general catalog, collection, offline inspection and local
  request-budget status CLI.
- `draft_history.py`: draft-specific selection and collection of current depth
  charts, player identities and two completed seasons of historical evidence.
- `draft_history_analysis.py`: offline historical calculations and role analysis.
  No HTTP calls. Saved commands must use the central client for any new downloads.

All generated files live under ignored `data/nflverse/`. The default shared cache
is `data/nflverse/cache/`. No credentials from `.env`, Sleeper or FantasyPros are
used or forwarded to GitHub. Fixed provider URLs and restricted HTTPS release
redirects allow GitHub's asset delivery without accepting arbitrary endpoints.

## Supported datasets

| Dataset | Published release tag / asset | Use tonight |
|---|---|---|
| `players` | `players` / `players.csv` | GSIS, PFR and ESPN crosswalk. Names for display |
| `depth_charts` | `depth_charts` / `depth_charts_YEAR.csv` | Current formation/slot/depth ordering |
| `player_stats` | `stats_player` / `stats_player_week_YEAR.csv` | Regular-season production and workload |
| `snap_counts` | `snap_counts` / `snap_counts_YEAR.csv` | Offensive participation and late usage |

Files are discovered in release metadata, not assumed present. CSV is preferred,
with CSV.gz supported if that is the published asset. Missing seasons or formats
raise an explicit error. No earlier-season or sample-data substitution occurs.
The general reader checks required schema and season columns where present. The
2025+ depth format uses `dt` timestamps instead of a season/week field. Its filename
and exact release metadata establish the requested year and the analysis checks
actual row timestamps. Historical depth schemas are not supported by the current
role-analysis adapter.

## Commands

Run from the project root. These are reusable commands, not inline API examples.

```sh
# Network: collect the six datasets needed for tonight.
python3 -m fantasy_agent draft_history collect --draft-season 2026 --seasons 2024 2025

# Offline: build the draft evidence from the checksummed collection.
python3 -m fantasy_agent draft_history_analysis --draft-season 2026

# Offline: inspect quarantined rows and unresolved IDs.
python3 -m fantasy_agent draft_history_analysis --draft-season 2026 --review-issues

# Offline: query saved evidence using a name fragment or a GSIS ID.
python3 -m fantasy_agent draft_history_analysis --draft-season 2026 --player 'PLAYER_NAME_OR_GSIS_ID'

# General provider commands; catalog and collect may use the network.
python3 -m fantasy_agent nflverse_collect catalog --dataset snap_counts --season 2025
python3 -m fantasy_agent nflverse_collect collect --dataset player_stats --season 2025
python3 -m fantasy_agent nflverse_collect inspect --file data/nflverse/draft/2026/depth_charts_2026.json

# Offline: inspect the shared local ledger and saved GitHub quota observation.
python3 -m fantasy_agent nflverse_collect usage

# Network metadata checks; unchanged assets are reused, not downloaded again.
python3 -m fantasy_agent draft_history collect --draft-season 2026 --seasons 2024 2025 --revalidate
```

The draft collector prints each dataset's status, record count, file location,
cache status, logical network attempts and asset publication time. Its manifest
records every successful and failed operation plus SHA-256 checksums of saved
snapshots. A failed collection never treats an old file as a successful new read.
The offline builder requires a complete matching manifest. Valid source assets
remain in the shared cache after failed replacements.

`--revalidate` on either collector forces publication metadata checks, preserving
unchanged asset downloads. Use it before an important refresh when waiting for the
historical metadata TTL would be inappropriate.

`draft_history.py collect --refresh ...` explicitly revalidates metadata and
redownloads assets. Use this only when a full refresh is intended, not during every
pick. Normal collection reuses unchanged downloaded assets. Running analysis alone
never refreshes any source. Recollect before rebuilding when freshness matters.

## Cache and retry policies

- Current player identities and depth charts revalidate release metadata on every
  read, using ETags when available. If asset identity, size, publication timestamp
  or digest changes, the asset revision changes and a new file is downloaded.
- Completed-season weekly stats and snaps reuse metadata for up to six hours.
  They are not permanently immutable: later corrections are detected on the next
  metadata refresh. A prior-year NFL season is treated as completed only from
  March onward. Older years qualify immediately. Current-season files revalidate
  on every read.
- Six hours is a maximum: metadata `Cache-Control: no-cache`, `no-store`,
  `max-age` and `Age` can shorten or disable local reuse. Catalog reads have a
  five-minute maximum. ETag 304 responses renew the check time, not the original
  asset download time. Metadata marked `no-store` is removed from the HTTP cache.
  A downloaded asset marked `no-store` likewise is not retained there. Explicit
  collector outputs are analytical snapshots, separate from this HTTP cache.
- Asset bytes are cached by revision and verified against a local SHA-256 hash on
  every use. Published SHA-256 digests are checked when available. Exact advertised
  size, CSV decoding, required fields and season checks run before cache writes.
  Optional caller validators run on cache hits too.
- Metadata revalidation failure raises rather than silently returning an outdated
  view of a current feed. Asset publication time, metadata-check time, original
  download time and depth observation time are distinct. None substitutes for the
  others. Publication metadata is not proof that every field reflects current NFL
  conditions.
- Serial local requests are spaced at least 0.25 seconds apart. Connection failures
  and HTTP 500/502/503/504 receive at most two retries, with one- and two-second
  backoff and 15-second per-attempt socket timeout. Invalid data and HTTP 404 are
  not retried. GitHub rate-limit responses create a persistent shared cooldown,
  honoring the later applicable Retry-After/reset deadline and a conservative
  backoff floor. Retry-After accepts seconds or an HTTP date. Repeated limit
  failures double the fallback delay from 60 seconds, capped at 3,840 seconds.
  Longer server deadlines still apply. A successful request resets that failure
  count. A 403 JSON message can identify a secondary limit even without headers.
  Error bodies are bounded and never logged or saved.
- Rolling-hour local budgets are **45 routine / 50 hard REST attempts** and
  **120 routine / 150 hard total attempts**. New requests stop at the routine
  boundary. Only bounded retries can use the reserve. These are conservative
  project limits. Unauthenticated GitHub REST quota is IP-wide, and downloads are
  not assumed to share that REST bucket. Attempts are recorded before I/O.  ETag
  304s count conservatively. Redirects belong to one logical download attempt,
  rather than separately counted HTTP requests.
- REST responses save quota observations. A successful response reporting zero
  remaining prevents the next REST request until reset, while allowing the asset
  download for the successful metadata response. Provider rate-limit errors stop
  all network access during the shared cooldown. `X-Poll-Interval` blocks early
  repolling of its resource. `usage` makes no network calls and shows observation
  time: missing provider quota is unknown, never proof of available quota.
- SQLite migration preserves the earlier attempt ledger. Unclassified legacy
  attempts count against both local buckets until they age out. Do not delete the
  database, switch cache directories or add a different downloader to evade a
  budget/cooldown. A rejected refresh fails explicitly. Callers may separately
  inspect saved evidence with its existing timestamps.
- A process lock coalesces local access. This does not coordinate separate hosts.
  Future cloud deployment should retain a single collector or distributed lock.
  Socket timeouts and lock waits are not a strict total command deadline. Do large
  collection before drafting and keep pick-time analysis offline.
- Download and decompression limits are 256 MiB per file. The annual depth-chart
  archive is large because it contains repeated snapshots. Do not repeatedly
  download or send that raw archive into model context.

## Historical calculations and interpretation

The offline output is `data/nflverse/draft/2026/draft_evidence.json`, with a readable
`DRAFT_EVIDENCE.md` beside it. Computation is deterministic for the same files,
analysis time and freshness threshold. `--as-of` accepts an explicit timezone-aware
ISO timestamp. Assets published later than that time are rejected.

- Include regular-season rows only. Check year, week and player/game uniqueness.
  Quarantine missing identity/game IDs and ambiguous crosswalks. Do not use names
  for silent joins. Derived player records carry GSIS/PFR/ESPN IDs. Joining them to
  Sleeper and FantasyPros remains a separate integration step.
- Calculate passing, rushing, receiving, kicking and source PPR totals and averages
  over recorded stat rows. Missing values remain unknown. A missing player/game row
  is not automatically a zero, proof of inactivity or a game played.
- Compare full-season usage with the last four observed regular-season league
  weeks. This is not the player's last four appearances. Preserve sample sizes.
- Offensive snap-share means are unweighted per-game means. They are not weighted
  season shares. No route participation or red-zone opportunity is inferred from
  these files.
- Select the latest snapshot for each team at or before analysis time, rather than
  each player's latest appearance, so removed players do not remain in a current
  depth chart. Roles older than 36 hours are flagged unusable. Record every team's
  actual age. Override the threshold deliberately if justified.
- Depth order is within a formation and slot. Listed-ahead IDs provide role context,
  not a guarantee that the next player inherits all work. Flag current teams absent
  from the latest historical season and players without recorded history.
- This is historical evidence, not current-season projections, exact league-scored
  points, calibrated outcome probabilities or an automatic draft ranking. Latest
  corrected historical files are not prediction-time snapshots for backtesting.

## Initial collection checkpoint

The initial collection downloaded six assets using ten logical requests (four
release-metadata reads plus six file downloads). The depth-chart archive contained
505,422 rows, with latest observed timestamp `2026-09-08T11:56:57Z`. Analysis covered
32 teams and 272 regular-season games in each of 2024 and 2025, producing 960 player
records and 607 current depth roles. None of the team depth snapshots exceeded the
36-hour threshold at the initial analysis time.

The report explicitly quarantines 36 historical records missing IDs, six unmatched
historical snap identities and one unmatched current depth row. Inspect those
issues before relying on affected candidates. No mock draft was started, and
FantasyPros and Sleeper incurred no calls for this collection.

The verification collection reused all six assets, making only two current-feed
metadata requests and no file downloads. The checksummed offline rebuild succeeded.
All 67 project tests passed, including revision invalidation, metadata 304 reuse,
rate-limit persistence, malformed data, partial collections, missing-value handling,
postseason exclusion, latest-team snapshot selection and ambiguous identity handling.

The subsequent documentation/policy audit passed **79 offline tests**. It added
coverage for request budgets, retry reserve, successful quota exhaustion, secondary
403 limits, metadata expiry, no-store handling, polling intervals, explicit
historical revalidation and preserving the legacy ledger. The local-only usage
check preserved all 12 earlier attempts. It sent no provider requests. Those
legacy attempts are conservatively classified as REST until the hour expires.

## Source documentation

- [nflverse update/availability schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html)
- [Player statistics and scope](https://nflreadr.nflverse.com/reference/load_player_stats.html)
- [Depth charts](https://nflreadr.nflverse.com/reference/load_depth_charts.html)
- [Snap counts from Pro Football Reference](https://nflreadr.nflverse.com/reference/load_snap_counts.html)
- [Player identifiers](https://nflreadr.nflverse.com/reference/load_players.html)
- [Published nflverse data](https://github.com/nflverse/nflverse-data)

Credit nflverse and underlying providers when sharing derived material. Public
availability does not imply unrestricted redistribution. Generated data is kept
local/private. The documented injury-feed outage and delayed participation feed
are reasons those datasets are not used here.  FantasyPros remains the current
injury/news source in our draft plan.
