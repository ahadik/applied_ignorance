# Stage 1 — FantasyPros access report

Generated: 2026-09-08T19:29:16.555740+00:00

Requested season: 2026
All access probes passed: True
Production entitlement: unconfirmed: successful responses do not prove account entitlement

| Probe | Result | Records | Cached |
|---|---|---:|---|
| player_directory | passed_basic_checks | 8545 | True |
| draft_ppr_consensus | passed_basic_checks | 551 | True |
| ppr_adp | passed_basic_checks | 712 | True |
| rb_season_projections | passed_basic_checks | 132 | True |
| recent_news | passed_basic_checks | 3 | True |
| current_injuries | passed_basic_checks | 224 | True |

## player_directory

Request: `nfl/players`; parameters: `{}`
Retrieved: 2026-09-08T19:28:53.324542+00:00
Source metadata: `{"count": 8545, "season": "2026", "sport": "NFL", "week": "0"}`
Source date examples: `[]`
Quota headers at fetch: `{}`

## draft_ppr_consensus

Request: `nfl/2026/consensus-rankings`; parameters: `{"position": "ALL", "scoring": "PPR", "type": "DRAFT", "week": 0}`
Retrieved: 2026-09-08T19:28:54.188063+00:00
Source metadata: `{"count": 551, "last_updated": "9/08", "last_updated_ts": 1788895038, "position_id": "ALL", "ranking_type_name": "draft", "scoring": "PPR", "sport": "NFL", "total_experts": 131, "week": "0", "year": "2026"}`
Source date examples: `[]`
Quota headers at fetch: `{}`

## ppr_adp

Request: `nfl/2026/consensus-rankings`; parameters: `{"position": "ALL", "scoring": "PPR", "type": "ADP", "week": 0}`
Retrieved: 2026-09-08T19:28:54.876617+00:00
Source metadata: `{"count": 712, "last_updated": "9/08", "last_updated_ts": 1788851365, "position_id": "ALL", "ranking_type_name": "adp", "scoring": "PPR", "sport": "NFL", "total_experts": 5, "week": "0", "year": "2026"}`
Source date examples: `[]`
Quota headers at fetch: `{}`

## rb_season_projections

Request: `nfl/2026/projections`; parameters: `{"position": "RB", "week": 0}`
Retrieved: 2026-09-08T19:28:55.708474+00:00
Source metadata: `{"count": "132", "positions": "RB", "scoring": "STD", "season": "2026", "week": "0"}`
Source date examples: `[]`
Quota headers at fetch: `{}`

## recent_news

Request: `nfl/news`; parameters: `{"limit": 3, "order_by": "updated"}`
Retrieved: 2026-09-08T19:28:58.147451+00:00
Source metadata: `{"count": 3, "sport": "NFL"}`
Source date examples: `["2026-09-07 21:11:25", "2026-09-08 19:05:34", "2026-09-08 19:09:51"]`
Quota headers at fetch: `{}`

## current_injuries

Request: `nfl/injuries`; parameters: `{"include_probabilities": true, "week": 1, "year": 2026}`
Retrieved: 2026-09-08T19:28:58.478758+00:00
Source metadata: `{"count": 224, "sport": "NFL"}`
Source date examples: `["2026-09-08 00:00:00", "2026-09-08 12:00:00", "2026-09-08 19:20:01"]`
Quota headers at fetch: `{}`

## Budget and checkpoint

Local attempts added during run: 0 (includes concurrent client activity, if any).
Local ledger after run: `{"attempts_last_24h": 6, "routine_remaining": 74, "hard_remaining": 94, "scope": "this shared local cache directory"}`

No documented account quota endpoint; numeric headers, if present, are observations at fetch time.

- Access diagnostics only; no scoring, identity mapping, or draft recommendations.
- RB is the projection access probe; QB/WR/TE/K/DST coverage remains for Stage 2.
- Broad rankings, expert metadata, and comparison endpoints are not probed; historical points remain disabled.
- An empty news/injury response does not prove absence of news/injuries.

Review access failures, data scope/source dates and production entitlement before Stage 2.

No draft-ready data or production entitlement is asserted by this report.
