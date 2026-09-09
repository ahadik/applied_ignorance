# FantasyPros data operating guidance

**Current draft freeze:** all 11 required feeds were prefetched at 6:35 p.m.
Eastern September 8. No further FP requests until the actual draft completes.
See [DRAFT_SESSION.md](DRAFT_SESSION.md); its active guard and fixed-snapshot
policy supersede routine refresh instructions for this session.

Reviewed September 8, 2026. Read this before implementing or changing any FantasyPros collector, valuation model, or MCP tool. Milestones 1 and 2 are complete for access and integrated draft evidence. `draft_inputs.py` collects all six projection positions and other baseline feeds; `draft_board.py` validates identities, scoring coverage and calculates supported scoring subtotals/starter value. See `MILESTONE_2.md` for source limitations and review commands; exact full-league totals and an optimized live draft strategy are not claimed.

## Stage 1 checkpoint — complete; account approval confirmed

On September 8, 2026, the user supplied the approval reminder shown by their
FantasyPros account: the API request is approved, the key receives full responses,
and its allowance is **1 request/second and 500 requests/day**. Access is personal
and non-commercial; commercial use, data resale and distribution of API access to
third parties are excluded. Caching is requested. This account-specific evidence
resolves the earlier production/full-response access and daily-limit questions;
it supersedes our provisional use of the older generic 100/day figure.

Evidence source: account notice transcribed by the user in this project, not an
entitlement inferred from HTTP 200 or an independently inspected account page.
No key is stored in this document. The notice does not specify a reset timezone,
rolling-versus-calendar window or current remaining balance. Those remain unknown
and do not block completion of the access milestone. Local enforcement is 400
routine attempts / 500 hard attempts in any rolling 24 hours, plus at least 1.05
seconds between requests. Existing usage records and cooldowns are preserved.
If the account, plan or key entitlement changes, recheck this policy.

Historical diagnostic files retain their original observations and may say
entitlement was unconfirmed at that time. This checkpoint supersedes that status;
do not rerun network probes just to rewrite an old report. Future diagnostics
point to this account evidence while still checking technical access separately.

Run the reusable access check from the project directory:

```sh
python3 fantasypros_diagnostic.py --season 2026
```

After the user saved the updated `.env`, all six access probes passed on September 8, 2026 at approximately 19:29 UTC (3:29 p.m. Eastern). The first credential-loading failure consumed zero calls. The successful run consumed six FantasyPros calls; a second run returned all six responses from cache and consumed zero additional FantasyPros calls. Each run also read Sleeper's public NFL state to establish injury week 1 of the 2026 regular season. That shared reader now lives at `sleeper.get_sleeper`; the diagnostic no longer depends on draft code. See `DATA_ACCESS.md` for the provider/domain separation.

| Access probe | Observed result |
|---|---|
| Player directory | 8,545 records; season 2026 |
| Draft PPR consensus | 551 records; 131 experts; season 2026, week 0; source update September 8 |
| PPR ADP | 712 records; 5 sources reported in `total_experts`; season 2026, week 0; source update September 8 |
| RB preseason projections | 132 records; season 2026, week 0; response labels scoring STD; no source update timestamp in diagnostic metadata |
| Recent news | Three requested records; includes September 8 publication dates |
| Injuries | 224 records requested for 2026 week 1; includes September 8 update dates |

These probes established access to current-season, recently dated data. Account approval is now separately confirmed above; complete feed freshness remains a domain-validation task. No recognized numeric quota headers were returned, so remaining provider balance is unknown. The successful diagnostic recorded six attempts under the then-current 80/100 local policy; those historical counts are not a current usage report. Do not claim all data validation is complete or start Stage 2 or a mock without the next user instruction.

Milestone 2 subsequently inspected all six projection positions, their raw stat fields, PPR totals, identities and injury scope. The observed STD label did not prevent using the separately supplied PPR fields; scoring gaps are recorded rather than hidden. See `MILESTONE_2.md` for the measured coverage and source limitations. The access probes themselves remain insufficient to establish a usable draft board.

The command probes the player directory, draft PPR consensus, PPR ADP, RB season projections, three recent news records, and injuries for the current regular-season week established through Sleeper's central reader. It skips injuries if that week cannot be verified. At most six FantasyPros requests are sent on an uncached run, with no diagnostic retries. Auth, connection, budget and cooldown failures stop further probes. Cache hits cost no provider call. Other projection positions and complete semantic/coverage validation belong to Stage 2.

Private reports are saved to `data/fantasypros/diagnostic.json` and `data/fantasypros/diagnostic.md`; rerunning replaces the diagnostic reports, not the validated provider cache. Reports contain scope/count/date metadata and any allowlisted numeric quota headers, not player feeds or credentials. Header observations retain the original fetch time on cache hits and are not a promise of current account balance. Successful basic checks alone never establish production entitlement or draft readiness; account evidence is recorded separately above. Review actual source dates during Stage 2. Do not start a mock as part of this command.

Validation: 29 project tests pass, using simulated transport and consuming no real API calls. Diagnostic tests cover early stopping, unresolved season/week, invalid data, and avoiding unsupported entitlement claims. Client tests also verify only allowlisted numeric quota headers persist across cache hits.

## Implemented shared entry point

All project FantasyPros reads must use `get_fantasypros`; do not create standalone requests in individual collectors or agents. Codex must invoke saved reusable commands that use this function, not run inline API snippets. The example below illustrates code to put inside a reusable collector module; it is not an instruction to execute a one-off request. The full collection CLI is now `draft_inputs.py collect --season 2026`; the diagnostic remains an access-only tool.

```python
from fantasypros import get_fantasypros, FantasyPros

result = get_fantasypros(
    'nfl/2026/projections',
    {'position': 'RB', 'week': 0},
    # validator=validate_rb_projections,  # add domain checks before valuation
)
data = result['data']
print(result['cache_hit'], result['fetched_at'])  # no credential logging
print(FantasyPros().usage())  # reads local ledger, makes no API call
```

- Persistent SQLite cache and a process lock live in ignored `data/fantasypros/`. Equivalent parameter order and string/bool forms share cache entries. Different scopes/parameters and credentials remain separate. All callers must use this same directory; separate computers or custom directories do not share quota.
- Defaults: players/experts 24 hours; projections/rankings/comparisons 6 hours; news/injuries 15 minutes. These are cache policies, not claims about provider freshness. Callers can shorten `max_age` for a justified deadline refresh. `max_age=0` intentionally requests new data; never use it in a routine loop.
- Local budget: new requests stop at 400 attempts per rolling 24 hours, with a 500-attempt absolute cap including retries. Only retries already underway can use the reserve; at most two retries are permitted per request. Each attempt is persisted before network I/O. The 500/day provider allowance comes from the user's account approval; local remaining counts are not provider balances, and activity outside this client is not counted.
- Calls are serialized and spaced at least 1.05 seconds apart. A shared lock coalesces simultaneous fresh-cache misses. A 429 saves a shared Retry-After cooldown and returns promptly; it does not sleep through long retry intervals or issue an immediate retry.
- 401/403 do not retry and pause that credential for 24 hours. A corrected/new credential gets its own cache/cooldown scope. Diagnose the underlying issue; do not delete quota records to bypass limits.
- Only supported relative NFL read paths are enabled. Historical player-points are intentionally excluded pending entitlement verification. No redirects are followed. Secret loading is non-executing and errors exclude headers/body.
- Invalid responses do not overwrite the last good cache. Expired cache is not silently returned as fresh. Cache hits still run caller-provided validation. The basic validator checks expected collections, explicit sample flags, sport/season and returned week/scoring when present; it does NOT establish production entitlement or complete projection semantics.
- Results expose retrieval time and cache-hit status. Provider update times remain inside returned data and must be handled separately by collectors. Domain adapters still must enforce data age, coverage, projection period, identity matching and scoring completeness.

Validation: 12 client tests, four diagnostic tests and the existing 13 tests pass. Tests cover caching/restarts, concurrent duplicate reads, spacing, retries, auth failures, quotas, cooldowns, invalid data, validator execution, restricted URLs and image-field removal. Tests use simulated transport and consume no real API calls. Cloud portability requires replacing the local macOS/Linux file lock with a shared server-side collector/lock; this implementation is local, not distributed.

## Sources and scope

Reviewed the v2 public reference's endpoint definitions, parameters, response schemas, shared models and examples, including non-NFL operations to establish the full documented scope:

- [Official rendered reference](https://api.fantasypros.com/public/v2/docs/)
- [Underlying OpenAPI 3.1.1 specification, API version 2.0](https://api.fantasypros.com/public/v2/docs/fantasypros_v2_public.yml)
- [Linked API terms](https://api.fantasypros.com/public/v2/terms-of-use), dated October 27, 2020
- [Current API product/access page](https://www.fantasypros.com/api-data/)

The product page advertises personal production access through HOF and a sample-data free tier. The specification still describes a limited free public API and labels its server “test.” Neither label proves the user's entitlement or that returned projections are production data. Validate actual account access, season, scope, freshness and payload before use. Do not buy another plan or assume a key guarantees production access.

## Authentication and access

Base URL: `https://api.fantasypros.com/public/v2/json`. All 12 documented operations are GET reads and use header `x-api-key`. Load `FANTASYPROS_API_KEY` from environment or the local `.env` with a non-executing parser; never source arbitrary shell contents. Never place the secret in query strings, prompts, logs, browser code, checkpoints or commits. Restrict credentials to the official API host, reject cross-host redirects, sanitize errors, and use bounded request timeouts. In cloud deployment use a secret manager and server-side requests.

The linked older terms specify personal/noncommercial use, one request/second and 100/day, caching, attribution for published work, and restrictions on historical player statistics and image URLs. The user's account approval explicitly supplies the applicable 500/day allowance and full responses; use that account-specific limit as recorded above. Full responses do not independently establish historical-data or redistribution rights. Historical points remain disabled and image fields are discarded; current work uses nflverse for history. Do not expose a raw-data redistribution service.

Implement a durable shared request ledger, at most one concurrent FantasyPros request, at least one second between requests, and a daily budget with retry reserve. Count failed attempts too. Honor Retry-After on 429; back off with bounded retries on timeouts/5xx; stop on 401/403; fix parameters rather than retry 400. Cache by endpoint plus normalized parameters. Never run this feed at the Sleeper pick tracker's five-second frequency.

## Complete endpoint map

Paths below are relative to the base; use sport `nfl` and season `2026` now, with explicit season/week in saved provenance.

| Operation | Inputs that matter | Our use |
|---|---|---|
| `/{sport}/players` | `player`, date `update=YYYY-MM-DD`, `ecr=included/excluded`, `external_ids` colon-separated, `show=pos_rank` | Identity crosswalk; PPR ECR/ADP metadata. Full initial directory; later date-filtered updates. Do not filter out unranked players from the master identity table. |
| `/{sport}/news` | `fpid`, `limit` up to 100 (default 25), `category=injury/recap/transaction/rumor/breaking`, `order_by=updated/created` | Role changes and injury evidence; preserve links, timestamps and item IDs; distinguish rumors from confirmed news. No documented cursor, so a 100-item window is not guaranteed complete history. |
| `/{sport}/injuries` | `year`, `week`, `include_probabilities=true`, colon-separated `team_id` or `player_ids` | Availability/practice evidence and provider probability estimates. Use explicit current NFL week; absence is not proof of health. |
| `/{sport}/compare-players` | Required `players` (2–4 IDs), `position`; optional `year`, `week`, `experts`, lowercase `ranking_type=draft/weekly/ros`, `details=players/experts/all` | Occasional tie-break analysis; NFL response nests rankings by scoring then player then expert. Not a simulation or trade-value API. |
| `/{sport}/{season}/rankings` | `week`, `player`, `filters`, `min`, `range=true`, `rankstats=true`; special `type=DRAFTERS` | Broad nested ECR/ADP and ranking dispersion. Parse scoring/week keys explicitly. Do not pass consensus-style type=DRAFT here. |
| `/{sport}/{season}/consensus-rankings` | Required `position`; `type`, `scoring=PPR`, `week`, `filters`, `experts=show/available`, `include_idp` | Primary draft/ROS consensus and ADP requests; record expert counts and publication timestamps. Use type=DRAFT or ADP tonight; test weekly semantics rather than inventing type=WEEKLY (not in NFL enum). |
| `/{sport}/{season}/rankings/experts` | `position`, `type`, `scoring`, `include_overall=true` | Expert freshness, source diversity and available accuracy fields. Confirm whether values are ranks or scores before weighting. |
| `/nfl/{season}/projections` | Required `position`; optional colon-separated `positions`, `players`, `filters`; `week=0` for preseason; `ros=true` for ROS | Numeric projection baseline. Request each of QB/RB/WR/TE/K/DST separately initially. Weekly uses explicit week; never conflate totals and weekly numbers. |
| `/nfl/{season}/player-points` | `start`, `end` inclusive week range, `position`, `scoring=STD/PPR/HALF`, `min` | Potential evaluation data only after historical-data entitlement is established. Default fantasy totals are not necessarily our league's scoring. |
| `/mlb/{season}/projections` | preseason/ros/daily/weekly; position/date/week/custom range; `fpIds` comma-separated; eligibility/league key | Reviewed; not used for NFL. |
| `/nba/{season}/projections` | type/position/date; `fpIds`, team IDs; totals/averages and precision | Reviewed; not used for NFL. |
| `/mlb/lineups` | start date, PRE/REG/PST, projected | Reviewed; not an NFL lineup or NFL weather endpoint. |

Documented NFL position aliases include ALL, FLX and OP; map provider DST to Sleeper DEF and FLX to our FLEX concept. Sleeper remains authoritative for league eligibility and roster ownership. Dynasty, rookie, best-ball and other ranking variants exist but do not belong in our redraft baseline.

## Tonight: collection and computation

1. Access probes and account approval are complete as recorded above. Recheck on access failures or account changes; save only sanitized diagnostic metadata. Validate current source dates and scope during collection.
2. Fetch player directory, draft PPR consensus, PPR ADP, six preseason positional projection sets, current injuries and recent news. A baseline should need about 11 calls, before optional expert/rank-stat queries. Some requests may be unavailable; report gaps rather than fabricate replacements.
3. Build a persisted crosswalk from FantasyPros player IDs to Sleeper IDs. Prefer verified shared IDs: FantasyPros `sportsdata_player_id` is described as Sportradar, and projections include `mflid`. Compare with actual Sleeper fields. `external_ids` does NOT list Sleeper. Require one-to-one matches and position checks; quarantine collisions and fuzzy-name matches for review. Treat team changes as warnings, not automatic identity changes. Map team defenses explicitly.
4. Validate season=2026, preseason scope, position, coverage/counts, unique IDs and numeric values. Store retrieval time separately from provider update time. If source time is absent, mark it unknown, not equal to retrieval time. Never use old-season examples as observations.
5. Compute league points from stat lines with a reviewed mapping, then value over replacement with flexible-slot allocation for 14 teams. Retain original projections separately. Combine marginal roster value with ADP-based availability estimates; make assumptions explicit and test sensitivity. ADP is not a guaranteed next-pick probability.
6. Produce controller candidates with Sleeper IDs, deterministic priorities, scoring basis, provenance and a brief rationale. Leave injury/bye caveats visible. Agent reasoning may propose changes but must preserve numeric evidence and record overrides.
7. Refresh the baseline around 8 p.m.; recheck news/injuries close to 9 p.m. During the draft reuse cached projections and recompute after Sleeper picks. Reserve calls for material news; do not refetch full projections every turn.

Budget example: two 11-call baselines (22), six extra injury/news pairs (12), six diagnostic/expert calls (6), totaling 40 calls before cache savings or retries. That is comfortably inside the 400-attempt routine budget; a larger allowance is not a reason to poll needlessly. This is a proposed schedule, not active automation or a promise of a provider update cadence.

## Scoring and schema hazards

Direct candidate mappings to review against actual league coefficients:

| FantasyPros | Sleeper scoring stat |
|---|---|
| pass_yds / pass_tds / pass_ints | pass_yd / pass_td / pass_int |
| rush_yds / rush_tds | rush_yd / rush_td |
| rec_rec / rec_yds / rec_tds | rec / rec_yd / rec_td |

Do not map `fumbles` to fumbles-lost without verifying its definition. `ret_tds`, `2pt_tds`, defensive TDs and points-allowed bands also require semantic checks. Kicker projections provide aggregate attempts/makes/extra points but not all distance bands; exact league scoring may therefore be impossible from these fields alone. Never claim exact scoring when any nonzero league category is unsupported. Provider `points_ppr` is a comparison baseline, not an automatic substitute.

Specific documentation inconsistencies to test with real payloads:

- Projection `stats` is declared an array; inspect real shape and validate an explicit adapter rather than blindly generating a client.
- K projection schema exists but is omitted from the projection response union.
- DST required fields contain the combined text `points_half def_sack`; do not implement that as a real field.
- `filters` description says comma-separated, but regex/examples show colons. Start with documented colon examples and verify actual returned experts.
- IDs/counts/weeks and numeric statistics can be strings; convert deliberately; null/empty/missing is not zero.
- Some expert schema fields use `default` versus `defaults`; record actual shape.
- Consensus NFL schema does not guarantee all dispersion fields advertised elsewhere; use the broad rankings rankstats response when needed.
- Misspelled documented keys such as `scrimage_yards_100` must be handled explicitly, not silently renamed in raw provenance.

Expert rank standard deviation measures disagreement about rank, NOT fantasy-point variance. Consensus sources are correlated, not independent draws. Do not multiply projections by probability_of_playing unless it is established that the projections are conditional on playing; that can double-count injury risk. Preserve probability nulls and practice-report submission flags.

## Season-long use

- After games: reconcile actual roster/results through Sleeper; ingest appropriately licensed performance data; save prediction-time snapshots to prevent hindsight leakage.
- Before waiver deadlines: weekly projections for immediate help, ROS for sustained value, role/injury news and available-player joins. Compute marginal lineup improvement and roster opportunity cost. FAAB bid recommendations require our own budget/opponent model, not an invented API field.
- Before each player's lineup lock: refresh relevant injury/practice data and weekly projections; optimize legal starting slots deterministically, preserving late-swap flexibility and locked players. Use official inactive reports as confirmation when material.
- Trades: compare projected lineup contribution over remaining weeks, replacement options, uncertainty and schedule coverage. Never treat a consensus rank difference as a point difference.
- Calibration: evaluate saved predictions out of sample, position by position. Choose expert weights conservatively with shrinkage; avoid fitting one week's results. Use historical statistics only from a source licensed for that use.

Schedule refreshes around actual league waiver/lineup deadlines and provider quota, not an assumed universal weekday. Implement alerts for stale or failed feeds, changed eligibility, roster-relevant injuries and deadline risk. No season automations are created by this document.

## Storage, cloud and MCP

Planned pipeline: provider reads → validated permitted snapshots → identity crosswalk → league scoring/value calculations → controller priorities → supervised Sleeper actions. Keep computation outside chat context.

Persist request parameters, season/week/scope/scoring, retrieved_at, provider_updated_at if known, expert IDs, validation status and software version. Retain only permitted fields; keep private caches out of Git and public artifacts. Never overwrite the last validated dataset with empty/error/sample responses.

Future authenticated MCP tools should return computed shortlists, lineup comparisons, data freshness and supporting source links. The backend owns secrets, caching and quotas; multiple agents must share one collector budget. Keep access personal, and verify provider terms before sending licensed raw feeds to additional services. LLMs interpret news and challenge strategies; scripts perform joins, scoring, optimization and reproducible simulations.

This API does not document Sleeper writes, NFL play-by-play, snap counts, target routes, NFL schedules/weather, sportsbook odds, or a full probability distribution. Obtain separately supported sources if those become necessary; do not infer endpoints from marketing language.

## Integration acceptance checks

- Account approval is confirmed above; still validate real payload freshness and scope before drafting with this source.
- Validate all six positional projection schemas and required scoring coverage.
- Review every unresolved player match; no name-only silent joins.
- Prove PPR conversion on hand-calculated examples and test missing fields.
- Test 401/403/429/5xx, quota exhaustion, stale feeds and safe last-good-data retention without exposing headers.
- Verify projections/ADP refresh changes controller candidates and drafted IDs remain excluded.
- Complete the integrated third mock only when the user requests it.
